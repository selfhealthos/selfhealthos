"""The heart, at two resolutions.

A day and a month are different questions and want different pictures, and the
old heart page tried to answer both with four charts of equal weight, none of
which dominated and none of which was legible.

**One day** is about *intensity over time*: where the trace sat, what it was
doing when it climbed, and which zone it climbed into. That only reads as a
picture if the zones are drawn behind the line, so `day()` returns the trace
together with the bpm boundaries the device itself used - and the night, which
explains the long low plateau that otherwise looks like a flat-lined sensor.

**A week or more** is about *recovery*: HRV and resting heart rate, neither of
which means much as an absolute number. Both are read against your own recent
history, so `history()` returns a baseline band per series alongside the
points. The thresholds in `scoring.py` say as much about HRV in their own
evidence string - "your own baseline is the real reference" - and a page that
prints that sentence while drawing no baseline is not much use.

The two share one date axis convention with the sleep pages: a value's date is
its local date, and a night belongs to the morning it ended on.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from statistics import fmean, pstdev

from django.utils import timezone as dj_timezone

from . import scoring, timeutils
from .models import DailyMetric, Sample, SleepSession

# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------

#: The zones, in the order they stack up the y-axis. Each one's floor is a
#: stored daily metric; its ceiling is the next zone's floor, and the top of
#: peak is Fitbit's estimated maximum. "Out of range" is deliberately not a
#: band: it is everything below fat burn, which is most of a day, and shading
#: it would tint the whole plot rather than mark anything.
ZONES: tuple[tuple[str, str, str], ...] = (
    ("fat_burn", "Fat burn", "zone_fat_burn_floor_bpm"),
    ("cardio", "Cardio", "zone_cardio_floor_bpm"),
    ("peak", "Peak", "zone_peak_floor_bpm"),
)

#: Where each zone's minute count is stored, so the shading and the totals
#: printed beside it come from the same payload and cannot disagree.
ZONE_MINUTES = {
    "fat_burn": "zone_fat_burn_minutes",
    "cardio": "zone_cardio_minutes",
    "peak": "zone_peak_minutes",
}


def day(user, on: date) -> dict:
    """One day's minute trace, the zones it moved through, and the night.

    Returns a shape even when there are no minute samples: a day with no
    intraday data and a day the heart stopped are not the same answer, and the
    page needs to be able to say which it is looking at.
    """
    tz = timeutils.tz_for(user)
    lower = timeutils.utc_from_local_parts(on, time(0, 0), tz)
    upper = timeutils.utc_from_local_parts(on + timedelta(days=1), time(0, 0), tz)

    points = [
        {"at": ts, "value": value}
        for ts, value in Sample.objects.filter(user=user, metric="hr", ts__gte=lower, ts__lt=upper)
        .order_by("ts")
        .values_list("ts", "value")
    ]
    values = [point["value"] for point in points]

    stored = dict(
        DailyMetric.objects.filter(user=user, local_date=on).values_list("metric", "value")
    )

    return {
        "date": on,
        "start": lower,
        "end": upper,
        "points": points,
        "count": len(points),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "resting_hr": stored.get("resting_hr"),
        "zones": _zones(stored),
        "sleep": sleep_windows(user, lower, upper),
    }


def _zones(stored: dict[str, float]) -> list[dict]:
    """The shaded bands, from the boundaries the device reported that day.

    Empty when the day predates storing them, and the page says so rather than
    inventing bands from 220-age: those would contradict the zone minutes
    printed next to them, and two numbers that disagree on the same card are
    worse than one number missing.
    """
    ceiling = stored.get("zone_peak_ceiling_bpm")
    bands = []
    for index, (key, label, floor_metric) in enumerate(ZONES):
        floor = stored.get(floor_metric)
        if floor is None:
            continue
        # The next zone's floor is this one's ceiling. Reading it from the
        # stored value rather than assuming they are contiguous means a gap in
        # the data leaves a band open-topped instead of silently widening it
        # over the zone above.
        upper_metric = ZONES[index + 1][2] if index + 1 < len(ZONES) else None
        top = stored.get(upper_metric) if upper_metric else ceiling
        bands.append(
            {
                "key": key,
                "label": label,
                "floor": floor,
                "ceiling": top,
                "minutes": stored.get(ZONE_MINUTES[key]),
            }
        )
    return bands


def sleep_windows(user, lower: datetime, upper: datetime) -> list[dict]:
    """Every main sleep that overlaps this local day, clipped to it.

    Usually two: the night that ended this morning and the one that starts this
    evening. Both are drawn, because the point of shading them is to explain
    the low stretches at each end of the trace, and dropping the second leaves
    the evening looking like an unexplained collapse.

    Public because the activity day view shades the same windows for the same
    reason - a step count that stops climbing for eight hours wants the same
    explanation a heart rate that flattens does.
    """
    return [
        {
            "started_at": max(session.started_at, lower),
            "ended_at": min(session.ended_at, upper),
            "local_date": session.local_date,
        }
        for session in SleepSession.objects.filter(
            user=user, is_main_sleep=True, started_at__lt=upper, ended_at__gt=lower
        ).order_by("started_at")
    ]


# --------------------------------------------------------------------------
# A window of days
# --------------------------------------------------------------------------

#: The two recovery series, and which way each one is good. The direction is
#: part of the response rather than a fact the page hardcodes, because both
#: lines share one axis on the chart: without it, two lines converging is
#: ambiguous, and the reading a shared axis most invites - "they crossed, so
#: something happened" - is the wrong one.
SERIES: tuple[tuple[str, str, str, str], ...] = (
    ("hrv_rmssd", "HRV (RMSSD)", "ms", "up"),
    ("resting_hr", "Resting heart rate", "bpm", "down"),
)

#: Days the baseline is computed over, regardless of the window being charted.
#: A 7-day view still compares against a month, because a baseline drawn from
#: the same seven points the line is made of is not a reference - it is the
#: line again, and it moves with every bad night rather than against it.
BASELINE_DAYS = 30

#: Below this many readings there is no baseline. Two points have a standard
#: deviation and it means nothing; drawing a band from it would put a confident
#: grey stripe around noise.
BASELINE_MINIMUM = 7


def history(user, *, days: int = 30) -> dict:
    """The recovery series, their baselines, and the scored table.

    One call rather than the four the page used to make: every panel here is
    built from the same two queries, and splitting them across endpoints made
    the page's own numbers arrive at four different moments.
    """
    days = max(1, min(days, 365))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(dj_timezone.now(), tz)
    start = end - timedelta(days=days - 1)
    baseline_start = end - timedelta(days=BASELINE_DAYS - 1)

    columns = table_columns(user)
    wanted = {column.metric for column in columns if column.metric}
    wanted |= {source for column in columns for source in column.sources}
    wanted |= {key for key, _, _, _ in SERIES}

    by_day: dict[date, dict[str, float]] = {}
    for local_date, metric, value in DailyMetric.objects.filter(
        user=user,
        metric__in=wanted,
        local_date__gte=min(start, baseline_start),
        local_date__lte=end,
    ).values_list("local_date", "metric", "value"):
        by_day.setdefault(local_date, {})[metric] = value

    series = []
    for key, label, unit, direction in SERIES:
        points = [
            {"date": local_date, "value": by_day[local_date][key]}
            for local_date in sorted(by_day)
            if key in by_day[local_date] and start <= local_date <= end
        ]
        recent = [
            by_day[local_date][key]
            for local_date in by_day
            if key in by_day[local_date] and local_date >= baseline_start
        ]
        series.append(
            {
                "metric": key,
                "label": label,
                "unit": unit,
                "direction": direction,
                "points": points,
                "baseline": _baseline(recent),
            }
        )

    rows = [
        {
            "date": local_date,
            "cells": table_cells(columns, by_day[local_date]),
        }
        for local_date in sorted(by_day, reverse=True)
        if start <= local_date <= end
    ]

    return {
        "start": start,
        "end": end,
        "days": days,
        "series": series,
        "columns": [
            {
                "key": column.key,
                "label": column.label,
                "unit": column.unit,
                "places": column.places,
                "evidence": column.evidence,
                "scored": column.scored,
            }
            for column in columns
        ],
        "rows": rows,
    }


def _baseline(values: list[float]) -> dict | None:
    """Mean and one standard deviation, or nothing.

    Population standard deviation rather than sample: this is a description of
    the days that happened, not an estimate drawn from a sample of a larger
    population of days that did not.
    """
    if len(values) < BASELINE_MINIMUM:
        return None
    mean = fmean(values)
    spread = pstdev(values)
    return {
        "mean": mean,
        "sd": spread,
        "low": mean - spread,
        "high": mean + spread,
        "days": len(values),
    }


# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------

#: Cardio and peak minutes summed - what the heart itself counted as hard work.
VIGOROUS = scoring.VIGOROUS_MINUTES

#: The two extremes of the day, shown and never coloured.
#:
#: The highest minute is a fact about what you did, not a verdict on it: 178
#: bpm is excellent during intervals and alarming at a desk, and no threshold
#: can tell those apart from the number. The lowest is the more interesting of
#: the pair - it is almost always mid-sleep, and it falls as fitness rises -
#: but it is a single minute of a wrist reflectance estimate, so it is noisier
#: than the resting heart rate two columns to its left, which is the scored
#: version of the same signal. Colouring both would say the same thing twice,
#: the second time less reliably.
#:
#: `scoring.py`'s rule is that an uncoloured cell says "no opinion", which is
#: the honest answer for both.
LOWEST_HR = scoring.Threshold(
    key="min_hr",
    label="Lowest HR",
    unit="bpm",
    metric="min_hr",
    evidence="Shown but not scored: the day's single lowest minute, usually "
    "mid-sleep. Resting HR is the steadier version of the same signal, and it "
    "is the one that carries a colour.",
)

PEAK_HR = scoring.Threshold(
    key="max_hr",
    label="Peak HR",
    unit="bpm",
    metric="max_hr",
    evidence="Shown but not scored: the day's highest minute means nothing "
    "without knowing what you were doing at the time.",
)


def table_columns(user) -> tuple[scoring.Threshold, ...]:
    """The heart table's columns, in draw order.

    Recovery first (what the night gave you), then output (what you spent, the
    broader measure before the narrower one it contains), then the two unscored
    extremes. VO2 max needs age/sex off the account, so this is built per user
    in the same way `scoring.columns_for` is.
    """
    return (
        scoring.RESTING_HR,
        scoring.HRV,
        scoring.vo2max_threshold(age=user.age_years, sex=user.sex),
        scoring.ACTIVE_MINUTES,
        VIGOROUS,
        LOWEST_HR,
        PEAK_HR,
    )


def table_cells(columns: tuple[scoring.Threshold, ...], metrics: dict[str, float]) -> list[dict]:
    """One scored cell per column, for one day."""
    cells = []
    for column in columns:
        if column.metric is None:
            # A summed column: absent, not zero, when nothing was reported.
            # Summing to 0.0 would score a day the watch spent charging as the
            # most sedentary day on record.
            parts = [metrics[key] for key in column.sources if key in metrics]
            value = sum(parts) if parts else None
        else:
            raw = metrics.get(column.metric)
            value = None if raw is None else raw * column.scale
        score = column.score(value) if value is not None else None
        cells.append(
            {
                "key": column.key,
                "value": value,
                "score": score,
                "band": scoring.band_for(score),
            }
        )
    return cells
