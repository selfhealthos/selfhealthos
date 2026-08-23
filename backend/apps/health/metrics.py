"""The metric vocabulary.

Every number this app stores in `Sample` or `DailyMetric` is keyed by one of
these strings. They are a public contract: they appear in REST responses, in MCP
tool arguments and in chart URLs, so renaming one is a breaking change and a
migration, not a rename.

Keys are snake_case, unprefixed, and describe the measurement rather than its
source. `steps` is steps whether Fitbit, a phone or a future watch supplied it -
the source belongs on the ingest record, not baked into the metric name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Agg = Literal["sum", "mean", "min", "max", "last"]


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    unit: str
    #: True if this metric can appear in `Sample` at 1-minute resolution.
    intraday: bool = False
    #: How intraday samples collapse into the daily rollup. Only meaningful
    #: when `intraday` is True and no authoritative daily value is supplied.
    agg: Agg = "mean"
    description: str = ""


def _m(key, label, unit, **kw) -> MetricDef:
    return MetricDef(key=key, label=label, unit=unit, **kw)


# --------------------------------------------------------------------------
# Intraday - stored in `Sample`, 1-minute resolution (see roadmap decision 1)
# --------------------------------------------------------------------------

INTRADAY: tuple[MetricDef, ...] = (
    _m(
        "hr",
        "Heart rate",
        "bpm",
        intraday=True,
        agg="mean",
        description="Beats per minute, averaged over the minute.",
    ),
    _m("steps", "Steps", "count", intraday=True, agg="sum"),
    _m("calories", "Calories", "kcal", intraday=True, agg="sum"),
    _m("distance", "Distance", "km", intraday=True, agg="sum"),
    _m("floors", "Floors", "count", intraday=True, agg="sum"),
    _m("elevation", "Elevation", "m", intraday=True, agg="sum"),
    _m(
        "spo2",
        "Blood oxygen",
        "%",
        intraday=True,
        agg="mean",
        description="Overnight only. Normal 95-100%; below 94% is worth noting.",
    ),
    _m(
        "hrv_rmssd",
        "HRV (RMSSD)",
        "ms",
        intraday=True,
        agg="mean",
        description="Five-minute windows during sleep.",
    ),
)

# --------------------------------------------------------------------------
# Daily - stored in `DailyMetric`, one row per user per date per metric
# --------------------------------------------------------------------------

DAILY: tuple[MetricDef, ...] = (
    # Activity, from the Fitbit daily summary
    _m("steps", "Steps", "count"),
    _m("distance_km", "Distance", "km"),
    _m("floors", "Floors", "count"),
    _m("calories_burned", "Calories burned", "kcal"),
    _m("sedentary_minutes", "Sedentary", "min"),
    _m("lightly_active_minutes", "Lightly active", "min"),
    _m("fairly_active_minutes", "Fairly active", "min"),
    _m("very_active_minutes", "Very active", "min"),
    _m("active_zone_minutes", "Active zone", "min"),
    # Heart
    _m(
        "resting_hr",
        "Resting heart rate",
        "bpm",
        description="One of the better long-term fitness signals; falling is improving.",
    ),
    _m("min_hr", "Minimum heart rate", "bpm"),
    _m("max_hr", "Maximum heart rate", "bpm"),
    _m("avg_hr", "Average heart rate", "bpm"),
    _m("zone_out_of_range_minutes", "Below fat burn", "min"),
    _m("zone_fat_burn_minutes", "Fat burn zone", "min"),
    _m("zone_cardio_minutes", "Cardio zone", "min"),
    _m("zone_peak_minutes", "Peak zone", "min"),
    # Where the zones above actually sit, in beats per minute. Stored per day
    # because they are the device's own boundaries: derived from an estimated
    # maximum heart rate that moves with age and, for the fat burn floor, with
    # resting heart rate. Recomputing them here as 220-age would produce bands
    # that disagree with the zone minutes sitting beside them.
    _m("zone_fat_burn_floor_bpm", "Fat burn from", "bpm"),
    _m("zone_cardio_floor_bpm", "Cardio from", "bpm"),
    _m("zone_peak_floor_bpm", "Peak from", "bpm"),
    _m(
        "zone_peak_ceiling_bpm",
        "Estimated maximum",
        "bpm",
        description="The top of Fitbit's peak zone, i.e. its estimate of your maximum "
        "heart rate. Not a measured maximum - see max_hr for that.",
    ),
    # Recovery
    _m(
        "hrv_rmssd",
        "HRV (RMSSD)",
        "ms",
        description="Daily average. Several days below personal baseline suggests "
        "overtraining or oncoming illness.",
    ),
    _m("hrv_coverage", "HRV coverage", "%"),
    _m("spo2_avg", "Blood oxygen (avg)", "%"),
    _m("spo2_min", "Blood oxygen (min)", "%"),
    _m("spo2_max", "Blood oxygen (max)", "%"),
    _m(
        "skin_temp_deviation",
        "Skin temperature",
        "°C",
        description="Deviation from personal baseline. Above +0.5 often precedes illness.",
    ),
    _m("breathing_rate", "Breathing rate", "breaths/min"),
    _m("vo2max", "VO2 max", "ml/kg/min"),
    # Sleep, from the main sleep session
    _m("sleep_minutes", "Time asleep", "min"),
    _m("sleep_efficiency", "Sleep efficiency", "%"),
    _m("sleep_deep_minutes", "Deep sleep", "min"),
    _m("sleep_light_minutes", "Light sleep", "min"),
    _m("sleep_rem_minutes", "REM sleep", "min"),
    _m("sleep_awake_minutes", "Awake in bed", "min"),
    _m("sleep_awakenings", "Awakenings", "count"),
    # Derived from hand-logged entries
    _m("weight_kg", "Weight", "kg"),
    _m("systolic", "Systolic", "mmHg", description="Normal <120, elevated 120-129, high >=130."),
    _m("diastolic", "Diastolic", "mmHg", description="Normal <80, high >=80."),
    _m(
        "bristol_mean",
        "Bristol score (mean)",
        "1-7",
        description="1-2 constipation, 3-4 ideal, 5-6 loose, 7 diarrhoea.",
    ),
    _m("bm_count", "Bowel movements", "count"),
    _m("diet_entries", "Food entries logged", "count"),
    _m("exercise_minutes", "Exercise", "min"),
    _m("exercise_sessions", "Exercise sessions", "count"),
    _m("gym_volume_kg", "Gym volume", "kg", description="Sum of weight x reps across all sets."),
    _m("gym_sets", "Gym sets", "count"),
    _m("habits_completed", "Habits completed", "count"),
    _m("habits_total", "Habits defined", "count"),
    _m("habit_completion_pct", "Habit completion", "%"),
    _m("note_count", "Diary entries", "count"),
    _m(
        "office_day",
        "Worked in office",
        "0/1",
        description="1 if the day was worked in the office. Absent means unknown, "
        "not work-from-home.",
    ),
)

INTRADAY_BY_KEY: dict[str, MetricDef] = {m.key: m for m in INTRADAY}
DAILY_BY_KEY: dict[str, MetricDef] = {m.key: m for m in DAILY}

#: Longest key, so the model field is sized from the data rather than a guess.
MAX_KEY_LENGTH = max(len(m.key) for m in INTRADAY + DAILY)

INTRADAY_CHOICES = [(m.key, m.label) for m in INTRADAY]
DAILY_CHOICES = [(m.key, m.label) for m in DAILY]


def daily_key_for(intraday_key: str) -> str:
    """The daily metric an intraday stream rolls up into.

    Most are the same word; the two that differ do so because the daily value
    means something different from the sum of the minutes.
    """
    return {"distance": "distance_km", "calories": "calories_burned"}.get(
        intraday_key, intraday_key
    )
