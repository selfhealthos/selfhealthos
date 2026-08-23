"""The entries timeline: every hand-logged entry on one day, in order.

The property worth pinning is the flattening itself - entries from several
different tables landing in one chronologically sorted list, each carrying
the type it came from - and that a day with nothing logged is a clean empty
list rather than an error.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.health import services
from apps.health.models import BpEntry, DietEntry, Note, WeightEntry

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make


@pytest.fixture
def today(alex):
    from apps.health import timeutils

    return timeutils.local_date_of(timezone.now(), timeutils.tz_for(alex))


def at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


def test_entries_are_flattened_and_sorted_oldest_first(alex, today):
    DietEntry.objects.create(
        created_by=alex, name="porridge", occurred_at=at(today, 8), local_date=today
    )
    WeightEntry.objects.create(
        created_by=alex, weight_kg=82.4, occurred_at=at(today, 7), local_date=today
    )
    BpEntry.objects.create(
        created_by=alex, systolic=118, diastolic=76, occurred_at=at(today, 20), local_date=today
    )

    result = services.entries_for_day(alex, today)

    assert [e["type"] for e in result["entries"]] == ["vitals_weight", "diet", "vitals_bp"]
    assert result["entries"][0]["value"] == "82.4 kg"
    assert result["entries"][1]["value"] == "porridge"
    assert result["entries"][2]["value"] == "118/76 mmHg"


def test_a_note_written_in_the_old_block_format_shows_plain_text(alex, today):
    Note.objects.create(
        created_by=alex,
        content='[{"t": "text", "v": "slept badly"}]',
        occurred_at=at(today, 9),
        local_date=today,
    )

    result = services.entries_for_day(alex, today)

    assert result["entries"][0]["value"] == "slept badly"


def test_a_day_with_nothing_logged_is_an_empty_list(alex, today):
    result = services.entries_for_day(alex, today)

    assert result == {"date": today, "entries": []}


def test_defaults_to_literally_today_not_the_latest_day_with_data(alex, today):
    DietEntry.objects.create(
        created_by=alex,
        name="yesterday's lunch",
        occurred_at=at(today - timedelta(days=1), 12),
        local_date=today - timedelta(days=1),
    )

    result = services.entries_for_day(alex)

    assert result["date"] == today
    assert result["entries"] == []


def test_entries_endpoint_is_scoped_to_the_caller(alex, client_for, today):
    sam = User.objects.create_user(username="sam", password=PASSWORD)
    DietEntry.objects.create(
        created_by=sam, name="sam's lunch", occurred_at=at(today, 12), local_date=today
    )

    response = client_for(alex).get(f"/api/v1/health/entries?on={today.isoformat()}")

    assert response.status_code == 200
    assert response.json()["entries"] == []
