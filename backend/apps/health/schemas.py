"""Response shapes for the health API.

Written out explicitly rather than resolved from the models: these same shapes
go to Claude over MCP in H4, and an auto-generated schema hides what crosses
that boundary.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from ninja import Schema


class HealthMetricOut(Schema):
    key: str
    label: str
    unit: str
    description: str = ""
    has_intraday: bool = False


class HealthMetricCoverageOut(Schema):
    days: int
    first: date | None = None
    last: date | None = None


class HealthSummaryOut(Schema):
    first_date: date | None = None
    last_date: date | None = None
    days_covered: int
    entries: dict[str, int]
    metrics: dict[str, HealthMetricCoverageOut]
    sample_count: int


# -- day view ---------------------------------------------------------------


class HealthDietItemOut(Schema):
    id: UUID
    name: str
    at: datetime


class HealthExerciseItemOut(Schema):
    id: UUID
    name: str
    duration_s: int
    at: datetime


class HealthBmItemOut(Schema):
    id: UUID
    bristol: int
    notes: str = ""
    at: datetime


class HealthBpItemOut(Schema):
    id: UUID
    systolic: int
    diastolic: int
    at: datetime


class HealthWeightItemOut(Schema):
    id: UUID
    weight_kg: float
    at: datetime


class HealthNoteItemOut(Schema):
    id: UUID
    title: str = ""
    content: str = ""
    at: datetime


class HealthGymSetItemOut(Schema):
    id: UUID
    exercise: str
    weight_kg: float
    reps: int
    volume_kg: float


class HealthHabitItemOut(Schema):
    id: UUID
    name: str
    completed: bool


class HealthSleepOut(Schema):
    started_at: datetime
    ended_at: datetime
    duration_minutes: int
    efficiency: int | None = None
    minutes_deep: int
    minutes_light: int
    minutes_rem: int
    minutes_awake: int
    awakenings_count: int


class HealthRecoveryOut(Schema):
    """The traffic light on the day. See services.recovery_for."""

    level: str
    label: str
    hrv: float | None = None
    resting_hr: float | None = None
    sleep_efficiency: float | None = None
    #: How many of the three inputs were available, so the UI can qualify it.
    inputs: int = 0


class HealthDayOut(Schema):
    date: date
    #: The zone the entry times should be rendered in. See `services.DayView`.
    timezone: str
    metrics: dict[str, float]
    diet: list[HealthDietItemOut]
    exercise: list[HealthExerciseItemOut]
    bm: list[HealthBmItemOut]
    bp: list[HealthBpItemOut]
    weight: list[HealthWeightItemOut]
    notes: list[HealthNoteItemOut]
    gym_sets: list[HealthGymSetItemOut]
    habits: list[HealthHabitItemOut]
    sleep: HealthSleepOut | None = None
    office_day: bool = False
    recovery: HealthRecoveryOut


# -- series -----------------------------------------------------------------


class HealthTrendPointOut(Schema):
    date: date
    value: float
    #: Trailing moving average, null until the window is full.
    average: float | None = None


class HealthTrendOut(Schema):
    metric: str
    label: str
    unit: str
    start: date
    end: date
    window: int
    count: int
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    points: list[HealthTrendPointOut]


class HealthIntradayPointOut(Schema):
    at: datetime
    value: float


class HealthIntradayOut(Schema):
    metric: str
    label: str
    unit: str
    date: date
    count: int
    minimum: float | None = None
    maximum: float | None = None
    points: list[HealthIntradayPointOut]


# -- heatmap ----------------------------------------------------------------


class HealthHeatmapColumnOut(Schema):
    key: str
    label: str
    unit: str
    #: Decimal places for display. The value is sent unrounded so a consumer
    #: that wants the raw number still has it.
    places: int
    #: False for a column shown without a colour, because no defensible
    #: threshold exists for it. See `scoring.WEIGHT`.
    scored: bool
    #: The research behind the thresholds, in one sentence. Rendered under the
    #: table: a colour that cannot say why it is red is just decoration.
    evidence: str
    days: int
    mean_score: float | None = None


class HealthHeatmapCellOut(Schema):
    key: str
    #: In the column's display unit, not the stored one - hours, not minutes.
    value: float | None = None
    #: 0-1, or null when there is no value or no threshold for it.
    score: float | None = None
    #: 1 (worst) to 5 (best). The colour step.
    band: int | None = None


class HealthHeatmapRowOut(Schema):
    date: date
    #: Unweighted mean of the day's scored cells.
    score: float | None = None
    band: int | None = None
    #: How many cells that mean is over. A 0.9 from one metric is not the same
    #: claim as a 0.9 from eleven, and the row cannot say so without this.
    scored_count: int
    #: Aligned to `columns`, same order, one cell each.
    cells: list[HealthHeatmapCellOut]


class HealthHeatmapOut(Schema):
    start: date
    end: date
    days: int
    #: Only columns with at least one value in the window.
    columns: list[HealthHeatmapColumnOut]
    #: Newest first, and only days holding data.
    rows: list[HealthHeatmapRowOut]


# -- habits -----------------------------------------------------------------


class HealthHabitRowOut(Schema):
    id: UUID
    name: str
    #: One boolean per date in `HealthHabitHistoryOut.dates`, same order. A
    #: parallel array rather than a list of dates, because the grid is rendered
    #: cell by cell and a membership test per cell is what makes it slow.
    completed: list[bool]
    current_streak: int
    best_streak: int
    total: int
    rate_7: float
    rate_30: float


class HealthHabitHistoryOut(Schema):
    start: date
    end: date
    dates: list[date]
    habits: list[HealthHabitRowOut]


# -- diet -------------------------------------------------------------------


class HealthFoodFlagOut(Schema):
    key: str
    label: str
    #: "watch" or "good". The UI cannot infer which from the label.
    tone: str


class HealthDietEntryOut(Schema):
    id: UUID
    name: str
    at: datetime
    local_date: date
    flags: list[str] = []
    #: Null until the phone has uploaded the photo via `/sync/photo` - the row
    #: itself lands with the rest of the batch well before that, so the entry
    #: is never hidden for want of a picture. See `HealthDocOut.image_url`.
    image_url: str | None = None


class HealthTopFoodOut(Schema):
    name: str
    count: int


class HealthDietLogOut(Schema):
    start: date
    end: date
    days: int
    search: str = ""
    entries: list[HealthDietEntryOut]
    top: list[HealthTopFoodOut]
    caffeine: list[HealthDietEntryOut]
    flag_catalogue: list[HealthFoodFlagOut]


# -- gut --------------------------------------------------------------------


class HealthBristolCountOut(Schema):
    bristol: int
    count: int


class HealthGutEntryOut(HealthBmItemOut):
    """A Bristol observation with the day it belongs to.

    The day view's `HealthBmItemOut` omits `local_date` because everything in
    that response is already one known day. Here the list spans a window, so
    each row has to say which day it is on - and inheriting rather than
    redefining keeps the two from drifting on the fields they share.
    """

    local_date: date


class HealthBadDayOut(Schema):
    date: date
    worst: int
    mean: float
    #: Everything eaten that day and the day before it.
    foods: list[str]


class HealthBristolDayOut(Schema):
    date: date
    #: Seven counts, for scores 1 through 7, in that order. A parallel array
    #: rather than a mapping because it is drawn as seven stacked segments in a
    #: fixed order, and a dict would let a key go missing mid-chart.
    counts: list[int]
    total: int


class HealthBristolDailyOut(Schema):
    start: date
    end: date
    days: int
    #: Days with no observations are absent, not zero. A gap is honest; a zero
    #: column asserts that nothing happened.
    points: list[HealthBristolDayOut]


class HealthGutSuspectOut(Schema):
    """A frequency count, deliberately not a correlation.

    `days_eaten` sits beside `before_bad_days` because without it the table
    indicts whatever is eaten most often. See `services.gut_detail`.
    """

    name: str
    before_bad_days: int
    days_eaten: int
    share: float


class HealthGutOut(Schema):
    start: date
    end: date
    days: int
    entries: list[HealthGutEntryOut]
    distribution: list[HealthBristolCountOut]
    bad_days: list[HealthBadDayOut]
    suspects: list[HealthGutSuspectOut]
    bad_day_count: int


# -- body -------------------------------------------------------------------


class HealthBodyMeasurementOut(Schema):
    id: UUID
    local_date: date
    waist_cm: float | None = None
    hips_cm: float | None = None
    neck_cm: float | None = None
    body_fat_pct: float | None = None
    notes: str = ""


class HealthFitnessTestOut(Schema):
    id: UUID
    local_date: date
    grip_kg: float | None = None
    single_leg_balance_s: float | None = None
    sit_to_stand_reps: int | None = None
    dead_hang_s: float | None = None
    notes: str = ""


class HealthWeightEntryOut(Schema):
    id: UUID
    local_date: date
    weight_kg: float
    notes: str = ""


class HealthBodyColumnOut(Schema):
    """One column of the Body table, and whether it carries a colour."""

    key: str
    label: str
    unit: str
    places: int
    #: False means the column has no threshold behind it and is drawn plain.
    #: An uncoloured number says "no opinion"; a guessed colour does not.
    scored: bool
    evidence: str = ""


class HealthBodyCellOut(Schema):
    key: str
    value: float | None = None
    score: float | None = None
    #: 1 (worst) to 5 (best), or null when the column is unscored or empty.
    band: int | None = None


class HealthBodyRowOut(Schema):
    date: date
    cells: list[HealthBodyCellOut]


class HealthBodyOut(Schema):
    start: date
    end: date
    days: int
    #: From the profile. Null means BMI and the waist-to-height ratio are not
    #: derivable, not that they are zero.
    height_cm: float | None = None
    #: The user's own goal, not a clinical threshold. Null means the weight
    #: column is drawn without a colour.
    target_weight_kg: float | None = None
    weights: list[HealthWeightEntryOut]
    measurements: list[HealthBodyMeasurementOut]
    columns: list[HealthBodyColumnOut]
    rows: list[HealthBodyRowOut]


class HealthFitnessOut(Schema):
    start: date
    end: date
    days: int
    tests: list[HealthFitnessTestOut]


class HealthBodyProfileOut(Schema):
    height_cm: float | None = None
    target_weight_kg: float | None = None


class HealthBodyProfileIn(Schema):
    """A PATCH of the two Body numbers.

    Both optional, and `None` is a meaningful value: sending `height_cm: null`
    unsets the height. `api.set_body_profile` passes the keys actually present
    in the request through to the service, so an absent key means "leave it"
    while a null one means "clear it".
    """

    height_cm: float | None = None
    target_weight_kg: float | None = None


class HealthWeightIn(Schema):
    weight_kg: float
    #: Absent means today in the user's own timezone. `local_date` is stored,
    #: not computed, so this decides the day forever.
    on: date | None = None
    notes: str = ""


class HealthMeasurementIn(Schema):
    """Tape-measure numbers. Every field optional, but not all of them."""

    waist_cm: float | None = None
    hips_cm: float | None = None
    neck_cm: float | None = None
    body_fat_pct: float | None = None
    on: date | None = None
    notes: str = ""


# -- labs -------------------------------------------------------------------


class HealthLabResultOut(Schema):
    id: UUID
    taken_on: date
    value: float
    unit: str = ""
    notes: str = ""


class HealthLabMarkerOut(Schema):
    #: Case-folded marker name. The grouping key, not for display.
    key: str
    name: str
    unit: str = ""
    count: int
    latest_value: float
    latest_on: date
    minimum: float
    maximum: float
    #: Oldest first - this is what a chart plots.
    results: list[HealthLabResultOut]


# -- notes and documents ----------------------------------------------------


class HealthNoteOut(Schema):
    id: UUID
    title: str = ""
    #: Plain text, with the block-JSON format already flattened.
    body: str = ""
    at: datetime
    local_date: date


class HealthDocOut(Schema):
    id: UUID
    title: str = ""
    at: datetime
    local_date: date
    #: Null until the phone uploads the photo via `/sync/photo`.
    image_url: str | None = None


# -- entries timeline --------------------------------------------------------


class HealthEntryOut(Schema):
    id: UUID
    type: str
    label: str
    at: datetime
    value: str
    #: Detail lines under `value`, one per line. Only `gym` fills it, where
    #: the card is an exercise and each line is one set ("80 kg x 10 reps") -
    #: every other type says everything it has to in `value`.
    lines: list[str] = []
    #: Set only for `diet`/`doc` rows with a synced photo. See
    #: `HealthDietEntryOut.image_url` for why it can be null on a row that
    #: otherwise looks complete.
    image_url: str | None = None


class HealthEntriesDayOut(Schema):
    date: date
    entries: list[HealthEntryOut]


class HealthEntryDeleteOut(Schema):
    id: UUID
    deleted: bool = True


# -- gym --------------------------------------------------------------------


class HealthGymDayOut(Schema):
    date: date
    tonnage_kg: float


class HealthGymCellOut(Schema):
    #: Null when the exercise was not trained that day. Not 0 - a movement you
    #: skipped is absent, not lifted with no weight.
    tonnage_kg: float | None = None
    #: The day's sets, compactly: `40x10`, or `10 reps` when bodyweight.
    sets: list[str] = []


class HealthGymExerciseOut(Schema):
    name: str
    total_kg: float
    #: One per date in `HealthGymLogOut.dates`, same order. A parallel array
    #: rather than a map, for the reason `HealthHabitRowOut.completed` is one.
    cells: list[HealthGymCellOut]


class HealthGymLogOut(Schema):
    start: date
    end: date
    days: int
    #: Only days actually trained, newest first - the grid's column order.
    dates: list[date]
    #: The same days oldest first, because a chart reads through time.
    series: list[HealthGymDayOut]
    exercises: list[HealthGymExerciseOut]
    total_kg: float
    sessions: int


# -- office days ------------------------------------------------------------


class HealthOfficeMonthOut(Schema):
    month: int
    count: int


class HealthOfficeOut(Schema):
    year: int
    years: list[int]
    days: list[date]
    by_month: list[HealthOfficeMonthOut]
    total: int
    #: The bounds of the whole record. Outside them nothing can be inferred -
    #: absence means unknown, not work-from-home.
    covers_from: date | None = None
    covers_to: date | None = None


class HealthOfficeDayOut(Schema):
    local_date: date
    worked: bool


class HealthOfficeReportDaysOut(Schema):
    wfh: int
    office: int
    weekend: int
    #: Weekdays inside the window but outside the office-day record's
    #: coverage - unclassifiable, not counted as either bucket.
    excluded: int


class HealthOfficeReportMetricOut(Schema):
    metric: str
    label: str
    unit: str
    #: "up" or "down" - which bucket mean is the good one. Null for most
    #: metrics: the report states the numbers and lets you judge them
    #: rather than asserting a direction the codebase doesn't otherwise back.
    direction: str | None = None
    wfh: float | None = None
    office: float | None = None
    weekend: float | None = None
    wfh_days: int
    office_days: int
    weekend_days: int
    #: The spread across buckets as a percentage of their overall mean, so a
    #: five-bpm resting-heart-rate swing and a two-thousand-step swing can be
    #: ranked on one scale. Used to order "biggest swings", not shown as a
    #: verdict.
    swing_pct: float | None = None


class HealthOfficeReportOut(Schema):
    start: date
    end: date
    days: HealthOfficeReportDaysOut
    covers_from: date | None = None
    covers_to: date | None = None
    metrics: list[HealthOfficeReportMetricOut]


# -- seasons ------------------------------------------------------------


class HealthSeasonReportDaysOut(Schema):
    summer: int
    autumn: int
    winter: int
    spring: int


class HealthSeasonReportMetricOut(Schema):
    metric: str
    label: str
    unit: str
    #: "up" or "down" - see `HealthOfficeReportMetricOut.direction`, the same
    #: restraint applies here.
    direction: str | None = None
    summer: float | None = None
    autumn: float | None = None
    winter: float | None = None
    spring: float | None = None
    summer_days: int
    autumn_days: int
    winter_days: int
    spring_days: int
    #: See `HealthOfficeReportMetricOut.swing_pct`.
    swing_pct: float | None = None


class HealthSeasonReportOut(Schema):
    start: date
    end: date
    days: HealthSeasonReportDaysOut
    metrics: list[HealthSeasonReportMetricOut]


# -- AI prompt report ---------------------------------------------------


class HealthAiReportOut(Schema):
    generated_at: datetime
    start: date
    end: date
    #: The whole document, ready to paste into a chatbot. Not split into
    #: fields per section - a chatbot reads prose, and there is no second
    #: consumer of the pieces the way `HealthOfficeReportOut.metrics` has
    #: the report page as one and MCP as a plausible second.
    markdown: str


# -- sleep ------------------------------------------------------------------


class HealthSleepSessionOut(Schema):
    id: UUID
    local_date: date
    started_at: datetime
    ended_at: datetime
    duration_minutes: int
    efficiency: int | None = None
    minutes_deep: int
    minutes_light: int
    minutes_rem: int
    minutes_awake: int
    awakenings_count: int
    sleep_score: int | None = None
    #: Whether this night has stage segments, and so a hypnogram to open.
    has_hypnogram: bool = False
    #: Scored cells for the table, aligned to `HealthSleepHistoryOut.columns`.
    #: Same shape and the same thresholds as the heatmap page's cells.
    cells: list[HealthHeatmapCellOut] = []


class HealthSleepPreviousOut(Schema):
    """The window before this one, for "what changed"."""

    #: False when either half holds too few nights to compare. A change
    #: measured against two nights is noise with a direction on it.
    comparable: bool
    nights_recorded: int
    duration_delta_minutes: float | None = None
    efficiency_delta: float | None = None


class HealthSleepSummaryOut(Schema):
    target_minutes: int
    #: Nights with a session, and days in the window. Both, because they are
    #: routinely far apart - a watch on the charger is a missing measurement,
    #: not a night of no sleep - and every average here is over the first.
    nights_recorded: int
    days_elapsed: int
    mean_duration_minutes: float | None = None
    mean_efficiency: float | None = None
    shortest_minutes: int | None = None
    longest_minutes: int | None = None
    nights_on_target: int = 0
    #: Average minutes above (positive) or below (negative) target per recorded
    #: night. Deliberately not a cumulative "sleep debt": over a window with
    #: gaps, a total mostly measures the nights nobody recorded.
    mean_shortfall_minutes: float | None = None
    #: Circular standard deviation of bedtime, in minutes. Consistency is
    #: invisible in a duration chart and is its own sleep variable.
    bedtime_spread_minutes: int | None = None
    previous: HealthSleepPreviousOut


class HealthSleepColumnOut(Schema):
    """One column of the night-by-night table."""

    key: str
    label: str
    unit: str
    places: int
    evidence: str


class HealthSleepHistoryOut(Schema):
    start: date
    end: date
    days: int
    sessions: list[HealthSleepSessionOut]
    #: The table's columns, in reading order. Cells on each session align to
    #: these by position, as on the heatmap.
    columns: list[HealthSleepColumnOut] = []
    summary: HealthSleepSummaryOut


# -- one night --------------------------------------------------------------


class HealthNightSegmentOut(Schema):
    """One run of one stage. The hypnogram is the list of these."""

    level: str
    started_at: datetime
    ended_at: datetime
    seconds: int
    #: Fitbit's `shortData` - stirrings under three minutes, overlaid on the
    #: trace rather than interrupting it.
    is_short: bool


class HealthNightPointOut(Schema):
    at: datetime
    value: float


class HealthNightRemPeriodOut(Schema):
    started_at: datetime
    ended_at: datetime
    minutes: float


class HealthNightArchitectureOut(Schema):
    sleep_onset_minutes: float | None = None
    rem_latency_minutes: float | None = None
    #: Wake after sleep onset. Time awake *before* falling asleep is latency,
    #: not fragmentation, and is excluded.
    waso_minutes: float | None = None
    longest_wake_minutes: float | None = None
    wake_episodes: int = 0
    #: Observed, not completed - the last cycle is usually cut off by waking.
    cycles: int = 0
    rem_periods: list[HealthNightRemPeriodOut] = []
    #: Percentage of total sleep time, per stage.
    stage_share: dict[str, float | None] = {}
    #: `{stage: [low, high]}` normal adult ranges, for drawing beside the share.
    stage_reference: dict[str, list[float]] = {}


class HealthNightDipOut(Schema):
    started_at: datetime
    ended_at: datetime
    lowest: float
    #: Percentage points below the running baseline.
    drop: float
    minutes: int


class HealthNightOxygenOut(Schema):
    count: int
    minimum: float | None = None
    mean: float | None = None
    maximum: float | None = None
    minutes_under_90: int = 0
    minutes_under_88: int = 0
    lowest_at: datetime | None = None
    dips: list[HealthNightDipOut] = []
    #: Estimated dips per hour at each threshold, keyed "3pct"/"4pct". Not an
    #: ODI: see the module docstring in `nights.py`.
    events_per_hour: dict[str, float | None] = {}
    hours_covered: float = 0.0


class HealthNightHeartOut(Schema):
    count: int
    minimum: float | None = None
    mean: float | None = None
    maximum: float | None = None
    lowest_at: datetime | None = None


class HealthNightBaselineOut(Schema):
    """What this sleeper's recent nights look like, so one night can be a delta."""

    days: int
    #: Averages are over recorded nights only, and null below five of them -
    #: two nights is not a personal norm to measure against.
    nights_recorded: int
    coverage_nights: int
    target_minutes: int
    mean_duration_minutes: float | None = None
    mean_efficiency: float | None = None
    shortest_minutes: int | None = None
    longest_minutes: int | None = None


class HealthNightVerdictOut(Schema):
    """The sentence at the top of the page. Rule-based and reproducible."""

    headline: str
    detail: str
    #: Against the personal baseline, and against the target.
    delta_minutes: float | None = None
    target_delta_minutes: float | None = None


class HealthNightSignalOut(Schema):
    key: str
    label: str
    value: str
    #: "ok", "watch" or "concern".
    state: str
    note: str


class HealthNightNeighboursOut(Schema):
    """The recorded nights either side, for paging. Null at the ends."""

    previous: date | None = None
    next: date | None = None
    #: The newest recorded night, so "Last night" means it from any page.
    latest: date | None = None


class HealthNightOut(Schema):
    date: date
    #: The zone the clock times are read in. See `HealthDayOut.timezone`.
    timezone: str
    session: HealthSleepSessionOut
    baseline: HealthNightBaselineOut
    verdict: HealthNightVerdictOut
    signals: list[HealthNightSignalOut] = []
    segments: list[HealthNightSegmentOut]
    #: Minute series clipped to the session, keyed by metric ("hr", "spo2").
    series: dict[str, list[HealthNightPointOut]]
    architecture: HealthNightArchitectureOut
    oxygen: HealthNightOxygenOut
    heart: HealthNightHeartOut
    #: Nightly values with no minute series of their own - breathing rate above
    #: all, which Fitbit publishes once per night and never intraday.
    context: dict[str, float] = {}
    has_hypnogram: bool = False
    neighbours: HealthNightNeighboursOut = HealthNightNeighboursOut()


# -- heart ------------------------------------------------------------------


class HealthHeartZoneOut(Schema):
    """One shaded band on the day chart, as the device defined it."""

    key: str
    label: str
    #: Beats per minute. `ceiling` is null on the topmost band when the day's
    #: estimated maximum was not reported - the band is then open-topped, which
    #: is drawn differently from a band that runs to a known ceiling.
    floor: float
    ceiling: float | None = None
    #: Minutes spent in the zone, from the same payload as the boundaries.
    minutes: float | None = None


class HealthHeartSleepWindowOut(Schema):
    started_at: datetime
    ended_at: datetime
    #: The night's own date, which is the morning it ended on - so a window
    #: shaded at the right-hand end of a day carries tomorrow's date.
    local_date: date


class HealthHeartDayOut(Schema):
    date: date
    #: Local midnight to local midnight, in UTC. The chart's x-axis extent, so
    #: a day with two samples is still drawn as a day rather than as two
    #: minutes stretched across the plot.
    start: datetime
    end: datetime
    points: list[HealthNightPointOut]
    count: int
    minimum: float | None = None
    maximum: float | None = None
    resting_hr: float | None = None
    #: Empty for days synced before the boundaries were stored. The page says
    #: so rather than drawing bands derived some other way.
    zones: list[HealthHeartZoneOut] = []
    sleep: list[HealthHeartSleepWindowOut] = []


class HealthHeartBaselineOut(Schema):
    mean: float
    sd: float
    low: float
    high: float
    days: int


class HealthHeartPointOut(Schema):
    date: date
    value: float


class HealthHeartSeriesOut(Schema):
    metric: str
    label: str
    unit: str
    #: "up" or "down" - which direction is the good one. Both series share one
    #: axis on the chart, where that is not inferable from the picture.
    direction: str
    points: list[HealthHeartPointOut]
    #: Mean ±1 SD over the trailing month, or null under seven readings.
    baseline: HealthHeartBaselineOut | None = None


class HealthScoredColumnOut(Schema):
    key: str
    label: str
    unit: str
    places: int
    evidence: str
    #: False for a column shown without a colour, because no threshold for it
    #: would be honest.
    scored: bool = True


class HealthScoredRowOut(Schema):
    date: date
    cells: list[HealthHeatmapCellOut]


class HealthHeartHistoryOut(Schema):
    start: date
    end: date
    days: int
    series: list[HealthHeartSeriesOut]
    columns: list[HealthScoredColumnOut] = []
    rows: list[HealthScoredRowOut] = []


# -- activity ---------------------------------------------------------------


class HealthExerciseTypeOut(Schema):
    name: str
    count: int
    minutes: float


class HealthExerciseWeekOut(Schema):
    #: The Monday the week starts on, not an ISO week string - an axis has to
    #: sort and label this.
    week: date
    minutes: float
    sessions: int


class HealthActivityOut(Schema):
    start: date
    end: date
    days: int
    by_type: list[HealthExerciseTypeOut]
    weekly: list[HealthExerciseWeekOut]
    sessions: int
    minutes: float


class HealthActivityHourOut(Schema):
    #: Local hour, 0-23. Always all twenty-four, including the empty ones - a
    #: bar chart of only the hours that had steps is a chart with no night in
    #: it.
    hour: int
    steps: float


class HealthActivityDayOut(Schema):
    date: date
    #: Local midnight to local midnight, in UTC. The x-axis extent, so a day
    #: with an hour of data is still drawn as a day.
    start: datetime
    end: datetime
    #: The climb: cumulative steps, carried only at the minutes it bends on.
    points: list[HealthNightPointOut]
    hours: list[HealthActivityHourOut] = []
    count: int
    total: float | None = None
    goal: int
    #: When the goal was crossed, or null on a day that did not cross it.
    goal_reached_at: datetime | None = None
    distance_km: float | None = None
    calories_burned: float | None = None
    active_minutes: float | None = None
    vigorous_minutes: float | None = None
    resting_hr: float | None = None
    sleep: list[HealthHeartSleepWindowOut] = []


class HealthActivityBarOut(Schema):
    date: date
    steps: float
    #: Moderate-to-vigorous minutes, or null when neither bucket was reported.
    active_minutes: float | None = None
    #: 1 (worst) to 5 (best), scored from `active_minutes`. Null means the day
    #: has steps but no intensity, which is drawn uncoloured rather than as a
    #: rest day.
    band: int | None = None


class HealthActivityPointOut(Schema):
    date: date
    value: float


class HealthActivitySeriesOut(Schema):
    metric: str
    label: str
    unit: str
    points: list[HealthActivityPointOut]


class HealthActivitySummaryOut(Schema):
    days_elapsed: int
    days_recorded: int
    mean_steps: float | None = None
    best_steps: float | None = None
    goal_days: int = 0
    mean_active_minutes: float | None = None
    active_days: int = 0
    #: The daily mean times seven. Stated per week because the recommendation
    #: is, and the window is not.
    active_per_week: float | None = None
    mean_vigorous_minutes: float | None = None
    vigorous_days: int = 0
    vigorous_per_week: float | None = None
    #: Waking hours only - Fitbit's sedentary total counts sleep.
    mean_sitting_hours: float | None = None
    sitting_days: int = 0


class HealthActivityHistoryOut(Schema):
    start: date
    end: date
    days: int
    goal: int
    bars: list[HealthActivityBarOut] = []
    #: Seven-day trailing mean of steps, omitted on days too sparse to have one.
    trailing: list[HealthActivityPointOut] = []
    series: list[HealthActivitySeriesOut] = []
    columns: list[HealthScoredColumnOut] = []
    rows: list[HealthScoredRowOut] = []
    summary: HealthActivitySummaryOut
    #: The logged workout library over the same window, for the card under the
    #: table. Null when the caller asked not to pay for it.
    logged: HealthActivityOut | None = None


# -- provider connections ---------------------------------------------------


class HealthConnectionOut(Schema):
    """One provider's state. Never carries a secret, in either direction.

    The client secret is write-only: it goes in through the settings form and
    is never read back out, so a compromised session cannot exfiltrate one
    that was set up earlier.
    """

    provider: str
    label: str
    status: str
    configured: bool = False
    connected: bool = False
    client_id: str = ""
    #: The exact string sent as `redirect_uri`, so the settings page tells you
    #: what to register rather than guessing from the browser's own address.
    #: Fitbit demands a byte-for-byte match, and this server's value can differ
    #: from the origin you happen to be browsing from.
    redirect_uri: str = ""
    scopes: list[str] = []
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync_error: str = ""
    synced_through: date | None = None


class HealthConnectionCredentialsIn(Schema):
    client_id: str
    #: Blank leaves the stored secret alone, so the form can be re-saved to
    #: change only the client id.
    client_secret: str = ""


class HealthAuthorizeOut(Schema):
    authorize_url: str


class HealthExchangeIn(Schema):
    code: str
    state: str


class HealthSyncQueued(Schema):
    provider: str
    queued: bool
    message: str


def connection_to_schema(connection) -> HealthConnectionOut:
    from django.conf import settings

    from .models import Connection

    return HealthConnectionOut(
        provider=connection.provider,
        label=Connection.Provider(connection.provider).label,
        status=connection.status,
        configured=connection.is_configured,
        connected=connection.is_connected,
        client_id=connection.client_id,
        redirect_uri=settings.FITBIT_REDIRECT_URI,
        scopes=list(connection.scopes or []),
        connected_at=connection.connected_at,
        last_sync_at=connection.last_sync_at,
        last_sync_error=connection.last_sync_error,
        synced_through=connection.synced_through,
    )


# --------------------------------------------------------------------------
# Phone sync
# --------------------------------------------------------------------------
#
# The request shapes mirror the Kotlin entities field for field, in the phone's
# own units and spellings: epoch milliseconds, `weightKg`, a `date` string. The
# translation happens here rather than on the device because the server is the
# side that can be fixed without an app store release.


class HealthGymExerciseIn(Schema):
    """One row of the phone's exercise catalogue.

    Sent alongside the sets because `GymSet.exercise` is a foreign key to it -
    without the catalogue, every set arrives unlinked and the exercise history
    view on the portal has nothing to group by.
    """

    #: The Room primary key: a UUID the phone generated. Identity, everywhere.
    id: str
    name: str
    last_weight_kg: float | None = None
    last_reps: int | None = None
    #: Epoch milliseconds, from Android's `System.currentTimeMillis()`.
    updated_at: int = 0
    deleted: bool = False


class HealthGymSetIn(Schema):
    id: str
    exercise_name: str
    weight_kg: float = 0
    reps: int = 0
    #: "YYYY-MM-DD" in the phone's local timezone. Sent rather than derived
    #: from the timestamp: a set logged at 11pm belongs to that day's workout
    #: even when the server reads the instant in UTC and calls it tomorrow.
    date: str
    timestamp: int = 0
    updated_at: int = 0
    deleted: bool = False


class HealthGymSyncIn(Schema):
    exercises: list[HealthGymExerciseIn] = []
    sets: list[HealthGymSetIn] = []


class HealthEntrySyncIn(Schema):
    """One batch of hand-logged rows from the phone — everything except gym.

    Every list is optional, so the phone sends only the types it has queued and
    a newer app talking to an older server degrades to "that type stays
    queued" rather than a 422 that strands the whole batch.

    The rows are deliberately loose (`dict`, not a schema per type). There are
    twelve types and the field mapping already lives in exactly one place,
    `entrysync.SPECS`; a parallel set of pydantic classes here would be a
    second place to update and a second place to forget. Validation is not
    lost - it happens per row in `entrysync`, where a bad row becomes a named
    rejection instead of a 422 that takes the other forty good rows with it.

    Every row carries `id` (the phone's UUID), `updated_at` (epoch ms) and
    `deleted`; time-bearing types add `timestamp` (epoch ms) or `date`
    ("YYYY-MM-DD").
    """

    diet: list[dict] = []
    exercise: list[dict] = []
    notes: list[dict] = []
    bm: list[dict] = []
    bp: list[dict] = []
    weight: list[dict] = []
    body: list[dict] = []
    fitness: list[dict] = []
    docs: list[dict] = []
    labs: list[dict] = []
    office_days: list[dict] = []
    habits: list[dict] = []
    habit_completions: list[dict] = []


class HealthSyncRejectionOut(Schema):
    id: str
    reason: str


class HealthSyncResultOut(Schema):
    """Per-row outcomes, never a bare 204.

    The phone marks synced *only* what appears in `accepted`. Reporting success
    for the batch is what loses data: one row the server could not store, and
    the phone forgets it forever while the request that dropped it returns 200.
    Rejections are returned rather than retried into oblivion, so a row that
    can never succeed can be surfaced instead of blocking the queue behind it.
    """

    accepted: list[str] = []
    rejected: list[HealthSyncRejectionOut] = []
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0


class HealthPhotoSyncOut(Schema):
    """One file, one reply - unlike the batch endpoints, a photo upload is
    never worth grouping: multipart bodies do not compose the way JSON rows
    do, and a phone with several pending photos already retries them one at a
    time.
    """

    stored: bool
    #: Set only when `stored` is false. Named so the phone can tell "the entry
    #: has not synced yet - try again next pass" from "this will never work"
    #: without parsing prose.
    reason: str | None = None
