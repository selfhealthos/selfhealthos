"""Fitbit: OAuth, the API client, and the day-by-day sync.

**The callback works on a LAN because Fitbit never calls it.** The
authorization code comes back as a 302 sent to the *browser*, so the redirect
URL only has to resolve from the machine doing the authorising - which is on
the same network as the server. The only outbound connection this service makes
is to `api.fitbit.com`, which is ordinary egress through NAT. No tunnel, no
port forward, no public address. Fitbit does require the redirect URL to be
HTTPS, which is why the portal's own certificate matters here.

**Refresh tokens are single-use and rotate**, and never expire until they are
used. Two consequences shape `refresh()` below and neither is theoretical:

  * Two syncs refreshing at once means one of them spends the token and the
    other is left holding a dead one - so the row is locked for the duration.
  * Losing the *new* refresh token after the old one has been spent breaks the
    connection permanently, with no way back but re-authorising - so it is
    committed before the access token is used for anything.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

import httpx
from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.core.exceptions import DomainError

from .. import metrics as metric_defs
from .. import timeutils
from ..models import Connection, DailyMetric, Sample, SleepSegment, SleepSession

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"
REVOKE_URL = "https://api.fitbit.com/oauth2/revoke"
API_ROOT = "https://api.fitbit.com"

#: Everything the portal's metric vocabulary can hold, and nothing else.
#: `nutrition` and `weight` are deliberately absent: those are logged on the
#: phone, and asking for a scope the app never reads is a permission the person
#: granted for no reason.
SCOPES = (
    "activity",
    "heartrate",
    "sleep",
    "oxygen_saturation",
    "respiratory_rate",
    "temperature",
    "cardio_fitness",
    "profile",
)

#: Refresh this far before the token actually expires, so a long sync does not
#: cross the boundary mid-flight.
REFRESH_MARGIN = timedelta(minutes=5)

#: Fitbit allows 150 requests per hour per user. One day costs about a dozen,
#: so this is roughly a twelve-day backfill per hour - which is why a long
#: backfill reports how far it got instead of pretending to finish.
REQUESTS_PER_DAY_ESTIMATE = 13


class FitbitError(DomainError):
    title = "Fitbit request failed"


class NeedsReconnect(FitbitError):
    """The grant is gone. Retrying cannot fix it; the person must re-authorise."""

    title = "Reconnect Fitbit"


class RateLimited(FitbitError):
    title = "Fitbit rate limit reached"

    def __init__(self, detail: str, retry_after: int | None = None):
        super().__init__(detail)
        self.retry_after = retry_after


# --------------------------------------------------------------------------
# OAuth
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    verifier: str


def start_authorization(connection: Connection, redirect_uri: str) -> AuthorizationRequest:
    """Build the URL to send the browser to, with PKCE and a state token.

    PKCE is not strictly required for a confidential client that keeps its
    secret server-side, but Fitbit recommends it and it costs two hashes: it
    closes the window where an authorization code intercepted in transit is
    redeemable by whoever caught it.
    """
    if not connection.is_configured:
        raise FitbitError("Save a Fitbit client ID and secret before connecting.")

    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    state = secrets.token_urlsafe(32)

    query = urlencode(
        {
            "client_id": connection.client_id,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": " ".join(SCOPES),
            "redirect_uri": redirect_uri,
            "state": state,
            # Long-lived by request; the refresh token is what actually keeps
            # the connection alive, but a short expiry means more refreshes and
            # every refresh is a chance to lose the rotating token.
            "expires_in": "604800",
        }
    )
    return AuthorizationRequest(url=f"{AUTHORIZE_URL}?{query}", state=state, verifier=verifier)


def _basic_auth(connection: Connection) -> str:
    raw = f"{connection.client_id}:{connection.client_secret}".encode()
    return base64.b64encode(raw).decode()


def exchange_code(connection: Connection, *, code: str, verifier: str, redirect_uri: str) -> None:
    """Trade the authorization code for tokens and store them."""
    payload = {
        "client_id": connection.client_id,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        # Sent again and must match the authorize request exactly - Fitbit
        # checks it to stop a code being redeemed against a different callback.
        "redirect_uri": redirect_uri,
    }
    data = _token_request(connection, payload)

    connection.access_token = data.get("access_token", "")
    connection.refresh_token = data.get("refresh_token", "")
    connection.token_expires_at = _expiry(data.get("expires_in"))
    connection.scopes = sorted((data.get("scope") or "").split())
    connection.provider_user_id = str(data.get("user_id") or "")
    connection.status = Connection.Status.CONNECTED
    connection.connected_at = dj_timezone.now()
    connection.last_sync_error = ""
    connection.save(
        update_fields=[
            "access_token_enc",
            "refresh_token_enc",
            "token_expires_at",
            "scopes",
            "provider_user_id",
            "status",
            "connected_at",
            "last_sync_error",
            "updated_at",
        ]
    )


def refresh(connection: Connection, *, force: bool = False) -> Connection:
    """Spend the refresh token and store the replacement, atomically.

    The row is locked for the whole exchange. Without it, two workers refreshing
    the same connection both present the same single-use token: one succeeds,
    the other gets an invalid_grant, and the connection is dead until somebody
    notices and reconnects.

    `force` is for the case where Fitbit has rejected a token that has not
    reached its advertised expiry - revoked from the Fitbit account, say. Then
    the stored expiry says "still valid" and the skip below would hand the same
    dead token back to a retry that is guaranteed to fail again.
    """
    try:
        return _refresh_locked(connection, force=force)
    except NeedsReconnect:
        # Marked *outside* the transaction below, which has just rolled back.
        # Writing the status inside it means the rollback undoes it, and the
        # connection goes on claiming to be healthy while every sync fails -
        # the exact failure this status exists to make visible.
        _mark_expired(connection)
        raise


def _refresh_locked(connection: Connection, *, force: bool) -> Connection:
    with transaction.atomic():
        locked = Connection.objects.select_for_update().get(pk=connection.pk)

        # Another worker may have refreshed while this one waited on the lock,
        # in which case there is nothing left to do.
        if (
            not force
            and locked.token_expires_at
            and locked.token_expires_at - REFRESH_MARGIN > _now()
        ):
            return locked

        if not locked.refresh_token_enc:
            raise NeedsReconnect("This Fitbit connection has no refresh token.")

        data = _token_request(
            locked,
            {
                "client_id": locked.client_id,
                "grant_type": "refresh_token",
                "refresh_token": locked.refresh_token,
            },
        )

        locked.access_token = data.get("access_token", "")
        # The new refresh token is committed inside the same transaction that
        # spent the old one. Anything less and a crash here loses the
        # connection with no way back but re-authorising.
        locked.refresh_token = data.get("refresh_token", "") or locked.refresh_token
        locked.token_expires_at = _expiry(data.get("expires_in"))
        locked.status = Connection.Status.CONNECTED
        locked.save(
            update_fields=[
                "access_token_enc",
                "refresh_token_enc",
                "token_expires_at",
                "status",
                "updated_at",
            ]
        )
        return locked


def _token_request(connection: Connection, payload: dict) -> dict:
    try:
        response = httpx.post(
            TOKEN_URL,
            data=payload,
            headers={
                "Authorization": f"Basic {_basic_auth(connection)}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise FitbitError(f"Could not reach Fitbit: {exc}") from exc

    if response.status_code == 401 or _is_invalid_grant(response):
        # No side effect here: this runs inside `refresh`'s transaction, so a
        # status written now would be rolled back by the raise. The caller
        # marks the connection instead, after the rollback.
        raise NeedsReconnect(
            "Fitbit rejected the credentials. Check the client ID and secret, then connect again."
        )
    if response.status_code >= 400:
        raise FitbitError(f"Fitbit returned {response.status_code}: {response.text[:300]}")
    return response.json()


def _is_invalid_grant(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    errors = body.get("errors") or []
    return any(item.get("errorType") in {"invalid_grant", "invalid_client"} for item in errors)


def _mark_expired(connection: Connection) -> None:
    Connection.objects.filter(pk=connection.pk).update(
        status=Connection.Status.EXPIRED, updated_at=_now()
    )


def revoke(connection: Connection) -> None:
    """Tell Fitbit to forget the grant. Best effort.

    A local disconnect that leaves the grant live at Fitbit is a token still
    out there, so this is worth attempting - but a network failure here must
    not stop the person disconnecting.
    """
    if not connection.refresh_token_enc:
        return
    try:
        httpx.post(
            REVOKE_URL,
            data={"token": connection.refresh_token},
            headers={"Authorization": f"Basic {_basic_auth(connection)}"},
            timeout=15.0,
        )
    except (httpx.HTTPError, Exception):
        logger.warning("could not revoke Fitbit grant for connection %s", connection.pk)


def _expiry(expires_in) -> datetime | None:
    try:
        return _now() + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return dj_timezone.now()


# --------------------------------------------------------------------------
# The API client
# --------------------------------------------------------------------------


class Client:
    """A thin authenticated GET, with the refresh handled underneath.

    Deliberately not a general HTTP wrapper: every call this makes is a GET
    against a documented path returning JSON, and the only interesting
    behaviours are refreshing on expiry and recognising a rate limit.
    """

    def __init__(self, connection: Connection):
        self.connection = connection
        self._http = httpx.Client(timeout=60.0, base_url=API_ROOT)
        self.requests = 0

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info) -> None:
        self._http.close()

    def get(self, path: str) -> dict | None:
        """Fetch one endpoint. `None` means "nothing recorded", not "failed".

        Fitbit answers 404 for a day a feature was not worn or not supported,
        which is a normal gap in a history rather than an error - treating it
        as one would abort a backfill on the first day someone left the watch
        on the charger.
        """
        self._ensure_token()
        try:
            response = self._http.get(
                path, headers={"Authorization": f"Bearer {self.connection.access_token}"}
            )
        except httpx.HTTPError as exc:
            raise FitbitError(f"Could not reach Fitbit: {exc}") from exc

        self.requests += 1

        if response.status_code == 401:
            # Expired earlier than advertised. Forced, because the stored
            # expiry still says the token is good and an unforced refresh would
            # skip and hand the same dead token to the retry.
            self.connection = refresh(self.connection, force=True)
            response = self._http.get(
                path, headers={"Authorization": f"Bearer {self.connection.access_token}"}
            )
            self.requests += 1
            if response.status_code == 401:
                _mark_expired(self.connection)
                raise NeedsReconnect("Fitbit rejected the access token.")

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimited(
                "Fitbit's hourly request limit was reached. Data pulled so far "
                "has been saved; try again later.",
                retry_after=int(retry_after) if (retry_after or "").isdigit() else None,
            )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise FitbitError(f"Fitbit returned {response.status_code}: {response.text[:300]}")

        try:
            return response.json()
        except ValueError:
            return None

    def _ensure_token(self) -> None:
        expires = self.connection.token_expires_at
        if not self.connection.access_token_enc or (expires and expires - REFRESH_MARGIN <= _now()):
            self.connection = refresh(self.connection)


# --------------------------------------------------------------------------
# The sync
# --------------------------------------------------------------------------


@dataclass
class SyncReport:
    days_requested: int = 0
    days_synced: int = 0
    #: Days whose minute data was already stored, so no per-day request was
    #: spent on them. The number that makes a long sync affordable.
    days_skipped: int = 0
    samples_written: int = 0
    daily_metrics_written: int = 0
    sleep_sessions: int = 0
    requests: int = 0
    stopped_early: str = ""
    synced_through: date | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "days_requested": self.days_requested,
            "days_synced": self.days_synced,
            "days_skipped": self.days_skipped,
            "samples_written": self.samples_written,
            "daily_metrics_written": self.daily_metrics_written,
            "sleep_sessions": self.sleep_sessions,
            "requests": self.requests,
            "stopped_early": self.stopped_early,
            "synced_through": self.synced_through.isoformat() if self.synced_through else None,
            "warnings": self.warnings,
        }


#: Intraday streams, at the 1-minute resolution decision 1 settled on. Asking
#: for `1sec` would be 60x the rows for data nothing in this system reads, and
#: would need a downsampling pass on the way in.
INTRADAY: tuple[tuple[str, str, str], ...] = (
    # (metric key, resource path, response key)
    ("hr", "activities/heart", "activities-heart-intraday"),
    ("steps", "activities/steps", "activities-steps-intraday"),
    ("calories", "activities/calories", "activities-calories-intraday"),
    ("distance", "activities/distance", "activities-distance-intraday"),
    ("floors", "activities/floors", "activities-floors-intraday"),
    ("elevation", "activities/elevation", "activities-elevation-intraday"),
)


#: Days at the end of the window always re-fetched, however complete they look.
#: The watch backfills last night's stages, resting heart rate and HRV hours
#: after the fact, so a sync that trusted "this day already has data" would
#: keep the first partial version of every day forever.
REFRESH_DAYS = 2


def sync(connection: Connection, *, start: date, end: date) -> SyncReport:
    """Pull one date range into `Sample`, `DailyMetric` and `SleepSession`.

    Two passes, because the two kinds of data cost wildly different amounts.

    **Everything with a range endpoint is fetched for the whole window at
    once** - daily metrics, sleep logs, hypnograms, overnight SpO2. That is
    about sixteen requests whether the window is one day or thirty.

    **Only intraday streams are fetched per day**, since Fitbit has no range
    form for minute-level data, and *only for days that have none*. A day whose
    minutes are already stored is skipped: the request would return the same
    rows and cost the same seven calls against a limit of 150 an hour. Skipping
    them is what makes a 30-day sync possible at all - it was 420 requests
    before, which is three hours of hitting the limit and resuming.

    The last couple of days are re-fetched regardless. Fitbit backfills them
    for hours afterwards, and a sync that only ever filled gaps would keep the
    first, partial version of every day forever.
    """
    report = SyncReport(days_requested=(end - start).days + 1)
    tz = timeutils.tz_for(connection.user)

    with Client(connection) as client:
        try:
            _sleep_ranges(client, connection.user, start, end, report)
            _daily_ranges(client, connection.user, start, end, report)
        except RateLimited as exc:
            report.stopped_early = str(exc.detail)
            report.requests = client.requests
            return report
        except FitbitError as exc:
            # A range endpoint failing is worth reporting but not worth
            # abandoning the intraday pass over.
            logger.warning("fitbit range pass failed: %s", exc)
            report.warnings.append(str(exc.detail))

        for day in _days_needing_intraday(connection.user, start, end, tz):
            try:
                _intraday_day(client, connection.user, day, tz, report)
            except RateLimited as exc:
                report.stopped_early = str(exc.detail)
                break
            except NeedsReconnect:
                raise
            except FitbitError as exc:
                # One bad day should not abandon the rest of a backfill.
                logger.warning("fitbit sync failed for %s: %s", day, exc)
                report.warnings.append(f"{day}: {exc.detail}")
            else:
                report.days_synced += 1
                report.synced_through = day

        report.days_skipped = report.days_requested - report.days_synced
        # Everything in the window is now as current as Fitbit has it, even the
        # days whose minutes were already stored - so the resume point is the
        # end of the window rather than the last day that needed work.
        if not report.stopped_early:
            report.synced_through = end
        report.requests = client.requests

    return report


def _days_needing_intraday(user, start: date, end: date, tz) -> list[date]:
    """Days in the window with no minute samples, newest first.

    Newest first because the recent days are the ones someone is looking at
    when they press Sync, and a rate limit part-way through should leave them
    with this week rather than with three weeks ago.
    """
    from django.db.models.functions import TruncDate

    lower = timeutils.utc_from_local_parts(start, time(0, 0), tz)
    upper = timeutils.utc_from_local_parts(end + timedelta(days=1), time(0, 0), tz)
    covered = set(
        Sample.objects.filter(user=user, metric="hr", ts__gte=lower, ts__lt=upper)
        .annotate(day=TruncDate("ts", tzinfo=tz))
        .values_list("day", flat=True)
        .distinct()
    )

    # Relative to *today*, not to the window's end. Only recent days are still
    # being backfilled by Fitbit; a window from three months ago is settled,
    # and re-fetching its last two days would spend requests on nothing.
    always = date.today() - timedelta(days=REFRESH_DAYS - 1)
    wanted = [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if start + timedelta(days=offset) not in covered or start + timedelta(days=offset) >= always
    ]
    return sorted(wanted, reverse=True)


def _intraday_day(client: Client, user, day: date, tz, report: SyncReport) -> None:
    """The minute streams for one day. The only per-day cost left."""
    for metric_key, resource, response_key in INTRADAY:
        report.samples_written += _intraday(
            client, user, day, tz, metric_key, resource, response_key
        )
    report.samples_written += _hrv_intraday(client, user, day, tz)


#: Fitbit's own ceilings on the two range endpoints the backfill uses. Asking
#: for more is a 400, so the backfill walks in chunks of exactly these.
SLEEP_RANGE_DAYS = 100
SPO2_RANGE_DAYS = 30


def backfill_detail(connection: Connection, *, start: date, end: date) -> SyncReport:
    """Fill in the hypnogram and the overnight SpO2 minutes for a past range.

    Separate from `sync` because it is cheap in exactly the way `sync` is not.
    The day-by-day sync spends fourteen requests per day, so three months of it
    is 1,300 requests against a 150/hour limit - days of pressing the button.
    Both endpoints here take a date *range*, so the same three months is five
    requests: 100 nights of sleep logs in one, and SpO2 in thirty-day chunks.

    Written for the migration that added `SleepSegment`, where the data existed
    at Fitbit all along and only the storage was new. It stays useful for any
    later gap, which is why it is a command rather than a one-off script.
    """
    report = SyncReport(days_requested=(end - start).days + 1)

    with Client(connection) as client:
        try:
            _sleep_ranges(client, connection.user, start, end, report)
        except RateLimited as exc:
            report.stopped_early = str(exc.detail)

        report.requests = client.requests

    report.synced_through = end
    return report


def _sleep_ranges(client: Client, user, start: date, end: date, report: SyncReport) -> None:
    """Sleep logs with their hypnograms, and the overnight SpO2 minutes."""
    tz = timeutils.tz_for(user)

    for chunk_start, chunk_end in _chunks(start, end, SLEEP_RANGE_DAYS):
        body = client.get(
            f"/1.2/user/-/sleep/date/{chunk_start:%Y-%m-%d}/{chunk_end:%Y-%m-%d}.json"
        )
        for session in (body or {}).get("sleep") or []:
            if _sleep_session(user, session):
                report.sleep_sessions += 1

    for chunk_start, chunk_end in _chunks(start, end, SPO2_RANGE_DAYS):
        body = client.get(
            f"/1/user/-/spo2/date/{chunk_start:%Y-%m-%d}/{chunk_end:%Y-%m-%d}/all.json"
        )
        # A range answers with a list of nights, a single date with one object.
        # Iterating the object would walk its *keys*, which is a string where a
        # night is expected - so normalise before the loop rather than trusting
        # a shape that changes with the length of the window.
        records = body if isinstance(body, list) else [body] if body else []
        for record in records:
            report.samples_written += _spo2_minutes(user, record, tz)


#: Scalar endpoints that also answer for a date *range*, and the field of the
#: response that carries the day. All of them cap the range at 30 days.
#:
#: `(path, list key, {response field: metric})`. The single-date forms of these
#: are in `SCALARS`; the mapping is deliberately the same shape so the two
#: cannot disagree about which Fitbit field is which portal metric.
DAILY_RANGES: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("/1/user/-/hrv/date/{start}/{end}.json", "hrv", {"dailyRmssd": "hrv_rmssd"}),
    ("/1/user/-/br/date/{start}/{end}.json", "br", {"breathingRate": "breathing_rate"}),
    (
        "/1/user/-/spo2/date/{start}/{end}.json",
        "",
        {"avg": "spo2_avg", "min": "spo2_min", "max": "spo2_max"},
    ),
    (
        "/1/user/-/temp/skin/date/{start}/{end}.json",
        "tempSkin",
        {"nightlyRelative": "skin_temp_deviation"},
    ),
    ("/1/user/-/cardioscore/date/{start}/{end}.json", "cardioScore", {"vo2Max": "vo2max"}),
    # Active zone minutes have their own resource rather than riding along on
    # the activity summary the way they used to. Kept even though the heatmap
    # deliberately scores `fairly_active_minutes + very_active_minutes`
    # instead - the metric is in the vocabulary, the day view shows it, and a
    # sync that silently stopped collecting it would be a gap nobody notices.
    (
        "/1/user/-/activities/active-zone-minutes/date/{start}/{end}.json",
        "activities-active-zone-minutes",
        {"activeZoneMinutes": "active_zone_minutes"},
    ),
)

#: Activity time series. One request covers the whole window - Fitbit allows up
#: to 1,095 days on these - and each answers `[{dateTime, value}]`.
ACTIVITY_RANGES: tuple[tuple[str, str], ...] = (
    ("steps", "steps"),
    ("distance", "distance_km"),
    ("floors", "floors"),
    ("calories", "calories_burned"),
    ("minutesSedentary", "sedentary_minutes"),
    ("minutesLightlyActive", "lightly_active_minutes"),
    ("minutesFairlyActive", "fairly_active_minutes"),
    ("minutesVeryActive", "very_active_minutes"),
)

#: Fitbit's ceiling on the scalar range endpoints, and on the heart series.
SCALAR_RANGE_DAYS = 30
HEART_RANGE_DAYS = 365


def backfill_daily(connection: Connection, *, start: date, end: date) -> SyncReport:
    """Fill `DailyMetric` for a past range through the range endpoints.

    The same trade as `backfill_detail`, applied to the numbers rather than the
    chronology. `sync` walks a day at a time and spends about fourteen requests
    on each, so three months of history is 1,300 requests against a 150/hour
    limit - days of pressing the button, which is why the archive ends up with
    resting heart rate on some days and nothing on the rest. Every endpoint
    below also answers for a range, so the same three months costs about thirty
    requests.

    Deliberately *not* the whole sync: intraday samples have no range form at
    all, so minute-level heart rate still arrives one day at a time. This fills
    what a chart of daily values needs.
    """
    report = SyncReport(days_requested=(end - start).days + 1)

    with Client(connection) as client:
        try:
            _daily_ranges(client, connection.user, start, end, report)
        except RateLimited as exc:
            # Everything already written stays written; the endpoints are
            # idempotent, so the answer is to run it again in an hour.
            report.stopped_early = str(exc.detail)

        report.requests = client.requests

    report.synced_through = end
    return report


def _daily_ranges(client: Client, user, start: date, end: date, report: SyncReport) -> None:
    for path, key, fields in DAILY_RANGES:
        _range_scalars(client, user, path, key, fields, start, end, report)
    _range_heart(client, user, start, end, report)
    _range_activity(client, user, start, end, report)


def _chunks(start: date, end: date, size: int):
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=size - 1), end)
        yield cursor, stop
        cursor = stop + timedelta(days=1)


def _range_scalars(client, user, path, key, fields, start, end, report) -> None:
    for chunk_start, chunk_end in _chunks(start, end, SCALAR_RANGE_DAYS):
        body = client.get(path.format(start=f"{chunk_start:%Y-%m-%d}", end=f"{chunk_end:%Y-%m-%d}"))
        # SpO2 answers with a bare list; the others wrap it in a named key.
        entries = body if isinstance(body, list) else (body or {}).get(key) or []
        for entry in entries:
            day = timeutils.parse_date(entry.get("dateTime"))
            value = entry.get("value")
            if day is None:
                continue
            values: dict[str, float] = {}
            if isinstance(value, int | float):
                _put(values, next(iter(fields.values())), value)
            elif isinstance(value, dict):
                for source_field, metric_key in fields.items():
                    _put(values, metric_key, value.get(source_field))
            if values:
                report.daily_metrics_written += _write_daily(user, day, values)


def _range_heart(client, user, start, end, report) -> None:
    """Resting heart rate, the zone minutes, and where the zones sit.

    The boundaries come free with the minutes - every `heartRateZones` entry
    carries `min` and `max` in bpm alongside its `minutes` - and were being
    dropped, which left the intraday trace with no honest way to shade them.
    """
    for chunk_start, chunk_end in _chunks(start, end, HEART_RANGE_DAYS):
        body = client.get(
            f"/1/user/-/activities/heart/date/{chunk_start:%Y-%m-%d}/{chunk_end:%Y-%m-%d}.json"
        )
        for entry in (body or {}).get("activities-heart") or []:
            day = timeutils.parse_date(entry.get("dateTime"))
            value = entry.get("value") or {}
            if day is None or not isinstance(value, dict):
                continue
            values: dict[str, float] = {}
            _put(values, "resting_hr", value.get("restingHeartRate"))
            for zone in value.get("heartRateZones") or []:
                name = zone.get("name", "")
                if metric := ZONE_METRICS.get(name):
                    _put(values, metric, zone.get("minutes"))
                if floor := ZONE_FLOORS.get(name):
                    _put(values, floor, zone.get("min"))
                if name == "Peak":
                    _put(values, "zone_peak_ceiling_bpm", zone.get("max"))
            if values:
                report.daily_metrics_written += _write_daily(user, day, values)


def _range_activity(client, user, start, end, report) -> None:
    for resource, metric in ACTIVITY_RANGES:
        body = client.get(
            f"/1/user/-/activities/{resource}/date/{start:%Y-%m-%d}/{end:%Y-%m-%d}.json"
        )
        for entry in (body or {}).get(f"activities-{resource}") or []:
            day = timeutils.parse_date(entry.get("dateTime"))
            if day is None:
                continue
            values: dict[str, float] = {}
            _put(values, metric, entry.get("value"))
            if values:
                report.daily_metrics_written += _write_daily(user, day, values)


def _write_daily(user, day: date, values: dict[str, float]) -> int:
    """Write the provider's own daily numbers as `source="device"`.

    That marking is what stops the nightly rollup recomputing them from the
    minute samples. Fitbit's resting heart rate is better than anything
    derivable here, and a rollup that clobbered it would quietly degrade the
    single best long-term signal in the dataset.
    """
    rows = [
        DailyMetric(
            user=user,
            local_date=day,
            metric=metric,
            value=value,
            source=DailyMetric.Source.DEVICE,
        )
        for metric, value in values.items()
        if metric in metric_defs.DAILY_BY_KEY
    ]
    if not rows:
        return 0
    DailyMetric.objects.bulk_create(
        rows,
        update_conflicts=True,
        update_fields=["value", "source", "computed_at"],
        unique_fields=["user", "local_date", "metric"],
    )
    return len(rows)


#: Fitbit's zone names onto the portal's metrics. Shared by the day sync and
#: the range backfill so the two cannot disagree about which zone is which.
ZONE_METRICS = {
    "Out of Range": "zone_out_of_range_minutes",
    "Fat Burn": "zone_fat_burn_minutes",
    "Cardio": "zone_cardio_minutes",
    "Peak": "zone_peak_minutes",
}

#: Where each zone starts, in bpm. "Out of Range" is deliberately absent: its
#: floor is 30, a device default rather than a boundary anyone crosses, and
#: storing it would draw a band across the bottom of every chart.
ZONE_FLOORS = {
    "Fat Burn": "zone_fat_burn_floor_bpm",
    "Cardio": "zone_cardio_floor_bpm",
    "Peak": "zone_peak_floor_bpm",
}


def _put(out: dict, metric: str, value) -> None:
    if value is None:
        return
    try:
        out[metric] = float(value)
    except (TypeError, ValueError):
        # Fitbit occasionally answers with a banded string, e.g. VO2 max as
        # "36-40". Nothing sensible to store, so it is dropped rather than
        # guessed at.
        return


def _intraday(
    client: Client, user, day: date, tz, metric_key: str, resource: str, response_key: str
) -> int:
    """One intraday stream for one day, at 1-minute resolution."""
    stamp = f"{day:%Y-%m-%d}"
    body = client.get(f"/1/user/-/{resource}/date/{stamp}/1d/1min.json")
    dataset = ((body or {}).get(response_key) or {}).get("dataset") or []
    if not dataset:
        return 0

    rows = []
    for point in dataset:
        clock, value = point.get("time"), point.get("value")
        if value is None or not clock:
            continue
        try:
            moment = timeutils.utc_from_local_parts(day, timeutils.parse_hms(clock), tz)
        except (ValueError, TypeError):
            continue
        rows.append(Sample(user=user, metric=metric_key, ts=moment, value=float(value)))

    return _write_samples(rows)


def _hrv_intraday(client: Client, user, day: date, tz) -> int:
    """HRV comes in five-minute windows during sleep, on its own endpoint."""
    stamp = f"{day:%Y-%m-%d}"
    body = client.get(f"/1/user/-/hrv/date/{stamp}/all.json")
    entries = (body or {}).get("hrv") or []

    rows = []
    for entry in entries:
        for point in entry.get("minutes") or []:
            value = (point.get("value") or {}).get("rmssd")
            stampstr = point.get("minute")
            if value is None or not stampstr:
                continue
            moment = timeutils.parse_local_iso(stampstr, tz)
            if moment is None:
                continue
            rows.append(Sample(user=user, metric="hrv_rmssd", ts=moment, value=float(value)))

    return _write_samples(rows)


def _spo2_minutes(user, record, tz) -> int:
    """One night's SpO2 minutes, from either the single-date or range form."""
    rows = []
    for point in (record or {}).get("minutes") or []:
        value, stamp = point.get("value"), point.get("minute")
        if value is None or not stamp:
            continue
        moment = timeutils.parse_local_iso(stamp, tz)
        if moment is None:
            continue
        rows.append(Sample(user=user, metric="spo2", ts=moment, value=float(value)))

    return _write_samples(rows)


def _write_samples(rows: list[Sample]) -> int:
    if not rows:
        return 0
    Sample.objects.bulk_create(
        rows,
        batch_size=2_000,
        update_conflicts=True,
        update_fields=["value"],
        unique_fields=["user", "metric", "ts"],
    )
    return len(rows)


def _sleep_session(user, session: dict, *, day: date | None = None) -> bool:
    """Write one sleep log and its hypnogram. False if it was unusable.

    Shared by the day sync and the range backfill, which get the same payload
    from two different endpoints - so a fix to how a night is read cannot land
    on one path and miss the other.
    """
    external_id = str(session.get("logId") or "")
    started = _parse_naive(session.get("startTime"), user)
    ended = _parse_naive(session.get("endTime"), user)
    if not external_id or started is None or ended is None:
        return False

    stages = ((session.get("levels") or {}).get("summary")) or {}
    local_date = timeutils.parse_date(session.get("dateOfSleep")) or day
    if local_date is None:
        return False

    row, _ = SleepSession.objects.update_or_create(
        user=user,
        external_id=external_id,
        defaults={
            # Fitbit's `dateOfSleep` is the morning you woke, which is the
            # convention every existing query already assumes.
            "local_date": local_date,
            "started_at": started,
            "ended_at": ended,
            "duration_minutes": int(session.get("minutesAsleep") or 0),
            "efficiency": session.get("efficiency"),
            "minutes_deep": _stage(stages, "deep"),
            "minutes_light": _stage(stages, "light"),
            "minutes_rem": _stage(stages, "rem"),
            "minutes_awake": _stage(stages, "wake") or int(session.get("minutesAwake") or 0),
            "awakenings_count": int(session.get("awakeCount") or 0),
            "is_main_sleep": bool(session.get("isMainSleep", True)),
        },
    )
    _segments(row, session, user)
    return True


def _stage(summary: dict, name: str) -> int:
    return int(((summary.get(name) or {}).get("minutes")) or 0)


#: Fitbit's level names, mapped onto the model's. Anything unrecognised is
#: stored as `unknown` rather than guessed at - a new level name should show up
#: as a grey block that prompts a question, not as light sleep.
_LEVELS = {
    "deep": SleepSegment.Level.DEEP,
    "light": SleepSegment.Level.LIGHT,
    "rem": SleepSegment.Level.REM,
    "wake": SleepSegment.Level.WAKE,
    "asleep": SleepSegment.Level.ASLEEP,
    "restless": SleepSegment.Level.RESTLESS,
    "awake": SleepSegment.Level.AWAKE_CLASSIC,
}


def _segments(row: SleepSession, session: dict, user) -> None:
    """The hypnogram: `levels.data`, plus `shortData` kept separately.

    Replaced wholesale rather than merged. A re-sync of the same night returns
    the same segments, and reconciling them one by one would be a diff against
    data that is immutable once the night is over - whereas a delete and an
    insert cannot leave a stale segment from a superseded version of the log.
    """
    levels = session.get("levels") or {}
    tz = timeutils.tz_for(user)

    rows: list[SleepSegment] = []
    for key, is_short in (("data", False), ("shortData", True)):
        for entry in levels.get(key) or []:
            started = timeutils.parse_local_iso(entry.get("dateTime"), tz)
            seconds = entry.get("seconds")
            if started is None or not seconds:
                continue
            rows.append(
                SleepSegment(
                    session=row,
                    started_at=started,
                    ended_at=started + timedelta(seconds=int(seconds)),
                    seconds=int(seconds),
                    level=_LEVELS.get(str(entry.get("level")), SleepSegment.Level.UNKNOWN),
                    is_short=is_short,
                )
            )

    if not rows:
        # Nothing to write, and nothing to clear either: a log that arrived
        # without levels (an unstaged "classic" night, or a manual entry) must
        # not delete segments a previous sync of the same night captured.
        return

    with transaction.atomic():
        SleepSegment.objects.filter(session=row).delete()
        SleepSegment.objects.bulk_create(rows, batch_size=500)


def _parse_naive(value, user) -> datetime | None:
    """Fitbit timestamps are local wall clock with no offset.

    Reading them as UTC is the classic way to file a 23:00 bedtime under the
    wrong day, so they are localised through the subject's timezone.
    """
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return timeutils.utc_from_local_parts(
        naive.date(), time(naive.hour, naive.minute, naive.second), timeutils.tz_for(user)
    )
