"""The subject's timezone: setting it, and what goes wrong when it is unset.

The regression pinned here rendered a complete, empty page rather than an
error. `User.timezone` defaults to `"UTC"` and nothing could change it, so a
subject in +10 who weighed in on Tuesday morning had the row stored under a
`local_date` the server still considered tomorrow - and every day-bounded read
(`body_history`, `entries_for_day`) filtered it straight back out. The POST
returned 201, the row was in the database, the rollup ran, and the Body page
showed nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.accounts import services as account_services
from apps.core.exceptions import DomainError
from apps.health import services as health_services

User = get_user_model()
PASSWORD = "x" * 14

#: 09:00 on Tuesday in Sydney is 23:00 on *Monday* in UTC. Any moment where the
#: two calendars disagree would do; this is the one from the bug report.
SYDNEY_MORNING = datetime(2026, 8, 24, 23, 45, tzinfo=UTC)


@pytest.fixture
def sydneysider(db):
    return User.objects.create_user(username="tz", password=PASSWORD, birth_date="1990-01-01")


@pytest.fixture
def signed_in(sydneysider):
    client = Client()
    client.force_login(sydneysider)
    return client


def test_the_column_default_is_utc_not_the_timeutils_fallback(sydneysider):
    """The drift that made the bug invisible.

    `timeutils.DEFAULT_TZ` is Melbourne and `tz_for`'s docstring used to claim
    the column defaulted to it. It does not - it defaults to `"UTC"`, which is
    non-empty and valid, so the Melbourne fallback never fires. If this ever
    flips, the docstring on `tz_for` is wrong again.
    """
    from apps.health import timeutils

    assert sydneysider.timezone == "UTC"
    assert timeutils.tz_for(sydneysider) == ZoneInfo("UTC")


def test_a_morning_weigh_in_is_lost_while_the_timezone_is_wrong(sydneysider):
    """The original failure, reproduced end to end. Not an error anywhere."""
    with patch.object(health_services, "_utcnow", return_value=SYDNEY_MORNING):
        # The browser's date picker offers the subject's own Tuesday.
        health_services.log_entry(sydneysider, kind="weight", value=70.0, on=None)
        body = health_services.body_history(sydneysider, days=730)

    # Stored under Monday, because the server's idea of "now" is UTC.
    assert body["end"].isoformat() == "2026-08-24"
    assert [w["weight_kg"] for w in body["weights"]] == [70.0]
    assert body["weights"][0]["local_date"].isoformat() == "2026-08-24"


def test_setting_the_timezone_puts_the_weigh_in_back_on_the_page(sydneysider):
    """The fix: same instant, same call, correct day - and it is visible."""
    account_services.set_timezone(sydneysider, "Australia/Sydney")

    with patch.object(health_services, "_utcnow", return_value=SYDNEY_MORNING):
        health_services.log_entry(sydneysider, kind="weight", value=70.0, on=None)
        body = health_services.body_history(sydneysider, days=730)
        entries = health_services.entries_for_day(sydneysider)

    assert body["end"].isoformat() == "2026-08-25"
    assert body["weights"][0]["local_date"].isoformat() == "2026-08-25"
    # The scored table under the chart reads DailyMetric, not the entry rows -
    # a separate path that the same window bug also silenced.
    assert [row["date"].isoformat() for row in body["rows"]] == ["2026-08-25"]
    assert entries["date"].isoformat() == "2026-08-25"
    assert [e["type"] for e in entries["entries"]] == ["vitals_weight"]


def test_a_backdated_entry_is_filed_in_the_subjects_own_calendar(sydneysider):
    """`on=` is a date in the subject's timezone, not the server's."""
    from datetime import date

    account_services.set_timezone(sydneysider, "Australia/Sydney")
    with patch.object(health_services, "_utcnow", return_value=SYDNEY_MORNING):
        entry, _ = health_services.log_entry(
            sydneysider, kind="weight", value=71.0, on=date(2026, 8, 25)
        )

    assert entry.local_date.isoformat() == "2026-08-25"
    # Noon in Sydney is 02:00 UTC. Filed at a real instant inside that day.
    assert entry.occurred_at == datetime(2026, 8, 25, 2, 0, tzinfo=UTC)


def test_patch_me_sets_the_timezone(signed_in, sydneysider):
    resp = signed_in.patch(
        "/api/v1/auth/me",
        data={"timezone": "Australia/Sydney"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Australia/Sydney"
    sydneysider.refresh_from_db()
    assert sydneysider.timezone == "Australia/Sydney"


def test_patch_me_rejects_a_zone_the_server_does_not_know(signed_in, sydneysider):
    resp = signed_in.patch(
        "/api/v1/auth/me",
        data={"timezone": "Australia/Sidney"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    sydneysider.refresh_from_db()
    assert sydneysider.timezone == "UTC"


def test_patch_me_leaves_an_unsent_field_alone(signed_in, sydneysider):
    """PATCH, not PUT - an empty body must not blank the timezone.

    The same trap `set_body_profile` documents: two forms on one page, each
    knowing about one field.
    """
    account_services.set_timezone(sydneysider, "Australia/Sydney")
    resp = signed_in.patch("/api/v1/auth/me", data={}, content_type="application/json")

    assert resp.status_code == 200
    sydneysider.refresh_from_db()
    assert sydneysider.timezone == "Australia/Sydney"


def test_set_timezone_rejects_blank(sydneysider):
    with pytest.raises(DomainError):
        account_services.set_timezone(sydneysider, "  ")


def test_the_picker_list_offers_real_places_and_not_the_etc_traps(signed_in):
    resp = signed_in.get("/api/v1/auth/timezones")
    assert resp.status_code == 200
    body = resp.json()

    assert "Australia/Sydney" in body["timezones"]
    assert "Australia/Melbourne" in body["timezones"]
    assert "UTC" in body["timezones"]
    assert body["current"] == "UTC"
    # `Etc/GMT+10` is *west* of Greenwich - offering it in a dropdown is
    # offering a trap. Legacy aliases are out for the same reason.
    assert not [name for name in body["timezones"] if name.startswith(("Etc/", "US/"))]


def test_a_legacy_alias_still_validates_even_though_it_is_not_offered(sydneysider):
    """The picker list is narrower than what `set_timezone` accepts, on purpose.

    An API client that sends `US/Pacific` is not wrong, just old.
    """
    account_services.set_timezone(sydneysider, "US/Pacific")
    assert sydneysider.timezone == "US/Pacific"
    assert "US/Pacific" not in account_services.timezone_choices()
