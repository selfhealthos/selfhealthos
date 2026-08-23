"""Deriving `DailyMetric` from everything else.

`DailyMetric` is the only table user-facing code reads, so this module decides
what a chart shows. It is entirely derived - dropping every row and recomputing
is always safe, which is what makes changing a metric's definition a re-run
rather than a migration.

**Ownership.** Three writers touch `DailyMetric` and they must not fight:

  * Rows with `source="device"` come from a wearable's own daily summary. They
    are authoritative and this module never touches them - Fitbit's resting
    heart rate is better than anything derivable from the minute samples it
    also supplied.
  * Rows with `source="derived"` are computed here, from entries, sleep
    sessions or samples. This module owns them completely: it overwrites them
    on every run and deletes the ones whose source data has gone.

The column is what makes that division work. Deciding by metric name instead
means a value computed from samples cannot be told apart from one the device
supplied, so the rollup must either clobber the device's numbers or freeze its
own the first time it writes them - and the second is the bug that is easy to
miss, because the data looks right until something upstream is corrected.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db.models import Avg, Count, Max, Min, Sum

from . import metrics, timeutils
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
    Sample,
    SleepSession,
    WeightEntry,
)

logger = logging.getLogger(__name__)


def rebuild(user, start: date, end: date) -> int:
    """Recompute every derived metric for `user` over an inclusive date range.

    Ownership runs off `DailyMetric.source`, not off a list of metric names:
    this function owns every `derived` row in the range and leaves every
    `device` row alone. Returns the number of rows written.
    """
    values: dict[tuple[date, str], float] = {}

    _from_entries(user, start, end, values)
    _from_sleep(user, start, end, values)
    _from_samples(user, start, end, values)
    _heart_extremes(user, start, end, values)

    if not values:
        _delete_stale(user, start, end, keep=set())
        return 0

    rows = [
        DailyMetric(
            user=user,
            local_date=day,
            metric=metric,
            value=value,
            source=DailyMetric.Source.DERIVED,
        )
        for (day, metric), value in sorted(values.items())
    ]
    DailyMetric.objects.bulk_create(
        rows,
        batch_size=5_000,
        update_conflicts=True,
        update_fields=["value", "source", "computed_at"],
        unique_fields=["user", "local_date", "metric"],
    )
    _delete_stale(user, start, end, keep=set(values))
    return len(rows)


def data_span(user) -> tuple[date | None, date | None]:
    """The full range of dates `user` has any health data for.

    Every source is consulted, not just the wearable's. Deriving the range from
    `Sample` and `DailyMetric` alone silently drops any day that was hand-logged
    outside the Fitbit coverage - a food diary entry the morning after the watch
    stopped syncing, or an office day recorded before it was first worn.
    """
    firsts: list[date] = []
    lasts: list[date] = []

    dated = (
        (BmEntry, "local_date"),
        (BpEntry, "local_date"),
        (BodyMeasurement, "local_date"),
        (DietEntry, "local_date"),
        (Doc, "local_date"),
        (ExerciseEntry, "local_date"),
        (FitnessTest, "local_date"),
        (GymSet, "local_date"),
        (HabitCompletion, "local_date"),
        (Note, "local_date"),
        (OfficeDay, "local_date"),
        (WeightEntry, "local_date"),
        (LabResult, "taken_on"),
    )
    for model, field in dated:
        bounds = model.objects.filter(created_by=user).aggregate(first=Min(field), last=Max(field))
        firsts.append(bounds["first"])
        lasts.append(bounds["last"])

    sleep = SleepSession.objects.filter(user=user).aggregate(
        first=Min("local_date"), last=Max("local_date")
    )
    firsts.append(sleep["first"])
    lasts.append(sleep["last"])

    daily = DailyMetric.objects.filter(user=user).aggregate(
        first=Min("local_date"), last=Max("local_date")
    )
    firsts.append(daily["first"])
    lasts.append(daily["last"])

    tz = timeutils.tz_for(user)
    samples = Sample.objects.filter(user=user).aggregate(first=Min("ts"), last=Max("ts"))
    firsts.append(timeutils.local_date_of(samples["first"], tz))
    lasts.append(timeutils.local_date_of(samples["last"], tz))

    present_first = [d for d in firsts if d is not None]
    present_last = [d for d in lasts if d is not None]
    if not present_first or not present_last:
        return None, None
    return min(present_first), max(present_last)


def rebuild_recent(user, days: int = 7) -> int:
    today = timeutils.local_date_of(_now(), timeutils.tz_for(user))
    return rebuild(user, today - timedelta(days=days - 1), today)


def _now():
    from django.utils import timezone

    return timezone.now()


def _delete_stale(user, start: date, end: date, *, keep: set[tuple[date, str]]) -> None:
    """Drop owned metrics whose source rows have gone.

    Without this, deleting the only weight entry for a day leaves the old
    `weight_kg` behind forever - a chart point with nothing underneath it.

    Scoped to `derived` rows: the device's own summaries are not this
    function's to delete.
    """
    existing = DailyMetric.objects.filter(
        user=user,
        local_date__gte=start,
        local_date__lte=end,
        source=DailyMetric.Source.DERIVED,
    ).values_list("id", "local_date", "metric")
    stale = [pk for pk, day, metric in existing if (day, metric) not in keep]
    if stale:
        DailyMetric.objects.filter(id__in=stale).delete()


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def _from_entries(user, start: date, end: date, out: dict) -> None:
    def put(day: date, metric: str, value) -> None:
        if value is not None:
            out[(day, metric)] = float(value)

    live = {"created_by": user, "deleted_at__isnull": True}
    span = {"local_date__gte": start, "local_date__lte": end}

    # Weight: the last reading of the day, not the mean. A morning and an
    # evening weigh-in are not two samples of one number.
    for row in (
        WeightEntry.objects.filter(**live, **span)
        .values("local_date")
        .annotate(latest=Max("occurred_at"))
    ):
        entry = (
            WeightEntry.objects.filter(
                **live, local_date=row["local_date"], occurred_at=row["latest"]
            )
            .only("weight_kg")
            .first()
        )
        if entry:
            put(row["local_date"], "weight_kg", entry.weight_kg)

    for row in (
        BpEntry.objects.filter(**live, **span)
        .values("local_date")
        .annotate(sys=Avg("systolic"), dia=Avg("diastolic"))
    ):
        put(row["local_date"], "systolic", row["sys"])
        put(row["local_date"], "diastolic", row["dia"])

    for row in (
        BmEntry.objects.filter(**live, **span)
        .values("local_date")
        .annotate(mean=Avg("bristol"), n=Count("id"))
    ):
        put(row["local_date"], "bristol_mean", row["mean"])
        put(row["local_date"], "bm_count", row["n"])

    for row in (
        DietEntry.objects.filter(**live, **span).values("local_date").annotate(n=Count("id"))
    ):
        put(row["local_date"], "diet_entries", row["n"])

    for row in (
        ExerciseEntry.objects.filter(**live, **span)
        .values("local_date")
        .annotate(seconds=Sum("duration_s"), n=Count("id"))
    ):
        put(row["local_date"], "exercise_minutes", round((row["seconds"] or 0) / 60.0, 1))
        put(row["local_date"], "exercise_sessions", row["n"])

    for row in (
        GymSet.objects.filter(**live, **span)
        .values("local_date")
        .annotate(volume=Sum("volume_kg"), n=Count("id"))
    ):
        put(row["local_date"], "gym_volume_kg", row["volume"])
        put(row["local_date"], "gym_sets", row["n"])

    for row in Note.objects.filter(**live, **span).values("local_date").annotate(n=Count("id")):
        put(row["local_date"], "note_count", row["n"])

    for row in OfficeDay.objects.filter(**live, **span).values("local_date"):
        put(row["local_date"], "office_day", 1)

    _habits(user, start, end, put)


def _habits(user, start: date, end: date, put) -> None:
    """A habit counts as done for a day if at least one completion exists.

    There can be several rows per habit per day - a second dose of something -
    so this is a distinct count, never a row count.
    """
    total = Habit.objects.filter(
        created_by=user, deleted_at__isnull=True, archived_at__isnull=True
    ).count()

    done = (
        HabitCompletion.objects.filter(
            created_by=user,
            deleted_at__isnull=True,
            local_date__gte=start,
            local_date__lte=end,
        )
        .values("local_date")
        .annotate(n=Count("habit_name", distinct=True))
    )
    for row in done:
        put(row["local_date"], "habits_completed", row["n"])
        put(row["local_date"], "habits_total", total)
        if total:
            put(row["local_date"], "habit_completion_pct", round(100.0 * row["n"] / total, 1))


def _from_sleep(user, start: date, end: date, out: dict) -> None:
    """The main sleep session only. Naps are real but they are not "last night"."""
    sessions = SleepSession.objects.filter(
        user=user, is_main_sleep=True, local_date__gte=start, local_date__lte=end
    ).order_by("local_date", "-duration_minutes")

    seen: set[date] = set()
    for session in sessions:
        if session.local_date in seen:
            continue
        seen.add(session.local_date)
        day = session.local_date
        out[(day, "sleep_minutes")] = float(session.duration_minutes)
        if session.efficiency is not None:
            out[(day, "sleep_efficiency")] = float(session.efficiency)
        out[(day, "sleep_deep_minutes")] = float(session.minutes_deep)
        out[(day, "sleep_light_minutes")] = float(session.minutes_light)
        out[(day, "sleep_rem_minutes")] = float(session.minutes_rem)
        out[(day, "sleep_awake_minutes")] = float(session.minutes_awake)
        out[(day, "sleep_awakenings")] = float(session.awakenings_count)


def _from_samples(user, start: date, end: date, out: dict) -> None:
    """Collapse intraday samples into daily values, filling gaps only.

    Bucketed in Python rather than SQL because the day a sample belongs to is a
    local-calendar question and the column is UTC: `date_trunc` would put every
    reading before 10am Melbourne on the previous day.
    """
    tz = timeutils.tz_for(user)
    #: Only the device's own daily summaries block a sample-derived value.
    #: Testing for *any* existing row instead would mean a value this function
    #: wrote on a previous run blocks itself forever, so a corrected sample
    #: import would never reach the chart.
    authoritative = set(
        DailyMetric.objects.filter(
            user=user,
            local_date__gte=start,
            local_date__lte=end,
            source=DailyMetric.Source.DEVICE,
        ).values_list("local_date", "metric")
    )

    # A local date range is a wider UTC range; pad both ends by a day so no
    # local midnight is clipped.
    lower = timeutils.utc_from_local_parts(start - timedelta(days=1), _midnight(), tz)
    upper = timeutils.utc_from_local_parts(end + timedelta(days=2), _midnight(), tz)

    totals: dict[tuple[date, str], float] = {}
    counts: dict[tuple[date, str], int] = {}

    rows = (
        Sample.objects.filter(user=user, ts__gte=lower, ts__lt=upper)
        .values_list("metric", "ts", "value")
        .iterator(chunk_size=10_000)
    )
    for metric_key, ts, value in rows:
        day = ts.astimezone(tz).date()
        if day < start or day > end:
            continue
        key = (day, metrics.daily_key_for(metric_key))
        totals[key] = totals.get(key, 0.0) + value
        counts[key] = counts.get(key, 0) + 1

    for key, total in totals.items():
        day, daily_key = key
        if (day, daily_key) in authoritative or (day, daily_key) in out:
            continue  # The device's own daily summary wins.
        definition = metrics.INTRADAY_BY_KEY.get(_intraday_key_for(daily_key))
        how = definition.agg if definition else "mean"
        out[key] = total / counts[key] if how == "mean" else total


def _heart_extremes(user, start: date, end: date, out: dict) -> None:
    """The day's lowest and highest minute of heart rate.

    Separate from `_from_samples` because that function collapses each intraday
    stream into exactly one daily value, chosen by the metric's `agg` - and the
    heart rate is the one stream three different daily metrics are read off.
    Expressing that as data would mean a stream declaring a list of
    (aggregation, destination) pairs to serve a single caller; the arithmetic
    written out is shorter and says what it does.

    Fitbit supplies neither of these. `min_hr` and `max_hr` existed in the
    vocabulary and were written only by the `one-data` archive importer, so
    every day synced live carried a blank where the archive had a number - the
    kind of gap that looks like missing history rather than a missing
    derivation.

    The mean is deliberately not written here: `_from_samples` already lands it
    through the generic path, and computing it twice under two keys would be
    two numbers that can disagree.
    """
    tz = timeutils.tz_for(user)
    authoritative = set(
        DailyMetric.objects.filter(
            user=user,
            local_date__gte=start,
            local_date__lte=end,
            metric__in=("min_hr", "max_hr"),
            source=DailyMetric.Source.DEVICE,
        ).values_list("local_date", "metric")
    )

    lower = timeutils.utc_from_local_parts(start - timedelta(days=1), _midnight(), tz)
    upper = timeutils.utc_from_local_parts(end + timedelta(days=2), _midnight(), tz)

    extremes: dict[date, tuple[float, float]] = {}
    rows = (
        Sample.objects.filter(user=user, metric="hr", ts__gte=lower, ts__lt=upper)
        .values_list("ts", "value")
        .iterator(chunk_size=10_000)
    )
    for ts, value in rows:
        day = ts.astimezone(tz).date()
        if day < start or day > end:
            continue
        found = extremes.get(day)
        extremes[day] = (
            (value, value) if found is None else (min(found[0], value), max(found[1], value))
        )

    for day, (lowest, highest) in extremes.items():
        for metric, value in (("min_hr", lowest), ("max_hr", highest)):
            if (day, metric) not in authoritative:
                out[(day, metric)] = value


def _intraday_key_for(daily_key: str) -> str:
    return {"distance_km": "distance", "calories_burned": "calories"}.get(daily_key, daily_key)


def _midnight():
    from datetime import time

    return time(0, 0)
