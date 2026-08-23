"""Admin registration.

Read-mostly: this data arrives from a phone and a wearable, and the admin exists
to inspect an import, not to hand-author health history. `Sample` is registered
without a changelist search because the table is millions of rows.
"""

from django.contrib import admin

from .models import (
    BmEntry,
    BodyMeasurement,
    BpEntry,
    DailyMetric,
    DietEntry,
    Doc,
    ExerciseEntry,
    FitnessTest,
    GymExercise,
    GymSet,
    Habit,
    HabitCompletion,
    LabResult,
    Note,
    OfficeDay,
    Profile,
    RawIngest,
    Sample,
    SleepSession,
    WeightEntry,
)


class OccurredAdmin(admin.ModelAdmin):
    list_display = ("local_date", "occurred_at", "created_by")
    list_filter = ("local_date", "created_by")
    date_hierarchy = "occurred_at"
    readonly_fields = ("client_id", "client_updated_at")


@admin.register(DietEntry)
class DietEntryAdmin(OccurredAdmin):
    list_display = ("name", "local_date", "occurred_at", "created_by")
    search_fields = ("name",)


@admin.register(ExerciseEntry)
class ExerciseEntryAdmin(OccurredAdmin):
    list_display = ("video_name", "duration_minutes", "local_date", "created_by")
    search_fields = ("video_name",)


@admin.register(BmEntry)
class BmEntryAdmin(OccurredAdmin):
    list_display = ("bristol", "local_date", "occurred_at", "created_by")


@admin.register(BpEntry)
class BpEntryAdmin(OccurredAdmin):
    list_display = ("systolic", "diastolic", "local_date", "created_by")


@admin.register(WeightEntry)
class WeightEntryAdmin(OccurredAdmin):
    list_display = ("weight_kg", "local_date", "occurred_at", "created_by")


@admin.register(Note)
class NoteAdmin(OccurredAdmin):
    list_display = ("title", "local_date", "occurred_at", "created_by")
    search_fields = ("title", "content")


@admin.register(Doc)
class DocAdmin(OccurredAdmin):
    list_display = ("title", "local_date", "created_by")
    search_fields = ("title",)


@admin.register(BodyMeasurement)
class BodyMeasurementAdmin(OccurredAdmin):
    list_display = ("local_date", "waist_cm", "hips_cm", "body_fat_pct", "created_by")


@admin.register(FitnessTest)
class FitnessTestAdmin(OccurredAdmin):
    list_display = ("local_date", "grip_kg", "dead_hang_s", "sit_to_stand_reps", "created_by")


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = ("marker_name", "value", "unit", "taken_on", "created_by")
    list_filter = ("marker_name", "taken_on")
    search_fields = ("marker_name",)


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "archived_at", "created_by")
    search_fields = ("name",)


@admin.register(HabitCompletion)
class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ("habit_name", "local_date", "completed_at", "created_by")
    list_filter = ("habit_name", "local_date")


@admin.register(GymExercise)
class GymExerciseAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "last_weight_kg", "last_reps")
    search_fields = ("name",)


@admin.register(GymSet)
class GymSetAdmin(admin.ModelAdmin):
    list_display = ("exercise_name", "local_date", "weight_kg", "reps", "volume_kg", "created_by")
    list_filter = ("local_date",)
    search_fields = ("exercise_name",)


@admin.register(OfficeDay)
class OfficeDayAdmin(admin.ModelAdmin):
    list_display = ("local_date", "created_by")
    list_filter = ("local_date",)


@admin.register(SleepSession)
class SleepSessionAdmin(admin.ModelAdmin):
    list_display = ("local_date", "duration_minutes", "efficiency", "is_main_sleep", "user")
    list_filter = ("is_main_sleep", "local_date")
    date_hierarchy = "started_at"


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = ("local_date", "metric", "value", "user")
    list_filter = ("metric", "local_date")


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("ts", "metric", "value", "user")
    list_filter = ("metric",)
    # No search and no date_hierarchy: both would scan a very large table.


@admin.register(RawIngest)
class RawIngestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "kind", "row_count", "processed_at", "user")
    list_filter = ("source", "kind")
    readonly_fields = ("payload", "checksum")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "height_cm", "target_weight_kg", "sleep_target_minutes")
