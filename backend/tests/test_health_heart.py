"""The heart page's two resolutions.

The failures pinned here are the quiet ones. A zone band that shades the wrong
range still looks like a chart. A baseline computed from the same seven points
the line is drawn from still draws a band, and the band still moves. A summed
column that reads a missing day as zero still colours the cell - red, on a day
the watch was on the charger.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone as dj_timezone

from apps.health import heart, rollups, timeutils
from apps.health.models import DailyMetric, Sample, SleepSession

User = get_user_model()
PASSWORD = "x" * 14
DAY = date(2026, 8, 12)


def local_today(user) -> date:
    """The window `history()` ends on.

    It ends at the subject's today rather than at the newest stored row, so the
    tests below seed relative to it. Anchoring them to a fixed date instead
    would make every window assertion depend on how far in the past that date
    had drifted.
    """
    return timeutils.local_date_of(dj_timezone.now(), timeutils.tz_for(user))


@pytest.fixture
def owner(db):
    # Non-UTC, so a local day is not a UTC day here and the difference shows.
    return User.objects.create_user(
        username="heart", password=PASSWORD, timezone="Australia/Melbourne"
    )


def daily(user, on: date, **values) -> None:
    for metric, value in values.items():
        DailyMetric.objects.update_or_create(
            user=user,
            local_date=on,
            metric=metric,
            defaults={"value": float(value), "source": DailyMetric.Source.DEVICE},
        )


ZONE_EDGES = {
    "zone_fat_burn_floor_bpm": 97,
    "zone_cardio_floor_bpm": 136,
    "zone_peak_floor_bpm": 166,
    "zone_peak_ceiling_bpm": 220,
}


# -- the day view -----------------------------------------------------------


def test_zones_take_their_ceiling_from_the_next_zone_s_floor(owner):
    daily(owner, DAY, **ZONE_EDGES, zone_cardio_minutes=40)

    zones = {zone["key"]: zone for zone in heart.day(owner, DAY)["zones"]}

    assert (zones["fat_burn"]["floor"], zones["fat_burn"]["ceiling"]) == (97, 136)
    assert (zones["cardio"]["floor"], zones["cardio"]["ceiling"]) == (136, 166)
    assert (zones["peak"]["floor"], zones["peak"]["ceiling"]) == (166, 220)
    # The minutes come from the same payload as the boundaries, so the shading
    # and the totals printed beside it cannot disagree.
    assert zones["cardio"]["minutes"] == 40


def test_a_zone_with_no_zone_above_it_is_open_topped(owner):
    """A gap must leave the band open, not silently widen it.

    If the peak floor is missing, taking "the next floor, or else the ceiling"
    would give cardio a ceiling of 220 - shading a third of the plot as cardio
    on a day that never left fat burn.
    """
    daily(
        owner,
        DAY,
        zone_fat_burn_floor_bpm=97,
        zone_cardio_floor_bpm=136,
        zone_peak_ceiling_bpm=220,
    )

    zones = {zone["key"]: zone for zone in heart.day(owner, DAY)["zones"]}

    assert "peak" not in zones
    assert zones["cardio"]["ceiling"] is None


def test_a_day_before_the_boundaries_were_stored_has_no_bands(owner):
    """Rather than bands invented from 220-age, which would contradict the
    zone minutes sitting next to them."""
    daily(owner, DAY, resting_hr=58, zone_cardio_minutes=40)

    day = heart.day(owner, DAY)

    assert day["zones"] == []
    assert day["resting_hr"] == 58


def test_the_trace_is_bounded_by_the_local_day(owner):
    """Melbourne is UTC+10, so a UTC-day query would take the trace from 10am
    to 10am and hand the page two half-days stitched together."""
    # 23:30 local on the 11th, and 00:30 local on the 12th.
    Sample.objects.create(
        user=owner, metric="hr", ts=datetime(2026, 8, 11, 13, 30, tzinfo=UTC), value=61
    )
    Sample.objects.create(
        user=owner, metric="hr", ts=datetime(2026, 8, 11, 14, 30, tzinfo=UTC), value=99
    )

    day = heart.day(owner, DAY)

    assert day["count"] == 1
    assert day["points"][0]["value"] == 99


def test_both_nights_touching_the_day_are_shaded_and_clipped(owner):
    """The night that ended this morning and the one starting tonight.

    Dropping the second leaves the evening looking like an unexplained
    collapse; leaving either unclipped draws a band off the end of the axis.
    """
    # Ended 06:00 local on the 12th; started 22:00 local on the 12th.
    SleepSession.objects.create(
        user=owner,
        external_id="a",
        local_date=DAY,
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 8, 11, 20, 0, tzinfo=UTC),
        duration_minutes=450,
        is_main_sleep=True,
    )
    SleepSession.objects.create(
        user=owner,
        external_id="b",
        local_date=DAY + timedelta(days=1),
        started_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
        duration_minutes=450,
        is_main_sleep=True,
    )

    day = heart.day(owner, DAY)

    assert len(day["sleep"]) == 2
    assert day["sleep"][0]["started_at"] == day["start"]
    assert day["sleep"][1]["ended_at"] == day["end"]


# -- the window view --------------------------------------------------------


def test_the_baseline_spans_a_month_even_when_the_chart_spans_a_week(owner):
    """A baseline drawn from the seven points the line is made of is not a
    reference - it is the line again, and it moves with every bad night."""
    today = local_today(owner)
    for offset in range(30):
        daily(owner, today - timedelta(days=offset), resting_hr=60, hrv_rmssd=50)

    history = heart.history(owner, days=7)

    resting = next(s for s in history["series"] if s["metric"] == "resting_hr")
    assert len(resting["points"]) == 7
    assert resting["baseline"]["days"] == 30


def test_too_few_readings_means_no_baseline(owner):
    """Two points have a standard deviation and it means nothing."""
    today = local_today(owner)
    for offset in range(3):
        daily(owner, today - timedelta(days=offset), hrv_rmssd=50)

    history = heart.history(owner, days=30)

    hrv = next(s for s in history["series"] if s["metric"] == "hrv_rmssd")
    assert hrv["points"]
    assert hrv["baseline"] is None


def test_each_series_carries_the_direction_that_is_good(owner):
    """Both share one axis on the chart, where it cannot be inferred: two
    lines converging reads as an event, and usually is not one."""
    today = local_today(owner)
    for offset in range(10):
        daily(owner, today - timedelta(days=offset), resting_hr=60, hrv_rmssd=50)

    directions = {s["metric"]: s["direction"] for s in heart.history(owner, days=30)["series"]}

    assert directions == {"hrv_rmssd": "up", "resting_hr": "down"}


# -- the table --------------------------------------------------------------


def test_vigorous_minutes_sum_the_cardio_and_peak_zones(owner):
    daily(owner, DAY, zone_cardio_minutes=14, zone_peak_minutes=7)

    cells = cells_for(owner, DAY)

    assert cells["vigorous_minutes"]["value"] == 21
    # 21 min/day is the top of WHO's vigorous range, so full marks.
    assert cells["vigorous_minutes"]["band"] == 5


def test_a_day_with_no_zone_minutes_is_blank_not_zero(owner):
    """Summing to 0.0 would score a day the watch spent charging as the most
    sedentary day on record - and colour it, confidently, red."""
    daily(owner, DAY, resting_hr=58)

    cells = cells_for(owner, DAY)

    assert cells["vigorous_minutes"]["value"] is None
    assert cells["vigorous_minutes"]["band"] is None


def test_the_day_s_extremes_are_shown_without_a_colour(owner):
    """178 bpm is excellent during intervals and alarming at a desk, and the
    number alone cannot tell those apart. The lowest minute is the same kind of
    fact, and resting HR is already its scored, steadier form."""
    daily(owner, DAY, max_hr=178, min_hr=44)

    cells = cells_for(owner, DAY)

    assert (cells["max_hr"]["value"], cells["max_hr"]["band"]) == (178, None)
    assert (cells["min_hr"]["value"], cells["min_hr"]["band"]) == (44, None)
    columns = {c["key"]: c for c in heart.history(owner, days=30)["columns"]}
    assert columns["max_hr"]["scored"] is False
    assert columns["min_hr"]["scored"] is False


def test_columns_run_recovery_then_output_then_the_extremes(owner):
    """Active before vigorous - the broader measure before the narrower one it
    contains - and both extremes last, beside each other."""
    keys = [column.key for column in heart.table_columns(owner)]

    assert keys == [
        "resting_hr",
        "hrv_rmssd",
        "vo2max",
        "active_minutes",
        "vigorous_minutes",
        "min_hr",
        "max_hr",
    ]


def test_rows_are_newest_first_and_inside_the_window(owner):
    today = local_today(owner)
    for offset in range(40):
        daily(owner, today - timedelta(days=offset), resting_hr=60)

    history = heart.history(owner, days=7)
    dates = [row["date"] for row in history["rows"]]

    assert dates == sorted(dates, reverse=True)
    assert dates[0] == history["end"]
    assert len(dates) == 7


# -- deriving the extremes --------------------------------------------------


def test_the_rollup_derives_the_day_s_lowest_and_highest_minute(owner):
    """Fitbit sends neither.

    `min_hr` and `max_hr` were in the vocabulary and written only by the
    archive importer, so every day synced live carried a blank where the
    archive had a number - a gap that reads as missing history rather than a
    missing derivation.
    """
    for minute, value in ((60, 71), (120, 48), (180, 152)):
        Sample.objects.create(
            user=owner,
            metric="hr",
            ts=datetime(2026, 8, 11, 14, 0, tzinfo=UTC) + timedelta(minutes=minute),
            value=value,
        )

    rollups.rebuild(owner, DAY, DAY)

    values = dict(
        DailyMetric.objects.filter(user=owner, local_date=DAY).values_list("metric", "value")
    )
    assert values["min_hr"] == 48
    assert values["max_hr"] == 152


def test_a_device_supplied_extreme_is_not_overwritten(owner):
    """Same rule the rest of the rollup follows: `source="device"` wins.

    Fitbit does not currently send these, but the archive importer does, and a
    derivation that clobbered imported history would silently degrade it.
    """
    DailyMetric.objects.create(
        user=owner,
        local_date=DAY,
        metric="min_hr",
        value=42.0,
        source=DailyMetric.Source.DEVICE,
    )
    Sample.objects.create(
        user=owner,
        metric="hr",
        ts=datetime(2026, 8, 11, 15, 0, tzinfo=UTC),
        value=99,
    )

    rollups.rebuild(owner, DAY, DAY)

    assert DailyMetric.objects.get(user=owner, local_date=DAY, metric="min_hr").value == 42.0


def cells_for(owner, on: date) -> dict:
    columns = heart.table_columns(owner)
    metrics = dict(
        DailyMetric.objects.filter(user=owner, local_date=on).values_list("metric", "value")
    )
    return {cell["key"]: cell for cell in heart.table_cells(columns, metrics)}
