"""Habit streaks, rates and the completion calendar.

Ported alongside the logic from the one-data dashboard. The failures worth
pinning are all arithmetic that looks plausible when wrong: a streak that
resets at midnight, a rate over 100%, a calendar row misaligned with its dates.
None of them raise.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.health import habits as habit_analytics
from apps.health.models import Habit, HabitCompletion

User = get_user_model()
PASSWORD = "x" * 14
TODAY = date(2026, 8, 10)


@pytest.fixture
def owner(db):
    # Non-UTC, so a local day is not a UTC day and the difference shows in
    # calendar-window assertions below.
    return User.objects.create_user(
        username="habits", password=PASSWORD, timezone="Australia/Melbourne"
    )


@pytest.fixture
def make():
    def _make(user, name: str, *offsets: int, sort_order: int = 0) -> Habit:
        """A habit ticked `offsets` days before TODAY."""
        habit = Habit.objects.create(created_by=user, name=name, sort_order=sort_order)
        for offset in offsets:
            HabitCompletion.objects.create(
                created_by=user,
                habit=habit,
                habit_name=name,
                local_date=TODAY - timedelta(days=offset),
            )
        return habit

    return _make


def only(user, **kw) -> dict:
    return habit_analytics.overview(user, today=TODAY, **kw)["habits"][0]


class TestStreaks:
    def test_a_run_ending_today(self, owner, make):
        make(owner, "Creatine", 0, 1, 2, 3)
        row = only(owner)
        assert row["current_streak"] == 4
        assert row["best_streak"] == 4

    def test_a_run_ending_yesterday_still_counts(self, owner, make):
        """Anchoring only on today reports zero all morning, before anything
        has been ticked, which is wrong every single day until it isn't."""
        make(owner, "Creatine", 1, 2, 3)
        assert only(owner)["current_streak"] == 3

    def test_a_run_that_ended_two_days_ago_is_over(self, owner, make):
        make(owner, "Creatine", 2, 3, 4)
        row = only(owner)
        assert row["current_streak"] == 0
        assert row["best_streak"] == 3

    def test_best_is_the_longest_run_anywhere_in_history(self, owner, make):
        make(owner, "Creatine", 0, 20, 21, 22, 23, 24)
        row = only(owner)
        assert row["current_streak"] == 1
        assert row["best_streak"] == 5

    def test_best_is_never_less_than_current(self, owner, make):
        make(owner, "Creatine", 0, 1)
        row = only(owner)
        assert row["best_streak"] >= row["current_streak"]

    def test_a_streak_can_reach_back_beyond_the_calendar_window(self, owner, make):
        """The grid shows 30 days; a 40-day streak is still 40 days."""
        make(owner, "Creatine", *range(40))
        assert only(owner, days=30)["current_streak"] == 40

    def test_never_ticked(self, owner, make):
        make(owner, "Creatine")
        row = only(owner)
        assert (row["current_streak"], row["best_streak"], row["total"]) == (0, 0, 0)


class TestRates:
    def test_a_full_month(self, owner, make):
        make(owner, "Creatine", *range(30))
        row = only(owner)
        assert row["rate_7"] == 100
        assert row["rate_30"] == 100

    def test_twice_in_a_day_is_still_one_day(self, owner, make):
        """A second dose must not push the rate over 100%."""
        habit = make(owner, "Creatine", *range(30))
        for offset in range(30):
            HabitCompletion.objects.create(
                created_by=owner,
                habit=habit,
                habit_name="Creatine",
                local_date=TODAY - timedelta(days=offset),
            )

        row = only(owner)
        assert row["rate_30"] == 100
        assert row["total"] == 30

    def test_below_half_is_flagged(self, owner, make):
        make(owner, "Sauna", 0, 1, 2)
        row = only(owner)
        assert row["rate_30"] == 10
        assert row["at_risk"] is True

    def test_a_good_month_is_not_flagged(self, owner, make):
        make(owner, "Sauna", *range(25))
        assert only(owner)["at_risk"] is False

    def test_older_ticks_do_not_count_toward_the_window(self, owner, make):
        make(owner, "Sauna", 40, 41, 42)
        row = only(owner)
        assert row["rate_30"] == 0
        assert row["total"] == 3


class TestCalendar:
    def test_the_row_aligns_with_the_dates(self, owner, make):
        """A misaligned row silently attributes a tick to the wrong day."""
        make(owner, "Gym", 0, 5)
        data = habit_analytics.overview(owner, days=10, today=TODAY)

        dates = data["dates"]
        days = data["habits"][0]["days"]
        assert len(dates) == len(days) == 10
        assert dates[-1] == TODAY
        assert dates[0] == TODAY - timedelta(days=9)

        ticked = {d for d, done in zip(dates, days, strict=True) if done}
        assert ticked == {TODAY, TODAY - timedelta(days=5)}

    def test_window_width_is_clamped_by_the_endpoint(self, owner, make, client_for):
        """`days` arrives from a query string a person can edit."""
        make(owner, "Gym", 0)
        body = client_for(owner).get("/api/v1/health/habits?days=100000").json()
        assert len(body["dates"]) == 365


class TestScoping:
    def test_another_persons_habits_are_not_listed(self, owner, make, db):
        make(owner, "Mine", 0)
        other = User.objects.create_user(username="other2", password=PASSWORD)
        make(other, "Theirs", 0)

        names = {row["name"] for row in habit_analytics.overview(owner, today=TODAY)["habits"]}
        assert names == {"Mine"}

    def test_a_deleted_completion_stops_counting(self, owner, make):
        habit = make(owner, "Creatine", 0, 1, 2)
        HabitCompletion.objects.filter(habit=habit, local_date=TODAY).update(
            deleted_at="2026-08-10T00:00:00Z"
        )

        row = only(owner)
        assert row["total"] == 2
        assert row["current_streak"] == 2  # anchored on yesterday

    def test_an_archived_habit_drops_off_the_page(self, owner, make):
        habit = make(owner, "Old thing", 0)
        habit.archived_at = "2026-08-01T00:00:00Z"
        habit.save(update_fields=["archived_at"])

        assert habit_analytics.overview(owner, today=TODAY)["habits"] == []

    def test_a_completion_with_no_link_still_counts_by_name(self, owner):
        """Completions can arrive before the habit that explains them."""
        HabitCompletion.objects.create(
            created_by=owner, habit=None, habit_name="Sauna", local_date=TODAY
        )
        Habit.objects.create(created_by=owner, name="Sauna")

        assert only(owner)["current_streak"] == 1


@pytest.mark.django_db
def test_the_endpoint_returns_the_page_in_one_call(owner, make, client_for):
    make(owner, "Creatine", 0, 1)
    make(owner, "Sauna", 3, sort_order=1)

    body = client_for(owner).get("/api/v1/health/habits?days=14").json()

    assert len(body["dates"]) == 14
    assert [h["name"] for h in body["habits"]] == ["Creatine", "Sauna"]
    assert all(len(h["completed"]) == 14 for h in body["habits"])


@pytest.mark.django_db
def test_anonymous_callers_are_refused(db):
    from django.test import Client

    assert Client().get("/api/v1/health/habits").status_code == 401
