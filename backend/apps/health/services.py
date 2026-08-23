"""All Health logic.

The REST router, the MCP tools (H4) and the UI are thin callers of these
functions. Nothing else in the app touches the ORM, which is what keeps the
three surfaces from drifting apart.

Almost everything reads `DailyMetric`. That is the point of the rollup: a trend
over a year is 365 rows, not a scan of a million samples. `Sample` is read by
exactly one function, `intraday`, and only ever for a single day.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from datetime import date, time, timedelta

from django.db.models import Count, Exists, Max, Min, OuterRef

from apps.core.exceptions import DomainError, NotFound
from apps.core.services import record_event

from . import devicesync, scoring, timeutils
from . import metrics as metric_defs
from .models import (
    BmEntry,
    BodyMeasurement,
    BpEntry,
    DailyMetric,
    DietEntry,
    Doc,
    ExerciseEntry,
    FitnessTest,
    GymSet,
    Habit,
    HabitCompletion,
    LabResult,
    Note,
    OfficeDay,
    Profile,
    Sample,
    SleepSegment,
    SleepSession,
    WeightEntry,
)

logger = logging.getLogger(__name__)

#: Guard on the trend endpoint. Ten years of daily values is 3,653 rows, which
#: is a chart nobody can read and a response nobody wants to parse.
MAX_TREND_DAYS = 3_700


class UnknownMetric(DomainError, ValueError):
    """The requested metric is not in the vocabulary."""

    title = "Unknown metric"


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------


def metric_catalogue() -> list[dict]:
    """Every metric that can be asked for, with its unit and meaning.

    Serves the API, and in H4 gives Claude the vocabulary before it guesses at
    a metric name.
    """
    intraday_keys = {m.key for m in metric_defs.INTRADAY}
    return [
        {
            "key": m.key,
            "label": m.label,
            "unit": m.unit,
            "description": m.description,
            "has_intraday": m.key in intraday_keys or metric_defs.daily_key_for(m.key) != m.key,
        }
        for m in metric_defs.DAILY
    ]


def resolve_metric(key: str) -> metric_defs.MetricDef:
    definition = metric_defs.DAILY_BY_KEY.get(key)
    if definition is None:
        raise UnknownMetric(f"{key!r} is not a known metric")
    return definition


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def summary(user) -> dict:
    """Coverage: what data exists, over what period, and how recently.

    The honest answer to "is there anything here", which is the first thing
    both a dashboard and a language model need to know before asking anything
    more specific.
    """
    from . import rollups

    start, end = rollups.data_span(user)
    entries = entry_counts(user)

    per_metric = {
        row["metric"]: {
            "days": row["days"],
            "first": row["first"],
            "last": row["last"],
        }
        for row in DailyMetric.objects.filter(user=user)
        .values("metric")
        .annotate(days=Count("id"), first=Min("local_date"), last=Max("local_date"))
        .order_by("metric")
    }

    return {
        "first_date": start,
        "last_date": end,
        "days_covered": (end - start).days + 1 if start and end else 0,
        "entries": entries,
        "metrics": per_metric,
        "sample_count": Sample.objects.filter(user=user).count(),
    }


def entry_counts(user) -> dict[str, int]:
    live = {"created_by": user, "deleted_at__isnull": True}
    return {
        "diet": DietEntry.objects.filter(**live).count(),
        "exercise": ExerciseEntry.objects.filter(**live).count(),
        "bm": BmEntry.objects.filter(**live).count(),
        "bp": BpEntry.objects.filter(**live).count(),
        "weight": WeightEntry.objects.filter(**live).count(),
        "notes": Note.objects.filter(**live).count(),
        "gym_sets": GymSet.objects.filter(**live).count(),
        "habits": Habit.objects.filter(**live).count(),
        "office_days": OfficeDay.objects.filter(**live).count(),
        "labs": LabResult.objects.filter(**live).count(),
        "body_measurements": BodyMeasurement.objects.filter(**live).count(),
        "sleep_sessions": SleepSession.objects.filter(user=user).count(),
    }


def portal_stats() -> dict:
    """The launcher tile and `home_describe`.

    Portal-wide rather than per-user, matching the registry's signature and the
    YouTube app's equivalent. Kept to three cheap aggregates - it runs on every
    render of the home page.
    """
    span = DailyMetric.objects.aggregate(first=Min("local_date"), last=Max("local_date"))
    return {
        "days": DailyMetric.objects.values("local_date").distinct().count(),
        "entries": DietEntry.objects.count()
        + ExerciseEntry.objects.count()
        + BmEntry.objects.count()
        + WeightEntry.objects.count()
        + GymSet.objects.count(),
        "earliest": span["first"].isoformat() if span["first"] else None,
        "latest": span["last"].isoformat() if span["last"] else None,
    }


# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DayView:
    date: date
    #: The timezone that decided which day these entries belong to. Returned so
    #: a caller renders their clock times in the same zone that filed them -
    #: a server-rendered page runs in UTC, and formatting there turns a 7:36am
    #: coffee into a 9:36pm one.
    timezone: str
    metrics: dict[str, float]
    diet: list[dict]
    exercise: list[dict]
    bm: list[dict]
    bp: list[dict]
    weight: list[dict]
    notes: list[dict]
    gym_sets: list[dict]
    habits: list[dict]
    sleep: dict | None
    office_day: bool
    #: Traffic-light read on the day, from HRV, resting HR and sleep
    #: efficiency. See `recovery_for`.
    recovery: dict


#: Thresholds for the recovery read, ported from the one-data dashboard's
#: `get_recovery_status`. They are this person's baselines, not population
#: norms - HRV of 65 is "good" here because their own range is 65-77.
RECOVERY_BANDS = {
    # metric: (good_at_or_better, poor_beyond), and whether higher is better.
    "hrv_rmssd": (65.0, 45.0, True),
    "resting_hr": (62.0, 72.0, False),
    "sleep_efficiency": (85.0, 70.0, True),
}


def recovery_for(values: dict[str, float]) -> dict:
    """A traffic light for the day, from whichever of the three inputs exist.

    Worst-wins rather than an average: the point of the badge is to notice a
    bad night, and averaging a poor HRV against good sleep efficiency hides
    exactly the day worth noticing. A missing input is skipped, not scored as
    zero - two green readings and no watch data is still a green day.
    """
    scores: list[str] = []
    for metric, (good, poor, higher_is_better) in RECOVERY_BANDS.items():
        value = values.get(metric)
        if value is None:
            continue
        if higher_is_better:
            scores.append("green" if value >= good else "red" if value < poor else "amber")
        else:
            scores.append("green" if value <= good else "red" if value > poor else "amber")

    if not scores:
        level, label = "unknown", "No data"
    elif "red" in scores:
        level, label = "red", "Low recovery"
    elif all(s == "green" for s in scores):
        level, label = "green", "Good recovery"
    else:
        level, label = "amber", "Moderate recovery"

    return {
        "level": level,
        "label": label,
        "hrv": values.get("hrv_rmssd"),
        "resting_hr": values.get("resting_hr"),
        "sleep_efficiency": values.get("sleep_efficiency"),
        #: How many of the three inputs were actually available, so the UI can
        #: say "from 2 of 3" rather than implying a full read.
        "inputs": len(scores),
    }


def day(user, on: date) -> DayView:
    """Everything recorded for one calendar day, in the subject's timezone."""
    live = {"created_by": user, "deleted_at__isnull": True, "local_date": on}

    values = dict(
        DailyMetric.objects.filter(user=user, local_date=on).values_list("metric", "value")
    )

    session = (
        SleepSession.objects.filter(user=user, local_date=on, is_main_sleep=True)
        .order_by("-duration_minutes")
        .first()
    )

    return DayView(
        date=on,
        timezone=str(timeutils.tz_for(user)),
        metrics=values,
        diet=[
            {"id": e.id, "name": e.name, "at": e.occurred_at}
            for e in DietEntry.objects.filter(**live).order_by("occurred_at")
        ],
        exercise=[
            {
                "id": e.id,
                "name": e.video_name,
                "duration_s": e.duration_s,
                "at": e.occurred_at,
            }
            for e in ExerciseEntry.objects.filter(**live).order_by("occurred_at")
        ],
        bm=[
            {"id": e.id, "bristol": e.bristol, "notes": e.notes, "at": e.occurred_at}
            for e in BmEntry.objects.filter(**live).order_by("occurred_at")
        ],
        bp=[
            {
                "id": e.id,
                "systolic": e.systolic,
                "diastolic": e.diastolic,
                "at": e.occurred_at,
            }
            for e in BpEntry.objects.filter(**live).order_by("occurred_at")
        ],
        weight=[
            {"id": e.id, "weight_kg": e.weight_kg, "at": e.occurred_at}
            for e in WeightEntry.objects.filter(**live).order_by("occurred_at")
        ],
        notes=[
            {"id": e.id, "title": e.title, "content": e.content, "at": e.occurred_at}
            for e in Note.objects.filter(**live).order_by("occurred_at")
        ],
        gym_sets=[
            {
                "id": e.id,
                "exercise": e.exercise_name,
                "weight_kg": e.weight_kg,
                "reps": e.reps,
                "volume_kg": e.volume_kg,
            }
            for e in GymSet.objects.filter(**live).order_by("exercise_name")
        ],
        habits=_habits_for_day(user, on),
        sleep=_sleep_dict(session),
        office_day=OfficeDay.objects.filter(
            created_by=user, deleted_at__isnull=True, local_date=on
        ).exists(),
        recovery=recovery_for(values),
    )


def _habits_for_day(user, on: date) -> list[dict]:
    """Every defined habit with whether it was done, not just the ticks.

    A list of completions cannot answer "what did I miss", which is the only
    question worth asking of a habit tracker.

    Matched on the foreign key first and the name only as a fallback, and then
    case-insensitively. The archive holds habits that differ from their own
    completions by capitalisation alone - "magnesium" against "Magnesium" -
    and an exact string match reports those as missed every single day.
    """
    completions = HabitCompletion.objects.filter(
        created_by=user, deleted_at__isnull=True, local_date=on
    ).values_list("habit_id", "habit_name")

    done_ids = {habit_id for habit_id, _ in completions if habit_id}
    done_names = {name.strip().casefold() for _, name in completions if name}

    return [
        {
            "id": h.id,
            "name": h.name,
            "completed": h.id in done_ids or h.name.strip().casefold() in done_names,
        }
        for h in Habit.objects.filter(
            created_by=user, deleted_at__isnull=True, archived_at__isnull=True
        ).order_by("sort_order", "name")
    ]


def _sleep_dict(session: SleepSession | None) -> dict | None:
    if session is None:
        return None
    return {
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "duration_minutes": session.duration_minutes,
        "efficiency": session.efficiency,
        "minutes_deep": session.minutes_deep,
        "minutes_light": session.minutes_light,
        "minutes_rem": session.minutes_rem,
        "minutes_awake": session.minutes_awake,
        "awakenings_count": session.awakenings_count,
    }


def latest_day_with_data(user) -> date | None:
    """The most recent day holding anything, so a dashboard opening on "today"
    at 6am - before the watch has synced - has something to show."""
    from . import rollups

    _, end = rollups.data_span(user)
    return end


# --------------------------------------------------------------------------
# Trends
# --------------------------------------------------------------------------


def trend(user, metric: str, start: date, end: date, *, window: int = 7) -> dict:
    """A daily series with a trailing moving average.

    Reads `DailyMetric` only - one row per day, whatever the underlying
    resolution was.
    """
    definition = resolve_metric(metric)
    if end < start:
        start, end = end, start
    if (end - start).days > MAX_TREND_DAYS:
        raise DomainError(f"Range too large; {MAX_TREND_DAYS} days is the maximum.")

    rows = list(
        DailyMetric.objects.filter(user=user)
        .series(metric, start, end)
        .values_list("local_date", "value")
    )

    values = [v for _, v in rows]
    points = [
        {"date": day, "value": value, "average": avg}
        for (day, value), avg in zip(rows, _moving_average(values, window), strict=True)
    ]
    return {
        "metric": definition.key,
        "label": definition.label,
        "unit": definition.unit,
        "start": start,
        "end": end,
        "window": window,
        "points": points,
        "count": len(points),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "mean": (sum(values) / len(values)) if values else None,
    }


def _moving_average(values: list[float], window: int) -> list[float | None]:
    """Trailing mean. `None` until there are enough points to fill the window,
    rather than averaging two days and calling it a seven-day trend."""
    if window < 2:
        return [None] * len(values)
    out: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        out.append(running / window if index >= window - 1 else None)
    return out


# --------------------------------------------------------------------------
# Intraday
# --------------------------------------------------------------------------


def intraday(user, metric: str, on: date) -> dict:
    """One day of minute samples for one metric.

    The only reader of `Sample`, and bounded to a single local day - at most
    1,440 points, which a browser charts without help.
    """
    definition = metric_defs.INTRADAY_BY_KEY.get(metric)
    if definition is None:
        raise UnknownMetric(f"{metric!r} has no intraday series")

    tz = timeutils.tz_for(user)
    lower = timeutils.utc_from_local_parts(on, time(0, 0), tz)
    upper = timeutils.utc_from_local_parts(on + timedelta(days=1), time(0, 0), tz)

    rows = (
        Sample.objects.filter(user=user, metric=metric, ts__gte=lower, ts__lt=upper)
        .order_by("ts")
        .values_list("ts", "value")
    )
    points = [{"at": ts, "value": value} for ts, value in rows]
    values = [p["value"] for p in points]
    return {
        "metric": definition.key,
        "label": definition.label,
        "unit": definition.unit,
        "date": on,
        "points": points,
        "count": len(points),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def trends(user, keys: list[str], start: date, end: date, *, window: int = 7) -> list[dict]:
    """Several metrics over one range, in one call.

    Exists because the deep-dive pages plot four to nine series at once and
    every one of them is a server-side `fetch` before the page can render. Nine
    sequential round trips is the difference between a page that appears and
    one that arrives in pieces; the queries themselves are all the same cheap
    index scan on `DailyMetric`.

    An unknown key is skipped rather than raising. The caller is a page asking
    for what it would like to draw, and one metric this archive has never held
    should leave a gap in the layout, not a 400 where the page was.
    """
    out = []
    for key in keys:
        try:
            out.append(trend(user, key, start, end, window=window))
        except UnknownMetric:
            continue
    return out


# --------------------------------------------------------------------------
# Heatmap
# --------------------------------------------------------------------------


def heatmap(user, *, days: int = 30) -> dict:
    """Every scored metric, one row per day, newest first.

    The trends page answers "which way is this one going"; this answers "what
    kind of day was that", which is a question about a dozen metrics at once and
    is unreadable as a dozen charts. A grid where a bad night and a bad step
    count sit side by side in the same row is the only layout that shows the
    two happening together.

    All the judgement lives in `scoring.py`. This function does the assembly:
    one query, one dict, and the arithmetic that turns a stored value into the
    unit a person reads it in.
    """
    days = max(1, min(days, 365))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)

    profile = Profile.objects.filter(user=user).first()
    column_set = scoring.columns_for(
        age=user.age_years,
        sex=user.sex,
        height_cm=profile.height_cm if profile else None,
    )

    # One query for every metric in the window, rather than one per column.
    # Fifteen columns over a year is fifteen index scans returning 5,000 rows
    # between them; as one `metric__in` it is a single scan of the same rows.
    wanted = {column.metric for column in column_set.columns if column.metric}
    wanted |= {source for column in column_set.columns for source in column.sources}
    by_day: dict[date, dict[str, float]] = {}
    for day, metric, value in DailyMetric.objects.filter(
        user=user, metric__in=wanted, local_date__gte=start, local_date__lte=end
    ).values_list("local_date", "metric", "value"):
        by_day.setdefault(day, {})[metric] = value

    rows = []
    for day in sorted(by_day, reverse=True):
        stored = by_day[day]
        cells = []
        scores = []
        for column in column_set.columns:
            value = _heatmap_value(column, stored, column_set.height_m)
            score = column.score(value) if value is not None else None
            if score is not None:
                scores.append(score)
            cells.append(
                {
                    "key": column.key,
                    "value": value,
                    "score": score,
                    "band": scoring.band_for(score),
                }
            )

        # An unweighted mean, and the tooltip says so. Any weighting would be an
        # opinion about whether a bad night outranks a missed walk, which is not
        # something the data supports and not something to bury in a constant.
        day_score = sum(scores) / len(scores) if scores else None
        rows.append(
            {
                "date": day,
                "score": day_score,
                "band": scoring.band_for(day_score),
                "scored_count": len(scores),
                "cells": cells,
            }
        )

    # Columns nobody has any data for are dropped rather than drawn empty. A
    # blood-pressure column of 90 blank cells is not information about blood
    # pressure, and it costs the columns that do have data their width.
    present = {cell["key"] for row in rows for cell in row["cells"] if cell["value"] is not None}
    columns = []
    for column in column_set.columns:
        if column.key not in present:
            continue
        scored = [
            cell["score"]
            for row in rows
            for cell in row["cells"]
            if cell["key"] == column.key and cell["score"] is not None
        ]
        columns.append(
            {
                "key": column.key,
                "label": column.label,
                "unit": column.unit,
                "places": column.places,
                "scored": column.scored,
                "evidence": column.evidence,
                "days": sum(
                    1
                    for row in rows
                    for cell in row["cells"]
                    if cell["key"] == column.key and cell["value"] is not None
                ),
                "mean_score": (sum(scored) / len(scored)) if scored else None,
            }
        )
    kept = {column["key"] for column in columns}
    for row in rows:
        row["cells"] = [cell for cell in row["cells"] if cell["key"] in kept]

    return {
        "start": start,
        "end": end,
        "days": days,
        "columns": columns,
        "rows": rows,
    }


def _heatmap_value(column, stored: dict[str, float], height_m: float | None) -> float | None:
    """One cell's value, in the unit its threshold is written in.

    The two derived columns are spelled out here rather than being expressed as
    data on the `Threshold`, because they are two different arithmetics - a
    ratio against a profile field, and a sum of two metrics - and a general
    little expression language for two cases is harder to read than the two
    cases.
    """
    if column.key == "bmi":
        weight = stored.get("weight_kg")
        # Guarded even though `columns_for` only adds the column when a height
        # exists: the two facts are set in different places and drifting apart
        # here would be a divide-by-zero on a page, not a test failure.
        if weight is None or not height_m:
            return None
        return weight / (height_m * height_m)
    if column.key == "active_minutes":
        parts = [stored[key] for key in column.sources if key in stored]
        # Absent, not zero, when neither bucket was reported. Summing to 0.0
        # here would score a day the watch spent on the bedside table as the
        # worst kind of sedentary.
        return sum(parts) if parts else None
    if column.metric is None:
        return None
    value = stored.get(column.metric)
    return None if value is None else value * column.scale


# --------------------------------------------------------------------------
# Habits
# --------------------------------------------------------------------------


def _completion_index(user, start: date | None = None, end: date | None = None):
    """(habit_id, name) -> the dates it was ticked, matched the forgiving way.

    Returns `(by_id, by_name)`, both mapping to sets of dates. Two indexes
    rather than one because a completion may carry the foreign key, the name,
    or - in the imported archive - a name whose capitalisation no longer
    matches the habit it belongs to. `_habits_for_day` already learned this the
    hard way: an exact string match reports "magnesium" against "Magnesium" as
    missed every single day, which turns a full year green into a full year
    blank.
    """
    rows = HabitCompletion.objects.filter(created_by=user, deleted_at__isnull=True)
    if start is not None:
        rows = rows.filter(local_date__gte=start)
    if end is not None:
        rows = rows.filter(local_date__lte=end)

    by_id: dict[object, set[date]] = {}
    by_name: dict[str, set[date]] = {}
    for habit_id, name, day in rows.values_list("habit_id", "habit_name", "local_date"):
        if habit_id:
            by_id.setdefault(habit_id, set()).add(day)
        if name:
            by_name.setdefault(name.strip().casefold(), set()).add(day)
    return by_id, by_name


def _streaks(done: set[date], today: date) -> tuple[int, int]:
    """(current, best) runs of consecutive days.

    The current streak is counted back from *yesterday* when today has not been
    ticked yet. Counting from today instead - which the dashboard did - reads a
    perfectly intact streak as zero every morning until the box is checked,
    which is precisely when someone looks at it for motivation. A day still in
    progress is not yet a missed day.
    """
    if not done:
        return 0, 0

    cursor = today if today in done else today - timedelta(days=1)
    current = 0
    while cursor in done:
        current += 1
        cursor -= timedelta(days=1)

    best = run = 1
    ordered = sorted(done)
    for previous, day in itertools.pairwise(ordered):
        run = run + 1 if (day - previous).days == 1 else 1
        best = max(best, run)

    return current, best


def habit_history(user, days: int = 30) -> dict:
    """The completion grid, streaks and recent rates for every live habit.

    One query for the habits and one for the completions, then everything is
    computed in memory: the grid alone is habits x days cells, and asking the
    database per cell is thousands of round trips for a table that fits in a
    few kilobytes.

    Streaks read the *whole* history, not the window - a 200-day streak is
    still 200 days long when the grid only shows a month of it.
    """
    days = max(1, min(days, 365))
    today = timeutils.local_date_of(_utcnow(), timeutils.tz_for(user))
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=offset) for offset in range(days)]

    habits = list(
        Habit.objects.filter(
            created_by=user, deleted_at__isnull=True, archived_at__isnull=True
        ).order_by("sort_order", "name")
    )
    by_id, by_name = _completion_index(user)

    week_ago = today - timedelta(days=6)
    month_ago = today - timedelta(days=29)

    out = []
    for habit in habits:
        done = by_id.get(habit.id, set()) | by_name.get(habit.name.strip().casefold(), set())
        current, best = _streaks(done, today)
        in_7 = sum(1 for d in done if week_ago <= d <= today)
        in_30 = sum(1 for d in done if month_ago <= d <= today)
        out.append(
            {
                "id": habit.id,
                "name": habit.name,
                "completed": [d in done for d in dates],
                "current_streak": current,
                "best_streak": best,
                "total": len(done),
                "rate_7": round(100.0 * in_7 / 7, 1),
                "rate_30": round(100.0 * in_30 / 30, 1),
            }
        )

    return {"start": start, "end": today, "dates": dates, "habits": out}


# --------------------------------------------------------------------------
# Diet
# --------------------------------------------------------------------------

#: Cap on the food log. Five hundred entries is roughly two months of a normal
#: day, and past that the page is a scroll nobody finishes - the search box is
#: the right tool, not a longer list.
DIET_LOG_LIMIT = 500


def diet_log(user, *, days: int = 30, search: str | None = None) -> dict:
    """The food log with its flags, the most-eaten items, and caffeine timing.

    Flags come from `foodflags`, applied here rather than stored - see that
    module for why. The caffeine slice is separate because the question it
    answers is about the clock, not the food: a coffee is unremarkable at 8am
    and worth noticing at 4pm.
    """
    from . import foodflags

    days = max(1, min(days, 3_650))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)

    rows = DietEntry.objects.filter(
        created_by=user,
        deleted_at__isnull=True,
        local_date__gte=start,
        local_date__lte=end,
    )
    term = (search or "").strip()
    if term:
        rows = rows.filter(name__icontains=term)

    entries = [
        {
            "id": e.id,
            "name": e.name,
            "at": e.occurred_at,
            "local_date": e.local_date,
            "flags": foodflags.flags_for(e.name),
        }
        for e in rows.order_by("-occurred_at")[:DIET_LOG_LIMIT]
    ]

    # Counted over the window rather than over the (capped, searched) log
    # above, so "most eaten" does not silently mean "most eaten among the
    # first five hundred rows that matched what you typed".
    counted = (
        DietEntry.objects.filter(
            created_by=user,
            deleted_at__isnull=True,
            local_date__gte=start,
            local_date__lte=end,
        )
        .values("name")
        .annotate(n=Count("id"))
        .order_by("-n", "name")[:30]
    )

    caffeine = [
        {"id": e["id"], "name": e["name"], "at": e["at"], "local_date": e["local_date"]}
        for e in entries
        if "caffeine" in e["flags"]
    ]

    return {
        "start": start,
        "end": end,
        "days": days,
        "search": term,
        "entries": entries,
        "top": [{"name": row["name"], "count": row["n"]} for row in counted],
        "caffeine": caffeine,
        "flag_catalogue": foodflags.catalogue(),
    }


# --------------------------------------------------------------------------
# Gut
# --------------------------------------------------------------------------

#: A Bristol score at or above this is the "bad day" the correlation is looking
#: for. 6 is loose, 7 is diarrhoea; 5 is common enough here to be a baseline
#: rather than an event.
LOOSE_BRISTOL = 6


def gut_detail(user, *, days: int = 30) -> dict:
    """Bristol scores over the window, and what was eaten before the bad days.

    **`suspects` is a frequency table, not a finding.** A food that appears
    before four bad days out of five looks damning until you notice it was
    eaten on ninety days out of ninety - so every row carries the count of
    days it was eaten at all, and the two numbers are shown together. Ranking
    on the bad-day count alone reliably indicts breakfast.

    "Before" means the day itself and the day before it, because that is the
    window a person can act on. Anything longer stops being a food diary and
    starts being an epidemiology study with one participant.
    """
    days = max(1, min(days, 3_650))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)

    entries = [
        {
            "id": e.id,
            "bristol": e.bristol,
            "notes": e.notes,
            "at": e.occurred_at,
            "local_date": e.local_date,
        }
        for e in BmEntry.objects.filter(
            created_by=user,
            deleted_at__isnull=True,
            local_date__gte=start,
            local_date__lte=end,
        ).order_by("-occurred_at")
    ]

    distribution = [
        {"bristol": score, "count": sum(1 for e in entries if e["bristol"] == score)}
        for score in range(1, 8)
    ]

    # Foods by day, over a window one day wider at the start so the day before
    # the earliest bad day still has its meals.
    foods_by_day: dict[date, list[str]] = {}
    for name, day in DietEntry.objects.filter(
        created_by=user,
        deleted_at__isnull=True,
        local_date__gte=start - timedelta(days=1),
        local_date__lte=end,
    ).values_list("name", "local_date"):
        foods_by_day.setdefault(day, []).append(name)

    bad_days = []
    for day in sorted({e["local_date"] for e in entries if e["bristol"] >= LOOSE_BRISTOL}):
        scores = [e["bristol"] for e in entries if e["local_date"] == day]
        preceding = foods_by_day.get(day - timedelta(days=1), []) + foods_by_day.get(day, [])
        bad_days.append(
            {
                "date": day,
                "worst": max(scores),
                "mean": round(sum(scores) / len(scores), 1),
                "foods": sorted(set(preceding)),
            }
        )

    bad_dates = {row["date"] for row in bad_days}
    eaten_on: dict[str, set[date]] = {}
    for day, names in foods_by_day.items():
        for name in names:
            eaten_on.setdefault(name.strip().lower(), set()).add(day)

    suspects = []
    for name, on_days in eaten_on.items():
        # A food is "before" a bad day if it was eaten that day or the one
        # before, which is the same window `bad_days` uses above.
        hits = sum(1 for bad in bad_dates if (bad in on_days or bad - timedelta(days=1) in on_days))
        if hits >= 2:
            suspects.append(
                {
                    "name": name,
                    "before_bad_days": hits,
                    "days_eaten": len(on_days),
                    "share": round(100.0 * hits / len(on_days), 1),
                }
            )
    suspects.sort(key=lambda row: (-row["before_bad_days"], -row["share"], row["name"]))

    return {
        "start": start,
        "end": end,
        "days": days,
        "entries": entries,
        "distribution": distribution,
        "bad_days": bad_days,
        "suspects": suspects[:25],
        "bad_day_count": len(bad_days),
    }


def bristol_daily(user, *, days: int = 90) -> dict:
    """How many of each Bristol score, per day.

    Separate from `gut_detail` and deliberately cheap: the trends page wants
    only this, and `gut_detail` loads every food entry in the window to build
    its suspect table - three years of meals to draw one column chart.

    Not derivable from `DailyMetric` either. That table holds one scalar per
    metric per day, and "two 4s and a 6" is three numbers; representing it
    there would mean seven new metric keys in a vocabulary that is a public
    contract, to serve one chart.

    Days with no observations are absent rather than zero-filled - the column
    chart draws a gap, which is honest, where a zero column would assert that
    nothing happened.
    """
    days = max(1, min(days, 3_650))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)

    rows = (
        BmEntry.objects.filter(
            created_by=user,
            deleted_at__isnull=True,
            local_date__gte=start,
            local_date__lte=end,
        )
        .values("local_date", "bristol")
        .annotate(n=Count("id"))
    )

    by_day: dict[date, list[int]] = {}
    for row in rows:
        counts = by_day.setdefault(row["local_date"], [0] * 7)
        # Bristol is 1-7 and the model constrains it, but a value outside that
        # would be an IndexError here rather than a wrong chart - clamp so a
        # bad row cannot take the page down.
        index = min(max(int(row["bristol"]), 1), 7) - 1
        counts[index] += row["n"]

    return {
        "start": start,
        "end": end,
        "days": days,
        "points": [
            {"date": day, "counts": counts, "total": sum(counts)}
            for day, counts in sorted(by_day.items())
        ],
    }


# --------------------------------------------------------------------------
# Body and fitness tests
# --------------------------------------------------------------------------


def body_history(user, *, days: int = 730) -> dict:
    """Tape-measure numbers and the functional self-tests.

    `height_cm` rides along because waist-to-height is the number worth reading
    and the waist alone cannot produce it. Absent height, the UI shows the
    measurements and omits the ratio rather than assuming a height.
    """
    days = max(1, min(days, 3_650))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)
    span = {"local_date__gte": start, "local_date__lte": end}
    live = {"created_by": user, "deleted_at__isnull": True}

    measurements = [
        {
            "id": m.id,
            "local_date": m.local_date,
            "waist_cm": m.waist_cm,
            "hips_cm": m.hips_cm,
            "neck_cm": m.neck_cm,
            "body_fat_pct": m.body_fat_pct,
            "notes": m.notes,
        }
        for m in BodyMeasurement.objects.filter(**live, **span).order_by("-local_date")
    ]

    tests = [
        {
            "id": t.id,
            "local_date": t.local_date,
            "grip_kg": t.grip_kg,
            "single_leg_balance_s": t.single_leg_balance_s,
            "sit_to_stand_reps": t.sit_to_stand_reps,
            "dead_hang_s": t.dead_hang_s,
            "notes": t.notes,
        }
        for t in FitnessTest.objects.filter(**live, **span).order_by("-local_date")
    ]

    profile = Profile.objects.filter(user=user).first()
    return {
        "start": start,
        "end": end,
        "days": days,
        "height_cm": profile.height_cm if profile else None,
        "measurements": measurements,
        "tests": tests,
    }


# --------------------------------------------------------------------------
# Labs
# --------------------------------------------------------------------------


def lab_history(user) -> list[dict]:
    """Every blood marker, grouped by name, each with its own history.

    Grouped on a case-folded key because `marker_name` is free text typed on a
    phone: "HDL", "hdl" and "Hdl " are one marker with three spellings, and
    grouping on the raw string draws three one-point charts instead of one
    chart with three points. The label shown is the most recent spelling, on
    the grounds that it is the one being used now.
    """
    rows = list(
        LabResult.objects.filter(created_by=user, deleted_at__isnull=True).order_by(
            "-taken_on", "marker_name"
        )
    )

    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.marker_key, []).append(row)

    out = []
    for key, results in grouped.items():
        # `rows` is newest-first, so the first element carries both the latest
        # value and the spelling to display.
        newest = results[0]
        values = [r.value for r in results]
        out.append(
            {
                "key": key,
                "name": newest.marker_name.strip(),
                "unit": newest.unit,
                "count": len(results),
                "latest_value": newest.value,
                "latest_on": newest.taken_on,
                "minimum": min(values),
                "maximum": max(values),
                "results": [
                    {
                        "id": r.id,
                        "taken_on": r.taken_on,
                        "value": r.value,
                        "unit": r.unit,
                        "notes": r.notes,
                    }
                    # Oldest-first, because this is what a chart plots.
                    for r in reversed(results)
                ],
            }
        )
    out.sort(key=lambda row: row["name"].lower())
    return out


# --------------------------------------------------------------------------
# Notes and documents
# --------------------------------------------------------------------------

NOTE_LIMIT = 200


def _note_body(content: str) -> str:
    """Plain text from a note, whichever format it was written in.

    The Android app changed `content` from plain text to a JSON block array
    partway through and did not migrate the old rows, so both shapes are in
    the table (see `Note`). Rendering the raw string shows a wall of
    `[{"t":"text","v":"…"}]` for every older note.
    """
    import json

    text = (content or "").strip()
    if not text.startswith("["):
        return content or ""
    try:
        blocks = json.loads(text)
    except (ValueError, TypeError):
        # Not the block format after all - a note that happens to open with a
        # bracket. Showing it verbatim is better than showing nothing.
        return content or ""
    return "\n".join(
        str(block.get("v", ""))
        for block in blocks
        if isinstance(block, dict) and block.get("t") == "text"
    ).strip()


def note_list(user, *, search: str | None = None, limit: int = NOTE_LIMIT) -> list[dict]:
    """Diary entries, newest first, optionally filtered.

    Search covers title and content. It runs against the raw `content`, block
    JSON and all, because the text a person typed is in there either way - the
    field names around it never match a search term.
    """
    rows = Note.objects.filter(created_by=user, deleted_at__isnull=True)
    term = (search or "").strip()
    if term:
        from django.db.models import Q

        rows = rows.filter(Q(title__icontains=term) | Q(content__icontains=term))

    return [
        {
            "id": note.id,
            "title": note.title,
            "body": _note_body(note.content),
            "at": note.occurred_at,
            "local_date": note.local_date,
        }
        for note in rows.order_by("-occurred_at")[: max(1, min(limit, 1_000))]
    ]


def doc_list(user, *, limit: int = NOTE_LIMIT) -> list[dict]:
    """Photographed documents - pathology results, scripts, referrals.

    `photo_path` is the on-device path from the export and is useless off the
    phone; `image_url` is null until the media backfill has matched a file to
    the row. The UI shows the row either way, because the date and title are
    the part worth keeping.
    """
    return [
        {
            "id": doc.id,
            "title": doc.title,
            "at": doc.occurred_at,
            "local_date": doc.local_date,
            "image_url": doc.photo.url if doc.photo else None,
        }
        for doc in Doc.objects.filter(created_by=user, deleted_at__isnull=True).order_by(
            "-occurred_at"
        )[: max(1, min(limit, 1_000))]
    ]


# --------------------------------------------------------------------------
# Office days
# --------------------------------------------------------------------------


def office_days(user, *, year: int | None = None) -> dict:
    """The days worked in the office, for one calendar year.

    Absence means unknown, not work-from-home - see `OfficeDay`. `covers_from`
    and `covers_to` are the bounds of the whole record, so the UI can say which
    part of the year the data actually speaks for instead of drawing a blank
    January that means "no data" and looks like "never went in".
    """
    tz = timeutils.tz_for(user)
    today = timeutils.local_date_of(_utcnow(), tz)

    rows = OfficeDay.objects.filter(created_by=user, deleted_at__isnull=True)
    bounds = rows.aggregate(first=Min("local_date"), last=Max("local_date"))
    year = year or (bounds["last"].year if bounds["last"] else today.year)

    days = sorted(
        rows.filter(local_date__year=year).values_list("local_date", flat=True),
    )

    by_month = [
        {"month": month, "count": sum(1 for d in days if d.month == month)}
        for month in range(1, 13)
    ]

    years = sorted(
        {d.year for d in rows.values_list("local_date", flat=True).distinct()}, reverse=True
    )

    return {
        "year": year,
        "years": years,
        "days": days,
        "by_month": by_month,
        "total": len(days),
        "covers_from": bounds["first"],
        "covers_to": bounds["last"],
    }


# --------------------------------------------------------------------------
# Sleep
# --------------------------------------------------------------------------


def sleep_history(user, *, days: int = 30) -> dict:
    """Main sleep sessions, newest first, with their stage breakdowns.

    Reads `SleepSession` rather than the `sleep_*` daily metrics because the
    stages have to add up: the rollup stores each stage as its own row, and
    reassembling five independent metrics into one night's bar re-introduces
    exactly the mismatch the session row already resolves.

    Naps are excluded. They are real, but this page answers "how did I sleep
    last night", and a 20-minute afternoon nap listed beside a 7-hour night
    makes the list unreadable.
    """
    days = max(1, min(days, 365))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)

    sessions = [
        {
            "id": s.id,
            "local_date": s.local_date,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "duration_minutes": s.duration_minutes,
            "efficiency": s.efficiency,
            "minutes_deep": s.minutes_deep,
            "minutes_light": s.minutes_light,
            "minutes_rem": s.minutes_rem,
            "minutes_awake": s.minutes_awake,
            "awakenings_count": s.awakenings_count,
            "sleep_score": s.sleep_score,
            # So the list can link only the nights that have a chronology to
            # show. Nights synced before `SleepSegment` existed have totals and
            # nothing else, and a link to an empty hypnogram is a dead end.
            "has_hypnogram": s.has_hypnogram,
        }
        for s in SleepSession.objects.filter(
            user=user, is_main_sleep=True, local_date__gte=start, local_date__lte=end
        )
        .annotate(
            has_hypnogram=Exists(
                SleepSegment.objects.filter(session=OuterRef("pk"), is_short=False)
            )
        )
        .order_by("-local_date")
    ]

    from . import nights

    return {
        "start": start,
        "end": end,
        "days": days,
        "sessions": _with_scored_cells(user, sessions, start, end),
        "columns": [
            {
                "key": column.key,
                "label": column.label,
                "unit": column.unit,
                "places": column.places,
                "evidence": column.evidence,
            }
            for column in nights.TABLE_COLUMNS
        ],
        "summary": nights.summary(user, start=start, end=end),
    }


def _with_scored_cells(user, sessions: list[dict], start: date, end: date) -> list[dict]:
    """Attach the scored cells each night's table row is drawn from.

    The same thresholds the heatmap page colours by, applied to the columns a
    sleep table wants. Scoring here rather than in the browser keeps one
    definition of "good" across the REST response, the page and any MCP answer
    - three surfaces that must not be able to disagree about whether a night
    was fine.
    """
    from . import nights

    wanted = {column.metric for column in nights.TABLE_COLUMNS if column.metric}
    by_day: dict[date, dict[str, float]] = {}
    for day, metric, value in DailyMetric.objects.filter(
        user=user, metric__in=wanted, local_date__gte=start, local_date__lte=end
    ).values_list("local_date", "metric", "value"):
        by_day.setdefault(day, {})[metric] = value

    for session in sessions:
        session["cells"] = nights.table_cells(session, by_day.get(session["local_date"], {}))
    return sessions


def night(user, on: date) -> dict:
    """One night in full - see `nights.detail`."""
    from . import nights

    found = nights.detail(user, on)
    if found is None:
        raise NotFound(f"No sleep session recorded for {on}.")
    return found


# --------------------------------------------------------------------------
# Heart
# --------------------------------------------------------------------------


def heart_day(user, on: date) -> dict:
    """One day's trace with its zones - see `heart.day`.

    No 404 for an empty day, unlike `night`. A night with no session is a
    missing measurement worth reporting as one; a day with no minute samples is
    ordinary - the intraday fetch only covers days Fitbit was asked for - and
    the page still has zones, a resting heart rate and a date to show.
    """
    from . import heart

    return heart.day(user, on)


def heart_history(user, *, days: int = 30) -> dict:
    """Recovery series with baselines, and the scored table - see `heart.history`."""
    from . import heart

    return heart.history(user, days=days)


def latest_day_with_intraday(user, metric: str = "hr") -> date | None:
    """The most recent local date holding minute samples.

    The day view defaults here rather than to today. Opening the page before
    the watch has synced - or on any day the intraday fetch skipped - would
    otherwise draw an empty plot, which is indistinguishable from a broken one.
    """
    tz = timeutils.tz_for(user)
    latest = (
        Sample.objects.filter(user=user, metric=metric).order_by("-ts").values_list("ts", flat=True)
    ).first()
    return timeutils.local_date_of(latest, tz) if latest else None


# --------------------------------------------------------------------------
# Activity
# --------------------------------------------------------------------------


def activity_history(user, *, days: int = 30, logged: bool = True) -> dict:
    """Steps with their intensity, the overlays and the scored table.

    `logged` bolts the workout library onto the same response. The page draws
    both, and two requests for one screen is how the numbers on it end up
    disagreeing about which window they cover.
    """
    from . import activity

    out = activity.history(user, days=days)
    out["logged"] = activity_detail(user, days=days) if logged else None
    return out


def activity_day(user, on: date) -> dict:
    """One day's step climb and its hours - see `activity.day`.

    No 404 for an empty day, for the reason `heart_day` gives: a day with no
    minute samples is ordinary, and the page still has a total, a goal and a
    date to show.
    """
    from . import activity

    return activity.day(user, on)


def activity_detail(user, *, days: int = 90) -> dict:
    """Logged workouts: what was done, and how it groups into weeks.

    Weeks start on Monday, matching `date.isocalendar`, so a week here is the
    same week the rest of the world means. The bucket is keyed by the Monday's
    date rather than by "2026-W23", because a chart axis has to sort and label
    it and an ISO week string does neither well.
    """
    days = max(1, min(days, 3_650))
    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = end - timedelta(days=days - 1)

    rows = ExerciseEntry.objects.filter(
        created_by=user,
        deleted_at__isnull=True,
        local_date__gte=start,
        local_date__lte=end,
    ).values_list("video_name", "duration_s", "local_date")

    by_type: dict[str, dict] = {}
    by_week: dict[date, dict] = {}
    for name, duration_s, day in rows:
        entry = by_type.setdefault(name, {"name": name, "count": 0, "minutes": 0.0})
        entry["count"] += 1
        entry["minutes"] += (duration_s or 0) / 60.0

        monday = day - timedelta(days=day.weekday())
        week = by_week.setdefault(monday, {"week": monday, "minutes": 0.0, "sessions": 0})
        week["minutes"] += (duration_s or 0) / 60.0
        week["sessions"] += 1

    types = sorted(by_type.values(), key=lambda row: (-row["count"], row["name"]))
    for row in types:
        row["minutes"] = round(row["minutes"], 1)

    weeks = [
        {**row, "minutes": round(row["minutes"], 1)}
        for row in sorted(by_week.values(), key=lambda row: row["week"])
    ]

    return {
        "start": start,
        "end": end,
        "days": days,
        "by_type": types[:25],
        "weekly": weeks,
        "sessions": sum(row["count"] for row in types),
        "minutes": round(sum(row["minutes"] for row in types), 1),
    }


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


class UnknownEntryKind(DomainError, ValueError):
    """The requested entry type is not one this app records."""

    title = "Unknown entry kind"


def log_entry(
    user,
    *,
    kind: str,
    value: float | None = None,
    text: str = "",
    systolic: int | None = None,
    diastolic: int | None = None,
    on: date | None = None,
):
    """Record one hand-logged entry and refresh the day's rollup.

    Returns (entry, human summary). The rollup runs inline rather than on the
    queue: a value logged from the chat that does not appear on the chart until
    the nightly job would read as the write having failed.
    """
    from . import rollups
    from .models import BmEntry, BpEntry, DietEntry, Note, WeightEntry

    tz = timeutils.tz_for(user)
    now = _utcnow()
    local_date = on or timeutils.local_date_of(now, tz)
    # A backdated entry keeps a real instant on the day it is filed under,
    # rather than pretending it happened at the moment it was typed.
    occurred_at = now if on is None else timeutils.utc_from_local_parts(on, time(12, 0), tz)

    common = {"created_by": user, "occurred_at": occurred_at, "local_date": local_date}
    kind = (kind or "").strip().lower()

    if kind == "weight":
        if value is None:
            raise UnknownEntryKind("A weight entry needs a value in kilograms.")
        entry = WeightEntry.objects.create(**common, weight_kg=float(value), notes=text)
        summary = f"{value} kg"
    elif kind == "bp":
        if systolic is None or diastolic is None:
            raise UnknownEntryKind("A blood pressure entry needs systolic and diastolic.")
        entry = BpEntry.objects.create(
            **common, systolic=int(systolic), diastolic=int(diastolic), notes=text
        )
        summary = f"{systolic}/{diastolic} mmHg"
    elif kind == "bm":
        if value is None or not 1 <= int(value) <= 7:
            raise UnknownEntryKind("A gut entry needs a Bristol value from 1 to 7.")
        entry = BmEntry.objects.create(**common, bristol=int(value), notes=text)
        summary = f"Bristol {int(value)}"
    elif kind == "food":
        if not text.strip():
            raise UnknownEntryKind("A food entry needs a name.")
        entry = DietEntry.objects.create(**common, name=text.strip()[:255])
        summary = text.strip()[:255]
    elif kind == "note":
        if not text.strip():
            raise UnknownEntryKind("A note needs some text.")
        entry = Note.objects.create(**common, title=text.strip()[:60], content=text)
        summary = text.strip()[:60]
    else:
        raise UnknownEntryKind(
            f"{kind!r} is not something this app records. Use weight, bp, bm, food or note."
        )

    record_event(verb=f"health.{kind}.logged", actor=user, target=entry, summary=summary)
    rollups.rebuild(user, local_date, local_date)
    return entry, summary


def log_exercise(user, *, video_name: str, duration_s: int, at=None):
    """Record one completed workout session.

    Called by `apps.fitness` when a clip is finished. It lives here, not there,
    because `ExerciseEntry` lives here: the importer, the daily rollups and the
    MCP tools all read it, and a second app reaching into this one's ORM is how
    those four callers start to disagree about what an exercise session is.
    """
    from . import rollups
    from .models import ExerciseEntry

    name = (video_name or "").strip()[:255] or "Unknown"
    seconds = max(0, int(duration_s or 0))

    tz = timeutils.tz_for(user)
    occurred_at = at or _utcnow()
    local_date = timeutils.local_date_of(occurred_at, tz)

    entry = ExerciseEntry.objects.create(
        created_by=user,
        occurred_at=occurred_at,
        local_date=local_date,
        video_name=name,
        duration_s=seconds,
    )
    record_event(
        verb="health.exercise.logged",
        actor=user,
        target=entry,
        summary=name,
        duration_s=seconds,
    )
    # Inline, like log_entry: a session that does not move the chart until the
    # nightly job reads as the workout not having counted.
    rollups.rebuild(user, local_date, local_date)
    return entry


def _utcnow():
    from django.utils import timezone as dj_timezone

    return dj_timezone.now()


# --------------------------------------------------------------------------
# Phone sync
# --------------------------------------------------------------------------


class _Batch:
    """Per-row outcomes for one sync request.

    Per-row rather than all-or-nothing, and this is the whole point of the
    endpoint. The phone's queue is the only copy of anything it has not yet
    sent, so a batch that fails as a unit because of one unreadable date would
    strand forty good entries behind it indefinitely. Each row is accepted or
    rejected on its own and named in the reply.
    """

    def __init__(self):
        self.accepted: list[str] = []
        self.rejected: list[dict] = []
        self.counts = dict.fromkeys(("created", "updated", "unchanged", "deleted"), 0)

    def record(self, client_id: str, merge_fn, *args) -> bool:
        """Run one row's merge. Returns whether it was stored."""
        try:
            outcome = merge_fn(*args)
        except devicesync.Rejected as exc:
            self.rejected.append({"id": client_id, "reason": exc.reason})
            return False
        self.accepted.append(client_id)
        self.counts[str(outcome)] += 1
        return True

    def reject(self, client_id: str, reason: str) -> None:
        self.rejected.append({"id": client_id, "reason": reason})

    def as_dict(self) -> dict:
        return {"accepted": self.accepted, "rejected": self.rejected, **self.counts}


def ingest_gym(user, *, exercises: list[dict], sets: list[dict]) -> dict:
    """Store a batch of gym rows from the phone.

    Exercises are merged before sets so a set can link to a catalogue row that
    arrived in the same request - the phone sends both together precisely
    because `GymSet.exercise` would otherwise be null on the first sync of a
    new movement.
    """
    from . import rollups
    from .models import GymExercise

    batch = _Batch()

    for row in exercises:
        batch.record(row["id"], _merge_gym_exercise, user, row)

    #: name -> catalogue row, resolved once after the merges above. A workout
    #: is thirty sets across five movements, so the per-row lookup this
    #: replaces was twenty-five queries that could only return something
    #: already in memory.
    catalogue = {e.name.lower(): e for e in GymExercise.objects.filter(created_by=user)}

    #: Days whose rollups this batch invalidates.
    touched: set[date] = set()

    for row in sets:
        day = timeutils.parse_date(row.get("date"))
        if day is None:
            # Deliberately a rejection, not a guess. Filing a set under the
            # wrong day is invisible; a named rejection is not.
            batch.reject(row["id"], f"unreadable date {row.get('date')!r}")
            continue
        if batch.record(row["id"], _merge_gym_set, user, row, day, catalogue):
            touched.add(day)

    # Inline, like log_entry: a set that syncs but does not move the gym volume
    # chart until the nightly job reads as the sync having failed. A backlog
    # cleared after a week away spans many days, so it is one rebuild over the
    # whole span rather than one per day.
    if touched:
        rollups.rebuild(user, min(touched), max(touched))

    if batch.accepted:
        record_event(
            verb="health.gym.synced",
            actor=user,
            summary=f"{len(batch.accepted)} gym rows from a device",
            rejected=len(batch.rejected),
            **batch.counts,
        )
    if batch.rejected:
        # A rejection is the one loss this design cannot rule out by itself:
        # the phone is told, but nobody is watching the phone.
        logger.warning(
            "gym sync rejected %d of %d rows for %s: %s",
            len(batch.rejected),
            len(exercises) + len(sets),
            user,
            batch.rejected[:5],
        )

    return batch.as_dict()


def _merge_gym_exercise(user, row: dict):
    from .models import GymExercise

    name = (row.get("name") or "").strip()[:128]
    if not name and not row.get("deleted"):
        raise devicesync.Rejected("exercise has no name")

    return devicesync.merge(
        GymExercise,
        user=user,
        client_id=row["id"],
        client_updated_at=timeutils.utc_from_epoch_ms(row.get("updated_at")),
        deleted=bool(row.get("deleted")),
        defaults={
            "name": name,
            "last_weight_kg": row.get("last_weight_kg"),
            "last_reps": row.get("last_reps"),
        },
    )


def _merge_gym_set(user, row: dict, day: date, catalogue: dict):
    from .models import GymSet

    name = (row.get("exercise_name") or "").strip()[:128]
    weight = float(row.get("weight_kg") or 0)
    reps = int(row.get("reps") or 0)

    return devicesync.merge(
        GymSet,
        user=user,
        client_id=row["id"],
        client_updated_at=timeutils.utc_from_epoch_ms(row.get("updated_at")),
        deleted=bool(row.get("deleted")),
        defaults={
            "local_date": day,
            "exercise_name": name,
            # Null when the movement was renamed on the phone and the
            # catalogue row has not caught up. The set still counts toward
            # volume; `exercise_name` is what the day view reads.
            "exercise": catalogue.get(name.lower()),
            "performed_at": timeutils.utc_from_epoch_ms(row.get("timestamp")),
            "weight_kg": weight,
            "reps": reps,
            "volume_kg": weight * reps,
        },
    )


def ingest_entries(user, payload: dict) -> dict:
    """Store a batch of hand-logged rows from the phone.

    The sibling of `ingest_gym` for every other entry type. Gym keeps its own
    endpoint because sets need the exercise catalogue resolved first; nothing
    here has that problem, so one endpoint covers the lot and
    `entrysync.SPECS` is the only place that knows the field names.
    """
    from . import entrysync, rollups

    batch = _Batch()
    touched = entrysync.ingest(user, payload, batch)

    # Inline, like ingest_gym: an entry that syncs but leaves the chart it
    # belongs on unchanged until the nightly job reads as the sync having
    # failed. One rebuild over the whole span, not one per day, because a
    # backlog cleared after a week away covers many days.
    if touched:
        rollups.rebuild(user, min(touched), max(touched))

    if batch.accepted:
        record_event(
            verb="health.entries.synced",
            actor=user,
            summary=f"{len(batch.accepted)} entries from a device",
            rejected=len(batch.rejected),
            **batch.counts,
        )
    if batch.rejected:
        logger.warning(
            "entry sync rejected %d rows for %s: %s",
            len(batch.rejected),
            user,
            batch.rejected[:5],
        )
    return batch.as_dict()
