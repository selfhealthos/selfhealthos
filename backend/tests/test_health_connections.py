"""Wearable connections: credentials, the OAuth handshake, and the sync.

The properties worth pinning here are the ones that fail quietly. A secret that
leaks into an API response, a callback that attaches someone else's Fitbit
account to this profile, a refresh that loses the rotating token — none of
those announce themselves.
"""

from __future__ import annotations

import json
from datetime import date, time, timedelta
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.health import connections as conn_services
from apps.health import crypto, timeutils
from apps.health.models import Connection, DailyMetric, Sample, SleepSegment, SleepSession
from apps.health.providers import fitbit

User = get_user_model()
PASSWORD = "x" * 14
REDIRECT = "https://home.laverty/apps/health/fitbit/callback"


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


@pytest.fixture
def sam(db):
    return User.objects.create_user(username="sam", password=PASSWORD)


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def configured(user, **kw) -> Connection:
    connection = Connection(
        user=user,
        provider=Connection.Provider.FITBIT,
        client_id=kw.pop("client_id", "23BCQY"),
    )
    connection.client_secret = kw.pop("client_secret", "a-secret")
    for key, value in kw.items():
        setattr(connection, key, value)
    connection.save()
    return connection


def connected(user, **kw) -> Connection:
    # Applied after the defaults below, so a test can hand in an already-expired
    # token without the helper quietly overwriting it.
    expires = kw.pop("token_expires_at", timezone.now() + timedelta(hours=8))
    connection = configured(user, **kw)
    connection.access_token = "access-1"
    connection.refresh_token = "refresh-1"
    connection.status = Connection.Status.CONNECTED
    connection.token_expires_at = expires
    connection.save()
    return connection


# --------------------------------------------------------------------------
# Credentials at rest
# --------------------------------------------------------------------------


def test_secrets_are_not_stored_in_the_clear(alex):
    connection = configured(alex, client_secret="b351e64bd6b4cae2771a1c7654d22193")

    assert connection.client_secret == "b351e64bd6b4cae2771a1c7654d22193"
    # What actually lands in the column - and therefore in a pg_dump.
    stored = Connection.objects.values("client_secret_enc").get(pk=connection.pk)
    assert "b351e64" not in stored["client_secret_enc"]
    assert connection.client_secret_enc != connection.client_secret


def test_a_rotated_key_is_a_clear_error_not_a_crash(alex):
    connection = configured(alex)

    with (
        patch.object(crypto, "_key", return_value=crypto.Fernet.generate_key()),
        pytest.raises(crypto.CannotDecrypt, match="reconnect"),
    ):
        _ = connection.client_secret


def test_the_secret_is_never_returned_by_the_api(alex, client_for):
    configured(alex, client_secret="super-secret-value")

    body = client_for(alex).get("/api/v1/health/connections").content.decode()

    assert "super-secret-value" not in body
    assert "client_secret" not in body
    # The client id is not a secret and is shown so the form can be edited.
    assert "23BCQY" in body


def test_saving_without_a_secret_keeps_the_stored_one(alex):
    configured(alex, client_secret="original")

    conn_services.save_credentials(alex, "fitbit", client_id="23BCQY", client_secret="")

    assert Connection.objects.get(user=alex).client_secret == "original"


def test_the_first_save_demands_a_secret(alex):
    with pytest.raises(Exception, match="secret is required"):
        conn_services.save_credentials(alex, "fitbit", client_id="23BCQY", client_secret="")


def test_changing_the_client_id_drops_the_grant(alex):
    """A grant issued to one app registration is meaningless under another."""
    connected(alex)

    conn_services.save_credentials(
        alex, "fitbit", client_id="DIFFERENT", client_secret="new-secret"
    )

    refreshed = Connection.objects.get(user=alex)
    assert refreshed.status == Connection.Status.CONFIGURED
    assert refreshed.refresh_token_enc == ""


def test_connections_are_private_to_their_owner(alex, sam, client_for):
    configured(alex)

    mine = client_for(alex).get("/api/v1/health/connections").json()
    theirs = client_for(sam).get("/api/v1/health/connections").json()

    assert [c["configured"] for c in mine] == [True]
    # Sam sees the provider offered, but nothing of Alex's registration.
    assert [c["configured"] for c in theirs] == [False]
    assert theirs[0]["client_id"] == ""


# --------------------------------------------------------------------------
# The OAuth handshake
# --------------------------------------------------------------------------


def test_the_authorize_url_carries_pkce_and_the_exact_redirect(alex):
    configured(alex)

    url = conn_services.authorize(alex, "fitbit", redirect_uri=REDIRECT)

    assert url.startswith(fitbit.AUTHORIZE_URL)
    assert "code_challenge_method=S256" in url
    assert "client_id=23BCQY" in url
    # Fitbit rejects a redirect_uri that differs from the registered one by so
    # much as a trailing slash, so it must survive round-tripping verbatim.
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    assert query["redirect_uri"] == [REDIRECT]
    assert query["state"][0]


def test_a_callback_cannot_be_replayed(alex):
    configured(alex)
    url = conn_services.authorize(alex, "fitbit", redirect_uri=REDIRECT)
    state = _state_from(url)

    with patch.object(fitbit, "exchange_code") as exchange:
        conn_services.exchange(alex, code="abc", state=state)
        assert exchange.called

    # Second use of the same state must fail: the code is spent and a replay
    # is either a stale bookmark or someone else's captured callback.
    with pytest.raises(Exception, match="expired or was already used"):
        conn_services.exchange(alex, code="abc", state=state)


def test_a_callback_cannot_be_claimed_by_another_account(alex, sam):
    """The failure this prevents is quiet and permanent.

    Two people share a browser; Alex starts the flow, Sam is the one logged in
    when Fitbit redirects back. Without this check Alex's Fitbit history is
    filed under Sam's profile, and nothing about the result looks wrong.
    """
    configured(alex)
    configured(sam)
    state = _state_from(conn_services.authorize(alex, "fitbit", redirect_uri=REDIRECT))

    with pytest.raises(Exception, match="different account"):
        conn_services.exchange(sam, code="abc", state=state)


def test_an_unknown_state_is_refused(alex):
    configured(alex)
    with pytest.raises(Exception, match="expired or was already used"):
        conn_services.exchange(alex, code="abc", state="never-issued")


def test_exchange_stores_the_tokens_and_marks_it_connected(alex):
    connection = configured(alex)

    with patch.object(fitbit.httpx, "post", return_value=_token_response()):
        fitbit.exchange_code(connection, code="abc", verifier="v" * 43, redirect_uri=REDIRECT)

    connection.refresh_from_db()
    assert connection.status == Connection.Status.CONNECTED
    assert connection.access_token == "new-access"
    assert connection.refresh_token == "new-refresh"
    assert connection.provider_user_id == "ABC123"
    assert connection.token_expires_at > timezone.now()


def test_authorising_needs_credentials_first(alex):
    Connection.objects.create(user=alex, provider="fitbit")
    with pytest.raises(Exception, match="client ID and secret"):
        conn_services.authorize(alex, "fitbit", redirect_uri=REDIRECT)


def _state_from(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)["state"][0]


def _token_response(**overrides) -> httpx.Response:
    body = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 28800,
        "scope": "activity heartrate sleep",
        "user_id": "ABC123",
        **overrides,
    }
    return httpx.Response(200, json=body, request=httpx.Request("POST", fitbit.TOKEN_URL))


# --------------------------------------------------------------------------
# Refresh - the rotating token
# --------------------------------------------------------------------------


def test_a_refresh_stores_the_new_rotating_token(alex):
    """Fitbit's refresh tokens are single-use.

    Keeping the old one after spending it means the next refresh presents a
    dead credential, and the connection breaks with no error until then.
    """
    connection = connected(alex, token_expires_at=timezone.now() - timedelta(minutes=1))

    with patch.object(
        fitbit.httpx,
        "post",
        return_value=_token_response(access_token="a2", refresh_token="r2"),
    ):
        fitbit.refresh(connection)

    connection.refresh_from_db()
    assert connection.access_token == "a2"
    assert connection.refresh_token == "r2"


def test_a_token_rejected_before_its_expiry_is_still_refreshed(alex):
    """Revoked from the Fitbit account, say.

    The stored expiry says the token is fine, so an unforced refresh skips and
    the retry presents the same dead token — a 401 loop that looks like a
    Fitbit outage rather than a revoked grant.
    """
    connection = connected(alex)  # expiry eight hours away

    with patch.object(
        fitbit.httpx, "post", return_value=_token_response(access_token="a3")
    ) as post:
        fitbit.refresh(connection, force=True)

    assert post.called
    connection.refresh_from_db()
    assert connection.access_token == "a3"


def test_a_refresh_keeps_the_old_token_if_none_is_returned(alex):
    connection = connected(alex)

    with patch.object(fitbit.httpx, "post", return_value=_token_response(refresh_token="")):
        fitbit.refresh(connection)

    connection.refresh_from_db()
    # Better a stale token that might work than a blank one that cannot.
    assert connection.refresh_token == "refresh-1"


def test_a_still_valid_token_is_not_refreshed(alex):
    """Two workers racing on the same connection.

    The loser of the lock must not spend the token the winner just obtained -
    it would invalidate it and break the connection.
    """
    connection = connected(alex)

    with patch.object(fitbit.httpx, "post") as post:
        fitbit.refresh(connection)

    assert not post.called


def test_an_invalid_grant_marks_the_connection_for_reconnection(alex):
    connection = connected(alex, token_expires_at=timezone.now() - timedelta(minutes=1))
    rejection = httpx.Response(
        400,
        json={"errors": [{"errorType": "invalid_grant"}]},
        request=httpx.Request("POST", fitbit.TOKEN_URL),
    )

    with (
        patch.object(fitbit.httpx, "post", return_value=rejection),
        pytest.raises(fitbit.NeedsReconnect),
    ):
        fitbit.refresh(connection)

    connection.refresh_from_db()
    # Not "error": no retry can fix this, so the UI must ask for a reconnect.
    assert connection.status == Connection.Status.EXPIRED


# --------------------------------------------------------------------------
# The sync window
# --------------------------------------------------------------------------


def test_the_first_sync_takes_a_week(alex):
    connection = connected(alex)
    start, end = conn_services.sync_window(connection, None)

    assert (end - start).days == conn_services.DEFAULT_BACKFILL_DAYS - 1


def test_a_later_sync_re_pulls_recent_days(alex):
    """The watch backfills.

    Last night's sleep stages and resting heart rate can land hours after the
    day is over, so a strictly forward-only sync captures the gaps and never
    the corrections.
    """
    through = timezone.localdate() - timedelta(days=1)
    connection = connected(alex, synced_through=through)

    start, end = conn_services.sync_window(connection, None)

    assert start == through - timedelta(days=conn_services.OVERLAP_DAYS)
    assert end == timezone.localdate()


def test_a_huge_range_is_clamped(alex):
    connection = connected(alex)
    start, end = conn_services.sync_window(connection, 3650)

    assert (end - start).days == conn_services.MAX_SYNC_DAYS - 1


# --------------------------------------------------------------------------
# Pulling data
# --------------------------------------------------------------------------

DAY = date(2026, 6, 4)


def fitbit_responses() -> dict:
    """One day of plausible Fitbit payloads, keyed by path fragment.

    Range shapes, because that is what the sync asks for now: every endpoint
    with a date-range form is fetched once for the whole window rather than
    once per day. `FakeHttp` matches on the first fragment that appears in the
    path, so the intraday keys come first - "/activities/heart/date/" is a
    prefix of both the range call and the 1-minute one.
    """
    stamp = f"{DAY:%Y-%m-%d}"
    activity_totals = {
        "steps": 9811,
        "distance": 7.501,
        "floors": 12,
        "calories": 2450,
        "minutesSedentary": 600,
        "minutesLightlyActive": 200,
        "minutesFairlyActive": 30,
        "minutesVeryActive": 45,
    }
    return {
        # -- intraday, per day. Must precede the range keys they share a prefix
        # with, or the range payload answers the 1-minute request.
        "/activities/heart/date/2026-06-04/1d/1min.json": {
            "activities-heart-intraday": {
                "dataset": [
                    {"time": "00:00:00", "value": 61},
                    {"time": "00:01:00", "value": 62},
                ]
            }
        },
        "/spo2/date/2026-06-04/2026-06-04/all.json": [
            {"dateTime": stamp, "minutes": [{"minute": f"{stamp}T02:00:00", "value": 96.5}]}
        ],
        "/hrv/date/2026-06-04/all.json": {
            "hrv": [{"minutes": [{"minute": f"{stamp}T02:00:00", "value": {"rmssd": 70.1}}]}]
        },
        # -- ranges
        "/spo2/date/": [{"dateTime": stamp, "value": {"avg": 96.1, "min": 92.0, "max": 99.0}}],
        "/hrv/date/": {"hrv": [{"dateTime": stamp, "value": {"dailyRmssd": 68.8}}]},
        "/br/date/": {"br": [{"dateTime": stamp, "value": {"breathingRate": 15.4}}]},
        "/temp/skin/date/": {"tempSkin": [{"dateTime": stamp, "value": {"nightlyRelative": -0.3}}]},
        "/cardioscore/date/": {"cardioScore": [{"dateTime": stamp, "value": {"vo2Max": 47.2}}]},
        "/activities/active-zone-minutes/date/": {
            "activities-active-zone-minutes": [
                {"dateTime": stamp, "value": {"activeZoneMinutes": 62}}
            ]
        },
        "/activities/heart/date/": {
            "activities-heart": [
                {
                    "dateTime": stamp,
                    "value": {
                        "restingHeartRate": 64,
                        "heartRateZones": [
                            {"name": "Out of Range", "min": 30, "max": 97, "minutes": 1200},
                            {"name": "Fat Burn", "min": 97, "max": 136, "minutes": 150},
                            {"name": "Cardio", "min": 136, "max": 166, "minutes": 40},
                            {"name": "Peak", "min": 166, "max": 220, "minutes": 5},
                        ],
                    },
                }
            ]
        },
        **{
            f"/activities/{resource}/date/": {
                f"activities-{resource}": [{"dateTime": stamp, "value": str(total)}]
            }
            for resource, total in activity_totals.items()
        },
        "/sleep/date/": {
            "sleep": [
                {
                    "logId": "sleep-1",
                    "dateOfSleep": stamp,
                    "startTime": "2026-06-03T22:31:00.000",
                    "endTime": "2026-06-04T05:50:00.000",
                    "minutesAsleep": 419,
                    "minutesAwake": 20,
                    "efficiency": 86,
                    "isMainSleep": True,
                    "awakeCount": 3,
                    "levels": {
                        "summary": {
                            "deep": {"minutes": 59},
                            "light": {"minutes": 260},
                            "rem": {"minutes": 100},
                            "wake": {"minutes": 20},
                        }
                    },
                }
            ]
        },
    }


class FakeHttp:
    """Stands in for httpx.Client, matching on a path fragment."""

    def __init__(self, responses: dict, *, status_for: dict | None = None):
        self.responses = responses
        self.status_for = status_for or {}
        self.paths: list[str] = []

    def get(self, path, headers=None):
        self.paths.append(path)
        for fragment, status in self.status_for.items():
            if fragment in path:
                return httpx.Response(status, request=httpx.Request("GET", path))
        for fragment, body in self.responses.items():
            if fragment in path:
                return httpx.Response(200, json=body, request=httpx.Request("GET", path))
        # Everything unmatched is "nothing recorded", which is what Fitbit
        # answers for a day a feature was not worn.
        return httpx.Response(404, request=httpx.Request("GET", path))

    def close(self):
        pass


def run_sync(connection, responses, **kw) -> fitbit.SyncReport:
    fake = FakeHttp(responses, **kw)
    with patch.object(fitbit.httpx, "Client", return_value=fake):
        report = fitbit.sync(connection, start=DAY, end=DAY)
    report.paths = fake.paths  # type: ignore[attr-defined]
    return report


def test_a_day_lands_as_daily_metrics_samples_and_sleep(alex):
    connection = connected(alex)

    report = run_sync(connection, fitbit_responses())

    assert report.days_synced == 1
    values = dict(
        DailyMetric.objects.filter(user=alex, local_date=DAY).values_list("metric", "value")
    )
    assert values["steps"] == 9811
    assert values["resting_hr"] == 64
    assert values["distance_km"] == 7.501
    assert values["active_zone_minutes"] == 62
    assert values["hrv_rmssd"] == 68.8
    assert values["spo2_avg"] == 96.1
    assert values["breathing_rate"] == 15.4

    assert Sample.objects.filter(user=alex, metric="hr").count() == 2
    session = SleepSession.objects.get(user=alex)
    assert session.local_date == DAY
    assert session.minutes_deep == 59
    assert session.duration_minutes == 419


def test_zone_boundaries_are_stored_with_the_zone_minutes(alex):
    """The bpm edges arrive in the same payload as the minutes.

    Without them the intraday trace has no honest way to shade the zones: the
    alternative is recomputing 220-age locally, which produces bands that
    disagree with the very minute totals printed beside them.
    """
    connection = connected(alex)

    run_sync(connection, fitbit_responses())

    values = dict(
        DailyMetric.objects.filter(user=alex, local_date=DAY).values_list("metric", "value")
    )
    assert values["zone_fat_burn_floor_bpm"] == 97
    assert values["zone_cardio_floor_bpm"] == 136
    assert values["zone_peak_floor_bpm"] == 166
    assert values["zone_peak_ceiling_bpm"] == 220
    # The "Out of Range" floor is a device default, not a boundary, and is the
    # one deliberately left unstored.
    assert "zone_out_of_range_floor_bpm" not in values


def test_provider_numbers_are_marked_authoritative(alex):
    """`source="device"` is what stops the nightly rollup recomputing them.

    Fitbit's resting heart rate is better than anything derivable from the
    minute samples it also supplied, and a rollup that overwrote it would
    quietly degrade the best long-term signal in the dataset.
    """
    connection = connected(alex)
    run_sync(connection, fitbit_responses())

    sources = set(
        DailyMetric.objects.filter(user=alex, local_date=DAY).values_list("source", flat=True)
    )
    assert sources == {DailyMetric.Source.DEVICE}


def test_intraday_is_requested_at_one_minute(alex):
    """Roadmap decision 1. `1sec` is 60x the rows for data nothing reads."""
    connection = connected(alex)
    report = run_sync(connection, fitbit_responses())

    intraday = [p for p in report.paths if "1d/" in p]  # type: ignore[attr-defined]
    assert intraday
    assert all(p.endswith("/1min.json") for p in intraday)
    assert not any("1sec" in p for p in report.paths)  # type: ignore[attr-defined]


def test_a_missing_day_is_a_gap_not_a_failure(alex):
    """Fitbit answers 404 for a day a feature was not worn or supported.

    Treating that as an error would abandon a backfill on the first day
    somebody left the watch on the charger.
    """
    connection = connected(alex)

    report = run_sync(connection, {})

    assert report.days_synced == 1
    assert report.warnings == []
    assert DailyMetric.objects.filter(user=alex).count() == 0


def test_a_rate_limit_keeps_what_the_range_pass_wrote(alex):
    """Fitbit allows 150 requests an hour, so a long sync will meet the limit.

    What matters is that it stops cleanly: the cheap range pass has already
    written the daily numbers and the sleep logs for the whole window, and
    those stay written when the per-day intraday pass is refused.
    """
    connection = connected(alex)
    later = DAY + timedelta(days=1)

    fake = FakeHttp(fitbit_responses(), status_for={"1d/1min.json": 429})
    with patch.object(fitbit.httpx, "Client", return_value=fake):
        report = fitbit.sync(connection, start=DAY, end=later)

    assert report.stopped_early
    assert DailyMetric.objects.filter(user=alex, local_date=DAY).exists()
    assert SleepSession.objects.filter(user=alex).exists()
    # And nothing was written for the day it never reached.
    assert not Sample.objects.filter(user=alex, metric="hr").exists()


def test_days_that_already_have_minutes_are_not_fetched_again(alex):
    """The change that makes a long sync affordable at all.

    Intraday is the only per-day cost left, at seven requests a day against a
    limit of 150 an hour. Re-fetching a day whose minutes are already stored
    returns identical rows for the same price, so a 30-day sync would spend its
    whole budget re-downloading three weeks nobody asked about.
    """
    connection = connected(alex)
    old = DAY - timedelta(days=10)
    Sample.objects.create(
        user=alex,
        metric="hr",
        ts=timeutils.utc_from_local_parts(old, time(3, 0), timeutils.tz_for(alex)),
        value=61.0,
    )

    fake = FakeHttp(fitbit_responses())
    with patch.object(fitbit.httpx, "Client", return_value=fake):
        fitbit.sync(connection, start=old, end=old + timedelta(days=1))

    asked = [path for path in fake.paths if "1d/1min.json" in path]
    assert not any(f"{old:%Y-%m-%d}" in path for path in asked), (
        "re-fetched a day whose minutes were already stored"
    )
    assert any(f"{old + timedelta(days=1):%Y-%m-%d}" in path for path in asked)


def test_the_last_days_are_always_re_fetched(alex):
    """Fitbit backfills last night for hours afterwards - stages, resting heart
    rate, HRV. A sync that trusted "this day has data" would keep the first
    partial version of every day forever.

    Anchored to today rather than to the end of the window, so a backfill of a
    settled month does not spend requests re-fetching its last two days."""
    connection = connected(alex)
    today = date.today()
    Sample.objects.create(
        user=alex,
        metric="hr",
        ts=timeutils.utc_from_local_parts(today, time(3, 0), timeutils.tz_for(alex)),
        value=61.0,
    )

    fake = FakeHttp(fitbit_responses())
    with patch.object(fitbit.httpx, "Client", return_value=fake):
        fitbit.sync(connection, start=today, end=today)

    assert any("1d/1min.json" in path for path in fake.paths)


def test_the_range_pass_costs_the_same_however_long_the_window(alex):
    """One request per endpoint for the window, not per day. This is the whole
    reason a season of history is affordable."""
    connection = connected(alex)

    fake = FakeHttp(fitbit_responses())
    with patch.object(fitbit.httpx, "Client", return_value=fake):
        fitbit.sync(connection, start=DAY - timedelta(days=20), end=DAY)

    ranges = [path for path in fake.paths if "1d/1min.json" not in path and "/all.json" not in path]
    assert len(ranges) <= 16, f"the range pass grew: {len(ranges)} requests"


def test_sleep_timestamps_are_localised_not_read_as_utc(alex):
    """Fitbit writes local wall clock with no offset.

    Read as UTC, a 22:31 bedtime in Melbourne lands ten hours out and the
    session is filed against the wrong day.
    """
    connection = connected(alex)
    run_sync(connection, fitbit_responses())

    session = SleepSession.objects.get(user=alex)
    from apps.health import timeutils

    local_start = session.started_at.astimezone(timeutils.tz_for(alex))
    assert (local_start.hour, local_start.minute) == (22, 31)
    assert local_start.date() == date(2026, 6, 3)


# --------------------------------------------------------------------------
# The REST surface
# --------------------------------------------------------------------------


def test_syncing_needs_a_connection(alex, client_for):
    configured(alex)  # credentials only, never authorised

    response = client_for(alex).post("/api/v1/health/connections/fitbit/sync")

    assert response.status_code == 400
    assert "Connect this provider" in response.json()["detail"]


def test_sync_queues_and_returns_immediately(alex, client_for):
    connected(alex)

    with patch("apps.health.tasks.sync_connection.delay") as queued:
        response = client_for(alex).post("/api/v1/health/connections/fitbit/sync")

    assert response.status_code == 202
    assert response.json()["queued"] is True
    assert queued.called


def test_saving_credentials_over_the_api(alex, client_for):
    response = client_for(alex).put(
        "/api/v1/health/connections/fitbit",
        data=json.dumps({"client_id": "23BCQY", "client_secret": "shh"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert Connection.objects.get(user=alex).client_secret == "shh"


def test_an_unknown_provider_is_rejected(alex, client_for):
    response = client_for(alex).put(
        "/api/v1/health/connections/garmin",
        data=json.dumps({"client_id": "x", "client_secret": "y"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "garmin" in response.json()["detail"]


def test_disconnect_keeps_the_credentials(alex, client_for):
    connected(alex)

    with patch.object(fitbit, "revoke"):
        response = client_for(alex).delete("/api/v1/health/connections/fitbit")

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    # The tedious part to set up survives; "disconnect" almost always means
    # "reconnect in a minute".
    assert body["configured"] is True


def test_anonymous_callers_cannot_see_connections():
    assert Client().get("/api/v1/health/connections").status_code == 401


def test_the_exchange_route_is_not_shadowed_by_the_provider_route(alex, client_for):
    """`/connections/exchange` must not be eaten by `/connections/{provider}`.

    Django takes the first URL pattern that matches and never backtracks on a
    method mismatch, so registering the parameterised path first makes POST
    return "405, Allow: PUT, DELETE" - for an endpoint that is in the OpenAPI
    document, at the right path, rejecting the only method it has. The OAuth
    callback dies there, and the browser is left on an error page blaming
    Fitbit.
    """
    response = client_for(alex).post(
        "/api/v1/health/connections/exchange",
        data=json.dumps({"code": "abc", "state": "not-a-real-state"}),
        content_type="application/json",
    )

    assert response.status_code != 405, "the {provider} route is shadowing /exchange again"
    # Reached the handler: an unknown state is refused on its merits.
    assert response.status_code == 400
    assert "expired or was already used" in response.json()["detail"]


def test_a_full_callback_round_trip_reaches_the_provider(alex, client_for):
    """authorize -> exchange over HTTP, the path the browser actually takes."""
    configured(alex)
    client = client_for(alex)

    started = client.post("/api/v1/health/connections/fitbit/authorize")
    assert started.status_code == 200
    state = _state_from(started.json()["authorize_url"])

    with patch.object(fitbit.httpx, "post", return_value=_token_response()):
        finished = client.post(
            "/api/v1/health/connections/exchange",
            data=json.dumps({"code": "abc", "state": state}),
            content_type="application/json",
        )

    assert finished.status_code == 200
    assert finished.json()["connected"] is True


# --------------------------------------------------------------------------
# The hypnogram and the overnight oxygen minutes
# --------------------------------------------------------------------------
#
# Both were in the payload all along and were being thrown away. What makes
# them worth testing is that a mistake in either is invisible: a segment filed
# ten hours out still draws a hypnogram, just of a night that never happened.


def _levels() -> dict:
    return {
        "summary": {
            "deep": {"minutes": 59},
            "light": {"minutes": 260},
            "rem": {"minutes": 100},
            "wake": {"minutes": 20},
        },
        "data": [
            {"dateTime": "2026-06-03T22:31:00.000", "level": "light", "seconds": 1800},
            {"dateTime": "2026-06-03T23:01:00.000", "level": "deep", "seconds": 2400},
            {"dateTime": "2026-06-03T23:41:00.000", "level": "rem", "seconds": 900},
        ],
        "shortData": [
            {"dateTime": "2026-06-03T23:20:00.000", "level": "wake", "seconds": 60},
        ],
    }


def _with_levels() -> dict:
    responses = fitbit_responses()
    responses["/sleep/date/"]["sleep"][0]["levels"] = _levels()
    return responses


def test_the_hypnogram_is_stored_with_the_session(alex):
    connection = connected(alex)

    run_sync(connection, _with_levels())

    session = SleepSession.objects.get(user=alex)
    segments = list(SleepSegment.objects.filter(session=session, is_short=False))
    assert [segment.level for segment in segments] == ["light", "deep", "rem"]
    assert segments[1].seconds == 2400


def test_segment_times_are_read_in_the_wearer_s_timezone(alex):
    """Fitbit writes these with no offset. Read as UTC, a 22:31 bedtime in
    Melbourne files the whole night ten hours late - onto the following
    evening, where it still renders as a perfectly plausible hypnogram."""
    connection = connected(alex)

    run_sync(connection, _with_levels())

    first = SleepSegment.objects.filter(is_short=False).order_by("started_at").first()
    assert first is not None
    local = first.started_at.astimezone(timeutils.tz_for(alex))
    assert (local.hour, local.minute) == (22, 31)


def test_short_wakes_are_flagged_rather_than_interleaved(alex):
    """`shortData` overlays the trace. Merged into the main run it would split
    the deep block it lands inside, and the night would read as fragmented."""
    connection = connected(alex)

    run_sync(connection, _with_levels())

    short = SleepSegment.objects.filter(is_short=True)
    assert short.count() == 1
    assert short.first().level == "wake"
    assert SleepSegment.objects.filter(is_short=False, level="deep").count() == 1


def test_a_resync_replaces_the_segments_rather_than_doubling_them(alex):
    connection = connected(alex)

    run_sync(connection, _with_levels())
    run_sync(connection, _with_levels())

    assert SleepSegment.objects.filter(is_short=False).count() == 3


def test_a_log_without_levels_keeps_the_segments_already_stored(alex):
    """A night that comes back without `levels` - a manual entry, or an
    unstaged classic log - must not delete a hypnogram an earlier sync got."""
    connection = connected(alex)
    run_sync(connection, _with_levels())

    run_sync(connection, fitbit_responses())

    assert SleepSegment.objects.filter(is_short=False).count() == 3


def test_overnight_spo2_minutes_are_stored_as_samples(alex):
    connection = connected(alex)
    responses = _with_levels()
    # Ahead of the daily `/spo2/date/` entry: FakeHttp matches on the first
    # fragment that fits, and the daily one is a prefix of this path.
    # Overriding the key keeps its position in the fixture, which is ahead of
    # the summary range - both share the "/spo2/date/" fragment and FakeHttp
    # answers with the first that fits.
    responses = {
        **responses,
        "/spo2/date/2026-06-04/2026-06-04/all.json": [
            {
                "dateTime": "2026-06-04",
                "minutes": [
                    {"minute": "2026-06-04T02:00:00", "value": 96.5},
                    {"minute": "2026-06-04T02:01:00", "value": 88.0},
                ],
            }
        ],
    }

    run_sync(connection, responses)

    values = list(
        Sample.objects.filter(user=alex, metric="spo2")
        .order_by("ts")
        .values_list("value", flat=True)
    )
    assert values == [96.5, 88.0]


def test_a_night_without_spo2_is_not_an_error(alex):
    """Fitbit answers 404 for a night SpO2 was not tracked, which is most
    nights for most people and not a warning."""
    connection = connected(alex)

    report = run_sync(connection, _with_levels(), status_for={"/spo2/date/": 404})

    assert report.warnings == []
    assert Sample.objects.filter(user=alex, metric="spo2").count() == 0
