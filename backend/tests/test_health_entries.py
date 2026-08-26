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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.health import services
from apps.health.models import BpEntry, DietEntry, Doc, Note, WeightEntry

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


def test_diet_and_doc_rows_carry_their_photo_url(alex, today, tmp_path, settings):
    """A photo attaches to its row via `/sync/photo`, well after
    `entries_for_day` has already been rendering that row without one - the
    timeline must pick it up once it exists, not just at creation.
    """
    settings.MEDIA_ROOT = tmp_path
    photo = SimpleUploadedFile("meal.jpg", b"not-really-a-jpeg", content_type="image/jpeg")

    diet = DietEntry.objects.create(
        created_by=alex, name="porridge", occurred_at=at(today, 8), local_date=today, photo=photo
    )
    Doc.objects.create(
        created_by=alex, title="Referral", occurred_at=at(today, 9), local_date=today
    )

    result = services.entries_for_day(alex, today)
    by_type = {e["type"]: e for e in result["entries"]}

    assert by_type["diet"]["image_url"] == diet.photo.url
    assert by_type["doc"]["image_url"] is None


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


# -- gym --------------------------------------------------------------------
#
# Gym is the one type where a card is *not* a row: sets are grouped into one
# card per exercise, because a leg day is thirty `GymSet` rows and thirty
# cards would bury everything else logged that day.


def gym_set(user, day: date, name: str, weight: float, reps: int, hour: int):
    from apps.health.models import GymSet

    return GymSet.objects.create(
        created_by=user,
        exercise_name=name,
        local_date=day,
        performed_at=at(day, hour),
        weight_kg=weight,
        reps=reps,
    )


def test_gym_sets_are_grouped_into_one_card_per_exercise(alex, today):
    gym_set(alex, today, "Squat", 80, 10, 9)
    gym_set(alex, today, "Squat", 85, 10, 10)
    gym_set(alex, today, "Chin Ups", 70, 8, 11)

    result = services.entries_for_day(alex, today)
    gym = [e for e in result["entries"] if e["type"] == "gym"]

    assert len(gym) == 2
    assert {e["value"] for e in gym} == {"Squat", "Chin Ups"}
    squat = next(e for e in gym if e["value"] == "Squat")
    assert squat["lines"] == ["80 kg x 10 reps", "85 kg x 10 reps"]


def test_set_lines_read_in_the_order_they_were_performed(alex, today):
    # Inserted heaviest-first so a pass that leaned on insertion order fails.
    gym_set(alex, today, "Squat", 90, 8, 11)
    gym_set(alex, today, "Squat", 80, 10, 9)
    gym_set(alex, today, "Squat", 85, 10, 10)

    result = services.entries_for_day(alex, today)
    squat = next(e for e in result["entries"] if e["type"] == "gym")

    assert squat["lines"] == ["80 kg x 10 reps", "85 kg x 10 reps", "90 kg x 8 reps"]


def test_a_bodyweight_set_says_reps_not_zero_kg(alex, today):
    gym_set(alex, today, "Press Ups", 0, 20, 9)

    result = services.entries_for_day(alex, today)
    card = next(e for e in result["entries"] if e["type"] == "gym")

    assert card["lines"] == ["20 reps"]


def test_a_gym_card_sits_at_its_earliest_set(alex, today):
    gym_set(alex, today, "Squat", 80, 10, 15)
    gym_set(alex, today, "Squat", 85, 10, 9)
    DietEntry.objects.create(
        created_by=alex, name="lunch", occurred_at=at(today, 12), local_date=today
    )

    result = services.entries_for_day(alex, today)

    # 09:00 squat group, then the 12:00 lunch - not the 15:00 last set.
    assert [e["type"] for e in result["entries"]] == ["gym", "diet"]


def test_gym_sets_from_another_day_do_not_leak_in(alex, today):
    gym_set(alex, today - timedelta(days=1), "Squat", 80, 10, 9)

    result = services.entries_for_day(alex, today)

    assert [e for e in result["entries"] if e["type"] == "gym"] == []
