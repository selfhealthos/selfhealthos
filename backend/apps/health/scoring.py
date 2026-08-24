"""What counts as a good day, per metric.

The heatmap needs one number per cell that says "better" or "worse", and the
only honest way to produce it is to write the thresholds down with their
evidence attached. This module is that list. `services.heatmap` reads it;
nothing else here touches the ORM.

Ported in spirit from the fitcypher dashboard's `METRIC_COLOR_MAPPING`, which
interpolated red→green between a hand-picked `min` and `max`. That shape cannot
express what most of these measurements actually do:

- **A two-sided optimum.** Sleep, blood pressure, BMI and Bristol all have a
  bad end in *both* directions. A min/max ramp has to pick one, and the old
  weight row picked wrong - it ran red at 60 kg to green at 80 kg, so gaining
  weight coloured green.
- **A plateau.** Steps stop buying much after ~8,000/day. A linear ramp to
  10,000 says the 9,000th step is worth as much as the 3,000th, and it isn't.
- **A floor that is not zero.** Nothing about 50 bpm resting is worse than 55.

So a threshold here is a piecewise-linear curve through explicit `(value,
score)` anchors, ascending by value, clamped at both ends. Every shape above
falls out of that one mechanism, and each anchor is a place where the evidence
can be named in a comment rather than smuggled into a slope.

Scores are 0-1. `band_for` buckets them into the five colour steps the UI
draws; the bucketing lives here so the REST response, an MCP answer and the
page all agree on what "good" means.

**A metric with no threshold is not scored.** It shows its value in a plain
cell. That is deliberate: an uncoloured number says "no opinion", whereas a
guessed colour says something false with total confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

#: Number of colour steps. Five is what a person can hold in their head from a
#: legend; more steps read as a continuous ramp nobody can decode per cell.
BANDS = 5


@dataclass(frozen=True)
class Threshold:
    """One column of the heatmap, and how to colour it.

    `metric` is the `DailyMetric` key the value comes from, or `None` for a
    column the service derives (BMI, which needs height as well as weight).
    """

    key: str
    label: str
    unit: str
    metric: str | None = None
    #: Extra `DailyMetric` keys a derived column needs. The service reads these
    #: too; without them a derived column queries nothing and is always blank.
    sources: tuple[str, ...] = ()
    #: `(value, score)` pairs, ascending by value. Score is clamped to the
    #: first and last anchor outside the range they span. Empty means the
    #: column is shown but never coloured.
    anchors: tuple[tuple[float, float], ...] = ()
    #: Multiplies the stored value before scoring and display. Minutes to
    #: hours, mostly - the anchors then read in the unit a person thinks in.
    scale: float = 1.0
    #: Decimal places for display.
    places: int = 0
    #: Why these anchors and not others. Surfaced in the UI, so it is the
    #: answer to "says who?" without leaving the page.
    evidence: str = ""

    @property
    def scored(self) -> bool:
        return bool(self.anchors)

    def score(self, value: float) -> float | None:
        """0-1 for a value already in this threshold's display unit."""
        if not self.anchors:
            return None
        if value <= self.anchors[0][0]:
            return self.anchors[0][1]
        for (low_value, low_score), (high_value, high_score) in pairwise(self.anchors):
            if value <= high_value:
                span = high_value - low_value
                # Two anchors at the same value would divide by zero; treat the
                # step as instantaneous and take the upper score.
                position = (value - low_value) / span if span else 1.0
                return low_score + position * (high_score - low_score)
        return self.anchors[-1][1]


def band_for(score: float | None) -> int | None:
    """The colour step, 1 (worst) to 5 (best).

    Bucketed rather than a continuous gradient because the cell has to be read
    against a legend. A continuous ramp can only be read against itself, which
    turns "was yesterday worse?" into a question about two adjacent shades.
    """
    if score is None:
        return None
    return min(BANDS, int(max(0.0, min(1.0, score)) * BANDS) + 1)


# --------------------------------------------------------------------------
# The thresholds
# --------------------------------------------------------------------------
#
# Sources are named per column. Where the research gives a range rather than a
# line - which is most of them - the anchors put full marks across the range
# and fall away outside it, rather than treating the edge of "normal" as a
# cliff. Population thresholds are also not diagnoses: they are the reason one
# cell is darker than another, and nothing here should be read as one.

SLEEP_HOURS = Threshold(
    key="sleep_hours",
    label="Sleep",
    unit="h",
    metric="sleep_minutes",
    scale=1 / 60,
    places=1,
    # AASM/SRS 2015 consensus: 7-9h for adults. Cappuccio 2010 (meta-analysis,
    # 1.3M people) finds raised mortality at BOTH ends, which is why this is a
    # band. The long arm is deliberately gentler than the short one: long sleep
    # is largely a marker of something else, whereas short sleep is causal in
    # the experimental literature.
    anchors=((3, 0.0), (5, 0.2), (6, 0.5), (6.75, 0.85), (7, 1.0), (9, 1.0), (10, 0.7), (12, 0.35)),
    evidence="7-9 h (AASM/SRS 2015 consensus). Both short and long sleep raise "
    "mortality (Cappuccio 2010); the short end falls away faster.",
)

SLEEP_EFFICIENCY = Threshold(
    key="sleep_efficiency",
    label="Sleep eff.",
    unit="%",
    metric="sleep_efficiency",
    # 85% is the conventional cut for normal sleep continuity; below 80% is one
    # of the criteria used in insomnia research.
    anchors=((60, 0.0), (70, 0.3), (80, 0.65), (85, 0.9), (90, 1.0)),
    evidence="≥85% is the conventional normal cut; <80% is an insomnia research criterion.",
)

RESTING_HR = Threshold(
    key="resting_hr",
    label="Resting HR",
    unit="bpm",
    metric="resting_hr",
    # Jensen 2013 (Copenhagen Male Study) and Zhang 2016 (meta-analysis): each
    # 10 bpm above ~60 carries roughly 9-20% higher all-cause mortality.
    # No penalty at the low end. A wearable's resting heart rate reads low
    # because of fitness far more often than because of pathological
    # bradycardia, and a daily colour grid is not the instrument that should be
    # raising that question.
    anchors=((45, 1.0), (55, 1.0), (60, 0.85), (65, 0.7), (70, 0.5), (80, 0.25), (90, 0.0)),
    evidence="Lower is better: ~10 bpm above 60 ≈ 9-20% higher all-cause "
    "mortality (Jensen 2013, Zhang 2016). Low values are not penalised.",
)

HRV = Threshold(
    key="hrv_rmssd",
    label="HRV",
    unit="ms",
    metric="hrv_rmssd",
    # Absolute banding is the weakest column here and says so. RMSSD is
    # strongly individual and falls with age; the reading that means anything
    # is this week against your own baseline, which the trends page shows.
    anchors=((10, 0.0), (20, 0.3), (30, 0.55), (45, 0.8), (60, 1.0)),
    evidence="Rough absolute bands only. RMSSD is highly individual and "
    "declines with age — your own baseline is the real reference.",
)

STEPS = Threshold(
    key="steps",
    label="Steps",
    unit="",
    metric="steps",
    # Saint-Maurice 2020 (JAMA): 8,000/day carries ~51% lower all-cause
    # mortality than 4,000, with the curve flattening around 10,000 - so full
    # marks arrive at 10,000 and nothing above it scores higher. Paluch 2022
    # (Lancet Public Health) puts the plateau lower still for over-60s.
    anchors=((0, 0.0), (2000, 0.15), (4000, 0.35), (6000, 0.6), (8000, 0.85), (10000, 1.0)),
    evidence="8,000/day ≈ 51% lower mortality than 4,000, plateauing near "
    "10,000 (Saint-Maurice 2020, JAMA).",
)

ACTIVE_MINUTES = Threshold(
    key="active_minutes",
    label="Active",
    unit="min",
    metric=None,
    sources=("fairly_active_minutes", "very_active_minutes"),
    # Moderate-to-vigorous minutes, summed from the two Fitbit buckets rather
    # than taken from `active_zone_minutes` - which is the obvious column and a
    # trap. The archive holds AZM as a literal 0.0 on every day the device never
    # supplied it, so scoring it draws a solid red stripe down the page for
    # someone averaging 37 vigorous minutes a day. The two bucket metrics are
    # simply absent when unknown, which is the difference between "no data" and
    # "did nothing" - and drawing that difference is what a blank cell is for.
    #
    # WHO 2020: 150-300 min/week of moderate activity, so 21 min/day is the
    # floor of the recommendation and 43 the top of its range.
    anchors=((0, 0.0), (10, 0.4), (21, 0.85), (35, 1.0)),
    evidence="WHO 2020: 150-300 min/week of moderate-to-vigorous activity ≈ "
    "21-43 min/day. Fitbit's moderate and vigorous minutes, summed.",
)

VIGOROUS_MINUTES = Threshold(
    key="vigorous_minutes",
    label="Vigorous",
    unit="min",
    metric=None,
    sources=("zone_cardio_minutes", "zone_peak_minutes"),
    # The cardio and peak zone minutes summed - time spent at a heart rate the
    # device itself classed as vigorous, which is the heart's own account of
    # the effort rather than the accelerometer's.
    #
    # WHO 2020 counts vigorous activity double: 75-150 min/week satisfies the
    # same recommendation as 150-300 moderate, so 11 min/day is the floor and
    # 21 the top of the range. Kept as a separate column from `active_minutes`
    # rather than folded into it because the two disagree in a way worth
    # seeing - a hard hill walk registers here and barely there.
    anchors=((0, 0.0), (5, 0.4), (11, 0.85), (21, 1.0)),
    evidence="WHO 2020: 75-150 min/week of vigorous activity ≈ 11-21 min/day. "
    "Fitbit's cardio and peak zone minutes, summed.",
)

EXERCISE_MINUTES = Threshold(
    key="exercise_minutes",
    label="Exercise",
    unit="min",
    metric="exercise_minutes",
    # The logged counterpart to the column above: what you said you did, rather
    # than what the watch saw. Same WHO basis, slightly more generous anchors
    # because a logged session is deliberate exercise rather than incidental
    # movement that happened to raise a heart rate.
    anchors=((0, 0.0), (15, 0.5), (30, 0.9), (45, 1.0)),
    evidence="WHO 2020: 150 min/week ≈ 21 min/day, 300 min/week ≈ 43.",
)

SPO2 = Threshold(
    key="spo2_avg",
    label="SpO₂",
    unit="%",
    metric="spo2_avg",
    places=1,
    # 95-100% is normal awake; overnight averages sit slightly lower. Below 92%
    # sustained is the level at which the number is worth showing a doctor.
    anchors=((88, 0.0), (92, 0.4), (94, 0.75), (95, 1.0)),
    evidence="95-100% is normal; a sustained overnight average below 92% is "
    "worth raising with a doctor.",
)

SPO2_MIN = Threshold(
    key="spo2_min",
    label="Lowest SpO₂",
    unit="%",
    metric="spo2_min",
    # Scored harder than the nightly average, and that is the point: an average
    # of 96% is unremarkable on a night that spent four minutes at 84%. In
    # oximetry a nadir below 90% is the level worth someone's attention and
    # below 88% is the conventional threshold for sustained desaturation.
    anchors=((80, 0.0), (88, 0.35), (90, 0.6), (93, 0.9), (95, 1.0)),
    evidence="A nadir below 90% is worth attention, below 88% is the "
    "conventional desaturation threshold. Wrist estimate, not oximetry.",
)

BREATHING_RATE = Threshold(
    key="breathing_rate",
    label="Breathing",
    unit="/min",
    metric="breathing_rate",
    places=1,
    # 12-20 breaths per minute is the normal adult resting range; overnight
    # values sit in its lower half. Both ends matter, so this is a band.
    anchors=((8, 0.0), (11, 0.7), (12, 1.0), (18, 1.0), (20, 0.7), (24, 0.0)),
    evidence="12-20 breaths/min is the normal adult resting range; overnight "
    "values usually sit in its lower half.",
)

SYSTOLIC = Threshold(
    key="systolic",
    label="Systolic",
    unit="mmHg",
    metric="systolic",
    # ACC/AHA 2017: <120 normal, 120-129 elevated, 130-139 stage 1, >=140
    # stage 2. Banded rather than one-sided because symptomatic hypotension is
    # also not a good day.
    anchors=((80, 0.2), (95, 0.8), (105, 1.0), (118, 1.0), (130, 0.55), (140, 0.3), (160, 0.0)),
    evidence="ACC/AHA 2017: <120 normal, 120-129 elevated, 130-139 stage 1, "
    "≥140 stage 2. Very low also scores down.",
)

DIASTOLIC = Threshold(
    key="diastolic",
    label="Diastolic",
    unit="mmHg",
    metric="diastolic",
    anchors=((50, 0.2), (60, 0.9), (70, 1.0), (78, 1.0), (85, 0.5), (90, 0.35), (100, 0.0)),
    evidence="ACC/AHA 2017: <80 normal, 80-89 stage 1, ≥90 stage 2.",
)

BRISTOL = Threshold(
    key="bristol_mean",
    label="Bristol",
    unit="1-7",
    metric="bristol_mean",
    places=1,
    # 3-4 is the ideal middle of the scale, 1-2 constipation, 5-7 loose. The
    # daily mean is a blunt instrument - one 2 and one 6 average to a perfect 4
    # - which is exactly why the gut page keeps the stacked counts.
    anchors=((1, 0.1), (2, 0.4), (3, 1.0), (4, 1.0), (5, 0.6), (6, 0.3), (7, 0.1)),
    evidence="3-4 is the ideal middle; 1-2 constipation, 5-7 loose. A daily "
    "mean hides a mixed day — see the Gut page for the counts.",
)

HABITS = Threshold(
    key="habit_completion_pct",
    label="Habits",
    unit="%",
    metric="habit_completion_pct",
    # Not a medical threshold and not presented as one: this is adherence to
    # habits you set yourself, where the only defensible target is all of them.
    anchors=((0, 0.0), (50, 0.4), (80, 0.8), (100, 1.0)),
    evidence="Your own adherence, not a clinical threshold: the target is the habits you set.",
)

WEIGHT = Threshold(
    key="weight_kg",
    label="Weight",
    unit="kg",
    metric="weight_kg",
    places=1,
    # No anchors on purpose. A weight is only interpretable against a height,
    # and the BMI column below appears as soon as the profile carries one. The
    # dashboard this replaces coloured 80 kg green and 60 kg red for everyone.
    evidence="Not scored: a weight means nothing without a height. Set one in "
    "your profile and a BMI column appears.",
)


def bmi_threshold() -> Threshold:
    """BMI, derived from weight and the profile height."""
    return Threshold(
        key="bmi",
        label="BMI",
        unit="kg/m²",
        metric=None,
        sources=("weight_kg",),
        places=1,
        # WHO bands are 18.5-24.9 normal, but the mortality nadir in the Global
        # BMI Mortality Collaboration (2016, 10.6M people) sits around 22-25,
        # and the underweight arm is steeper than the overweight one at the
        # same distance from it.
        anchors=(
            (15, 0.0),
            (17.5, 0.25),
            (18.5, 0.6),
            (20, 0.9),
            (21.5, 1.0),
            (24, 1.0),
            (25, 0.95),
            (27, 0.7),
            (30, 0.45),
            (35, 0.2),
            (40, 0.0),
        ),
        evidence="Mortality nadir ≈ 22-25 (Global BMI Mortality Collaboration "
        "2016); WHO normal range 18.5-24.9. BMI ignores body composition.",
    )


#: Baseline VO2 max anchors for a 40-year-old male, before `vo2max_threshold`
#: shifts them. Kodama 2009 (JAMA): each 1 MET (3.5 ml/kg/min) higher
#: cardiorespiratory fitness carries ~13% lower all-cause mortality, and the
#: gap between the bottom quintile and the rest is the largest step in it.
_VO2MAX_BASE: tuple[tuple[float, float], ...] = (
    (25, 0.0),
    (32, 0.35),
    (38, 0.6),
    (44, 0.85),
    (50, 1.0),
)

#: ml/kg/min subtracted for a female reference. The sex difference in VO2 max
#: is roughly 15-20% at the same age and training state, largely haemoglobin
#: mass and body composition.
_VO2MAX_FEMALE_OFFSET = 7.0

#: ml/kg/min per year away from 40. VO2 max declines by roughly 10% per decade
#: in untrained adults; without shifting for it a fit 60-year-old reads red
#: every single day for being 60.
_VO2MAX_PER_YEAR = 0.35


def vo2max_threshold(*, age: int | None = None, sex: str = "") -> Threshold:
    """VO2 max, banded against age and sex when the profile supplies them.

    An unadjusted band is the one that fails loudly: population norms differ by
    more than 15 ml/kg/min across the adult range, so a fixed cut either paints
    every older person red or every younger one green. Absent a profile this
    falls back to the 40-year-old male reference and says so.
    """
    shift = 0.0
    note = "Unadjusted (no age or sex in your profile): banded for a 40-year-old male."
    if sex.strip().lower().startswith("f"):
        shift -= _VO2MAX_FEMALE_OFFSET
    if age is not None:
        shift += (40 - age) * _VO2MAX_PER_YEAR
    if age is not None or sex:
        note = f"Shifted {shift:+.1f} ml/kg/min for your age and sex."

    return Threshold(
        key="vo2max",
        label="VO₂ max",
        unit="",
        metric="vo2max",
        anchors=tuple((value + shift, score) for value, score in _VO2MAX_BASE),
        evidence="Each 1 MET (3.5 ml/kg/min) of fitness ≈ 13% lower all-cause "
        f"mortality (Kodama 2009, JAMA). {note}",
    )


#: Everything with a fixed threshold, in the order the heatmap draws it:
#: recovery first, then output, then the hand-logged columns that arrive in
#: bursts. Columns with no data in the window are dropped by the service, so
#: this is the superset rather than what any given page shows.
FIXED: tuple[Threshold, ...] = (
    SLEEP_HOURS,
    SLEEP_EFFICIENCY,
    RESTING_HR,
    HRV,
    STEPS,
    ACTIVE_MINUTES,
    EXERCISE_MINUTES,
    SPO2,
    WEIGHT,
    SYSTOLIC,
    DIASTOLIC,
    BRISTOL,
    HABITS,
)


@dataclass(frozen=True)
class ColumnSet:
    """The thresholds for one person, in draw order."""

    columns: tuple[Threshold, ...]
    #: Height in metres, when the profile has one. `None` means no BMI column.
    height_m: float | None = None
    by_key: dict[str, Threshold] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_key.update({column.key: column for column in self.columns})


def columns_for(
    *, age: int | None = None, sex: str = "", height_cm: float | None = None
) -> ColumnSet:
    """The column list for one person.

    Two of the thresholds depend on who is being measured - VO2 max on age and
    sex, BMI on height - so the set is built per user rather than being a
    module constant.
    """
    height_m = height_cm / 100 if height_cm else None
    columns: list[Threshold] = []
    for column in FIXED:
        columns.append(column)
        # BMI reads better immediately after the weight it is derived from.
        if column is WEIGHT and height_m:
            columns.append(bmi_threshold())
        if column is EXERCISE_MINUTES:
            columns.append(vo2max_threshold(age=age, sex=sex))
    return ColumnSet(columns=tuple(columns), height_m=height_m)


# --------------------------------------------------------------------------
# Body composition
# --------------------------------------------------------------------------
#
# The three columns below are the Body page's, not the heatmap's, and they are
# deliberately not in `FIXED`. Waist and height are tape-measure numbers taken
# every few weeks, not daily metrics: adding them to the heatmap would widen
# every row by two columns that are blank on 95% of days, which is the shape
# `services.heatmap` already drops columns to avoid.


def waist_height_threshold() -> Threshold:
    """Waist-to-height ratio - waist and height in the same unit, divided.

    The reason the Body page leads with this rather than BMI: it needs no
    scales, it detects central adiposity that BMI misses entirely in someone of
    "normal" weight, and the healthy limit is one number a person can actually
    remember - keep your waist under half your height.
    """
    return Threshold(
        key="waist_height_ratio",
        label="Waist/height",
        unit="ratio",
        metric=None,
        places=2,
        # NICE NG246 (2025) and Ashwell's boundary values: 0.4-0.49 healthy,
        # 0.5-0.59 increased central adiposity, 0.6+ high. The low arm falls
        # away below 0.4 because a ratio that low is underweight or a
        # mis-measured tape, not a better result than 0.45 - this is the
        # two-sided optimum the module docstring is about.
        anchors=(
            (0.34, 0.2),
            (0.40, 0.9),
            (0.43, 1.0),
            (0.47, 1.0),
            (0.50, 0.75),
            (0.55, 0.45),
            (0.60, 0.2),
            (0.70, 0.0),
        ),
        evidence="Keep your waist under half your height. 0.4-0.49 healthy, "
        "0.5-0.59 increased, 0.6+ high central adiposity (NICE NG246 2025; "
        "Ashwell boundary values).",
    )


#: WHO waist-circumference cut-offs, `(increased_risk, substantially_increased)`
#: in cm, by sex. Europid values; the WHO notes lower cut-offs are appropriate
#: for South Asian, Chinese and Japanese populations, which is one reason the
#: waist-to-height ratio above is the column this page leads with - it needs no
#: population-specific cut-off at all.
_WAIST_CUTOFFS: dict[str, tuple[float, float]] = {
    "male": (94.0, 102.0),
    "female": (80.0, 88.0),
}


def waist_threshold(*, sex: str = "") -> Threshold:
    """Waist circumference, banded against the WHO's sex-specific cut-offs.

    Unscored without a sex on the profile. The two sets of cut-offs are 14 cm
    apart, so picking one for someone who has not said would colour a healthy
    82 cm waist either green or amber on a coin toss - and a colour is exactly
    the thing that reads as certainty.
    """
    key = "female" if sex.strip().lower().startswith("f") else "male" if sex else ""
    if not key:
        return Threshold(
            key="waist_cm",
            label="Waist",
            unit="cm",
            metric=None,
            places=1,
            evidence="Not scored: the WHO waist cut-offs are sex-specific and "
            "14 cm apart. Set a sex on your profile and this column bands.",
        )

    increased, substantial = _WAIST_CUTOFFS[key]
    return Threshold(
        key="waist_cm",
        label="Waist",
        unit="cm",
        metric=None,
        places=1,
        # Full marks comfortably under the "increased risk" cut-off, falling
        # away through it to "substantially increased" and beyond. The bottom
        # anchor is well below either cut-off rather than at zero: a 55 cm
        # waist is not a better outcome than a 70 cm one.
        anchors=(
            (increased - 30, 0.7),
            (increased - 20, 1.0),
            (increased - 8, 1.0),
            (increased, 0.7),
            (substantial, 0.4),
            (substantial + 12, 0.15),
            (substantial + 25, 0.0),
        ),
        evidence=f"WHO cut-offs for {key}s: {increased:.0f} cm increased risk, "
        f"{substantial:.0f} cm substantially increased.",
    )


def weight_threshold(*, target_kg: float | None = None) -> Threshold:
    """Weight, banded against this person's own target - or not at all.

    `WEIGHT` above stays unscored on purpose and that reasoning has not
    changed: there is no population threshold for a weight, and the dashboard
    this replaced coloured 80 kg green and 60 kg red for everyone. What makes a
    colour defensible here is that the line is one the user set themselves, so
    the column header names the target and the colour means "against the number
    you chose", not "against health".

    The band is symmetric because a target missed by 3 kg in either direction
    is missed by 3 kg; nothing here knows whether the goal was to lose or gain.
    """
    if not target_kg or target_kg <= 0:
        return Threshold(
            key="weight_kg",
            label="Weight",
            unit="kg",
            metric="weight_kg",
            places=1,
            evidence="Not scored: a weight means nothing without a height or a "
            "goal. The BMI column bands it against a height; set a target "
            "weight and this column bands against that.",
        )

    return Threshold(
        key="weight_kg",
        label="Weight",
        unit="kg",
        metric="weight_kg",
        places=1,
        # Absolute kilograms, not a percentage: 3 kg is 3 kg of the same
        # journey whether the target is 60 or 100, and a percentage band would
        # make the same miss score differently for two people.
        anchors=(
            (target_kg - 12, 0.0),
            (target_kg - 6, 0.45),
            (target_kg - 2, 0.9),
            (target_kg, 1.0),
            (target_kg + 2, 0.9),
            (target_kg + 6, 0.45),
            (target_kg + 12, 0.0),
        ),
        evidence=f"Your own target of {target_kg:g} kg, not a clinical "
        "threshold. Full marks within 2 kg, falling away either side.",
    )


def body_columns_for(
    *, sex: str = "", height_cm: float | None = None, target_weight_kg: float | None = None
) -> ColumnSet:
    """The Body page's four columns, in the order the table draws them.

    Weight first because it is the one recorded most often, then the two things
    derived from it and the profile, then the tape measure. BMI and the ratio
    are dropped rather than drawn blank when no height is set - a column of
    ninety em-dashes is not information about your body.
    """
    height_m = height_cm / 100 if height_cm else None
    columns: list[Threshold] = [weight_threshold(target_kg=target_weight_kg)]
    if height_m:
        columns.append(bmi_threshold())
    columns.append(waist_threshold(sex=sex))
    if height_m:
        columns.append(waist_height_threshold())
    return ColumnSet(columns=tuple(columns), height_m=height_m)
