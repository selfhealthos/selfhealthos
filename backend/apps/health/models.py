"""Health data model.

Three shapes, chosen by how the data actually behaves rather than by where it
came from:

  * **Domain tables** - hand-logged entries and structured sessions. Real
    columns, real constraints, tens of rows a day.
  * **`Sample`** - intraday telemetry at 1-minute resolution. Narrow, uniform,
    ~9k rows a day, never read by a dashboard.
  * **`DailyMetric`** - one scalar per user per date per metric. Everything that
    draws a chart or answers an MCP question reads this and nothing else.

See `docs/roadmap-health.md` decisions 1-3 for why.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, OwnedModel, OwnedQuerySet, Taggable

from . import metrics

# --------------------------------------------------------------------------
# Abstract bases
# --------------------------------------------------------------------------


class DeviceEntryQuerySet(OwnedQuerySet):
    def live(self) -> DeviceEntryQuerySet:
        """Excludes tombstoned rows. Almost every read wants this."""
        return self.filter(deleted_at__isnull=True)

    def for_user(self, user) -> DeviceEntryQuerySet:
        """Health data is read as one person's, always.

        Unlike the shared library apps, a merged household weight chart is not
        a thing anyone wants. Attribution stays `created_by` (roadmap decision
        4); this is the filter that makes the detail views personal.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(created_by=user)

    def on(self, local_date) -> DeviceEntryQuerySet:
        return self.filter(local_date=local_date)

    def between(self, start, end) -> DeviceEntryQuerySet:
        """Inclusive on both ends - date ranges people type are inclusive."""
        return self.filter(local_date__gte=start, local_date__lte=end)


class DeviceEntry(OwnedModel):
    """An entry that may originate on a phone and sync in later.

    `client_id` is the UUID the Android app generated when the row was first
    saved offline. It is the idempotency key: the same entry arriving twice,
    from two phones or from a re-run import, is one row. Rows created in the
    portal UI have no client id, which is why it is nullable rather than the
    primary key.

    `client_updated_at` is the phone's `updatedAt`. Two phones editing the same
    entry resolve by keeping the higher value - the only conflict rule that
    works without a coordinator.
    """

    client_id = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    client_updated_at = models.DateTimeField(null=True, blank=True, editable=False)

    #: Tombstone. Written by phone sync, and a delete that cannot
    #: propagate is a delete that silently comes back on the next sync, and
    #: adding the column now costs nothing.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = DeviceEntryQuerySet.as_manager()

    class Meta:
        abstract = True


class OccurredEntry(DeviceEntry):
    """A `DeviceEntry` that happened at a moment in time.

    `occurred_at` is a true UTC instant. `local_date` is the calendar day it
    belongs to in the subject's timezone, stored rather than computed: "what did
    I eat today" is otherwise a query no index can serve, and a sleep session
    crossing midnight becomes an argument every time it is read.
    """

    occurred_at = models.DateTimeField(db_index=True)
    local_date = models.DateField(db_index=True)

    class Meta:
        abstract = True
        ordering = ["-occurred_at"]


# --------------------------------------------------------------------------
# Hand-logged entries
# --------------------------------------------------------------------------


class DietEntry(OccurredEntry, Taggable):
    """One food or drink, as typed on the phone.

    Deliberately not nutrition data: the app records what was eaten, not how
    many grams of protein it held. Flagging (caffeine, dairy, added sugar) is a
    rule applied at read time, not a column.
    """

    name = models.CharField(max_length=255)
    #: On-device path from the export. Useless off-device, kept only so the
    #: media backfill in H6 can match a photo to its entry.
    photo_path = models.TextField(blank=True)
    photo = models.ImageField(upload_to="health/diet/%Y/%m/", null=True, blank=True)

    class Meta(OccurredEntry.Meta):
        verbose_name_plural = "diet entries"
        indexes = [models.Index(fields=["created_by", "local_date"])]


class ExerciseEntry(OccurredEntry):
    """A workout session, named after the video followed."""

    video_name = models.CharField(max_length=255)
    duration_s = models.PositiveIntegerField(default=0)

    class Meta(OccurredEntry.Meta):
        verbose_name_plural = "exercise entries"
        indexes = [models.Index(fields=["created_by", "local_date"])]

    @property
    def duration_minutes(self) -> float:
        return round(self.duration_s / 60.0, 1)


class BmEntry(OccurredEntry):
    """Bristol Stool Scale observation. 1-2 constipation, 3-4 ideal, 5-6 loose, 7 diarrhoea."""

    bristol = models.PositiveSmallIntegerField(
        choices=[(n, str(n)) for n in range(1, 8)],
        help_text="Bristol Stool Scale, 1-7.",
    )
    notes = models.TextField(blank=True)

    class Meta(OccurredEntry.Meta):
        verbose_name = "bowel movement"
        indexes = [models.Index(fields=["created_by", "local_date"])]


class BpEntry(OccurredEntry):
    """Blood pressure. Normal <120/80, elevated 120-129/<80, high >=130/80."""

    systolic = models.PositiveSmallIntegerField()
    diastolic = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True)

    class Meta(OccurredEntry.Meta):
        verbose_name = "blood pressure reading"
        indexes = [models.Index(fields=["created_by", "local_date"])]

    @property
    def pulse_pressure(self) -> int:
        return self.systolic - self.diastolic


class WeightEntry(OccurredEntry):
    weight_kg = models.FloatField()
    notes = models.TextField(blank=True)

    class Meta(OccurredEntry.Meta):
        verbose_name_plural = "weight entries"
        indexes = [models.Index(fields=["created_by", "local_date"])]


class Note(OccurredEntry, Taggable):
    """A diary entry.

    `content` is either plain text or a JSON-encoded block array beginning with
    `[` - the Android app changed format partway through and did not migrate
    the old rows. `title` is always plain text, which is why analysis reads it.
    """

    title = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)

    class Meta(OccurredEntry.Meta):
        indexes = [models.Index(fields=["created_by", "local_date"])]

    @property
    def is_block_content(self) -> bool:
        return self.content.lstrip().startswith("[")


class Doc(OccurredEntry, Taggable):
    """A photographed document - pathology result, script, referral."""

    title = models.CharField(max_length=255, blank=True)
    photo_path = models.TextField(blank=True)
    photo = models.ImageField(upload_to="health/docs/%Y/%m/", null=True, blank=True)

    class Meta(OccurredEntry.Meta):
        indexes = [models.Index(fields=["created_by", "local_date"])]


class LabResult(DeviceEntry):
    """One marker from one blood test.

    `marker_name` is free text typed on the phone, so grouping normalises case.
    `taken_on` is the test date and may be backdated well before the row was
    created, which is why this is not an `OccurredEntry`.
    """

    marker_name = models.CharField(max_length=128)
    value = models.FloatField()
    unit = models.CharField(max_length=32, blank=True)
    taken_on = models.DateField(db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-taken_on", "marker_name"]
        indexes = [models.Index(fields=["created_by", "marker_name", "taken_on"])]

    @property
    def marker_key(self) -> str:
        return self.marker_name.strip().lower()


class BodyMeasurement(OccurredEntry):
    """Tape-measure numbers. Every field is optional - only what was taken."""

    waist_cm = models.FloatField(null=True, blank=True)
    hips_cm = models.FloatField(null=True, blank=True)
    neck_cm = models.FloatField(null=True, blank=True)
    body_fat_pct = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(OccurredEntry.Meta):
        indexes = [models.Index(fields=["created_by", "local_date"])]


class FitnessTest(OccurredEntry):
    """Functional self-tests. Higher is better for every one of them."""

    grip_kg = models.FloatField(null=True, blank=True)
    single_leg_balance_s = models.FloatField(null=True, blank=True)
    sit_to_stand_reps = models.PositiveSmallIntegerField(null=True, blank=True)
    dead_hang_s = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(OccurredEntry.Meta):
        indexes = [models.Index(fields=["created_by", "local_date"])]


class OfficeDay(DeviceEntry):
    """A day worked in the office.

    The source file is called `wfh.ndjson` and lists the opposite of what its
    name says - `one-data/CLAUDE.md` records that reading it backwards has
    already inverted an analysis once. The importer translates and the name
    here makes the mistake unrepresentable.

    Absence means unknown, not work-from-home: outside the range the data
    covers, nothing can be inferred.
    """

    local_date = models.DateField(db_index=True)

    class Meta:
        ordering = ["-local_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["created_by", "local_date"], name="health_officeday_unique_day"
            )
        ]


# --------------------------------------------------------------------------
# Habits
# --------------------------------------------------------------------------


class Habit(DeviceEntry):
    name = models.CharField(max_length=128)
    sort_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class HabitCompletion(DeviceEntry):
    """A tick against a habit on a day.

    There can be several rows per habit per day - a second dose of something -
    so "was this habit done today" is an existence check, never a count.
    `habit_name` is denormalised because the phone sends it, and because a habit
    renamed later should not silently rewrite history.
    """

    habit = models.ForeignKey(
        Habit, null=True, blank=True, on_delete=models.SET_NULL, related_name="completions"
    )
    habit_name = models.CharField(max_length=128)
    local_date = models.DateField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-local_date", "habit_name"]
        indexes = [models.Index(fields=["created_by", "local_date"])]


# --------------------------------------------------------------------------
# Gym
# --------------------------------------------------------------------------


class GymExercise(DeviceEntry):
    name = models.CharField(max_length=128)
    #: Muscle group. The Android app does not collect it and the archive has
    #: none, so it stays empty until something supplies it.
    category = models.CharField(max_length=64, blank=True)
    last_weight_kg = models.FloatField(null=True, blank=True)
    last_reps = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class GymSet(DeviceEntry):
    """One set. Volume is stored, not computed on read, because it is summed
    across thousands of rows on every trend query."""

    exercise = models.ForeignKey(
        GymExercise, null=True, blank=True, on_delete=models.SET_NULL, related_name="sets"
    )
    exercise_name = models.CharField(max_length=128)
    local_date = models.DateField(db_index=True)
    performed_at = models.DateTimeField(null=True, blank=True)
    weight_kg = models.FloatField(default=0)
    reps = models.PositiveSmallIntegerField(default=0)
    volume_kg = models.FloatField(default=0)

    class Meta:
        ordering = ["-local_date", "exercise_name"]
        indexes = [models.Index(fields=["created_by", "local_date"])]

    def save(self, *args, **kwargs):
        self.volume_kg = (self.weight_kg or 0) * (self.reps or 0)
        super().save(*args, **kwargs)


# --------------------------------------------------------------------------
# Sleep
# --------------------------------------------------------------------------


class SleepSession(BaseModel):
    """One sleep session from the wearable.

    Not a `DeviceEntry`: it never originates on the phone, and its identity is
    Fitbit's own log id. `local_date` is the date Fitbit assigns, which is the
    morning you woke - the convention every existing query already assumes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sleep_sessions"
    )
    external_id = models.CharField(max_length=64)
    local_date = models.DateField(db_index=True)

    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=0)
    efficiency = models.PositiveSmallIntegerField(null=True, blank=True)

    minutes_deep = models.PositiveSmallIntegerField(default=0)
    minutes_light = models.PositiveSmallIntegerField(default=0)
    minutes_rem = models.PositiveSmallIntegerField(default=0)
    minutes_awake = models.PositiveSmallIntegerField(default=0)
    awakenings_count = models.PositiveSmallIntegerField(default=0)

    is_main_sleep = models.BooleanField(default=True)
    sleep_score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-local_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "external_id"], name="health_sleepsession_unique_external"
            )
        ]
        indexes = [models.Index(fields=["user", "local_date"])]

    def __str__(self) -> str:
        return f"{self.local_date} {self.duration_minutes}min"


class SleepSegment(models.Model):
    """One stage, from when it started to when it ended.

    The hypnogram. `SleepSession` holds how many minutes of each stage a night
    contained, which is the summary; this holds *when*, which is the shape.
    They answer different questions and neither derives the other: two hours of
    deep sleep in one early block is a normal night, and the same two hours
    scattered in eight-minute fragments is not, and the totals are identical.

    Fitbit returns these in `levels.data` on the sleep log the session came
    from. They were being discarded, so the stage columns were all that
    survived a night - and a stacked bar of those totals is the one chart shape
    that destroys the chronology it is drawn from.

    Not a `BaseModel`: a segment is a fact about a session rather than a record
    anyone owns, it is rewritten wholesale whenever its session is re-synced,
    and there are thirty to sixty of them per night.
    """

    class Level(models.TextChoices):
        DEEP = "deep", "Deep"
        LIGHT = "light", "Light"
        REM = "rem", "REM"
        WAKE = "wake", "Awake"
        #: Devices without stage tracking, and Fitbit's older "classic" logs.
        #: Kept as themselves rather than mapped onto the four above: calling
        #: `restless` "light sleep" invents a measurement nobody took.
        ASLEEP = "asleep", "Asleep (unstaged)"
        RESTLESS = "restless", "Restless"
        AWAKE_CLASSIC = "awake", "Awake (unstaged)"
        UNKNOWN = "unknown", "Unknown"

    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(SleepSession, on_delete=models.CASCADE, related_name="segments")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    seconds = models.PositiveIntegerField(default=0)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.UNKNOWN)
    #: From Fitbit's `shortData` - wake episodes under three minutes, which it
    #: reports separately and overlays on the main trace rather than
    #: interrupting it. Kept apart for the same reason: they are momentary
    #: stirrings, and folding them into the main run would shatter every stage
    #: block they land in.
    is_short = models.BooleanField(default=False)

    class Meta:
        ordering = ["started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "started_at", "is_short"],
                name="health_sleepsegment_unique_start",
            )
        ]
        indexes = [models.Index(fields=["session", "started_at"])]

    def __str__(self) -> str:
        return f"{self.level} {self.seconds}s from {self.started_at:%H:%M}"


# --------------------------------------------------------------------------
# Time series
# --------------------------------------------------------------------------


class Sample(models.Model):
    """One intraday reading, at 1-minute resolution.

    Not a `BaseModel`: a UUID primary key and two timestamp columns would more
    than double the width of a row that nothing ever links to, in the one table
    where width is measured in millions of rows. A bigint surrogate is enough.

    The unique constraint is the import's idempotency key *and* the index the
    single-day chart reads, which is why there is no second index beside it.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_samples"
    )
    metric = models.CharField(max_length=metrics.MAX_KEY_LENGTH, choices=metrics.INTRADAY_CHOICES)
    ts = models.DateTimeField()
    value = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "metric", "ts"], name="health_sample_unique_point"
            )
        ]

    def __str__(self) -> str:
        return f"{self.metric}@{self.ts:%Y-%m-%d %H:%M} = {self.value}"


class DailyMetricQuerySet(models.QuerySet):
    def for_user(self, user) -> DailyMetricQuerySet:
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(user=user)

    def series(self, metric: str, start, end) -> DailyMetricQuerySet:
        return self.filter(metric=metric, local_date__gte=start, local_date__lte=end).order_by(
            "local_date"
        )


class DailyMetric(models.Model):
    """One scalar, one person, one day.

    Everything user-facing reads this table: charts, trends, the day view, every
    MCP tool. It is derived - `rollups.py` can rebuild any date from the domain
    tables and `Sample` - so it is safe to delete and recompute, and safe to
    change the definition of a metric by recomputing rather than migrating.
    """

    class Source(models.TextChoices):
        #: Supplied by the device's own daily summary. Authoritative, and never
        #: recomputed - Fitbit's resting heart rate is better than anything
        #: derivable from the minute samples it also gave us.
        DEVICE = "device", "Device daily summary"
        #: Computed by `rollups.py` from entries, sessions or samples. Owned
        #: entirely by the rollup, which is free to overwrite or delete it.
        DERIVED = "derived", "Derived"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_daily"
    )
    local_date = models.DateField()
    metric = models.CharField(max_length=metrics.MAX_KEY_LENGTH, choices=metrics.DAILY_CHOICES)
    value = models.FloatField()
    #: Which writer owns this row. Without it the rollup cannot tell a value it
    #: wrote last night from one the device supplied, so it either clobbers the
    #: device's numbers or freezes its own forever.
    source = models.CharField(max_length=16, choices=Source, default=Source.DERIVED)
    computed_at = models.DateTimeField(auto_now=True)

    objects = DailyMetricQuerySet.as_manager()

    class Meta:
        ordering = ["-local_date", "metric"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "local_date", "metric"], name="health_dailymetric_unique"
            )
        ]
        indexes = [
            # The trend query: one metric, one person, a date range.
            models.Index(fields=["user", "metric", "local_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.local_date} {self.metric}={self.value}"


# --------------------------------------------------------------------------
# Ingest provenance
# --------------------------------------------------------------------------


class RawIngest(BaseModel):
    """What arrived, before anything interpreted it.

    Kept so that fixing a parser is a re-run rather than a re-export from a
    phone that may since have been wiped. Deliberately *not* written by the
    one-data bulk import: that archive is already an immutable git history of
    exactly what arrived, and copying it into JSONB would duplicate 85MB to no
    end.
    """

    class Source(models.TextChoices):
        PHONE = "phone", "Phone sync"
        FITBIT = "fitbit", "Fitbit API"
        IMPORT = "import", "File import"

    source = models.CharField(max_length=16, choices=Source, db_index=True)
    #: What the payload holds, e.g. "diet" or "fitbit_sleep".
    kind = models.CharField(max_length=64, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    payload = models.JSONField(default=dict)
    #: SHA-256 of the payload, so a phone retrying a sync it already delivered
    #: is recognised without re-parsing it.
    checksum = models.CharField(max_length=64, db_index=True, blank=True)
    row_count = models.PositiveIntegerField(default=0)

    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["source", "-created_at"])]


# --------------------------------------------------------------------------
# Provider connections
# --------------------------------------------------------------------------


class Connection(BaseModel):
    """One person's link to one wearable provider.

    **The client credentials are per user, not per household**, which looks
    like duplication and is not. Fitbit grants intraday access automatically
    only to a *Personal* app, and only for the Fitbit account that registered
    it; a single shared registration would have to apply to Fitbit for intraday
    access and wait to be granted it case by case. Since 1-minute intraday data
    is the entire premise of the schema (roadmap decision 1), everyone
    registering their own Personal app is what makes the feature exist at all.

    Secrets are encrypted at rest - see `crypto.py` for what that does and does
    not protect.
    """

    class Provider(models.TextChoices):
        FITBIT = "fitbit", "Fitbit"

    class Status(models.TextChoices):
        #: Credentials saved, no OAuth grant yet.
        CONFIGURED = "configured", "Not connected"
        CONNECTED = "connected", "Connected"
        #: The grant was rejected or revoked. Needs re-authorising, and no
        #: amount of retrying will fix it - which is why it is not "error".
        EXPIRED = "expired", "Needs reconnecting"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_connections"
    )
    provider = models.CharField(max_length=32, choices=Provider)

    client_id = models.CharField(max_length=64, blank=True)
    client_secret_enc = models.TextField(blank=True, editable=False)
    access_token_enc = models.TextField(blank=True, editable=False)
    refresh_token_enc = models.TextField(blank=True, editable=False)

    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    #: The provider's own id for the account, so a connection re-pointed at a
    #: different Fitbit account is visible rather than silently mixing two
    #: people's data into one history.
    provider_user_id = models.CharField(max_length=64, blank=True)

    status = models.CharField(max_length=16, choices=Status, default=Status.CONFIGURED)
    connected_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
    #: Latest day successfully pulled, so an incremental sync knows where to
    #: resume without asking the provider what it already sent.
    synced_through = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["provider"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"], name="health_connection_unique_per_user"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} for {self.user}"

    # -- secrets ---------------------------------------------------------
    #
    # Plaintext is never a field, so it cannot be selected, serialised into an
    # API response or printed by an admin list display by accident.

    @property
    def client_secret(self) -> str:
        from . import crypto

        return crypto.decrypt(self.client_secret_enc)

    @client_secret.setter
    def client_secret(self, value: str) -> None:
        from . import crypto

        self.client_secret_enc = crypto.encrypt(value or "")

    @property
    def access_token(self) -> str:
        from . import crypto

        return crypto.decrypt(self.access_token_enc)

    @access_token.setter
    def access_token(self, value: str) -> None:
        from . import crypto

        self.access_token_enc = crypto.encrypt(value or "")

    @property
    def refresh_token(self) -> str:
        from . import crypto

        return crypto.decrypt(self.refresh_token_enc)

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        from . import crypto

        self.refresh_token_enc = crypto.encrypt(value or "")

    # -- state -----------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret_enc)

    @property
    def is_connected(self) -> bool:
        return self.status == self.Status.CONNECTED and bool(self.refresh_token_enc)

    @property
    def masked_secret(self) -> str:
        """Enough to recognise which secret is stored, never enough to use."""
        return f"••••{self.client_id[-4:]}" if self.client_id else ""


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


class Profile(BaseModel):
    """The context every report needs before it says anything useful.

    Structured where a number is genuinely a number - height drives
    waist-to-height banding - and free text everywhere else, because medical
    history does not fit a schema and pretending otherwise loses the nuance
    that makes it worth reading.

    Birth date and sex live on the account (`accounts.User`), not here - both
    are collected at signup and are account-level identity, not a Health
    setting. `scoring.columns_for()`/`vo2max_threshold()` read `user.age_years`
    and `user.sex` directly; this model only supplies `height_cm`.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_profile"
    )
    height_cm = models.FloatField(null=True, blank=True)

    target_weight_kg = models.FloatField(null=True, blank=True)
    daily_step_goal = models.PositiveIntegerField(null=True, blank=True)
    #: Minutes of sleep aimed for. Stored rather than assumed because the whole
    #: sleep page is framed against it - "20 minutes short" is a sentence, "7h
    #: 10m" is a number - and a target hard-coded in a template cannot be
    #: someone else's. 450 is 7h 30m, the middle of the 7-9h adult range.
    sleep_target_minutes = models.PositiveSmallIntegerField(default=450)

    medical_history = models.TextField(blank=True)
    family_history = models.TextField(blank=True)
    medications = models.TextField(blank=True)
    supplements = models.TextField(blank=True)
    dietary_restrictions = models.TextField(blank=True)
    goals = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Profile for {self.user}"
