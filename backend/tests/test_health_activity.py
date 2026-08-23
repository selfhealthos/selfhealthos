"""The activity page's two resolutions.

The failures pinned here are the ones that still draw a convincing picture.
A trailing mean over two recorded days still plots a line and still calls
itself a week. Sedentary minutes printed without the night subtracted still
render as a plausible number of hours. A summed intensity column that reads a
missing day as zero still colours the cell - red, on a day nobody measured.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone as dj_timezone

from apps.health import activity, timeutils
from apps.health.models import DailyMetric, Sample, SleepSession

User = get_user_model()
PASSWORD = "x" * 14
DAY = date(2026, 8, 12)


def local_today(user) -> date:
    """The window `history()` ends on - see the same helper in the heart tests."""
    return timeutils.local_date_of(dj_timezone.now(), timeutils.tz_for(user))


@pytest.fixture
def owner(db):
    # Non-UTC, so a local day is not a UTC day and the difference shows in
    # every day-boundary assertion below.
    return User.objects.create_user(
        username="activity", password=PASSWORD, timezone="Australia/Melbourne"
    )


def daily(user, on: date, **values) -> None:
    for metric, value in values.items():
        DailyMetric.objects.update_or_create(
            user=user,
            local_date=on,
            metric=metric,
            defaults={"value": float(value), "source": DailyMetric.Source.DEVICE},
        )


def cells(row) -> dict:
    return {cell["key"]: cell for cell in row["cells"]}


# -- the day view -----------------------------------------------------------


def test_the_climb_is_cumulative_and_bounded_by_the_local_day(owner):
    """Melbourne is UTC+10, so a UTC-day query would take the climb from 10am
    to 10am and hand the page two half-days stitched together."""
    # 23:30 local on the 11th, then 00:30 and 01:30 local on the 12th.
    for at, value in (
        (datetime(2026, 8, 11, 13, 30, tzinfo=UTC), 500),
        (datetime(2026, 8, 11, 14, 30, tzinfo=UTC), 300),
        (datetime(2026, 8, 11, 15, 30, tzinfo=UTC), 200),
    ):
        Sample.objects.create(user=owner, metric="steps", ts=at, value=value)

    day = activity.day(owner, DAY)

    assert day["count"] == 2
    # Cumulative, not per-minute: 300 then 300+200. The 500 belongs to the
    # 11th and must not seed the 12th's total.
    assert [point["value"] for point in day["points"]] == [300, 500]


def test_the_climb_carries_a_point_only_where_it_bends(owner):
    """A cumulative line is collinear through every zero minute, so ~900
    minutes of a normal day are filler. Dropping them has to be lossless."""
    base = datetime(2026, 8, 11, 22, 0, tzinfo=UTC)  # 08:00 local on the 12th
    for offset in range(10):
        Sample.objects.create(
            user=owner,
            metric="steps",
            ts=base + timedelta(minutes=offset),
            # Steps in three of the ten minutes.
            value=100 if offset in (2, 5, 9) else 0,
        )

    points = activity.day(owner, DAY)["points"]

    # Three bends, plus an anchor at the first sampled minute so the line does
    # not begin mid-morning on a full-day axis.
    assert [point["value"] for point in points] == [0, 100, 200, 300]
    assert points[0]["at"] == base


def test_the_goal_crossing_is_the_minute_it_happened(owner):
    base = datetime(2026, 8, 11, 22, 0, tzinfo=UTC)
    for offset in range(4):
        Sample.objects.create(
            user=owner, metric="steps", ts=base + timedelta(minutes=offset), value=3_000
        )

    day = activity.day(owner, DAY)

    # 3k, 6k, 9k, 12k - the fourth minute is the one that crosses 10,000.
    assert day["goal_reached_at"] == base + timedelta(minutes=3)


def test_a_day_that_never_reaches_the_goal_says_so_rather_than_guessing(owner):
    Sample.objects.create(
        user=owner, metric="steps", ts=datetime(2026, 8, 11, 22, 0, tzinfo=UTC), value=900
    )

    assert activity.day(owner, DAY)["goal_reached_at"] is None


def test_the_hours_include_the_empty_ones(owner):
    """A bar chart of only the hours that had steps is a chart with no night."""
    Sample.objects.create(
        user=owner, metric="steps", ts=datetime(2026, 8, 11, 22, 0, tzinfo=UTC), value=900
    )

    hours = activity.day(owner, DAY)["hours"]

    assert len(hours) == 24
    assert hours[8]["steps"] == 900  # 22:00 UTC is 08:00 in Melbourne
    assert hours[3]["steps"] == 0


def test_the_daily_rollup_wins_over_the_sum_of_the_minutes(owner):
    """They disagree by a few steps and the rollup is the device's own figure.
    The page must not show a total that contradicts the heatmap."""
    Sample.objects.create(
        user=owner, metric="steps", ts=datetime(2026, 8, 11, 22, 0, tzinfo=UTC), value=9_990
    )
    daily(owner, DAY, steps=10_002)

    assert activity.day(owner, DAY)["total"] == 10_002


def test_a_day_with_minute_data_and_no_rollup_still_has_a_total(owner):
    Sample.objects.create(
        user=owner, metric="steps", ts=datetime(2026, 8, 11, 22, 0, tzinfo=UTC), value=9_990
    )

    assert activity.day(owner, DAY)["total"] == 9_990


def test_the_night_is_shaded_so_the_flat_stretch_is_explained(owner):
    SleepSession.objects.create(
        user=owner,
        external_id="a",
        local_date=DAY,
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 8, 11, 20, 0, tzinfo=UTC),
        duration_minutes=450,
        is_main_sleep=True,
    )

    day = activity.day(owner, DAY)

    assert len(day["sleep"]) == 1
    assert day["sleep"][0]["started_at"] == day["start"]


# -- the window view --------------------------------------------------------


def test_a_bar_is_coloured_by_intensity_not_by_its_own_height(owner):
    """The whole point of the master chart: 15,000 steps with eight active
    minutes and 15,000 with fifty-five were an identical mark before."""
    today = local_today(owner)
    daily(owner, today, steps=15_000, fairly_active_minutes=1, very_active_minutes=1)
    daily(
        owner,
        today - timedelta(days=1),
        steps=15_000,
        fairly_active_minutes=25,
        very_active_minutes=30,
    )

    bars = {bar["date"]: bar for bar in activity.history(owner, days=7)["bars"]}

    assert bars[today]["steps"] == bars[today - timedelta(days=1)]["steps"]
    assert bars[today]["band"] == 1
    assert bars[today - timedelta(days=1)]["band"] == 5


def test_a_day_with_steps_and_no_intensity_is_uncoloured_not_a_rest_day(owner):
    """Absent is not zero. Summing nothing to 0.0 paints the bar the colour of
    a day spent sitting, on a day the buckets simply were not reported."""
    today = local_today(owner)
    daily(owner, today, steps=12_000)

    bar = activity.history(owner, days=7)["bars"][0]

    assert bar["active_minutes"] is None
    assert bar["band"] is None


def test_the_trailing_mean_needs_enough_recorded_days_to_be_a_week(owner):
    """A 'weekly average' standing on two days is not one. The gap it leaves
    says so more honestly than a line drawn through it would."""
    today = local_today(owner)
    daily(owner, today, steps=10_000)
    daily(owner, today - timedelta(days=1), steps=10_000)

    trailing = activity.history(owner, days=7)["trailing"]

    assert trailing == []


def test_the_trailing_mean_divides_by_recorded_days_not_by_seven(owner):
    """Dividing by seven turns a week the watch was off into a collapse in
    activity that never happened."""
    today = local_today(owner)
    for offset in range(5):
        daily(owner, today - timedelta(days=offset), steps=10_000)

    trailing = {
        point["date"]: point["value"] for point in activity.history(owner, days=7)["trailing"]
    }

    assert trailing[today] == 10_000


def test_the_trailing_mean_reaches_back_before_the_window(owner):
    """Otherwise the first week of every chart climbs out of nothing."""
    today = local_today(owner)
    for offset in range(10):
        daily(owner, today - timedelta(days=offset), steps=8_000)

    # A three-day window, whose first day still has six earlier days behind it.
    trailing = activity.history(owner, days=3)["trailing"]

    assert len(trailing) == 3
    assert all(point["value"] == 8_000 for point in trailing)


def test_sitting_has_the_night_subtracted(owner):
    """Fitbit counts sleep as sedentary, so the raw figure runs past 18 h.
    Printed as 'sitting' it is a number that would be quoted wrongly forever.
    """
    today = local_today(owner)
    daily(owner, today, steps=9_000, sedentary_minutes=1_080, sleep_minutes=480)

    row = activity.history(owner, days=7)["rows"][0]

    assert cells(row)["awake_sedentary"]["value"] == pytest.approx(10.0)


def test_sitting_is_blank_without_a_night_to_subtract(owner):
    """A sedentary total with no sleep session is off by a whole night, and
    printing it anyway shows eighteen hours of sitting on a day that had ten."""
    today = local_today(owner)
    daily(owner, today, steps=9_000, sedentary_minutes=1_080)

    assert cells(activity.history(owner, days=7)["rows"][0])["awake_sedentary"]["value"] is None


def test_sitting_is_never_negative(owner):
    """The two figures come from different endpoints and a nap counted in both
    can push the subtraction below zero. A negative hour is noise."""
    today = local_today(owner)
    daily(owner, today, steps=9_000, sedentary_minutes=400, sleep_minutes=480)

    assert cells(activity.history(owner, days=7)["rows"][0])["awake_sedentary"]["value"] == 0.0


def test_a_missing_intensity_cell_is_blank_rather_than_zero(owner):
    """Red on a day the watch was on the charger is the failure this prevents."""
    today = local_today(owner)
    daily(owner, today, steps=9_000)

    cell = cells(activity.history(owner, days=7)["rows"][0])["active_minutes"]

    assert cell["value"] is None
    assert cell["band"] is None


def test_a_day_holding_only_a_resting_heart_rate_is_not_an_activity_day(owner):
    """Otherwise the table fills with blank rows on every day the watch was
    worn asleep and taken off after breakfast."""
    today = local_today(owner)
    daily(owner, today, resting_hr=58)
    daily(owner, today - timedelta(days=1), steps=9_000)

    dates = [row["date"] for row in activity.history(owner, days=7)["rows"]]

    assert dates == [today - timedelta(days=1)]


def test_floors_and_active_zone_minutes_are_not_columns(owner):
    """Both are traps rather than measurements here: floors is a literal zero
    on every row, and active zone minutes cannot tell 'did nothing' from 'no
    data'."""
    keys = {column["key"] for column in activity.history(owner, days=7)["columns"]}

    assert "floors" not in keys
    assert "active_zone_minutes" not in keys


def test_every_average_states_how_many_days_it_is_over(owner):
    """A mean over the window rather than over the recorded days would report
    every unworn week as a week of not moving."""
    today = local_today(owner)
    daily(owner, today, steps=12_000, fairly_active_minutes=10, very_active_minutes=20)
    daily(owner, today - timedelta(days=1), steps=8_000)

    summary = activity.history(owner, days=30)["summary"]

    assert summary["days_elapsed"] == 30
    assert summary["days_recorded"] == 2
    assert summary["mean_steps"] == 10_000
    # Only one of the two days reported intensity, and the mean says so.
    assert summary["active_days"] == 1
    assert summary["mean_active_minutes"] == 30


def test_the_intensity_average_is_stated_per_week(owner):
    """90 minutes is excellent over seven days and poor over ninety. The
    recommendation is weekly; the window is not."""
    today = local_today(owner)
    for offset in range(10):
        daily(
            owner,
            today - timedelta(days=offset),
            steps=9_000,
            zone_cardio_minutes=4,
            zone_peak_minutes=1,
        )

    summary = activity.history(owner, days=90)["summary"]

    assert summary["vigorous_per_week"] == 35
