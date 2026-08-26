"""Correcting one row on the entries timeline.

The property worth pinning hardest is the stored `local_date`: moving an
entry's time across midnight has to re-file it on the new day, or the
correction lands somewhere no day-scoped query will ever look - including the
day view the person just made it on. The rollup has to follow across both
days for the same reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.core.exceptions import DomainError, NotFound
from apps.health import services, timeutils
from apps.health.models import BmEntry, BpEntry, DietEntry, ExerciseEntry, Note, WeightEntry

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
    return timeutils.local_date_of(timezone.now(), timeutils.tz_for(alex))


def a_diet(user, day, name="porridge", hour=8):
    return DietEntry.objects.create(
        created_by=user,
        name=name,
        occurred_at=datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC),
        local_date=day,
    )


def at_local(user, day, hour, minute=0):
    return timeutils.utc_from_local_parts(day, time(hour, minute), timeutils.tz_for(user))


# -- the stored local_date --------------------------------------------------


def test_moving_the_time_across_midnight_refiles_the_day(alex, today):
    entry = a_diet(alex, today)
    yesterday = today - timedelta(days=1)
    moved_to = at_local(alex, yesterday, 21, 30)

    services.update_entry(alex, entry_type="diet", entry_id=entry.id, at=moved_to)

    entry.refresh_from_db()
    # Without this the row keeps yesterday's instant while still filed under
    # today, and drops out of both days' views.
    assert entry.local_date == yesterday
    assert entry.occurred_at == moved_to


def test_the_edited_entry_shows_up_on_the_day_it_moved_to(alex, today):
    entry = a_diet(alex, today)
    yesterday = today - timedelta(days=1)

    services.update_entry(
        alex, entry_type="diet", entry_id=entry.id, at=at_local(alex, yesterday, 21, 30)
    )

    assert [e["id"] for e in services.entries_for_day(alex, today)["entries"]] == []
    assert [e["id"] for e in services.entries_for_day(alex, yesterday)["entries"]] == [entry.id]


def test_editing_only_a_field_leaves_the_day_alone(alex, today):
    entry = a_diet(alex, today)

    services.update_entry(alex, entry_type="diet", entry_id=entry.id, fields={"name": "toast"})

    entry.refresh_from_db()
    assert entry.name == "toast"
    assert entry.local_date == today


# -- per-type fields --------------------------------------------------------


def test_a_bp_reading_can_be_corrected(alex, today):
    entry = BpEntry.objects.create(
        created_by=alex,
        systolic=180,
        diastolic=76,
        occurred_at=at_local(alex, today, 9),
        local_date=today,
    )

    services.update_entry(alex, entry_type="vitals_bp", entry_id=entry.id, fields={"systolic": 118})

    entry.refresh_from_db()
    assert (entry.systolic, entry.diastolic) == (118, 76)


def test_a_weight_can_be_corrected(alex, today):
    entry = WeightEntry.objects.create(
        created_by=alex,
        weight_kg=8.24,
        occurred_at=at_local(alex, today, 7),
        local_date=today,
    )

    services.update_entry(
        alex, entry_type="vitals_weight", entry_id=entry.id, fields={"weight_kg": 82.4}
    )

    entry.refresh_from_db()
    assert entry.weight_kg == pytest.approx(82.4)


def test_a_note_can_be_rewritten(alex, today):
    entry = Note.objects.create(
        created_by=alex,
        title="slept badly",
        content="up at 3",
        occurred_at=at_local(alex, today, 22),
        local_date=today,
    )

    services.update_entry(
        alex, entry_type="note", entry_id=entry.id, fields={"content": "up at 3 and again at 5"}
    )

    entry.refresh_from_db()
    assert entry.content == "up at 3 and again at 5"
    assert entry.title == "slept badly"


# -- validation -------------------------------------------------------------


def test_an_edit_cannot_smuggle_in_a_value_creation_would_refuse(alex, today):
    entry = BmEntry.objects.create(
        created_by=alex,
        bristol=4,
        occurred_at=at_local(alex, today, 9),
        local_date=today,
    )

    with pytest.raises(DomainError):
        services.update_entry(alex, entry_type="gut", entry_id=entry.id, fields={"bristol": 9})

    entry.refresh_from_db()
    assert entry.bristol == 4


def test_a_field_that_belongs_to_another_type_is_refused(alex, today):
    entry = a_diet(alex, today)

    with pytest.raises(DomainError):
        services.update_entry(alex, entry_type="diet", entry_id=entry.id, fields={"systolic": 120})


def test_a_datetime_only_type_takes_the_time_but_not_fields(alex, today):
    entry = ExerciseEntry.objects.create(
        created_by=alex,
        video_name="squats",
        duration_s=60,
        occurred_at=at_local(alex, today, 9),
        local_date=today,
    )
    moved = at_local(alex, today, 18)

    services.update_entry(alex, entry_type="exercise", entry_id=entry.id, at=moved)
    entry.refresh_from_db()
    assert entry.occurred_at == moved

    with pytest.raises(DomainError):
        services.update_entry(
            alex, entry_type="exercise", entry_id=entry.id, fields={"name": "lunges"}
        )


def test_a_grouped_gym_card_is_not_editable(alex, today):
    from apps.health.models import GymSet

    row = GymSet.objects.create(
        created_by=alex, exercise_name="Squat", local_date=today, weight_kg=80, reps=10
    )

    # One card stands for many sets, so there is no single row "edit" means.
    with pytest.raises(NotFound):
        services.update_entry(alex, entry_type="gym", entry_id=row.id, at=timezone.now())


# -- sync ordering ----------------------------------------------------------


def test_editing_a_phone_row_makes_the_portal_the_newest_write(alex, today):
    entry = a_diet(alex, today)
    entry.client_id = uuid.uuid4()
    entry.client_updated_at = timezone.now() - timedelta(days=1)
    entry.save()
    before = entry.client_updated_at

    services.update_entry(alex, entry_type="diet", entry_id=entry.id, fields={"name": "toast"})

    entry.refresh_from_db()
    # Otherwise a stale copy still queued on the phone wins the last-write
    # comparison in devicesync.merge and silently undoes this correction.
    assert entry.client_updated_at > before


def test_a_portal_only_row_gets_no_client_timestamp(alex, today):
    entry = a_diet(alex, today)

    services.update_entry(alex, entry_type="diet", entry_id=entry.id, fields={"name": "toast"})

    entry.refresh_from_db()
    assert entry.client_updated_at is None


# -- scoping ----------------------------------------------------------------


def test_editing_someone_elses_entry_is_a_404(alex, today):
    owner = User.objects.create_user(username="owner", password=PASSWORD)
    entry = a_diet(owner, today)

    with pytest.raises(NotFound):
        services.update_entry(alex, entry_type="diet", entry_id=entry.id, fields={"name": "x"})

    entry.refresh_from_db()
    assert entry.name == "porridge"


def test_a_tombstoned_entry_cannot_be_edited(alex, today):
    entry = a_diet(alex, today)
    entry.deleted_at = timezone.now()
    entry.save(update_fields=["deleted_at"])

    with pytest.raises(NotFound):
        services.update_entry(alex, entry_type="diet", entry_id=entry.id, fields={"name": "x"})


def test_the_endpoint_edits_and_reports_the_new_day(alex, client_for, today):
    entry = a_diet(alex, today)
    yesterday = today - timedelta(days=1)
    moved = at_local(alex, yesterday, 21, 30)

    response = client_for(alex).patch(
        f"/api/v1/health/entries/diet/{entry.id}",
        data={"at": moved.isoformat(), "name": "toast"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["local_date"] == yesterday.isoformat()
    entry.refresh_from_db()
    assert entry.name == "toast"


def test_anonymous_callers_are_refused(alex, today):
    entry = a_diet(alex, today)

    response = Client().patch(
        f"/api/v1/health/entries/diet/{entry.id}",
        data={"name": "toast"},
        content_type="application/json",
    )

    assert response.status_code in (401, 403)
