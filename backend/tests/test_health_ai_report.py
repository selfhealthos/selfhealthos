"""The AI prompt report: a markdown export meant to be pasted into a
third-party chatbot.

The property worth pinning is what shows up versus what silently doesn't -
a blank medications field must never render as "Medications: " (which reads
as "confirmed none" rather than "never filled in"), and a section with
nothing to say must not render an empty heading.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.health.models import (
    DailyMetric,
    DietEntry,
    ExerciseEntry,
    GymSet,
    Habit,
    HabitCompletion,
    LabResult,
    Profile,
)

User = get_user_model()
PASSWORD = "x" * 14
ENDPOINT = "/api/v1/health/ai-report"


@pytest.fixture
def alex(db):
    return User.objects.create_user(
        username="alex", password=PASSWORD, birth_date=date(1985, 6, 1), sex="male"
    )


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make


def _metric(user, on: date, metric: str, value: float) -> None:
    DailyMetric.objects.create(
        user=user, local_date=on, metric=metric, value=value, source=DailyMetric.Source.DEVICE
    )


def _at(on: date, hour: int = 8):
    return datetime(on.year, on.month, on.day, hour, tzinfo=UTC)


def test_the_intro_states_name_age_and_sex(alex, client_for):
    response = client_for(alex).get(ENDPOINT)

    assert response.status_code == 200
    markdown = response.json()["markdown"]
    assert "My name is alex." in markdown
    assert "year old male" in markdown


def test_a_blank_medical_field_is_omitted_not_shown_empty(alex, client_for):
    Profile.objects.create(user=alex, medications="", supplements="Vitamin D")

    response = client_for(alex).get(ENDPOINT)

    markdown = response.json()["markdown"]
    assert "Medications" not in markdown
    assert "Supplements: Vitamin D" in markdown


def test_profile_goals_appear_in_the_intro(alex, client_for):
    Profile.objects.create(user=alex, goals="Lose 5kg and sleep better")

    response = client_for(alex).get(ENDPOINT)

    assert "Lose 5kg and sleep better" in response.json()["markdown"]


def test_a_metric_with_data_shows_mean_min_and_max(alex, client_for):
    today = date.today()
    _metric(alex, today - timedelta(days=5), "steps", 8000)
    _metric(alex, today - timedelta(days=4), "steps", 12000)

    response = client_for(alex).get(f"{ENDPOINT}?days=30")

    markdown = response.json()["markdown"]
    assert "## Daily metrics" in markdown
    assert "| Steps | 10,000 count | 8,000 count | 12,000 count | 2 |" in markdown


def test_a_metric_with_no_data_in_the_window_is_absent(alex, client_for):
    response = client_for(alex).get(f"{ENDPOINT}?days=30")

    assert "## Daily metrics" not in response.json()["markdown"]


def test_recent_diet_entries_are_listed_newest_first(alex, client_for):
    today = date.today()
    older, newer = today - timedelta(days=10), today - timedelta(days=2)
    DietEntry.objects.create(
        created_by=alex, name="Porridge", occurred_at=_at(older), local_date=older
    )
    DietEntry.objects.create(
        created_by=alex, name="Salad", occurred_at=_at(newer), local_date=newer
    )

    response = client_for(alex).get(f"{ENDPOINT}?days=30")

    markdown = response.json()["markdown"]
    assert markdown.index("Salad") < markdown.index("Porridge")


def test_recent_workouts_show_duration_in_minutes(alex, client_for):
    on = date.today() - timedelta(days=3)
    ExerciseEntry.objects.create(
        created_by=alex,
        video_name="Push-Up Challenge",
        duration_s=600,
        occurred_at=_at(on),
        local_date=on,
    )

    response = client_for(alex).get(f"{ENDPOINT}?days=30")

    assert "Push-Up Challenge (10 min)" in response.json()["markdown"]


def test_recent_gym_sets_show_weight_and_reps(alex, client_for):
    on = date.today() - timedelta(days=3)
    GymSet.objects.create(
        created_by=alex, exercise_name="Bench press", local_date=on, weight_kg=60, reps=8
    )

    response = client_for(alex).get(f"{ENDPOINT}?days=30")

    assert "Bench press — 60 kg x 8" in response.json()["markdown"]


def test_lab_results_show_the_most_recent_value_per_marker(alex, client_for):
    LabResult.objects.create(
        created_by=alex, marker_name="Ferritin", value=80, unit="ug/L", taken_on=date(2026, 1, 1)
    )
    LabResult.objects.create(
        created_by=alex, marker_name="Ferritin", value=95, unit="ug/L", taken_on=date(2026, 6, 1)
    )

    response = client_for(alex).get(ENDPOINT)

    markdown = response.json()["markdown"]
    assert "**Ferritin**: 95 ug/L (taken 2026-06-01)" in markdown
    assert "80 ug/L" not in markdown


def test_habit_streaks_are_reported(alex, client_for):
    habit = Habit.objects.create(created_by=alex, name="Magnesium")
    today = date.today()
    for offset in range(3):
        on = today - timedelta(days=offset)
        HabitCompletion.objects.create(
            created_by=alex,
            habit=habit,
            habit_name="Magnesium",
            local_date=on,
            completed_at=_at(on),
        )

    response = client_for(alex).get(ENDPOINT)

    assert "**Magnesium**: 3-day current streak" in response.json()["markdown"]


def test_a_user_with_nothing_tracked_still_gets_an_intro_and_closing(alex, client_for):
    response = client_for(alex).get(ENDPOINT)

    assert response.status_code == 200
    markdown = response.json()["markdown"]
    assert markdown.startswith("# My health data")
    assert "What I'd like from you" in markdown


def test_anonymous_callers_are_refused(db):
    response = Client().get(ENDPOINT)
    assert response.status_code in (401, 403)
