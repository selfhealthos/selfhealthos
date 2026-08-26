"""Deleting one row from the entries timeline.

The property worth pinning is that this is a tombstone, not a removal - see
the root CLAUDE.md's devicesync-merge-semantics trap - and that it is scoped
to the caller: naming another account's id must not delete it, and must not
tell the caller whether it existed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.health import rollups
from apps.health.models import DailyMetric, DietEntry

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


def _diet_entry(user, on: date, name: str = "Porridge") -> DietEntry:
    return DietEntry.objects.create(
        created_by=user,
        name=name,
        occurred_at=datetime(on.year, on.month, on.day, 8, tzinfo=UTC),
        local_date=on,
    )


def test_deleting_an_entry_tombstones_it(alex, client_for):
    entry = _diet_entry(alex, date.today())

    response = client_for(alex).delete(f"/api/v1/health/entries/diet/{entry.id}")

    assert response.status_code == 200
    assert response.json() == {"id": str(entry.id), "deleted": True}
    entry.refresh_from_db()
    assert entry.deleted_at is not None


def test_a_deleted_entry_disappears_from_the_timeline(alex, client_for):
    today = date.today()
    entry = _diet_entry(alex, today)

    client_for(alex).delete(f"/api/v1/health/entries/diet/{entry.id}")
    response = client_for(alex).get(f"/api/v1/health/entries?on={today.isoformat()}")

    assert response.json()["entries"] == []


def test_deleting_the_only_entry_for_a_day_clears_its_rollup(alex, client_for):
    today = date.today()
    entry = _diet_entry(alex, today)
    rollups.rebuild(alex, today, today)
    assert DailyMetric.objects.filter(user=alex, local_date=today, metric="diet_entries").exists()

    client_for(alex).delete(f"/api/v1/health/entries/diet/{entry.id}")

    assert not DailyMetric.objects.filter(
        user=alex, local_date=today, metric="diet_entries"
    ).exists()


def test_deleting_twice_is_a_404_the_second_time(alex, client_for):
    entry = _diet_entry(alex, date.today())
    client = client_for(alex)

    first = client.delete(f"/api/v1/health/entries/diet/{entry.id}")
    second = client.delete(f"/api/v1/health/entries/diet/{entry.id}")

    assert first.status_code == 200
    assert second.status_code == 404


def test_an_unknown_entry_type_is_a_404(alex, client_for):
    entry = _diet_entry(alex, date.today())

    response = client_for(alex).delete(f"/api/v1/health/entries/moonphase/{entry.id}")

    assert response.status_code == 404
    entry.refresh_from_db()
    assert entry.deleted_at is None


def test_a_random_id_is_a_404_not_a_500(alex, client_for):
    response = client_for(alex).delete(f"/api/v1/health/entries/diet/{uuid.uuid4()}")

    assert response.status_code == 404


def test_deleting_someone_elses_entry_is_a_404(alex, client_for):
    owner = User.objects.create_user(username="owner", password=PASSWORD)
    entry = _diet_entry(owner, date.today())

    response = client_for(alex).delete(f"/api/v1/health/entries/diet/{entry.id}")

    assert response.status_code == 404
    entry.refresh_from_db()
    assert entry.deleted_at is None


def test_anonymous_callers_are_refused(alex, db):
    entry = _diet_entry(alex, date.today())

    response = Client().delete(f"/api/v1/health/entries/diet/{entry.id}")

    assert response.status_code in (401, 403)


# -- gym --------------------------------------------------------------------


def _gym_set(user, day: date, name: str, weight: float, reps: int):
    from apps.health.models import GymSet

    return GymSet.objects.create(
        created_by=user,
        exercise_name=name,
        local_date=day,
        performed_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC),
        weight_kg=weight,
        reps=reps,
    )


def test_deleting_a_gym_card_tombstones_the_whole_exercise(alex, client_for):
    day = date.today()
    first, second, third = (
        _gym_set(alex, day, "Squat", 80, 10),
        _gym_set(alex, day, "Squat", 85, 10),
        _gym_set(alex, day, "Squat", 90, 8),
    )

    # The card's id is only its first set's - see services.entries_for_day.
    response = client_for(alex).delete(f"/api/v1/health/entries/gym/{first.id}")

    assert response.status_code == 200
    for entry in (first, second, third):
        entry.refresh_from_db()
        assert entry.deleted_at is not None, "a set was left behind by the card's delete"


def test_deleting_one_exercise_leaves_the_others_alone(alex, client_for):
    day = date.today()
    squat = _gym_set(alex, day, "Squat", 80, 10)
    chins = _gym_set(alex, day, "Chin Ups", 70, 8)

    client_for(alex).delete(f"/api/v1/health/entries/gym/{squat.id}")

    chins.refresh_from_db()
    assert chins.deleted_at is None


def test_deleting_a_gym_card_leaves_the_same_exercise_on_other_days(alex, client_for):
    today, yesterday = date.today(), date.today() - timedelta(days=1)
    todays = _gym_set(alex, today, "Squat", 80, 10)
    yesterdays = _gym_set(alex, yesterday, "Squat", 75, 10)

    client_for(alex).delete(f"/api/v1/health/entries/gym/{todays.id}")

    yesterdays.refresh_from_db()
    assert yesterdays.deleted_at is None
