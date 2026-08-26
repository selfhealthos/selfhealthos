"""The gym page: tonnage over time and the per-exercise grid behind it.

The properties worth pinning are that a rest day is absent rather than a
zero (padding the gaps would imply sessions that never happened), that the
grid's cells stay aligned to the date columns they are drawn under, and that
bodyweight work - which carries no external load, so no tonnage - still
shows the sets it was actually made of.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.health import services
from apps.health.models import GymSet

User = get_user_model()
PASSWORD = "x" * 14


@pytest.fixture
def alex(db):
    return User.objects.create_user(username="alex", password=PASSWORD)


@pytest.fixture
def today(alex):
    from apps.health import timeutils

    return timeutils.local_date_of(timezone.now(), timeutils.tz_for(alex))


def a_set(user, day, name, weight, reps, hour=9):
    return GymSet.objects.create(
        created_by=user,
        exercise_name=name,
        local_date=day,
        performed_at=datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC),
        weight_kg=weight,
        reps=reps,
    )


def test_tonnage_is_weight_times_reps_summed_over_the_day(alex, today):
    a_set(alex, today, "Squat", 80, 10)
    a_set(alex, today, "Squat", 100, 5)

    log = services.gym_log(alex, days=30)

    assert log["total_kg"] == pytest.approx(1300.0)
    assert log["series"] == [{"date": today, "tonnage_kg": pytest.approx(1300.0)}]


def test_a_rest_day_is_absent_not_a_zero(alex, today):
    a_set(alex, today - timedelta(days=2), "Squat", 80, 10)
    a_set(alex, today, "Squat", 80, 10)

    log = services.gym_log(alex, days=30)

    # The day between them was not trained and must not appear at all - a
    # zero-tonnage bar claims a session that never happened.
    assert log["dates"] == [today, today - timedelta(days=2)]
    assert log["sessions"] == 2


def test_dates_are_newest_first_and_the_series_is_oldest_first(alex, today):
    for back in (0, 1, 2):
        a_set(alex, today - timedelta(days=back), "Squat", 80, 10)

    log = services.gym_log(alex, days=30)

    assert log["dates"] == [today, today - timedelta(days=1), today - timedelta(days=2)]
    assert [p["date"] for p in log["series"]] == list(reversed(log["dates"]))


def test_cells_line_up_with_the_date_columns(alex, today):
    yesterday = today - timedelta(days=1)
    a_set(alex, today, "Squat", 80, 10)
    a_set(alex, yesterday, "Bench", 60, 10)

    log = services.gym_log(alex, days=30)
    by_name = {e["name"]: e for e in log["exercises"]}

    # dates is [today, yesterday]; each row must be null in the column it did
    # not train, or the grid silently shifts a weight onto the wrong day.
    assert log["dates"] == [today, yesterday]
    assert [c["tonnage_kg"] for c in by_name["Squat"]["cells"]] == [800.0, None]
    assert [c["tonnage_kg"] for c in by_name["Bench"]["cells"]] == [None, 600.0]


def test_an_untrained_cell_carries_no_sets(alex, today):
    a_set(alex, today, "Squat", 80, 10)
    a_set(alex, today - timedelta(days=1), "Bench", 60, 10)

    log = services.gym_log(alex, days=30)
    squat = next(e for e in log["exercises"] if e["name"] == "Squat")

    assert squat["cells"][1]["sets"] == []


def test_bodyweight_work_keeps_its_sets_despite_zero_tonnage(alex, today):
    a_set(alex, today, "Press Ups", 0, 25)

    log = services.gym_log(alex, days=30)
    row = next(e for e in log["exercises"] if e["name"] == "Press Ups")

    assert row["cells"][0]["tonnage_kg"] == 0.0
    assert row["cells"][0]["sets"] == ["25 reps"]


def test_set_notation_is_compact_for_loaded_work(alex, today):
    a_set(alex, today, "Squat", 82.5, 8)

    log = services.gym_log(alex, days=30)
    row = next(e for e in log["exercises"] if e["name"] == "Squat")

    assert row["cells"][0]["sets"] == ["82.5x8"]


def test_exercises_are_ordered_by_how_much_work_they_carried(alex, today):
    a_set(alex, today, "Curl", 10, 10)
    a_set(alex, today, "Squat", 100, 10)
    a_set(alex, today, "Bench", 60, 10)

    log = services.gym_log(alex, days=30)

    assert [e["name"] for e in log["exercises"]] == ["Squat", "Bench", "Curl"]


def test_sets_outside_the_window_are_excluded(alex, today):
    a_set(alex, today - timedelta(days=40), "Squat", 80, 10)

    log = services.gym_log(alex, days=30)

    assert log["dates"] == []
    assert log["total_kg"] == 0.0
    assert log["exercises"] == []


def test_a_tombstoned_set_stops_counting(alex, today):
    kept = a_set(alex, today, "Squat", 80, 10)
    gone = a_set(alex, today, "Squat", 80, 10)
    gone.deleted_at = timezone.now()
    gone.save(update_fields=["deleted_at"])

    log = services.gym_log(alex, days=30)
    row = next(e for e in log["exercises"] if e["name"] == "Squat")

    assert log["total_kg"] == pytest.approx(kept.volume_kg)
    assert row["cells"][0]["sets"] == ["80x10"]


def test_the_endpoint_is_scoped_to_the_caller(alex, today):
    sam = User.objects.create_user(username="sam", password=PASSWORD)
    a_set(sam, today, "Squat", 80, 10)

    client = Client()
    client.force_login(alex)
    response = client.get("/api/v1/health/gym?days=30")

    assert response.status_code == 200
    assert response.json()["exercises"] == []


def test_anonymous_callers_are_refused(alex, db):
    response = Client().get("/api/v1/health/gym?days=30")

    assert response.status_code in (401, 403)
