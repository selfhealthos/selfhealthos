"""Merging the phone's hand-logged entries — everything except gym.

Gym went first and got its own endpoint (`services.ingest_gym`) because sets
need the exercise catalogue resolved before they can be linked. Nothing else
does: every remaining type is a flat row keyed by the phone's UUID, so they
share one endpoint and one table of specs rather than eleven near-identical
functions and eleven near-identical tests.

The protocol is the gym protocol, and the rules it exists to enforce are in
`devicesync`: `client_id` is identity, `client_updated_at` breaks ties, and a
delete is a tombstone. What this module adds is only the per-type mapping from
the phone's field names to the model's.

**Adding a type is adding a `_Spec` here**, plus a `SyncPayload` field on the
phone. Anything with a `local_date` that a chart reads must set `rollup=True`,
or the entry syncs and the chart it belongs on does not move until the nightly
job runs — which reads exactly like the sync having failed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from . import devicesync, timeutils
from .models import (
    BmEntry,
    BodyMeasurement,
    BpEntry,
    DietEntry,
    Doc,
    ExerciseEntry,
    FitnessTest,
    Habit,
    HabitCompletion,
    LabResult,
    Note,
    OfficeDay,
    WeightEntry,
)

logger = logging.getLogger(__name__)


class Rejected(devicesync.Rejected):
    """Re-exported so callers need only this module."""


def _text(row: dict, key: str, limit: int | None = None) -> str:
    """A string field, never None. Blank columns are `blank=True`, not nullable."""
    value = str(row.get(key) or "").strip()
    return value[:limit] if limit else value


def _number(row: dict, key: str) -> float | None:
    """A nullable float. Absent and unparseable both mean "not taken"."""
    value = row.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _whole(row: dict, key: str) -> int | None:
    value = _number(row, key)
    return None if value is None else int(value)


@dataclass(frozen=True)
class _Spec:
    """One syncable entry type.

    `build` maps a phone row to the model's own fields. The timing columns are
    added by `_defaults_for`, because getting `local_date` wrong is how an
    entry lands on the wrong day and nobody notices.
    """

    key: str
    model: type
    build: Callable[[dict], dict]
    #: OccurredEntry subclasses get `occurred_at` + `local_date` from the
    #: row's timestamp. The rest carry their own date column, named here.
    occurred: bool = True
    #: For non-occurred types: the model column, and the phone field holding a
    #: `YYYY-MM-DD` string for it.
    date_field: str = ""
    date_source: str = "date"
    #: Whether a row of this type invalidates that day's `DailyMetric`.
    rollup: bool = False
    #: Fields copied straight across with no transform.
    extra: dict = field(default_factory=dict)


SPECS: tuple[_Spec, ...] = (
    _Spec(
        key="diet",
        model=DietEntry,
        rollup=True,
        build=lambda row: {
            "name": _text(row, "name", 255),
            # The on-device path, kept but useless off-device. The photo itself
            # is uploaded separately; see `docs`/`diet` photo backfill.
            "photo_path": _text(row, "photo_path"),
        },
    ),
    _Spec(
        key="exercise",
        model=ExerciseEntry,
        rollup=True,
        build=lambda row: {
            "video_name": _text(row, "video_name", 255),
            "duration_s": max(0, _whole(row, "duration_s") or 0),
        },
    ),
    _Spec(
        key="notes",
        model=Note,
        build=lambda row: {
            "title": _text(row, "title", 255),
            "content": str(row.get("content") or ""),
        },
    ),
    _Spec(
        key="bm",
        model=BmEntry,
        rollup=True,
        build=lambda row: {
            "bristol": _bristol(row),
            "notes": str(row.get("notes") or ""),
        },
    ),
    _Spec(
        key="bp",
        model=BpEntry,
        rollup=True,
        build=lambda row: {
            "systolic": _required_whole(row, "systolic"),
            "diastolic": _required_whole(row, "diastolic"),
            "notes": str(row.get("notes") or ""),
        },
    ),
    _Spec(
        key="weight",
        model=WeightEntry,
        rollup=True,
        build=lambda row: {
            "weight_kg": _required_number(row, "weight_kg"),
            "notes": str(row.get("notes") or ""),
        },
    ),
    _Spec(
        key="body",
        model=BodyMeasurement,
        build=lambda row: {
            "waist_cm": _number(row, "waist_cm"),
            "hips_cm": _number(row, "hips_cm"),
            "neck_cm": _number(row, "neck_cm"),
            "body_fat_pct": _number(row, "body_fat_pct"),
            "notes": str(row.get("notes") or ""),
        },
    ),
    _Spec(
        key="fitness",
        model=FitnessTest,
        build=lambda row: {
            "grip_kg": _number(row, "grip_kg"),
            "single_leg_balance_s": _number(row, "single_leg_balance_s"),
            "sit_to_stand_reps": _whole(row, "sit_to_stand_reps"),
            "dead_hang_s": _number(row, "dead_hang_s"),
            "notes": str(row.get("notes") or ""),
        },
    ),
    _Spec(
        key="docs",
        model=Doc,
        build=lambda row: {
            "title": _text(row, "title", 255),
            "photo_path": _text(row, "photo_path"),
        },
    ),
    # --- types carrying their own date rather than an instant --------------
    _Spec(
        key="labs",
        model=LabResult,
        occurred=False,
        date_field="taken_on",
        date_source="date",
        build=lambda row: {
            "marker_name": _text(row, "marker_name", 128) or _reject("missing marker name"),
            "value": _required_number(row, "value"),
            "unit": _text(row, "unit", 32),
            "notes": str(row.get("notes") or ""),
        },
    ),
    _Spec(
        key="office_days",
        model=OfficeDay,
        occurred=False,
        date_field="local_date",
        date_source="date",
        build=lambda row: {},
    ),
    _Spec(
        key="habit_completions",
        model=HabitCompletion,
        occurred=False,
        date_field="local_date",
        date_source="date",
        rollup=True,
        build=lambda row: {
            "habit_name": _text(row, "habit_name", 128),
            "completed_at": timeutils.utc_from_epoch_ms(row.get("completed_at")),
        },
    ),
    _Spec(
        key="habits",
        model=Habit,
        occurred=False,
        build=lambda row: {
            "name": _text(row, "name", 128) or _reject("missing habit name"),
            "sort_order": _whole(row, "sort_order") or 0,
            "archived_at": timeutils.utc_from_epoch_ms(row.get("archived_at")),
        },
    ),
)

SPECS_BY_KEY = {spec.key: spec for spec in SPECS}


def _reject(reason: str):
    raise Rejected(reason)


def _bristol(row: dict) -> int:
    value = _whole(row, "bristol")
    if value is None or not (1 <= value <= 7):
        # The column is a choice field, so an out-of-range value would raise on
        # save anyway - but as a 500, not as a named rejection the phone can
        # show. Checking here keeps the batch alive and says which row it was.
        raise Rejected(f"bristol must be 1-7, got {row.get('bristol')!r}")
    return value


def _required_number(row: dict, key: str) -> float:
    value = _number(row, key)
    if value is None:
        raise Rejected(f"missing {key}")
    return value


def _required_whole(row: dict, key: str) -> int:
    return int(_required_number(row, key))


def _defaults_for(spec: _Spec, row: dict, user) -> tuple[dict, date | None]:
    """The model fields for one row, plus the day its rollup belongs to."""
    defaults = spec.build(row)

    if spec.occurred:
        occurred_at = timeutils.utc_from_epoch_ms(row.get("timestamp"))
        if occurred_at is None:
            raise Rejected(f"unreadable timestamp {row.get('timestamp')!r}")
        day = timeutils.local_date_of(occurred_at, timeutils.tz_for(user))
        defaults["occurred_at"] = occurred_at
        defaults["local_date"] = day
        return defaults, day

    if spec.date_field:
        day = timeutils.parse_date(row.get(spec.date_source))
        if day is None:
            # A guess would file the entry under the wrong day invisibly; a
            # named rejection is loud. Same reasoning as the gym importer.
            raise Rejected(f"unreadable date {row.get(spec.date_source)!r}")
        defaults[spec.date_field] = day
        return defaults, day

    # Habits have no date at all - a definition, not an observation.
    return defaults, None


def ingest(user, payload: dict, batch) -> set[date]:
    """Merge every type present in `payload`. Returns the days to re-roll.

    `batch` is `services._Batch`; it collects the per-row outcomes that become
    the reply. Unknown keys are ignored rather than rejected, so a newer phone
    sending a type this server has not learned about yet degrades to "that type
    stays queued" instead of failing the whole request.
    """
    touched: set[date] = set()

    # Habits before completions, so a completion can link to a definition that
    # arrived in the same request - the same ordering problem gym has with its
    # exercise catalogue.
    for spec in SPECS:
        rows = payload.get(spec.key) or []
        for row in rows:
            client_id = str(row.get("id") or "")
            try:
                defaults, day = _defaults_for(spec, row, user)
            except Rejected as exc:
                batch.reject(client_id, exc.reason)
                continue

            # `_Batch.record` calls its merge function positionally, so the
            # keyword-heavy `devicesync.merge` is wrapped rather than passed.
            stored = batch.record(
                client_id,
                _merge_one,
                spec.model,
                user,
                client_id,
                row,
                defaults,
            )

            if stored and spec.rollup and day is not None:
                touched.add(day)

    _link_completions(user)
    return touched


def _merge_one(model, user, client_id: str, row: dict, defaults: dict):
    return devicesync.merge(
        model,
        user=user,
        client_id=client_id,
        client_updated_at=timeutils.utc_from_epoch_ms(row.get("updated_at")),
        deleted=bool(row.get("deleted")),
        defaults=defaults,
    )


def _link_completions(user) -> None:
    """Point completions at their habit definition where the names match.

    Done after the merges rather than per row: a completion can arrive before
    the habit that explains it, and `habit_name` is denormalised precisely so
    that the link being absent is a missing convenience rather than lost data.
    """
    habits = {h.name.lower(): h for h in Habit.objects.filter(created_by=user)}
    if not habits:
        return

    unlinked = HabitCompletion.objects.filter(created_by=user, habit__isnull=True)
    updates = []
    for completion in unlinked:
        habit = habits.get(completion.habit_name.lower())
        if habit is not None:
            completion.habit = habit
            updates.append(completion)
    if updates:
        HabitCompletion.objects.bulk_update(updates, ["habit"])
