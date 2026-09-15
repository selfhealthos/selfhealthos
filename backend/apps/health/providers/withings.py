"""Withings: OAuth, the measure API, and the pull into hand-logged entries.

Same three-call contract as `fitbit.py` - `start_authorization`, `exchange_code`,
`sync` - so `connections.py` drives both without knowing which is which. What
differs is worth reading before changing anything here.

**Errors arrive inside HTTP 200.** Withings puts success or failure in a
`status` field in the response body and returns 200 for both. Every branch in
the Fitbit client keys off `response.status_code`; port one of those here and
every failure reads as a success with an empty body. `_call()` below is the
only place that unwraps the envelope, and nothing else in this module is
allowed to look at a status code.

**Values are `value x 10^unit`.** A weight comes back as
`{"value": 73485, "unit": -3}` and means 73.485 kg. `unit` is a power of ten,
never a unit name. Reading `value` on its own yields a number a thousand times
too large that is still plausible enough to chart.

**Refresh tokens rotate and are single-use**, exactly as Fitbit's do, with a
tighter window: the old one dies 8 hours after it is spent, or immediately once
the new access token is used. The locking and same-transaction commit in
`refresh()` are the same shape as Fitbit's for the same reasons, and are not
optional.

**Measurements land as `WeightEntry` / `BodyMeasurement` / `BpEntry`, not as
`DailyMetric`.** A scale reading is the same kind of fact as one typed into the
phone, and the rollup already knows how to turn weight entries into a
`weight_kg` series - taking the last reading of the day rather than the mean,
which is the rule a morning and an evening weigh-in actually need. Writing
`weight_kg` straight to `DailyMetric` as `source="device"` would make it
authoritative forever and permanently shadow anything hand-logged, because
`rollups._delete_stale` only ever touches `derived` rows.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.core.exceptions import DomainError

from .. import timeutils
from ..models import BodyMeasurement, BpEntry, Connection, WeightEntry

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
MEASURE_URL = "https://wbsapi.withings.net/measure"

#: Only what this module actually reads. `user.info` would additionally allow
#: `getdevice`, and `user.activity` the step counts - neither is used here, and
#: a scope asked for and never read is a permission granted for no reason.
SCOPES = ("user.metrics",)

#: Withings access tokens last 3 hours. Refresh early enough that a long
#: backfill cannot cross the boundary mid-flight.
REFRESH_MARGIN = timedelta(minutes=5)

#: Envelope status meaning the grant is gone. Deliberately just the one:
#: marking a connection EXPIRED forces a manual reconnect, so a code this
#: module has not confirmed the meaning of is reported as an ordinary error
#: instead. A wrong "needs reconnecting" is worse than a visible error message.
UNAUTHORIZED_STATUS = 401

#: Withings' own rate limit signal.
RATE_LIMIT_STATUS = 601

#: Substrings Withings uses in `error` when the *refresh token itself* is dead,
#: which it reports on the token endpoint without always using status 401.
DEAD_GRANT_HINTS = ("invalid_grant", "invalid_token", "refresh_token", "unauthorized")


class WithingsError(DomainError):
    title = "Withings request failed"


class NeedsReconnect(WithingsError):
    """The grant is gone. Retrying cannot fix it; the person must re-authorise."""

    title = "Reconnect Withings"


class RateLimited(WithingsError):
    title = "Withings rate limit reached"


# --------------------------------------------------------------------------
# Measurement types
# --------------------------------------------------------------------------
#
# `getmeas` returns whatever the account's hardware produces. Only the types
# this app has somewhere to put are requested - asking for the other thirty
# would enlarge every response with rows the writer would then discard.

MEASTYPE_WEIGHT = 1
MEASTYPE_FAT_RATIO = 6
MEASTYPE_FAT_MASS = 8
MEASTYPE_DIASTOLIC = 9
MEASTYPE_SYSTOLIC = 10

WANTED_MEASTYPES = (
    MEASTYPE_WEIGHT,
    MEASTYPE_FAT_RATIO,
    MEASTYPE_FAT_MASS,
    MEASTYPE_DIASTOLIC,
    MEASTYPE_SYSTOLIC,
)

#: Real measurements. Category 2 is the user's *goals* - a target weight typed
#: into the app, which is not a thing that happened and must never become an
#: entry.
CATEGORY_REAL = 1

#: One `getmeas` page. Withings pages with `more`/`offset`; this is how many
#: measure groups come back per request.
PAGE_SIZE = 500

#: Stop after this many pages of one sync, however much history is left. A
#: decade of daily weigh-ins is about four thousand groups, so this is ample -
#: it exists to bound a pathological account rather than to trim a normal one.
MAX_PAGES = 40


# --------------------------------------------------------------------------
# OAuth
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    #: Always empty. Withings has no PKCE on this flow, but `connections.py`
    #: stashes whatever is here and hands it back to `exchange_code`, so the
    #: field has to exist for the shared handshake to typecheck.
    verifier: str = ""


def start_authorization(connection: Connection, redirect_uri: str) -> AuthorizationRequest:
    """Build the URL to send the browser to.

    No PKCE: Withings does not offer it on this flow, and the client secret
    never leaves the server, so the code is redeemable only by this backend.
    """
    if not connection.is_configured:
        raise WithingsError("Save a Withings client ID and secret before connecting.")

    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": connection.client_id,
            # Comma-separated, unlike Fitbit's space-separated list. A space
            # here is accepted at the authorize screen and then produces a
            # grant with no scopes at all.
            "scope": ",".join(SCOPES),
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return AuthorizationRequest(url=f"{AUTHORIZE_URL}?{query}", state=state)


def exchange_code(connection: Connection, *, code: str, verifier: str, redirect_uri: str) -> None:
    """Trade the authorization code for tokens and store them.

    `verifier` is accepted and ignored - see `AuthorizationRequest`.
    """
    data = _token_request(
        connection,
        {
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "code": code,
            # Must match the authorize request byte for byte; Withings checks
            # it to stop a code being redeemed against a different callback.
            "redirect_uri": redirect_uri,
        },
    )

    connection.access_token = data.get("access_token", "")
    connection.refresh_token = data.get("refresh_token", "")
    connection.token_expires_at = _expiry(data.get("expires_in"))
    connection.scopes = sorted((data.get("scope") or "").replace(",", " ").split())
    connection.provider_user_id = str(data.get("userid") or "")
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

    Identical in shape to Fitbit's, and for the same two reasons: the row is
    locked so two workers cannot both present the same single-use token, and
    the replacement is committed in the transaction that spent the old one so a
    crash mid-exchange cannot leave the connection unrecoverable.
    """
    try:
        return _refresh_locked(connection, force=force)
    except NeedsReconnect:
        # Marked *outside* the transaction that has just rolled back. Writing
        # the status inside it means the rollback undoes it and the connection
        # goes on claiming to be healthy while every sync fails.
        _mark_expired(connection)
        raise


def _refresh_locked(connection: Connection, *, force: bool) -> Connection:
    with transaction.atomic():
        locked = Connection.objects.select_for_update().get(pk=connection.pk)

        # Another worker may have refreshed while this one waited on the lock.
        if (
            not force
            and locked.token_expires_at
            and locked.token_expires_at - REFRESH_MARGIN > _now()
        ):
            return locked

        if not locked.refresh_token_enc:
            raise NeedsReconnect("This Withings connection has no refresh token.")

        data = _token_request(
            locked,
            {
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "refresh_token": locked.refresh_token,
            },
        )

        locked.access_token = data.get("access_token", "")
        # Committed inside the same transaction that spent the old one.
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
    """The token endpoint. Credentials go in the body, not a Basic header.

    Withings has no Basic-auth form: `client_id` and `client_secret` are
    ordinary form fields alongside the grant, and the endpoint is the same
    `/v2/oauth2` for both grant types, distinguished only by `action`.
    """
    body = dict(payload, client_id=connection.client_id, client_secret=connection.client_secret)
    try:
        response = httpx.post(TOKEN_URL, data=body, timeout=30.0)
    except httpx.HTTPError as exc:
        raise WithingsError(f"Could not reach Withings: {exc}") from exc

    # A transport-level failure is still possible and still means nothing came
    # back; only *after* this does the envelope become the source of truth.
    if response.status_code >= 400:
        raise WithingsError(f"Withings returned {response.status_code}: {response.text[:300]}")

    try:
        envelope = response.json()
    except ValueError as exc:
        raise WithingsError("Withings returned a response that was not JSON.") from exc

    status = envelope.get("status")
    if status == 0:
        return envelope.get("body") or {}

    detail = str(envelope.get("error") or "")
    if status == UNAUTHORIZED_STATUS or any(hint in detail.lower() for hint in DEAD_GRANT_HINTS):
        # No side effect here: this runs inside `refresh`'s transaction, so a
        # status written now would be rolled back by the raise. The caller
        # marks the connection after the rollback.
        raise NeedsReconnect(
            "Withings rejected the credentials. Check the client ID and secret, then connect again."
        )
    raise WithingsError(f"Withings refused the token request (status {status}): {detail}")


def revoke(connection: Connection) -> None:
    """Nothing to call.

    Withings has no token-revocation endpoint on the public API - a grant is
    withdrawn by the person from their Withings account, not by the client. The
    local disconnect in `connections.disconnect` still clears the stored tokens,
    which is the part this app controls. Defined because `connections.py` calls
    `module.revoke()` for every provider.
    """
    return None


def _mark_expired(connection: Connection) -> None:
    Connection.objects.filter(pk=connection.pk).update(
        status=Connection.Status.EXPIRED, updated_at=_now()
    )


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
    """An authenticated POST that unwraps Withings' envelope.

    POST rather than GET because Withings takes its parameters as form fields
    on every endpoint, `action` included.
    """

    def __init__(self, connection: Connection):
        self.connection = connection
        self._http = httpx.Client(timeout=60.0)
        self.requests = 0

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info) -> None:
        self._http.close()

    def call(self, url: str, payload: dict) -> dict:
        self._ensure_token()
        envelope = self._post(url, payload)

        if envelope.get("status") == UNAUTHORIZED_STATUS:
            # Expired earlier than advertised - revoked from the Withings
            # account, say. Forced, because the stored expiry still claims the
            # token is good and an unforced refresh would skip and hand the
            # same dead token back.
            self.connection = refresh(self.connection, force=True)
            envelope = self._post(url, payload)
            if envelope.get("status") == UNAUTHORIZED_STATUS:
                _mark_expired(self.connection)
                raise NeedsReconnect("Withings rejected the access token.")

        status = envelope.get("status")
        if status == 0:
            return envelope.get("body") or {}
        if status == RATE_LIMIT_STATUS:
            raise RateLimited(
                "Withings' request limit was reached. Data pulled so far has "
                "been saved; try again later."
            )
        raise WithingsError(
            f"Withings returned status {status}: {envelope.get('error') or '(no detail)'}"
        )

    def _post(self, url: str, payload: dict) -> dict:
        try:
            response = self._http.post(
                url,
                data=payload,
                headers={"Authorization": f"Bearer {self.connection.access_token}"},
            )
        except httpx.HTTPError as exc:
            raise WithingsError(f"Could not reach Withings: {exc}") from exc

        self.requests += 1
        if response.status_code >= 400:
            raise WithingsError(f"Withings returned {response.status_code}: {response.text[:300]}")
        try:
            return response.json()
        except ValueError as exc:
            raise WithingsError("Withings returned a response that was not JSON.") from exc

    def _ensure_token(self) -> None:
        expires = self.connection.token_expires_at
        if not self.connection.access_token_enc or (expires and expires - REFRESH_MARGIN <= _now()):
            self.connection = refresh(self.connection)


# --------------------------------------------------------------------------
# Readings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One measure group, already in real units and a real timezone.

    The intermediate both the API sync and the CSV import normalise to, so the
    writer below is the single place that decides what a scale reading becomes.
    """

    taken_at: datetime
    local_date: date
    weight_kg: float | None = None
    fat_ratio_pct: float | None = None
    fat_mass_kg: float | None = None
    systolic: int | None = None
    diastolic: int | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            value is not None
            for value in (
                self.weight_kg,
                self.fat_ratio_pct,
                self.fat_mass_kg,
                self.systolic,
                self.diastolic,
            )
        )


def real_value(measure: dict) -> float:
    """`value` scaled by `unit`, which is a power of ten and not a unit name."""
    return float(measure.get("value", 0)) * (10 ** int(measure.get("unit", 0)))


def reading_from_group(group: dict, *, fallback_tz: ZoneInfo) -> Reading | None:
    """Turn one `getmeas` measure group into a `Reading`.

    The group carries its own `timezone`, and that is what decides `local_date`
    - not the user's current one. `local_date` is stored rather than computed,
    and a weigh-in taken in another timezone genuinely belongs to the calendar
    day it was morning in, not to the day it was back home. A history spanning
    a move or a holiday gets this wrong in a way nothing downstream can repair.
    """
    epoch = group.get("date")
    if epoch is None:
        return None

    taken_at = datetime.fromtimestamp(int(epoch), tz=ZoneInfo("UTC"))
    tz = _zone(group.get("timezone")) or fallback_tz

    values: dict[int, float] = {}
    for measure in group.get("measures") or []:
        meastype = measure.get("type")
        if meastype in WANTED_MEASTYPES:
            values[meastype] = real_value(measure)

    reading = Reading(
        taken_at=taken_at,
        local_date=timeutils.local_date_of(taken_at, tz),
        weight_kg=values.get(MEASTYPE_WEIGHT),
        fat_ratio_pct=values.get(MEASTYPE_FAT_RATIO),
        fat_mass_kg=values.get(MEASTYPE_FAT_MASS),
        systolic=_as_int(values.get(MEASTYPE_SYSTOLIC)),
        diastolic=_as_int(values.get(MEASTYPE_DIASTOLIC)),
    )
    return None if reading.is_empty else reading


def _zone(name) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError):
        # A timezone this machine's tzdata does not know is not worth failing a
        # decade of history over; the caller's own zone is a better guess than
        # nothing.
        logger.warning("withings sent an unknown timezone %r", name)
        return None


def _as_int(value: float | None) -> int | None:
    return None if value is None else round(value)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


@dataclass
class SyncReport:
    days_requested: int = 0
    #: Days this sync covered - the whole window, since one call answers for
    #: all of it. `connections._finish` rebuilds rollups over this span.
    days_synced: int = 0
    #: Days that actually held a measurement. The interesting number for a
    #: person reading the sync report, and never the one the rollup uses.
    days_with_readings: int = 0
    groups_seen: int = 0
    weight_entries: int = 0
    body_measurements: int = 0
    bp_entries: int = 0
    duplicates_skipped: int = 0
    requests: int = 0
    stopped_early: str = ""
    synced_through: date | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "days_requested": self.days_requested,
            "days_synced": self.days_synced,
            "days_with_readings": self.days_with_readings,
            "groups_seen": self.groups_seen,
            "weight_entries": self.weight_entries,
            "body_measurements": self.body_measurements,
            "bp_entries": self.bp_entries,
            "duplicates_skipped": self.duplicates_skipped,
            "requests": self.requests,
            "stopped_early": self.stopped_early,
            "synced_through": self.synced_through.isoformat() if self.synced_through else None,
            "warnings": self.warnings,
        }


def write_readings(user, readings: list[Reading], report: SyncReport) -> set[date]:
    """Store readings as entries, skipping ones already held.

    **Identity is `(user, occurred_at)`, and `client_id` stays None.** A scale
    cannot produce two readings in the same second, so the instant is a natural
    key - and it is the one thing the API sync and the CSV import agree on
    exactly, which is what lets a CSV backfill and a live sync overlap without
    doubling every row.

    `client_id` is deliberately not used for this. It is a *global* identity
    key that devicesync rejects when presented by a different user, and it
    belongs to the phone's own UUIDs; minting values into that namespace from a
    third party risks a collision whose failure mode is a rejected phone sync.
    The partner-logged workout fan-out sets it to None for the same reason.
    """
    touched: set[date] = set()
    if not readings:
        return touched

    # One query for the whole batch rather than one per reading: a first
    # backfill is hundreds of readings and this runs on every sync.
    instants = [reading.taken_at for reading in readings]
    existing_weight = set(
        WeightEntry.objects.filter(created_by=user, occurred_at__in=instants).values_list(
            "occurred_at", flat=True
        )
    )
    existing_body = set(
        BodyMeasurement.objects.filter(created_by=user, occurred_at__in=instants).values_list(
            "occurred_at", flat=True
        )
    )
    existing_bp = set(
        BpEntry.objects.filter(created_by=user, occurred_at__in=instants).values_list(
            "occurred_at", flat=True
        )
    )

    weights, bodies, bps = [], [], []

    for reading in readings:
        common = {
            "created_by": user,
            "occurred_at": reading.taken_at,
            "local_date": reading.local_date,
        }

        if reading.weight_kg is not None:
            if reading.taken_at in existing_weight:
                report.duplicates_skipped += 1
            else:
                weights.append(WeightEntry(**common, weight_kg=reading.weight_kg))
                touched.add(reading.local_date)

        # Body fat is reported as a ratio by modern scales and as a mass by
        # older ones. Either can be turned into the percentage this app stores,
        # so a scale that only reports mass is not silently dropped.
        fat_pct = reading.fat_ratio_pct
        if fat_pct is None and reading.fat_mass_kg is not None and reading.weight_kg:
            fat_pct = reading.fat_mass_kg / reading.weight_kg * 100
        if fat_pct is not None and reading.taken_at not in existing_body:
            bodies.append(BodyMeasurement(**common, body_fat_pct=round(fat_pct, 2)))
            touched.add(reading.local_date)

        if (
            reading.systolic is not None
            and reading.diastolic is not None
            and reading.taken_at not in existing_bp
        ):
            bps.append(BpEntry(**common, systolic=reading.systolic, diastolic=reading.diastolic))
            touched.add(reading.local_date)

    WeightEntry.objects.bulk_create(weights, batch_size=500)
    BodyMeasurement.objects.bulk_create(bodies, batch_size=500)
    BpEntry.objects.bulk_create(bps, batch_size=500)

    report.weight_entries += len(weights)
    report.body_measurements += len(bodies)
    report.bp_entries += len(bps)
    return touched


# --------------------------------------------------------------------------
# The sync
# --------------------------------------------------------------------------


def fetch_readings(
    client: Client,
    *,
    since: datetime,
    until: datetime,
    fallback_tz: ZoneInfo,
    report: SyncReport,
) -> list[Reading]:
    """Page through `getmeas` for one window and parse what comes back.

    Shared by the routine sync and the history backfill so the two cannot
    disagree about paging, category or which measure types are wanted - a
    backfill that quietly asked for a different set than the sync would leave
    a seam in the archive at whatever date the two met.

    A rate limit stops the walk and is recorded rather than raised: the pages
    already collected are real data, and throwing them away to report the
    limit would make a long backfill unable to make progress at all.
    """
    readings: list[Reading] = []
    offset = 0

    for _ in range(MAX_PAGES):
        payload = {
            "action": "getmeas",
            "meastypes": ",".join(str(code) for code in WANTED_MEASTYPES),
            "category": CATEGORY_REAL,
            "startdate": int(since.timestamp()),
            "enddate": int(until.timestamp()),
            "offset": offset,
        }
        try:
            body = client.call(MEASURE_URL, payload)
        except RateLimited as exc:
            report.stopped_early = str(exc.detail)
            break

        groups = body.get("measuregrps") or []
        report.groups_seen += len(groups)
        for group in groups:
            reading = reading_from_group(group, fallback_tz=fallback_tz)
            if reading is not None:
                readings.append(reading)

        if not body.get("more"):
            break
        offset = body.get("offset", 0)
    else:
        report.warnings.append(f"Stopped after {MAX_PAGES} pages; narrow the range and run again.")

    return readings


def sync(connection: Connection, *, start: date, end: date) -> SyncReport:
    """Pull one date range of measurements into entries.

    One paged `getmeas` call for the whole window, not one per day. A scale
    produces a handful of measure groups a day and the endpoint takes a range,
    so a month costs a single request where Fitbit's minute data costs seven a
    day. This is why `connections.MAX_SYNC_DAYS` is not the binding constraint
    it is for Fitbit.
    """
    report = SyncReport(days_requested=(end - start).days + 1)
    fallback_tz = timeutils.tz_for(connection.user)

    # Whole local days, converted to the instants that bound them. Not
    # `date.toordinal() * 86400` or any other UTC-midnight shortcut: the window
    # a person means by "the 14th" is their own day, and near a date boundary
    # the two differ by a reading.
    window_start = timeutils.utc_from_local_parts(start, time(0, 0), fallback_tz)
    window_end = timeutils.utc_from_local_parts(end, time(0, 0), fallback_tz) + timedelta(days=1)

    with Client(connection) as client:
        readings = fetch_readings(
            client,
            since=window_start,
            until=window_end,
            fallback_tz=fallback_tz,
            report=report,
        )
        report.requests = client.requests

    touched = write_readings(connection.user, readings, report)
    report.days_with_readings = len(touched)

    # `days_synced` means "days this sync covered", not "days that held
    # something". One `getmeas` call answers for the whole window, so every day
    # in it is covered even when most are empty. It has to be the span, because
    # `connections._finish` rebuilds rollups over
    # `synced_through - days_synced .. synced_through` - reporting the three
    # days that happened to have a weigh-in would leave the rest of the window
    # un-rebuilt, and `_delete_stale` would never clear a metric whose entry
    # has since been deleted.
    if not report.stopped_early:
        report.days_synced = report.days_requested
        # A day with no weigh-in is a real answer, not a gap to re-fetch
        # forever, so the resume point is the end of the window either way.
        report.synced_through = end
    elif touched:
        report.days_synced = (max(touched) - start).days + 1
        report.synced_through = max(touched)

    return report
