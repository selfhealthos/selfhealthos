"""A markdown export of everything tracked, meant to be pasted into a
third-party AI chatbot - ChatGPT, Gemini, Claude, whichever - for the
person's own health insight.

This is deliberately *not* the H10-style in-portal chat some deployments
build: it calls no LLM itself, needs no API key, and produces one static
string. The design bet is that the person is going to paste this somewhere
external anyway, so the useful thing this module can do is make that paste
as information-dense and unambiguous as possible - one document, units on
every number, and the interpretive context (`MetricDef.description`) that
already lives on the metric catalogue rather than left for the reader to
look up.

**Layered on what already exists, not a new source of truth.** Every number
here comes from `DailyMetric`, the same rollup `office_report` and
`season_report` read - this module adds no new aggregation logic for
anything already shaped as a daily metric. What it adds is the handful of
things that never rolled up into a scalar because they are not one:
food names, workout names, individual lab results, habit streaks. Those are
read directly from their own tables, capped, most-recent-first.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

from . import metrics as metric_defs
from . import timeutils
from .models import (
    BodyMeasurement,
    DailyMetric,
    DietEntry,
    ExerciseEntry,
    FitnessTest,
    GymSet,
    Habit,
    LabResult,
    Profile,
)

#: Individual rows are read newest-first and capped here - long enough that a
#: few months of daily logging still fits, short enough that a paste into a
#: chat box stays a paste rather than a file upload.
RECENT_ENTRY_LIMIT = 60
RECENT_GYM_LIMIT = 60

#: Below this many days present in a bucket, a day-type or season comparison
#: is noise dressed as a pattern - three logged Tuesdays is not "you sleep
#: worse at the office". Matches the discipline `office_report` and
#: `season_report` already apply per metric (`len(present) < 2` is skipped
#: entirely); this is the additional bar for *featuring* a swing here rather
#: than merely not hiding it.
MIN_BUCKET_DAYS = 5
#: Only worth mentioning above this relative spread - see `office_report`'s
#: `swing_pct`. Below it, three numbers that are all basically the same are
#: not a pattern worth spending the reader's attention on.
MIN_SWING_PCT = 10
PATTERN_HIGHLIGHTS = 4


def _utcnow():
    from django.utils import timezone as dj_timezone

    return dj_timezone.now()


def build(user, *, days: int | None = None) -> dict:
    """Everything this user has tracked, as one markdown document.

    `days=None` is all-time, and is the sensible default for this specific
    report even though the callers it shares a window-selector UI with
    default shorter: an AI asked for health insight benefits from as much
    history as exists, not a recent slice, precisely because it does not
    already know the person the way they know themselves.
    """
    from . import rollups

    tz = timeutils.tz_for(user)
    end = timeutils.local_date_of(_utcnow(), tz)
    start = (
        (rollups.data_span(user)[0] or end)
        if days is None
        else end - timedelta(days=max(1, days) - 1)
    )

    sections = [
        _intro(user, start, end),
        _profile_section(user),
        _metrics_section(user, start, end),
        _body_section(user, start, end),
        _diet_section(user, start, end),
        _exercise_section(user, start, end),
        _gym_section(user, start, end),
        _labs_section(user),
        _habits_section(user, end),
        _patterns_section(user, days),
        _closing(),
    ]
    markdown = "\n\n".join(section for section in sections if section)

    return {"generated_at": _utcnow(), "start": start, "end": end, "markdown": markdown}


def _fmt(value: float, unit: str) -> str:
    rounded = round(value, 0 if abs(value) >= 100 else 1)
    if rounded == int(rounded):
        rounded = int(rounded)
    text = f"{rounded:,}"
    return f"{text} {unit}" if unit else text


def _intro(user, start: date, end: date) -> str:
    sex_word = {"male": "male", "female": "female", "other": "person"}.get(user.sex)
    age = user.age_years

    who = f"My name is {user.username}."
    if age is not None and sex_word:
        who += f" I am a {age} year old {sex_word}."
    elif age is not None:
        who += f" I am {age} years old."

    ask = (
        "I would like your help understanding my health: patterns you notice, "
        "anything worth paying attention to, and what you'd want to know more "
        "about before giving me advice."
    )

    profile = Profile.objects.filter(user=user).first()
    goal_line = ""
    if profile and profile.goals.strip():
        goal_line = f"\n\nWhat I'm trying to achieve: {profile.goals.strip()}"

    return (
        "# My health data\n\n"
        f"{who} {ask}{goal_line}\n\n"
        f"Below is data I've tracked from **{start.isoformat()}** to **{end.isoformat()}**, "
        "exported from my own self-hosted health tracker. Units are stated on every "
        "number; where a metric has an established normal range or interpretation, "
        "I've included it directly rather than making you look it up."
    )


def _profile_section(user) -> str:
    profile = Profile.objects.filter(user=user).first()
    lines = ["## Profile"]

    if profile and profile.height_cm:
        lines.append(f"- Height: {_fmt(profile.height_cm, 'cm')}")
    if profile and profile.target_weight_kg:
        lines.append(f"- Target weight: {_fmt(profile.target_weight_kg, 'kg')}")
    if profile and profile.daily_step_goal:
        lines.append(f"- Daily step goal: {profile.daily_step_goal:,}")
    if profile:
        lines.append(f"- Sleep target: {_fmt(profile.sleep_target_minutes, 'min')}")
    if profile and profile.dietary_restrictions.strip():
        lines.append(f"- Dietary restrictions: {profile.dietary_restrictions.strip()}")

    # Medical context is free text a person typed for exactly this purpose -
    # an AI they're about to ask for health insight - so it is included
    # without a separate opt-in. Left out entirely rather than shown empty:
    # an empty "Medications: (none)" line reads as "I checked, there are
    # none" when the truth is just as often "I never filled this in".
    medical = [
        ("Medical history", profile.medical_history if profile else ""),
        ("Family history", profile.family_history if profile else ""),
        ("Medications", profile.medications if profile else ""),
        ("Supplements", profile.supplements if profile else ""),
    ]
    medical_lines = [
        f"- {label}: {text.strip()}" for label, text in medical if text and text.strip()
    ]
    if medical_lines:
        lines.append("")
        lines.append("**Medical context**")
        lines.extend(medical_lines)

    return "\n".join(lines) if len(lines) > 1 else ""


def _metrics_section(user, start: date, end: date) -> str:
    """One row per tracked metric with data in the window: mean, min, max.

    Every number here already went through the rollup job's zero-vs-absent
    handling before it became a `DailyMetric` row (see the root CLAUDE.md's
    domain traps) - this just reads what is there, the same way
    `office_report` does.
    """
    rows = []
    for definition in metric_defs.DAILY:
        values = list(
            DailyMetric.objects.filter(user=user)
            .series(definition.key, start, end)
            .values_list("value", flat=True)
        )
        if not values:
            continue
        mean, lo, hi = fmean(values), min(values), max(values)
        line = (
            f"| {definition.label} | {_fmt(mean, definition.unit)} | "
            f"{_fmt(lo, definition.unit)} | {_fmt(hi, definition.unit)} | {len(values)} |"
        )
        rows.append((definition.description, line))

    if not rows:
        return ""

    lines = [
        "## Daily metrics",
        "Mean, minimum and maximum across every day a value was recorded in the window.",
        "",
        "| Metric | Mean | Min | Max | Days recorded |",
        "|---|---|---|---|---|",
    ]
    lines.extend(line for _, line in rows)

    return "\n".join(lines) + _metric_notes(rows)


def _metric_notes(rows: list[tuple[str, str]]) -> str:
    notes = [f"- {description}" for description, _line in rows if description]
    if not notes:
        return ""
    return "\n\nWhat these mean:\n" + "\n".join(notes)


def _body_section(user, start: date, end: date) -> str:
    latest_body = (
        BodyMeasurement.objects.filter(
            created_by=user, deleted_at__isnull=True, local_date__lte=end
        )
        .order_by("-local_date")
        .first()
    )
    latest_fitness = (
        FitnessTest.objects.filter(created_by=user, deleted_at__isnull=True, local_date__lte=end)
        .order_by("-local_date")
        .first()
    )
    if not latest_body and not latest_fitness:
        return ""

    lines = ["## Body measurements and fitness tests", "Most recent of each on file."]
    if latest_body:
        parts = []
        if latest_body.waist_cm:
            parts.append(f"waist {_fmt(latest_body.waist_cm, 'cm')}")
        if latest_body.hips_cm:
            parts.append(f"hips {_fmt(latest_body.hips_cm, 'cm')}")
        if latest_body.neck_cm:
            parts.append(f"neck {_fmt(latest_body.neck_cm, 'cm')}")
        if latest_body.body_fat_pct:
            parts.append(f"body fat {_fmt(latest_body.body_fat_pct, '%')}")
        profile = Profile.objects.filter(user=user).first()
        if latest_body.waist_cm and profile and profile.height_cm:
            ratio = latest_body.waist_cm / profile.height_cm
            parts.append(f"waist-to-height ratio {ratio:.2f}")
        if parts:
            lines.append(f"- **{latest_body.local_date.isoformat()}**: {', '.join(parts)}")
    if latest_fitness:
        parts = []
        if latest_fitness.grip_kg:
            parts.append(f"grip strength {_fmt(latest_fitness.grip_kg, 'kg')}")
        if latest_fitness.single_leg_balance_s:
            parts.append(f"single-leg balance {_fmt(latest_fitness.single_leg_balance_s, 's')}")
        if latest_fitness.sit_to_stand_reps:
            parts.append(f"sit-to-stand {latest_fitness.sit_to_stand_reps} reps")
        if latest_fitness.dead_hang_s:
            parts.append(f"dead hang {_fmt(latest_fitness.dead_hang_s, 's')}")
        if parts:
            lines.append(f"- **{latest_fitness.local_date.isoformat()}**: {', '.join(parts)}")

    return "\n".join(lines)


def _diet_section(user, start: date, end: date) -> str:
    rows = list(
        DietEntry.objects.filter(
            created_by=user, deleted_at__isnull=True, local_date__gte=start, local_date__lte=end
        )
        .order_by("-occurred_at")
        .values_list("local_date", "name")[:RECENT_ENTRY_LIMIT]
    )
    if not rows:
        return ""

    total = DietEntry.objects.filter(
        created_by=user, deleted_at__isnull=True, local_date__gte=start, local_date__lte=end
    ).count()
    lines = [
        "## Recent food log",
        f"{'Every entry' if total <= len(rows) else f'The {len(rows)} most recent of {total} entries'} "
        "in the window, newest first.",
        "",
    ]
    lines.extend(f"- {day.isoformat()}: {name}" for day, name in rows)
    return "\n".join(lines)


def _exercise_section(user, start: date, end: date) -> str:
    rows = list(
        ExerciseEntry.objects.filter(
            created_by=user, deleted_at__isnull=True, local_date__gte=start, local_date__lte=end
        )
        .order_by("-occurred_at")
        .values_list("local_date", "video_name", "duration_s")[:RECENT_ENTRY_LIMIT]
    )
    if not rows:
        return ""

    lines = ["## Recent workouts", "Newest first.", ""]
    lines.extend(
        f"- {day.isoformat()}: {name} ({round(duration_s / 60)} min)"
        for day, name, duration_s in rows
    )
    return "\n".join(lines)


def _gym_section(user, start: date, end: date) -> str:
    rows = list(
        GymSet.objects.filter(
            created_by=user, deleted_at__isnull=True, local_date__gte=start, local_date__lte=end
        )
        .order_by("-local_date", "-performed_at")
        .values_list("local_date", "exercise_name", "weight_kg", "reps")[:RECENT_GYM_LIMIT]
    )
    if not rows:
        return ""

    lines = [
        "## Recent gym sets",
        "Newest first - weight x reps per set, for spotting progression.",
        "",
    ]
    lines.extend(
        f"- {day.isoformat()}: {name} — {weight:g} kg x {reps}" for day, name, weight, reps in rows
    )
    return "\n".join(lines)


def _labs_section(user) -> str:
    results = LabResult.objects.filter(created_by=user, deleted_at__isnull=True).order_by(
        "marker_name", "-taken_on"
    )
    latest_by_marker: dict[str, LabResult] = {}
    for result in results:
        latest_by_marker.setdefault(result.marker_key, result)

    if not latest_by_marker:
        return ""

    lines = ["## Lab results", "Most recent value per marker."]
    for result in sorted(latest_by_marker.values(), key=lambda r: r.marker_name.lower()):
        unit = f" {result.unit}" if result.unit else ""
        lines.append(
            f"- **{result.marker_name}**: {result.value:g}{unit} (taken {result.taken_on.isoformat()})"
        )
    return "\n".join(lines)


def _habits_section(user, today: date) -> str:
    from .services import _completion_index, _streaks

    habits = list(
        Habit.objects.filter(
            created_by=user, deleted_at__isnull=True, archived_at__isnull=True
        ).order_by("sort_order", "name")
    )
    if not habits:
        return ""

    by_id, by_name = _completion_index(user)
    lines = [
        "## Habits",
        "Current streak = consecutive days up to and including yesterday if today isn't ticked yet.",
    ]
    for habit in habits:
        done = by_id.get(habit.id, set()) | by_name.get(habit.name.strip().casefold(), set())
        current, best = _streaks(done, today)
        lines.append(
            f"- **{habit.name}**: {current}-day current streak (best {best}), {len(done)} total completions"
        )
    return "\n".join(lines)


def _patterns_section(user, days: int | None) -> str:
    """The biggest already-computed swings from the WFH and Seasons reports.

    Reuses `office_report`/`season_report` rather than re-deriving anything -
    this section exists to surface what those pages have already found, not
    to compute a third version of the same comparison.
    """
    from .services import office_report, season_report

    lines: list[str] = []

    office = office_report(user, days=days)
    office_lines = _pattern_lines(
        office["metrics"], ("wfh", "office", "weekend"), ("WFH", "Office", "Weekend")
    )
    if office_lines:
        lines.append(
            "**Work-from-home vs. office vs. weekend** (see the Work From Home report for the rest):"
        )
        lines.extend(office_lines)

    seasons = season_report(user, days=days)
    season_lines = _pattern_lines(
        seasons["metrics"],
        ("summer", "autumn", "winter", "spring"),
        ("Summer", "Autumn", "Winter", "Spring"),
    )
    if season_lines:
        if lines:
            lines.append("")
        lines.append("**By season** (see the Seasons report for the rest):")
        lines.extend(season_lines)

    if not lines:
        return ""
    return "## Notable patterns already found\n\n" + "\n".join(lines)


def _pattern_lines(
    metrics: list[dict], bucket_keys: tuple[str, ...], bucket_labels: tuple[str, ...]
) -> list[str]:
    day_key_of = {k: f"{k}_days" for k in bucket_keys}
    candidates = [
        m
        for m in metrics
        if (m.get("swing_pct") or 0) >= MIN_SWING_PCT
        and all(
            m.get(day_key_of[k], 0) >= MIN_BUCKET_DAYS for k in bucket_keys if m.get(k) is not None
        )
    ]
    out = []
    for metric in candidates[:PATTERN_HIGHLIGHTS]:
        parts = [
            f"{label} {_fmt(metric[key], metric['unit'])}"
            for key, label in zip(bucket_keys, bucket_labels, strict=False)
            if metric.get(key) is not None
        ]
        out.append(f"- **{metric['label']}**: {' · '.join(parts)}")
    return out


def _closing() -> str:
    return (
        "## What I'd like from you\n\n"
        "Based on everything above: what patterns stand out, what would you want "
        "to know more about before giving me advice, and what would you suggest I "
        "focus on first?"
    )
