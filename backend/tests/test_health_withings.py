"""Withings: the envelope, the unit scaling, the timezone, and the import.

Every test here pins a failure mode that produces plausible-looking wrong data
rather than an error - which is the only kind worth having for an importer.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.utils import timezone as dj_timezone

from apps.health import connections
from apps.health.models import BodyMeasurement, BpEntry, Connection, DailyMetric, WeightEntry
from apps.health.providers import withings

pytestmark = pytest.mark.django_db


UTC = ZoneInfo("UTC")


@pytest.fixture
def connection(user):
    connection = Connection.objects.create(
        user=user,
        provider=Connection.Provider.WITHINGS,
        client_id="test-client",
        status=Connection.Status.CONNECTED,
    )
    connection.client_secret = "test-secret"
    connection.access_token = "access-1"
    connection.refresh_token = "refresh-1"
    connection.token_expires_at = dj_timezone.now() + timedelta(hours=2)
    connection.save()
    return connection


def group(epoch: int, measures, tz="Australia/Sydney") -> dict:
    return {
        "date": epoch,
        "timezone": tz,
        "measures": [{"type": t, "value": v, "unit": u} for t, v, u in measures],
    }


# --------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------


def test_token_error_inside_http_200_is_not_treated_as_success(connection, monkeypatch):
    """Withings reports failure in the body and still answers 200.

    The whole Fitbit client branches on `response.status_code`. If that shape
    is copied here, this response reads as a success carrying an empty body and
    the connection is left holding an empty access token.
    """

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": 503, "error": "Invalid Params"}

    monkeypatch.setattr(withings.httpx, "post", lambda *a, **k: Response())

    with pytest.raises(withings.WithingsError) as caught:
        withings.exchange_code(
            connection,
            code="abc",
            verifier="",
            redirect_uri="https://example.test/withings/callback",
        )
    assert "503" in str(caught.value.detail)


def test_dead_refresh_token_marks_expired_outside_the_transaction(connection, monkeypatch):
    """A failed grant must survive the rollback that reports it.

    Marked inside the transaction, the raise rolls the status back and the
    connection goes on claiming to be healthy while every sync fails.
    """

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": 401, "error": "invalid_grant"}

    monkeypatch.setattr(withings.httpx, "post", lambda *a, **k: Response())

    with pytest.raises(withings.NeedsReconnect):
        withings.refresh(connection, force=True)

    connection.refresh_from_db()
    assert connection.status == Connection.Status.EXPIRED


def test_refresh_stores_the_rotated_token(connection, monkeypatch):
    """Withings rotates the refresh token; losing the new one is unrecoverable."""

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "status": 0,
                "body": {
                    "access_token": "access-2",
                    "refresh_token": "refresh-2",
                    "expires_in": 10800,
                },
            }

    monkeypatch.setattr(withings.httpx, "post", lambda *a, **k: Response())

    refreshed = withings.refresh(connection, force=True)
    assert refreshed.access_token == "access-2"
    assert refreshed.refresh_token == "refresh-2"

    connection.refresh_from_db()
    assert connection.refresh_token == "refresh-2"


def test_refresh_keeps_the_old_token_when_none_is_returned(connection, monkeypatch):
    """A response with no new refresh token must not blank the stored one."""

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": 0, "body": {"access_token": "access-2", "expires_in": 10800}}

    monkeypatch.setattr(withings.httpx, "post", lambda *a, **k: Response())

    withings.refresh(connection, force=True)
    connection.refresh_from_db()
    assert connection.refresh_token == "refresh-1"


# --------------------------------------------------------------------------
# Unit scaling
# --------------------------------------------------------------------------


def test_value_is_scaled_by_unit_as_a_power_of_ten():
    """`unit` is an exponent, not a unit name.

    Reading `value` alone gives 73485 kg, which is wrong by a factor of a
    thousand and still charts without complaint.
    """
    assert withings.real_value({"value": 73485, "unit": -3}) == pytest.approx(73.485)
    assert withings.real_value({"value": 1834, "unit": -2}) == pytest.approx(18.34)
    assert withings.real_value({"value": 72, "unit": 0}) == pytest.approx(72.0)


def test_group_without_a_wanted_measure_is_dropped():
    """A group holding only types this app has no home for is not an entry."""
    # 12 is a temperature reading: real, and nothing here stores it.
    assert (
        withings.reading_from_group(group(1_700_000_000, [(12, 3650, -2)]), fallback_tz=UTC) is None
    )


# --------------------------------------------------------------------------
# Timezones
# --------------------------------------------------------------------------


def test_local_date_comes_from_the_groups_own_timezone():
    """`local_date` is stored, not computed, so the wrong day is permanent.

    07:30 in Sydney on the 15th is 21:30 UTC on the 14th. A reading taken in
    Sydney belongs to the 15th whatever timezone the server or the account is
    in now.
    """
    sydney_morning = int(datetime(2026, 9, 14, 21, 30, tzinfo=UTC).timestamp())

    reading = withings.reading_from_group(
        group(sydney_morning, [(1, 73485, -3)], tz="Australia/Sydney"),
        fallback_tz=ZoneInfo("Europe/London"),
    )
    assert reading.local_date == date(2026, 9, 15)


def test_unknown_timezone_falls_back_rather_than_failing():
    """A zone this machine's tzdata lacks must not abort a decade of history."""
    reading = withings.reading_from_group(
        group(1_700_000_000, [(1, 73485, -3)], tz="Mars/Olympus_Mons"),
        fallback_tz=UTC,
    )
    assert reading is not None
    assert reading.weight_kg == pytest.approx(73.485)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def test_weight_lands_as_an_entry_not_a_device_daily_metric(user):
    """The rollup owns `weight_kg`, and must go on owning it.

    Written as `source="device"` it would be authoritative forever, and
    `rollups._delete_stale` - which only touches `derived` rows - could never
    clear it. A hand-logged correction would be permanently shadowed.
    """
    reading = withings.reading_from_group(group(1_700_000_000, [(1, 73485, -3)]), fallback_tz=UTC)
    report = withings.SyncReport()

    withings.write_readings(user, [reading], report)

    assert WeightEntry.objects.filter(created_by=user).count() == 1
    assert not DailyMetric.objects.filter(user=user, metric="weight_kg").exists()


def test_rollup_turns_imported_weight_into_the_daily_metric(user):
    """The point of writing entries: the existing rollup does the rest."""
    from apps.health import rollups

    reading = withings.reading_from_group(group(1_700_000_000, [(1, 73485, -3)]), fallback_tz=UTC)
    withings.write_readings(user, [reading], withings.SyncReport())

    rollups.rebuild(user, reading.local_date, reading.local_date)

    metric = DailyMetric.objects.get(user=user, metric="weight_kg", local_date=reading.local_date)
    assert metric.value == pytest.approx(73.485)
    assert metric.source == DailyMetric.Source.DERIVED


def test_the_same_reading_twice_is_one_row(user):
    """Re-running an import, or syncing a range a CSV covered, must not double."""
    reading = withings.reading_from_group(group(1_700_000_000, [(1, 73485, -3)]), fallback_tz=UTC)

    withings.write_readings(user, [reading], withings.SyncReport())
    second = withings.SyncReport()
    withings.write_readings(user, [reading], second)

    assert WeightEntry.objects.filter(created_by=user).count() == 1
    assert second.weight_entries == 0
    assert second.duplicates_skipped == 1


def test_imported_rows_carry_no_client_id(user):
    """`client_id` is the phone's namespace and devicesync rejects intruders."""
    reading = withings.reading_from_group(group(1_700_000_000, [(1, 73485, -3)]), fallback_tz=UTC)
    withings.write_readings(user, [reading], withings.SyncReport())

    assert WeightEntry.objects.get(created_by=user).client_id is None


def test_fat_mass_without_a_ratio_becomes_a_percentage(user):
    """Older scales report mass where newer ones report a ratio.

    Dropping the mass-only case would silently lose body composition from every
    pre-2015 scale.
    """
    reading = withings.reading_from_group(
        group(1_700_000_000, [(1, 80000, -3), (8, 10000, -3)]), fallback_tz=UTC
    )
    withings.write_readings(user, [reading], withings.SyncReport())

    measurement = BodyMeasurement.objects.get(created_by=user)
    assert measurement.body_fat_pct == pytest.approx(12.5)


def test_blood_pressure_needs_both_halves(user):
    """A systolic with no diastolic is not a blood pressure reading."""
    reading = withings.reading_from_group(group(1_700_000_000, [(10, 132, 0)]), fallback_tz=UTC)
    withings.write_readings(user, [reading], withings.SyncReport())

    assert not BpEntry.objects.filter(created_by=user).exists()


# --------------------------------------------------------------------------
# The sync
# --------------------------------------------------------------------------


def test_sync_pages_through_every_result(connection, monkeypatch):
    """`more`/`offset` paging: stopping at page one silently truncates history."""
    pages = [
        {"measuregrps": [group(1_700_000_000, [(1, 73485, -3)])], "more": 1, "offset": 1},
        {"measuregrps": [group(1_700_086_400, [(1, 73200, -3)])], "more": 0},
    ]
    calls = []

    def fake_call(self, url, payload):
        calls.append(payload)
        return pages[len(calls) - 1]

    monkeypatch.setattr(withings.Client, "call", fake_call)
    monkeypatch.setattr(withings.Client, "_ensure_token", lambda self: None)

    report = withings.sync(connection, start=date(2023, 11, 14), end=date(2023, 11, 16))

    assert len(calls) == 2
    assert calls[1]["offset"] == 1
    assert report.weight_entries == 2


def test_sync_reports_the_window_not_the_days_that_held_data(connection, monkeypatch):
    """`days_synced` feeds the rollup rebuild range in `connections._finish`.

    Reporting only the days with a weigh-in would leave the rest of the window
    un-rebuilt, so a deleted entry's stale metric would never be cleared.
    """
    monkeypatch.setattr(
        withings.Client,
        "call",
        lambda self, url, payload: {"measuregrps": [group(1_700_000_000, [(1, 73485, -3)])]},
    )
    monkeypatch.setattr(withings.Client, "_ensure_token", lambda self: None)

    report = withings.sync(connection, start=date(2023, 11, 1), end=date(2023, 11, 30))

    assert report.days_requested == 30
    assert report.days_synced == 30
    assert report.days_with_readings == 1
    assert report.synced_through == date(2023, 11, 30)


def test_sync_asks_only_for_real_measurements(connection, monkeypatch):
    """Category 2 is the user's *target* weight, which never happened."""
    seen = {}

    def fake_call(self, url, payload):
        seen.update(payload)
        return {"measuregrps": []}

    monkeypatch.setattr(withings.Client, "call", fake_call)
    monkeypatch.setattr(withings.Client, "_ensure_token", lambda self: None)

    withings.sync(connection, start=date(2023, 11, 1), end=date(2023, 11, 2))
    assert seen["category"] == withings.CATEGORY_REAL


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


def test_withings_is_offered_as_a_provider(user):
    providers = {c.provider for c in connections.list_connections(user)}
    assert Connection.Provider.WITHINGS in providers


def test_each_provider_gets_its_own_callback():
    """One shared callback path could not tell the two flows apart."""
    fitbit_uri = connections.redirect_uri_for(Connection.Provider.FITBIT)
    withings_uri = connections.redirect_uri_for(Connection.Provider.WITHINGS)

    assert fitbit_uri != withings_uri
    assert withings_uri.endswith("/withings/callback")


def test_authorize_url_uses_comma_separated_scopes(connection):
    """A space-separated scope list is accepted and yields a grant with none."""
    request = withings.start_authorization(connection, "https://example.test/withings/callback")

    assert "scope=user.metrics" in request.url
    assert request.state
    assert request.verifier == ""


# --------------------------------------------------------------------------
# The importer
# --------------------------------------------------------------------------


def write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_csv_import_reads_kilograms(user, tmp_path):
    path = write(
        tmp_path,
        "weight.csv",
        'Date,"Weight (kg)","Fat mass (kg)"\n'
        '"2026-09-14 07:05:00","73.485","10.173"\n'
        '"2026-09-13 07:02:11","73.900",""\n',
    )
    call_command("import_withings", path, user=user.username)

    assert WeightEntry.objects.filter(created_by=user).count() == 2
    assert WeightEntry.objects.order_by("-occurred_at").first().weight_kg == pytest.approx(73.485)


def test_csv_import_converts_pounds(user, tmp_path):
    """Withings exports in the account's own unit.

    Reading a pounds column as kilograms is wrong by 2.2x and looks entirely
    plausible on a chart, which is why the header decides and nothing assumes.
    """
    path = write(tmp_path, "weight.csv", 'Date,"Weight (lb)"\n"2026-09-14 07:05:00","162.0"\n')
    call_command("import_withings", path, user=user.username)

    assert WeightEntry.objects.get(created_by=user).weight_kg == pytest.approx(73.48, abs=0.01)


def test_csv_import_refuses_a_mass_column_with_no_unit(user, tmp_path):
    """Better to stop than to guess kilograms."""
    from django.core.management.base import CommandError

    path = write(tmp_path, "weight.csv", 'Date,Weight\n"2026-09-14 07:05:00","73.485"\n')

    with pytest.raises(CommandError, match="unit"):
        call_command("import_withings", path, user=user.username)


def test_csv_import_treats_a_blank_cell_as_absent(user, tmp_path):
    """A blank fat-mass column is "not measured", never 0.0."""
    path = write(
        tmp_path,
        "weight.csv",
        'Date,"Weight (kg)","Fat mass (kg)"\n"2026-09-14 07:05:00","73.485",""\n',
    )
    call_command("import_withings", path, user=user.username)

    assert not BodyMeasurement.objects.filter(created_by=user).exists()


def test_csv_import_is_idempotent(user, tmp_path):
    path = write(tmp_path, "weight.csv", 'Date,"Weight (kg)"\n"2026-09-14 07:05:00","73.485"\n')

    call_command("import_withings", path, user=user.username)
    call_command("import_withings", path, user=user.username)

    assert WeightEntry.objects.filter(created_by=user).count() == 1


def test_csv_import_builds_the_daily_metric(user, tmp_path):
    path = write(tmp_path, "weight.csv", 'Date,"Weight (kg)"\n"2026-09-14 07:05:00","73.485"\n')
    call_command("import_withings", path, user=user.username)

    metric = DailyMetric.objects.get(user=user, metric="weight_kg", local_date=date(2026, 9, 14))
    assert metric.value == pytest.approx(73.485)


def test_csv_import_keeps_the_local_calendar_day(user, tmp_path):
    """An early-morning weigh-in belongs to that morning, not to UTC's yesterday."""
    path = write(tmp_path, "weight.csv", 'Date,"Weight (kg)"\n"2026-09-14 07:05:00","73.485"\n')
    call_command("import_withings", path, user=user.username)

    assert WeightEntry.objects.get(created_by=user).local_date == date(2026, 9, 14)


def test_json_import_matches_the_sync(user, tmp_path):
    """A getmeas dump and a live sync must produce identical rows.

    This is what lets a CSV/JSON backfill and the ongoing sync overlap at the
    join without doubling every reading in the overlap.
    """
    groups = [group(1_700_000_000, [(1, 73485, -3)])]
    path = write(tmp_path, "dump.json", json.dumps(groups))

    call_command("import_withings", path, user=user.username)
    assert WeightEntry.objects.filter(created_by=user).count() == 1

    reading = withings.reading_from_group(groups[0], fallback_tz=UTC)
    report = withings.SyncReport()
    withings.write_readings(user, [reading], report)

    assert WeightEntry.objects.filter(created_by=user).count() == 1
    assert report.duplicates_skipped == 1


def test_dry_run_writes_nothing(user, tmp_path):
    path = write(tmp_path, "weight.csv", 'Date,"Weight (kg)"\n"2026-09-14 07:05:00","73.485"\n')
    call_command("import_withings", path, user=user.username, dry_run=True)

    assert not WeightEntry.objects.filter(created_by=user).exists()
