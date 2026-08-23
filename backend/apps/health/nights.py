"""One night, read the way a sleep study is read.

The rest of the app summarises a night into totals - seven hours, 22% deep,
average SpO2 96%. Those answer "how much"; none of them answer "what happened",
and the questions that matter clinically are all the second kind. Whether REM
came back every ninety minutes and lengthened towards morning. Whether the
oxygen dipped, when, and whether the heart rate moved with it. A total cannot
hold any of that: two hours of deep sleep in one early block and the same two
hours in eight-minute fragments are the same number and a different night.

So this module reads `SleepSegment` (the chronology) and `Sample` (the minutes)
and derives the indices a clinician would look for, each named after the thing
it actually is.

**What this is not.** Fitbit is a consumer wrist device, not a polysomnograph
and not a pulse oximeter. Its stages are inferred from movement and heart-rate
variability, and its SpO2 is a reflectance estimate averaged into one-minute
buckets. The desaturation count here is therefore *an estimate of dips visible
at one-minute resolution*, never an ODI - a real ODI is scored from continuous
oximetry at 1 Hz, and the brief dips that define sleep apnoea are exactly the
ones a one-minute average erases. Everything derived here is labelled that way
in the response, because a number that looks clinical and is not is worse than
no number at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import scoring, timeutils
from .models import DailyMetric, Sample, SleepSegment, SleepSession

#: Stages that mean "asleep". Everything else is time in bed, awake.
ASLEEP = frozenset(
    {
        SleepSegment.Level.DEEP,
        SleepSegment.Level.LIGHT,
        SleepSegment.Level.REM,
        SleepSegment.Level.ASLEEP,
        SleepSegment.Level.RESTLESS,
    }
)

#: Normal adult reference ranges, as percentages of total sleep time. From the
#: AASM scoring manual's normative values; they vary with age, and the point of
#: showing them is that a percentage means nothing without the range beside it.
STAGE_REFERENCE: dict[str, tuple[float, float]] = {
    "deep": (13.0, 23.0),
    "rem": (20.0, 25.0),
    "light": (45.0, 55.0),
}

#: Minutes. Two REM periods closer together than this are one period that was
#: briefly interrupted, which is how sleep studies score them - otherwise a
#: single stir mid-REM reports as two cycles and the architecture reads
#: fragmented when it was not.
REM_MERGE_GAP = 15

#: A drop of this many percentage points below the running baseline is what
#: counts as a dip. 3% is the threshold the AASM uses for a hypopnoea-linked
#: desaturation; 4% is the other convention, and both are reported.
DESAT_THRESHOLDS = (3.0, 4.0)

#: Minutes of preceding readings the baseline is taken from. A dip is a fall
#: from what the night was doing a moment ago, not from a whole-night average -
#: against a nightly mean, a slow shallow drift reads as a permanent
#: desaturation and a genuine sharp dip during a low patch reads as nothing.
BASELINE_WINDOW = 10


@dataclass(frozen=True)
class Span:
    """A run of one stage."""

    level: str
    started_at: datetime
    ended_at: datetime
    seconds: int
    is_short: bool

    @property
    def minutes(self) -> float:
        return self.seconds / 60


def detail(user, on: date) -> dict | None:
    """The whole night: hypnogram, aligned minute series, and the indices.

    `None` when there is no main sleep session for that date, which the API
    turns into a 404 - an empty hypnogram and a real one with nothing in it are
    different answers and should not render the same.
    """
    session = (
        SleepSession.objects.filter(user=user, local_date=on, is_main_sleep=True)
        .order_by("-duration_minutes")
        .first()
    )
    if session is None:
        return None

    segments = list(SleepSegment.objects.filter(session=session).order_by("started_at"))
    spans = [
        Span(
            level=row.level,
            started_at=row.started_at,
            ended_at=row.ended_at,
            seconds=row.seconds,
            is_short=row.is_short,
        )
        for row in segments
    ]
    main = [span for span in spans if not span.is_short]

    # The minute series are clipped to the session rather than the day: the
    # question this page asks is what happened *during* the night, and a full
    # day of heart rate on the same axis compresses the eight hours that matter
    # into a third of the width.
    series = {
        key: _samples(user, key, session.started_at, session.ended_at) for key in ("hr", "spo2")
    }

    shape = architecture(main)
    oxygen_read = oxygen(series["spo2"])
    against = baseline(user, on)

    return {
        "date": on,
        # Not optional. A server component renders in UTC, and formatting a
        # 23:14 bedtime there puts lights-out at 13:14 the same afternoon -
        # the same trap `HealthDayOut` carries a timezone to avoid.
        "timezone": str(timeutils.tz_for(user)),
        "session": {
            "id": session.id,
            "local_date": session.local_date,
            "sleep_score": session.sleep_score,
            "has_hypnogram": bool(main),
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "duration_minutes": session.duration_minutes,
            "efficiency": session.efficiency,
            "minutes_deep": session.minutes_deep,
            "minutes_light": session.minutes_light,
            "minutes_rem": session.minutes_rem,
            "minutes_awake": session.minutes_awake,
            "awakenings_count": session.awakenings_count,
        },
        "segments": [
            {
                "level": span.level,
                "started_at": span.started_at,
                "ended_at": span.ended_at,
                "seconds": span.seconds,
                "is_short": span.is_short,
            }
            for span in spans
        ],
        "series": series,
        "architecture": shape,
        "oxygen": oxygen_read,
        "heart": _heart(series["hr"]),
        "baseline": against,
        "verdict": verdict(session, against, oxygen_read),
        "signals": signals(session, shape, oxygen_read),
        "context": _context(user, on),
        "has_hypnogram": bool(main),
        "neighbours": neighbours(user, on),
    }


def neighbours(user, on: date) -> dict:
    """The recorded nights either side of this one, and the newest of all.

    Stepping by a calendar day would be wrong: a night the watch was off has
    no session, so `on - 1` is a 404 as often as not and the arrows would
    dead-end on exactly the gaps a person is trying to page past. These are
    the adjacent *recorded* dates, so every arrow that renders leads somewhere.

    `latest` is here because paging away from the newest night otherwise
    strands you - the "Last night" tab links to whatever date is on screen,
    which is only "last night" on the first page.
    """
    dates = SleepSession.objects.filter(user=user, is_main_sleep=True)
    return {
        "previous": dates.filter(local_date__lt=on)
        .order_by("-local_date")
        .values_list("local_date", flat=True)
        .first(),
        "next": dates.filter(local_date__gt=on)
        .order_by("local_date")
        .values_list("local_date", flat=True)
        .first(),
        "latest": dates.order_by("-local_date").values_list("local_date", flat=True).first(),
    }


def _samples(user, metric: str, start: datetime, end: datetime) -> list[dict]:
    rows = (
        Sample.objects.filter(user=user, metric=metric, ts__gte=start, ts__lte=end)
        .order_by("ts")
        .values_list("ts", "value")
    )
    return [{"at": ts, "value": value} for ts, value in rows]


# --------------------------------------------------------------------------
# The night against its own history
# --------------------------------------------------------------------------
#
# A duration on its own is not a fact anyone can act on. Seven hours is a good
# night for one person and a short one for the next, and the only two things
# that make it legible are the target and what this sleeper usually gets. Both
# live here so the page can state a delta instead of a number.

#: Days of history the comparison is drawn from. Long enough to absorb one bad
#: week, short enough that a change of habit shows up inside a month.
BASELINE_DAYS = 30

#: Below this many recorded nights the average is not worth stating. Two nights
#: is not a personal norm, and "38 minutes above your average" computed from
#: two nights is a sentence with false authority.
BASELINE_MINIMUM_NIGHTS = 5


def target_minutes(user) -> int:
    from .models import Profile

    profile = Profile.objects.filter(user=user).first()
    return profile.sleep_target_minutes if profile else 450


def baseline(user, on: date, *, days: int = BASELINE_DAYS) -> dict:
    """What this sleeper's recent nights actually look like.

    Averaged over *recorded* nights, never over elapsed days. A watch left on
    the charger is a missing measurement, and counting it as a night of no
    sleep would drag every average down and invent a decline that never
    happened. `nights_recorded` and `coverage_nights` are both returned so the
    page can say which it is.
    """
    window_start = on - timedelta(days=days)
    rows = list(
        SleepSession.objects.filter(
            user=user,
            is_main_sleep=True,
            local_date__gte=window_start,
            local_date__lt=on,
        ).values_list("duration_minutes", "efficiency")
    )
    durations = [duration for duration, _ in rows if duration]
    efficiencies = [efficiency for _, efficiency in rows if efficiency]
    enough = len(durations) >= BASELINE_MINIMUM_NIGHTS

    return {
        "days": days,
        "nights_recorded": len(durations),
        "coverage_nights": days,
        "target_minutes": target_minutes(user),
        "mean_duration_minutes": (round(sum(durations) / len(durations)) if enough else None),
        "mean_efficiency": (
            round(sum(efficiencies) / len(efficiencies)) if efficiencies and enough else None
        ),
        "shortest_minutes": min(durations) if enough else None,
        "longest_minutes": max(durations) if enough else None,
    }


#: Fractions of the target. A night within 30 minutes of it is "on target";
#: below 85% of it - a bit over an hour short of 7h30 - is short enough that
#: nothing else about the night matters as much.
ON_TARGET_TOLERANCE = 30
SHORT_FRACTION = 0.85

#: Efficiency is time asleep over time in bed. 85% is the conventional normal
#: cut; below 75% the night was spent mostly awake in bed.
EFFICIENCY_GOOD = 85
EFFICIENCY_POOR = 75


def verdict(session, against: dict, oxygen_read: dict) -> dict:
    """A sentence naming the dominant problem, or saying there wasn't one.

    Deterministic and rule-based rather than generated: this text sits at the
    top of a health page, so it has to be reproducible, auditable and identical
    for the same night every time it renders. It is also the one part of the
    page a person will read instead of the charts, which is exactly why it must
    not be able to say anything the data does not support.

    The rules encode one clinical distinction worth more than the rest: short
    sleep with *good* efficiency is a schedule problem - not enough time in bed
    - while adequate time in bed with poor efficiency is a sleep-quality
    problem. They call for different things and look identical in a duration
    number alone.
    """
    target = against["target_minutes"]
    duration = session.duration_minutes
    efficiency = session.efficiency
    mean = against["mean_duration_minutes"]

    on_target = duration >= target - ON_TARGET_TOLERANCE
    short = duration < target * SHORT_FRACTION
    efficient = efficiency is None or efficiency >= EFFICIENCY_GOOD
    inefficient = efficiency is not None and efficiency < EFFICIENCY_POOR

    if on_target and efficient:
        headline, detail = "A good night", "You hit your target and slept solidly through it."
    elif short and efficient:
        headline = "Good sleep, but short"
        detail = (
            "You slept well once you were asleep - the shortfall is time in bed, not sleep quality."
        )
    elif short and inefficient:
        headline = "Short and broken"
        detail = "Both the time in bed and the sleep within it were below your usual."
    elif inefficient:
        headline = "Enough time in bed, restless in it"
        detail = "You spent long enough in bed; much of it was spent awake."
    elif on_target:
        headline, detail = "Close to your target", "A little more broken than your best nights."
    else:
        headline, detail = "Below your target", "Short of the sleep you are aiming for."

    parts = [detail]
    if mean is not None:
        delta = duration - mean
        if abs(delta) >= 15:
            direction = "above" if delta > 0 else "below"
            parts.append(
                f"That is {_hm(abs(delta))} {direction} your {against['days']}-day average."
            )
    # The oxygen line is appended rather than allowed to set the headline: a
    # wrist SpO2 estimate is not grounds for leading a health page with alarm.
    if oxygen_read["minimum"] is not None and oxygen_read["minimum"] < 90:
        parts.append(
            f"Blood oxygen dipped to {oxygen_read['minimum']:.0f}% at its lowest, "
            "which is worth a look below."
        )

    return {
        "headline": headline,
        "detail": " ".join(parts),
        "delta_minutes": (duration - mean) if mean is not None else None,
        "target_delta_minutes": duration - target,
    }


def _hm(minutes: float) -> str:
    hours, rest = divmod(round(minutes), 60)
    return f"{hours}h {rest:02d}m" if hours else f"{rest}m"


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    value: str
    #: "ok", "watch" or "concern". Three states, because a fourth would be a
    #: judgement nobody could act on differently.
    state: str
    note: str


def signals(session, shape: dict, oxygen_read: dict) -> list[dict]:
    """One line per metric: what it was, and whether it is worth attention.

    A tick beside a number is the part people actually read. The thresholds are
    the same ones `scoring.py` documents with their evidence; they are not
    re-derived here, only rendered.
    """
    out: list[Signal] = []

    if session.efficiency is not None:
        out.append(
            Signal(
                key="efficiency",
                label="Efficiency",
                value=f"{session.efficiency}%",
                state=(
                    "ok"
                    if session.efficiency >= EFFICIENCY_GOOD
                    else "concern"
                    if session.efficiency < EFFICIENCY_POOR
                    else "watch"
                ),
                note="normal 85%+",
            )
        )

    for key, label, share_key in (
        ("deep", "Deep sleep", "deep"),
        ("rem", "REM", "rem"),
    ):
        share = (shape.get("stage_share") or {}).get(share_key)
        low, high = STAGE_REFERENCE[share_key]
        if share is None:
            continue
        out.append(
            Signal(
                key=key,
                label=label,
                value=f"{share:.0f}%",
                state="ok" if low <= share <= high else "watch",
                note=f"normal {low:.0f}-{high:.0f}%",
            )
        )

    waso = shape.get("waso_minutes")
    if waso is not None:
        out.append(
            Signal(
                key="waso",
                label="Awake in the night",
                value=_hm(waso),
                state="ok" if waso <= 30 else "watch" if waso <= 60 else "concern",
                note="normal under 30m",
            )
        )

    if oxygen_read["minimum"] is not None:
        lowest = oxygen_read["minimum"]
        out.append(
            Signal(
                key="spo2",
                label="Lowest blood oxygen",
                value=f"{lowest:.0f}%",
                state="ok" if lowest >= 90 else "watch" if lowest >= 88 else "concern",
                note="normal 95-100%",
            )
        )

    return [
        {
            "key": signal.key,
            "label": signal.label,
            "value": signal.value,
            "state": signal.state,
            "note": signal.note,
        }
        for signal in out
    ]


# --------------------------------------------------------------------------
# Sleep architecture
# --------------------------------------------------------------------------


def architecture(spans: list[Span]) -> dict:
    """Latencies, fragmentation and cycles, from the chronology.

    Every one of these is invisible in the stage totals, which is the whole
    argument for storing the segments: `minutes_awake` counts the same 40
    minutes whether they were one long 3am wakefulness or twenty brief stirs.
    """
    if not spans:
        return {
            "sleep_onset_minutes": None,
            "rem_latency_minutes": None,
            "waso_minutes": None,
            "longest_wake_minutes": None,
            "wake_episodes": 0,
            "cycles": 0,
            "rem_periods": [],
            "stage_share": {},
        }

    lights_out = spans[0].started_at
    asleep = [span for span in spans if span.level in ASLEEP]
    first_sleep = asleep[0].started_at if asleep else None
    final_wake = asleep[-1].ended_at if asleep else None

    # Wake *after* sleep onset, which is the measured quantity - the twenty
    # minutes spent reading before falling asleep is latency, not fragmented
    # sleep, and counting it as WASO makes a normal night look broken.
    wake_after = [
        span
        for span in spans
        if span.level not in ASLEEP
        and first_sleep is not None
        and span.started_at >= first_sleep
        and final_wake is not None
        and span.ended_at <= final_wake
    ]

    rem_periods = _rem_periods(spans)
    total_sleep = sum(span.seconds for span in asleep) / 60

    share = {}
    for level in ("deep", "light", "rem"):
        minutes = sum(span.minutes for span in spans if span.level == level)
        share[level] = round(minutes / total_sleep * 100, 1) if total_sleep else None

    return {
        "sleep_onset_minutes": (
            round((first_sleep - lights_out).total_seconds() / 60, 1) if first_sleep else None
        ),
        "rem_latency_minutes": (
            round((rem_periods[0]["started_at"] - first_sleep).total_seconds() / 60, 1)
            if rem_periods and first_sleep
            else None
        ),
        "waso_minutes": round(sum(span.minutes for span in wake_after), 1),
        "longest_wake_minutes": (
            round(max(span.minutes for span in wake_after), 1) if wake_after else 0.0
        ),
        "wake_episodes": len(wake_after),
        # A completed cycle ends with a REM period, so counting REM periods is
        # counting cycles. The last one is often cut short by the alarm, which
        # is why this is "cycles observed" rather than "cycles completed".
        "cycles": len(rem_periods),
        "rem_periods": rem_periods,
        "stage_share": share,
        "stage_reference": {key: list(value) for key, value in STAGE_REFERENCE.items()},
    }


def _rem_periods(spans: list[Span]) -> list[dict]:
    """REM runs, merging any two less than `REM_MERGE_GAP` minutes apart."""
    periods: list[dict] = []
    for span in spans:
        if span.level != SleepSegment.Level.REM:
            continue
        previous = periods[-1] if periods else None
        if previous and (span.started_at - previous["ended_at"]) <= timedelta(
            minutes=REM_MERGE_GAP
        ):
            previous["ended_at"] = span.ended_at
            previous["minutes"] = round(
                (previous["ended_at"] - previous["started_at"]).total_seconds() / 60, 1
            )
            continue
        periods.append(
            {
                "started_at": span.started_at,
                "ended_at": span.ended_at,
                "minutes": round(span.minutes, 1),
            }
        )
    return periods


# --------------------------------------------------------------------------
# The night-by-night table
# --------------------------------------------------------------------------
#
# The same idea as the heatmap page: a cell carries its value and a colour
# band, and the band comes from `scoring.py` rather than from anything decided
# here. A table of numbers makes the reader compare every figure against a
# range they have to remember; a table of scored cells lets a bad week be
# spotted from across the room, and still carries the numbers.

#: The columns, in reading order: how long, how well, what it was made of, and
#: then the overnight signals. Two of these are derived from the session rather
#: than read from a metric, which is why the column carries the threshold and
#: the extraction is in `table_cells` below.
TABLE_COLUMNS: tuple[scoring.Threshold, ...] = (
    scoring.SLEEP_HOURS,
    scoring.SLEEP_EFFICIENCY,
    scoring.Threshold(
        key="deep_share",
        label="Deep",
        unit="%",
        # Share of time asleep rather than minutes: 60 minutes of deep sleep is
        # a good night in six hours and a poor one in nine, and the minutes
        # column cannot tell those apart.
        anchors=((5, 0.0), (10, 0.4), (13, 0.9), (16, 1.0), (23, 1.0), (30, 0.6)),
        evidence="13-23% of time asleep is the normal adult range (AASM).",
    ),
    scoring.Threshold(
        key="rem_share",
        label="REM",
        unit="%",
        anchors=((8, 0.0), (14, 0.5), (20, 1.0), (25, 1.0), (30, 0.7), (40, 0.3)),
        evidence="20-25% of time asleep is the normal adult range (AASM).",
    ),
    scoring.RESTING_HR,
    scoring.HRV,
    scoring.BREATHING_RATE,
    scoring.SPO2_MIN,
)


def table_cells(session: dict, metrics: dict[str, float]) -> list[dict]:
    """One scored cell per column, for one night.

    `session` is the row shape `services.sleep_history` builds; `metrics` is
    that night's `DailyMetric` values. Sleep duration, efficiency and the stage
    shares come from the session itself rather than from the daily rollup,
    because the session is where the stages are guaranteed to add up.
    """
    asleep = session["duration_minutes"] or 0
    derived = {
        "sleep_hours": asleep / 60 if asleep else None,
        "sleep_efficiency": session["efficiency"],
        "deep_share": (session["minutes_deep"] / asleep * 100) if asleep else None,
        "rem_share": (session["minutes_rem"] / asleep * 100) if asleep else None,
    }

    cells = []
    for column in TABLE_COLUMNS:
        if column.key in derived:
            value = derived[column.key]
        elif column.metric:
            raw = metrics.get(column.metric)
            value = None if raw is None else raw * column.scale
        else:
            value = None
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


# --------------------------------------------------------------------------
# The window, for the trend view
# --------------------------------------------------------------------------


def summary(user, *, start: date, end: date) -> dict:
    """What the last N nights say, in the terms the page asks its question in.

    Everything here is per *recorded* night. The distinction matters more than
    it sounds: 13 nights recorded out of 30 is this dataset's normal, and a
    cumulative "sleep debt" over such a window is mostly a measure of nights
    the watch was not worn. So the shortfall is reported as an average per
    recorded night, which stays true whatever the coverage - and the coverage
    is returned beside it rather than left for the reader to assume.
    """
    rows = list(
        SleepSession.objects.filter(
            user=user, is_main_sleep=True, local_date__gte=start, local_date__lte=end
        )
        .order_by("local_date")
        .values_list("local_date", "duration_minutes", "efficiency", "started_at")
    )
    target = target_minutes(user)
    elapsed = (end - start).days + 1

    durations = [duration for _, duration, _, _ in rows if duration]
    efficiencies = [efficiency for _, _, efficiency, _ in rows if efficiency]

    # The preceding window of equal length, for "what changed". Compared only
    # when both halves hold enough nights to mean anything - a change against
    # two nights is noise with a direction.
    span = timedelta(days=elapsed)
    previous = list(
        SleepSession.objects.filter(
            user=user,
            is_main_sleep=True,
            local_date__gte=start - span,
            local_date__lt=start,
        ).values_list("duration_minutes", "efficiency")
    )
    previous_durations = [duration for duration, _ in previous if duration]
    previous_efficiencies = [efficiency for _, efficiency in previous if efficiency]

    comparable = (
        len(durations) >= BASELINE_MINIMUM_NIGHTS
        and len(previous_durations) >= BASELINE_MINIMUM_NIGHTS
    )

    return {
        "target_minutes": target,
        "nights_recorded": len(durations),
        "days_elapsed": elapsed,
        "mean_duration_minutes": _mean(durations),
        "mean_efficiency": _mean(efficiencies),
        "shortest_minutes": min(durations) if durations else None,
        "longest_minutes": max(durations) if durations else None,
        "nights_on_target": sum(
            1 for duration in durations if duration >= target - ON_TARGET_TOLERANCE
        ),
        # Negative means short. Per recorded night, never cumulative.
        "mean_shortfall_minutes": (round(_mean(durations) - target) if durations else None),
        "bedtime_spread_minutes": _bedtime_spread(
            [started for _, _, _, started in rows], timeutils.tz_for(user)
        ),
        "previous": {
            "comparable": comparable,
            "nights_recorded": len(previous_durations),
            "duration_delta_minutes": (
                round(_mean(durations) - _mean(previous_durations)) if comparable else None
            ),
            "efficiency_delta": (
                round(_mean(efficiencies) - _mean(previous_efficiencies))
                if comparable and efficiencies and previous_efficiencies
                else None
            ),
        },
    }


def _mean(values: list) -> float | None:
    return sum(values) / len(values) if values else None


def _bedtime_spread(starts: list[datetime], tz) -> int | None:
    """How much bedtime moves about, in minutes.

    Consistency is a sleep variable in its own right, and it is invisible in
    every duration chart: seven 7-hour nights beginning anywhere between 9pm
    and 2am are seven good nights and a circadian mess.

    Measured as the spread of local bedtimes around their own circular mean,
    because clock time wraps - 23:50 and 00:10 are twenty minutes apart, and
    arithmetic on the raw numbers calls them twenty-three hours apart.
    """
    if len(starts) < 3:
        return None
    angles = []
    for moment in starts:
        local = moment.astimezone(tz)
        fraction = (local.hour * 60 + local.minute) / 1440
        angles.append(fraction * 2 * math.pi)

    mean_x = sum(math.cos(angle) for angle in angles) / len(angles)
    mean_y = sum(math.sin(angle) for angle in angles) / len(angles)
    resultant = math.hypot(mean_x, mean_y)
    if resultant < 1e-9:
        return None
    # Circular standard deviation, back into minutes of a 24-hour clock.
    deviation = math.sqrt(-2 * math.log(resultant))
    return round(deviation / (2 * math.pi) * 1440)


# --------------------------------------------------------------------------
# Oxygen
# --------------------------------------------------------------------------


def oxygen(points: list[dict]) -> dict:
    """Nadir, time below the thresholds, and dips - never an average alone.

    An overnight mean is the one oxygen statistic that cannot show the thing
    worth finding. A night at 96% that spends four minutes at 84% averages to
    96%, and the four minutes are the entire clinical content of the night.
    """
    values = [point["value"] for point in points]
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "mean": None,
            "maximum": None,
            "minutes_under_90": 0,
            "minutes_under_88": 0,
            "lowest_at": None,
            "dips": [],
            "events_per_hour": {},
            "hours_covered": 0.0,
        }

    lowest = min(points, key=lambda point: point["value"])
    # Each sample is one minute, so a count of samples is a count of minutes.
    hours = len(values) / 60

    dips = _dips(points, DESAT_THRESHOLDS[0])
    return {
        "count": len(values),
        "minimum": min(values),
        "mean": round(sum(values) / len(values), 1),
        "maximum": max(values),
        "minutes_under_90": sum(1 for value in values if value < 90),
        "minutes_under_88": sum(1 for value in values if value < 88),
        "lowest_at": lowest["at"],
        "dips": dips,
        "events_per_hour": {
            f"{int(threshold)}pct": (
                round(len(_dips(points, threshold)) / hours, 1) if hours else None
            )
            for threshold in DESAT_THRESHOLDS
        },
        "hours_covered": round(hours, 1),
    }


def _dips(points: list[dict], threshold: float) -> list[dict]:
    """Falls of `threshold` points below the running baseline.

    The baseline is the median of the preceding `BASELINE_WINDOW` minutes, and
    a dip ends when the reading comes back to within one point of it. Median
    rather than mean so that the dip being measured does not drag the baseline
    it is measured against down with it.
    """
    events: list[dict] = []
    open_event: dict | None = None

    for index, point in enumerate(points):
        history = [p["value"] for p in points[max(0, index - BASELINE_WINDOW) : index]]
        if len(history) < 3:
            # Too early in the night to know what normal was. Skipping is the
            # honest choice: a baseline from one reading calls the second
            # reading a desaturation half the time.
            continue
        baseline = sorted(history)[len(history) // 2]
        value = point["value"]

        if open_event is None:
            if value <= baseline - threshold:
                open_event = {
                    "started_at": point["at"],
                    "ended_at": point["at"],
                    "baseline": baseline,
                    "lowest": value,
                }
        else:
            open_event["ended_at"] = point["at"]
            open_event["lowest"] = min(open_event["lowest"], value)
            if value >= open_event["baseline"] - 1:
                events.append(_closed(open_event))
                open_event = None

    if open_event is not None:
        events.append(_closed(open_event))
    return events


def _closed(event: dict) -> dict:
    return {
        "started_at": event["started_at"],
        "ended_at": event["ended_at"],
        "lowest": event["lowest"],
        "drop": round(event["baseline"] - event["lowest"], 1),
        "minutes": round((event["ended_at"] - event["started_at"]).total_seconds() / 60) + 1,
    }


def _heart(points: list[dict]) -> dict:
    """The night's heart rate, and where it bottomed out.

    The minimum matters here for the same reason the SpO2 nadir does: the
    lowest overnight heart rate tracks recovery, and its *timing* against the
    oxygen trace is what makes the two charts worth stacking.
    """
    values = [point["value"] for point in points]
    if not values:
        return {"count": 0, "minimum": None, "mean": None, "maximum": None, "lowest_at": None}
    lowest = min(points, key=lambda point: point["value"])
    return {
        "count": len(values),
        "minimum": min(values),
        "mean": round(sum(values) / len(values), 1),
        "maximum": max(values),
        "lowest_at": lowest["at"],
    }


def _context(user, on: date) -> dict:
    """The night's daily metrics, for the numbers that have no minute series.

    Breathing rate is the reason this exists: Fitbit publishes one nightly
    average per night and no intraday stream at all, so it cannot join the
    stacked timeline and belongs here as a number instead of being faked into
    a flat line across the chart.
    """
    wanted = ("breathing_rate", "hrv_rmssd", "spo2_avg", "spo2_min", "skin_temp_deviation")
    return dict(
        DailyMetric.objects.filter(user=user, local_date=on, metric__in=wanted).values_list(
            "metric", "value"
        )
    )
