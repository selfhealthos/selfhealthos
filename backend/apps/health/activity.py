"""Movement, at two resolutions.

Built to the shape `heart.py` settled on, and for the same reason: the page it
replaces was four charts of equal weight, none of them dominant and three of
them showing almost nothing. What is asked of an activity page is two
questions at different zoom levels, so the window control picks which one is
answered.

**One day** is about *when*: which hours the steps happened in, and whether the
day ever got over the line. That is a cumulative climb against a goal, with the
hours underneath it - `day()` returns both from one query, plus the night, so
the eight-hour flat stretch is explained rather than looking like a dead
sensor.

**A week or more** is about *how much, and how hard*. Those are two different
numbers and the page has been showing only the first: 15,000 steps with eight
active minutes is a day of pottering and 15,000 with fifty-five is a walk, and
until now they were the same mark. So `history()` returns steps per day
*together with* the day's moderate-to-vigorous minutes and the band those score
into, and the chart draws volume as height and intensity as colour.

Two metrics are deliberately absent from everything here:

- **`floors`.** Every row is a literal 0.0 - the device does not report it -
  and a column of zeroes is worse than no column, because it reads as a fact
  about the person rather than about the hardware.
- **`active_zone_minutes`.** Same trap `scoring.ACTIVE_MINUTES` documents: the
  archive holds it as 0.0 on every day it was never supplied, so it cannot
  tell "did nothing" from "no data". The two bucket metrics are simply absent
  when unknown, and a blank cell is the whole point.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.utils import timezone as dj_timezone

from . import heart, scoring, timeutils
from .models import DailyMetric, Sample

#: The steps target every view on this page measures against. Not scored *at*
#: this number - `scoring.STEPS` gives full marks from 10,000 and most of them
#: by 8,000, because that is where the mortality curve flattens - but it is the
#: line people set for themselves and the one the charts draw.
GOAL_STEPS = 10_000


# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------


def day(user, on: date) -> dict:
    """One local day of steps: the climb, the hours, and the night.

    Returns a shape even when there are no minute samples. A day the intraday
    fetch skipped and a day nobody moved are different answers, and the page
    has to be able to say which it is looking at - the same rule `heart.day`
    follows.
    """
    tz = timeutils.tz_for(user)
    lower = timeutils.utc_from_local_parts(on, time(0, 0), tz)
    upper = timeutils.utc_from_local_parts(on + timedelta(days=1), time(0, 0), tz)

    samples = list(
        Sample.objects.filter(user=user, metric="steps", ts__gte=lower, ts__lt=upper)
        .order_by("ts")
        .values_list("ts", "value")
    )

    points, hours, total, reached = _climb(samples, lower, upper, tz)

    stored = dict(
        DailyMetric.objects.filter(user=user, local_date=on).values_list("metric", "value")
    )

    return {
        "date": on,
        "start": lower,
        "end": upper,
        "points": points,
        "hours": hours,
        "count": len(samples),
        # The rolled-up daily total where there is one, and the sum of the
        # minutes otherwise. They can disagree by a few steps and the daily
        # figure is the device's own, so it wins - but a day with minute data
        # and no rollup yet still gets a total rather than a dash.
        "total": stored.get("steps", total),
        "goal": GOAL_STEPS,
        "goal_reached_at": reached,
        "distance_km": stored.get("distance_km"),
        "calories_burned": stored.get("calories_burned"),
        "active_minutes": _summed(stored, ("fairly_active_minutes", "very_active_minutes")),
        "vigorous_minutes": _summed(stored, ("zone_cardio_minutes", "zone_peak_minutes")),
        "resting_hr": stored.get("resting_hr"),
        "sleep": heart.sleep_windows(user, lower, upper),
    }


def _climb(
    samples: list[tuple[datetime, float]], lower: datetime, upper: datetime, tz
) -> tuple[list[dict], list[dict], float, datetime | None]:
    """The cumulative line, the hourly bars, and when the goal was crossed.

    The line carries a point only at minutes where the count actually moved,
    plus both ends of the day. A cumulative curve only bends where something
    happened, so the other ~900 minutes of a normal day are collinear filler -
    dropping them is lossless and roughly halves the payload. Both ends are
    kept regardless, because a line that starts at the first step drawn across
    a full-day axis implies the morning was never measured.
    """
    points: list[dict] = []
    buckets: dict[int, float] = {}
    running = 0.0
    reached: datetime | None = None

    for ts, value in samples:
        if value:
            running += value
            local_hour = ts.astimezone(tz).hour
            buckets[local_hour] = buckets.get(local_hour, 0.0) + value
            points.append({"at": ts, "value": running})
            if reached is None and running >= GOAL_STEPS:
                reached = ts

    if samples:
        # Anchor both ends so the climb spans the day rather than the interval
        # that happened to contain movement.
        first_ts = samples[0][0]
        last_ts = samples[-1][0]
        if not points or points[0]["at"] > first_ts:
            points.insert(0, {"at": first_ts, "value": 0.0})
        if points[-1]["at"] < last_ts:
            points.append({"at": last_ts, "value": running})

    hours = [{"hour": hour, "steps": buckets.get(hour, 0.0)} for hour in range(24)]
    return points, hours, running, reached


def _summed(metrics: dict[str, float], keys: tuple[str, ...]) -> float | None:
    """Sum of whichever of `keys` were reported, or None if none were.

    Never 0.0 for an absent day: summing nothing to zero would score a day the
    watch spent on the charger as the most sedentary day on record.
    """
    parts = [metrics[key] for key in keys if key in metrics]
    return sum(parts) if parts else None


# --------------------------------------------------------------------------
# A window of days
# --------------------------------------------------------------------------

#: Days in the trailing mean drawn over the bars. Seven, so the line is a week
#: and every weekday is represented once - a five-day mean of someone who walks
#: at weekends moves for reasons that are about the calendar, not the person.
TRAILING_DAYS = 7

#: Recorded days a trailing window needs before it draws a point. Under this,
#: the "weekly average" is an average of two days wearing the label of seven,
#: which is exactly the kind of quiet lie the sleep page's "over N nights"
#: wording exists to prevent.
TRAILING_MINIMUM = 4


#: Distance, shown and never coloured. There is no distance recommendation to
#: score against - the guidance is all in steps and in minutes - and a stride
#: length the watch estimated is the only thing separating this column from the
#: steps column beside it.
DISTANCE = scoring.Threshold(
    key="distance_km",
    label="Distance",
    unit="km",
    metric="distance_km",
    places=1,
    evidence="Shown but not scored: no guideline is written in kilometres, and "
    "this is steps multiplied by an estimated stride length.",
)

#: Light activity, shown and never coloured. It is real movement and it is not
#: what the guidelines count: WHO's 150-300 minutes are moderate-to-vigorous,
#: and light minutes displace sitting rather than satisfying that target.
LIGHTLY_ACTIVE = scoring.Threshold(
    key="lightly_active_minutes",
    label="Light",
    unit="min",
    metric="lightly_active_minutes",
    evidence="Shown but not scored: light activity displaces sitting, but the "
    "WHO target counts moderate-to-vigorous minutes only.",
)

#: Sedentary time with the night taken out of it.
#:
#: **Fitbit's sedentary minutes include sleep.** The raw figure averages over
#: eighteen hours a day, and printed as "sedentary" it is a number that would
#: be quoted wrongly forever. Subtracting the night gives the waking figure,
#: which is the one the sitting literature is written about.
#:
#: Unscored by choice. There is a real literature here - the mortality
#: association above roughly ten waking hours is consistent - but the
#: subtraction already makes this the most derived column on the page, and it
#: is only as good as the sleep session it leans on. Colouring an estimate
#: built on an estimate would say something confident that the inputs do not
#: support, and `scoring.py`'s rule is that an uncoloured cell says "no
#: opinion".
AWAKE_SEDENTARY = scoring.Threshold(
    key="awake_sedentary",
    label="Sitting",
    unit="h",
    metric=None,
    sources=("sedentary_minutes", "sleep_minutes"),
    places=1,
    evidence="Sedentary minutes with the night subtracted — Fitbit counts "
    "sleep as sedentary, so the raw figure runs past 18 h. Shown but not "
    "scored: it is an estimate resting on another estimate.",
)

#: Calories, shown and never coloured. Most of this number is being alive:
#: basal metabolic rate is roughly 1,600-1,800 of the ~2,500 daily average
#: here, so the column moves far less than the effort behind it does, and no
#: threshold could separate a hard day from a warm one.
CALORIES = scoring.Threshold(
    key="calories_burned",
    label="Calories",
    unit="kcal",
    metric="calories_burned",
    evidence="Shown but not scored: most of a day's burn is basal metabolic "
    "rate, so this moves much less than the effort behind it.",
)


def table_columns() -> tuple[scoring.Threshold, ...]:
    """The activity table's columns, in draw order.

    Volume first (what you did), then intensity broad-before-narrow (how hard),
    then the two columns that describe the rest of the day, then the one signal
    that says whether any of it is working. Every scored column here reuses a
    threshold from `scoring.py` rather than defining a second opinion about the
    same measurement - the heatmap, the heart page and this page have to agree
    on what a good step count is.
    """
    return (
        scoring.STEPS,
        DISTANCE,
        scoring.ACTIVE_MINUTES,
        scoring.VIGOROUS_MINUTES,
        LIGHTLY_ACTIVE,
        AWAKE_SEDENTARY,
        CALORIES,
        scoring.RESTING_HR,
    )


#: The two overlays that ride the master chart's shared axis, and what each is
#: summed from. Both are minute counts, so they sit on that axis in their own
#: unit without conversion - the condition the sleep page's shared axis rests
#: on, applied here.
SERIES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "active_minutes",
        "Active minutes",
        "min",
        ("fairly_active_minutes", "very_active_minutes"),
    ),
    (
        "vigorous_minutes",
        "Vigorous minutes",
        "min",
        ("zone_cardio_minutes", "zone_peak_minutes"),
    ),
    ("resting_hr", "Resting heart rate", "bpm", ("resting_hr",)),
)

#: A row needs one of these to exist. A day carrying only a resting heart rate
#: is not an activity day, and listing it would fill the table with blank rows
#: on every day the watch was worn asleep and taken off after breakfast.
ROW_EVIDENCE = (
    "steps",
    "distance_km",
    "lightly_active_minutes",
    "fairly_active_minutes",
    "very_active_minutes",
    "calories_burned",
)


def history(user, *, days: int = 30) -> dict:
    """Steps per day with their intensity, the overlays, and the scored table.

    One call and one query, for the reason `heart.history` gives: every panel
    on the page is built from the same rows, and splitting them across
    endpoints made the page's own numbers arrive at four different moments.
    """
    days = max(1, min(days, 365))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(dj_timezone.now(), tz)
    start = end - timedelta(days=days - 1)

    columns = table_columns()
    wanted = {column.metric for column in columns if column.metric}
    wanted |= {source for column in columns for source in column.sources}
    wanted |= {source for _, _, _, sources in SERIES for source in sources}

    # The trailing mean needs the six days before the window, or the first
    # week of every chart would climb out of nothing.
    fetch_from = start - timedelta(days=TRAILING_DAYS - 1)

    by_day: dict[date, dict[str, float]] = {}
    for local_date, metric, value in DailyMetric.objects.filter(
        user=user,
        metric__in=wanted,
        local_date__gte=fetch_from,
        local_date__lte=end,
    ).values_list("local_date", "metric", "value"):
        by_day.setdefault(local_date, {})[metric] = value

    in_window = [
        local_date
        for local_date in sorted(by_day)
        if start <= local_date <= end and any(key in by_day[local_date] for key in ROW_EVIDENCE)
    ]

    bars = []
    for local_date in in_window:
        if "steps" not in by_day[local_date]:
            continue
        active = _summed(by_day[local_date], scoring.ACTIVE_MINUTES.sources)
        bars.append(
            {
                "date": local_date,
                "steps": by_day[local_date]["steps"],
                "active_minutes": active,
                # The colour on the bar. Intensity, not volume: height already
                # says how far, and a tall bar the colour of a rest day is the
                # thing this chart exists to make visible.
                "band": scoring.band_for(
                    None if active is None else scoring.ACTIVE_MINUTES.score(active)
                ),
            }
        )

    series = []
    for key, label, unit, sources in SERIES:
        points = []
        for local_date in in_window:
            value = _summed(by_day[local_date], sources)
            if value is not None:
                points.append({"date": local_date, "value": value})
        series.append({"metric": key, "label": label, "unit": unit, "points": points})

    rows = [
        {"date": local_date, "cells": table_cells(columns, by_day[local_date])}
        for local_date in reversed(in_window)
    ]

    return {
        "start": start,
        "end": end,
        "days": days,
        "goal": GOAL_STEPS,
        "bars": bars,
        "trailing": _trailing_steps(by_day, start, end),
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
        "summary": _summary(by_day, in_window, days),
    }


def _trailing_steps(by_day: dict[date, dict[str, float]], start: date, end: date) -> list[dict]:
    """A seven-day trailing mean of steps, over the days that have one.

    Drawn over the bars because daily steps here swing from zero to twenty
    thousand, and a bar forest that noisy has no readable trend in it. The mean
    is over *recorded* days in the window rather than over seven, for the same
    reason every average on the sleep page is: dividing by seven would turn a
    week the watch was off into a collapse in activity that never happened.

    Below `TRAILING_MINIMUM` recorded days the point is omitted entirely. A
    "weekly average" standing on two days is not one, and the gap it leaves
    says so more honestly than a line drawn through it would.
    """
    out = []
    current = start
    while current <= end:
        values = []
        for offset in range(TRAILING_DAYS):
            when = current - timedelta(days=offset)
            if when in by_day and "steps" in by_day[when]:
                values.append(by_day[when]["steps"])
        if len(values) >= TRAILING_MINIMUM:
            out.append({"date": current, "value": sum(values) / len(values)})
        current += timedelta(days=1)
    return out


def table_cells(columns: tuple[scoring.Threshold, ...], metrics: dict[str, float]) -> list[dict]:
    """One scored cell per column, for one day."""
    cells = []
    for column in columns:
        value = _cell_value(column, metrics)
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


def _cell_value(column: scoring.Threshold, metrics: dict[str, float]) -> float | None:
    """The value behind one cell, in the column's display unit.

    `awake_sedentary` is the one column whose sources are not simply summed,
    which is why this is not `heart.table_cells`. Both of its inputs are
    required: a sedentary total with no sleep session to subtract is off by a
    whole night, and printing it anyway would show eighteen hours of sitting on
    a day that had eight.
    """
    if column is AWAKE_SEDENTARY:
        sedentary = metrics.get("sedentary_minutes")
        asleep = metrics.get("sleep_minutes")
        if sedentary is None or asleep is None:
            return None
        # Clamped at zero rather than allowed negative. The two numbers come
        # from different Fitbit endpoints and a nap counted in both can push
        # the subtraction below zero; a negative hour of sitting is noise, not
        # a finding.
        return max(0.0, sedentary - asleep) / 60
    if column.metric is None:
        return _summed(metrics, column.sources)
    raw = metrics.get(column.metric)
    return None if raw is None else raw * column.scale


def _summary(by_day: dict[date, dict[str, float]], in_window: list[date], days: int) -> dict:
    """The numbers under the chart, each one stated over what it is an average of.

    Every mean here divides by the days that recorded the thing being averaged,
    never by the window. The two differ by a lot - a third of the last year has
    no data at all - and the second would report every unworn week as a week of
    not moving.
    """

    def values(*keys: str) -> list[float]:
        out = []
        for local_date in in_window:
            value = _summed(by_day[local_date], keys)
            if value is not None:
                out.append(value)
        return out

    steps = values("steps")
    active = values(*scoring.ACTIVE_MINUTES.sources)
    vigorous = values(*scoring.VIGOROUS_MINUTES.sources)
    sitting = []
    for local_date in in_window:
        hours = _cell_value(AWAKE_SEDENTARY, by_day[local_date])
        if hours is not None:
            sitting.append(hours)

    def mean(sample: list[float]) -> float | None:
        return sum(sample) / len(sample) if sample else None

    return {
        "days_elapsed": days,
        "days_recorded": len(steps),
        "mean_steps": mean(steps),
        "best_steps": max(steps) if steps else None,
        "goal_days": sum(1 for value in steps if value >= GOAL_STEPS),
        "mean_active_minutes": mean(active),
        "active_days": len(active),
        # Stated per week because that is the unit the recommendation is
        # written in, and the window is not: 90 minutes is excellent over seven
        # days and poor over ninety. Same argument as the heart page's zone mix.
        "active_per_week": None if not active else mean(active) * 7,
        "mean_vigorous_minutes": mean(vigorous),
        "vigorous_days": len(vigorous),
        "vigorous_per_week": None if not vigorous else mean(vigorous) * 7,
        "mean_sitting_hours": mean(sitting),
        "sitting_days": len(sitting),
    }
