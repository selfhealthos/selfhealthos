"""Seasons: every metric averaged by the season its day fell in.

The property worth pinning is the month-to-season mapping itself. This
deployment defaults to `Australia/Melbourne` (see `timeutils.DEFAULT_TZ`), so
the seasons are Southern Hemisphere - December is summer, not winter. Getting
that backwards doesn't crash or 500; every card on the report still renders,
with two seasons silently swapped. That's exactly the shape of bug
`one-data/CLAUDE.md` already documents once for `wfh.ndjson` (see
`OfficeDay`), so it's worth a direct assertion here rather than trusting the
comment on `_SEASON_BY_MONTH`.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.health.models import DailyMetric

User = get_user_model()
PASSWORD = "x" * 14
ENDPOINT = "/api/v1/health/seasons/report"


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


def _metric(user, on: date, metric: str, value: float) -> None:
    DailyMetric.objects.create(
        user=user, local_date=on, metric=metric, value=value, source=DailyMetric.Source.DEVICE
    )


def test_december_and_february_are_both_summer(alex, client_for):
    """The Southern Hemisphere summer spans a calendar year boundary - a
    mapping keyed on "is this the start or end of the year" rather than the
    literal month would split it in two.
    """
    _metric(alex, date(2025, 12, 15), "steps", 8000)
    _metric(alex, date(2026, 2, 10), "steps", 10000)
    _metric(alex, date(2026, 6, 1), "steps", 4000)

    response = client_for(alex).get(ENDPOINT)

    assert response.status_code == 200
    steps = next(m for m in response.json()["metrics"] if m["metric"] == "steps")
    assert steps["summer"] == 9000
    assert steps["summer_days"] == 2
    assert steps["winter"] == 4000


#: A fixed past year, not `date.today()`-relative: the four representative
#: days need to land on opposite sides of "today" as little as possible, and
#: a day in the future of whenever this test happens to run would fall
#: outside `season_report`'s window and silently vanish from the bucket
#: instead of failing loudly - see the `StopIteration` this caught once.
YEAR = 2020


@pytest.mark.parametrize(
    "on,season",
    [
        (date(YEAR, 1, 15), "summer"),
        (date(YEAR, 4, 15), "autumn"),
        (date(YEAR, 7, 15), "winter"),
        (date(YEAR, 10, 15), "spring"),
    ],
)
def test_a_representative_day_from_each_season_lands_in_its_own_bucket(
    alex, client_for, on, season
):
    _metric(alex, on, "resting_hr", 60)
    other_season_day = {
        "summer": date(YEAR, 7, 15),
        "autumn": date(YEAR, 1, 15),
        "winter": date(YEAR, 4, 15),
        "spring": date(YEAR, 1, 15),
    }[season]
    _metric(alex, other_season_day, "resting_hr", 70)

    response = client_for(alex).get(ENDPOINT)

    assert response.status_code == 200
    resting_hr = next(m for m in response.json()["metrics"] if m["metric"] == "resting_hr")
    assert resting_hr[season] == 60
    assert resting_hr[f"{season}_days"] == 1


def test_season_report_skips_metrics_with_only_one_bucket(alex, client_for):
    _metric(alex, date(2026, 1, 5), "resting_hr", 60)
    _metric(alex, date(2026, 1, 20), "resting_hr", 62)

    response = client_for(alex).get(ENDPOINT)

    assert response.status_code == 200
    keys = [m["metric"] for m in response.json()["metrics"]]
    assert "resting_hr" not in keys


def test_a_lower_is_better_metric_gets_a_down_direction(alex, client_for):
    _metric(alex, date(2026, 1, 10), "resting_hr", 60)
    _metric(alex, date(2026, 7, 10), "resting_hr", 65)

    response = client_for(alex).get(ENDPOINT)

    resting_hr = next(m for m in response.json()["metrics"] if m["metric"] == "resting_hr")
    assert resting_hr["direction"] == "down"


def test_a_metric_with_no_established_direction_is_unranked(alex, client_for):
    _metric(alex, date(2026, 1, 10), "sleep_minutes", 400)
    _metric(alex, date(2026, 7, 10), "sleep_minutes", 420)

    response = client_for(alex).get(ENDPOINT)

    metric = next(m for m in response.json()["metrics"] if m["metric"] == "sleep_minutes")
    assert metric["direction"] is None


def test_an_empty_window_is_an_empty_metrics_list(alex, client_for):
    response = client_for(alex).get(f"{ENDPOINT}?days=7")

    assert response.status_code == 200
    assert response.json()["metrics"] == []


def test_anonymous_callers_are_refused(db):
    response = Client().get(ENDPOINT)
    assert response.status_code in (401, 403)
