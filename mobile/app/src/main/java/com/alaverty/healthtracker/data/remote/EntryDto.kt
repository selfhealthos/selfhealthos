package com.alaverty.healthtracker.data.remote

import com.alaverty.healthtracker.data.local.entity.BmEntry
import com.alaverty.healthtracker.data.local.entity.BodyMeasurement
import com.alaverty.healthtracker.data.local.entity.BpEntry
import com.alaverty.healthtracker.data.local.entity.DietEntry
import com.alaverty.healthtracker.data.local.entity.DocEntry
import com.alaverty.healthtracker.data.local.entity.ExerciseEntry
import com.alaverty.healthtracker.data.local.entity.FitnessTest
import com.alaverty.healthtracker.data.local.entity.Habit
import com.alaverty.healthtracker.data.local.entity.HabitCompletion
import com.alaverty.healthtracker.data.local.entity.LabResult
import com.alaverty.healthtracker.data.local.entity.PersonalNote
import com.alaverty.healthtracker.data.local.entity.WeightEntry
import com.alaverty.healthtracker.data.local.entity.WfhEntry
import com.google.gson.annotations.SerializedName

/**
 * Wire shapes for `POST /api/v1/health/sync/entries` — every type except gym.
 *
 * Written out rather than posting the Room entities directly, for the reason
 * given in [HomeDto]: serialising the entities would make their column names
 * part of the API contract, so renaming one or adding a local-only field like
 * `isSynced` would change what the server receives.
 *
 * Three fields are on every row and carry the whole protocol:
 *
 *  - `id` — the UUID the phone generated when the row was first saved, offline.
 *    Identity. It is what makes a resend safe.
 *  - `updated_at` — the phone's own `updatedAt`, in epoch millis. Higher wins,
 *    which is the only conflict rule available without a coordinator.
 *  - `deleted` — a tombstone, not an absence. A row missing from the batch
 *    means "nothing to say about it", never "delete it".
 */

data class EntrySyncRequest(
    val diet: List<DietDto> = emptyList(),
    val exercise: List<ExerciseDto> = emptyList(),
    val notes: List<NoteDto> = emptyList(),
    val bm: List<BmDto> = emptyList(),
    val bp: List<BpDto> = emptyList(),
    val weight: List<WeightDto> = emptyList(),
    val body: List<BodyDto> = emptyList(),
    val fitness: List<FitnessDto> = emptyList(),
    val docs: List<DocDto> = emptyList(),
    val labs: List<LabDto> = emptyList(),
    @SerializedName("office_days") val officeDays: List<OfficeDayDto> = emptyList(),
    val habits: List<HabitDto> = emptyList(),
    @SerializedName("habit_completions") val habitCompletions: List<HabitCompletionDto> = emptyList()
) {
    val isEmpty: Boolean
        get() = diet.isEmpty() && exercise.isEmpty() && notes.isEmpty() && bm.isEmpty() &&
            bp.isEmpty() && weight.isEmpty() && body.isEmpty() && fitness.isEmpty() &&
            docs.isEmpty() && labs.isEmpty() && officeDays.isEmpty() && habits.isEmpty() &&
            habitCompletions.isEmpty()

    /** Every id in the batch, for matching against the server's `accepted`. */
    fun allIds(): List<String> =
        diet.map { it.id } + exercise.map { it.id } + notes.map { it.id } + bm.map { it.id } +
            bp.map { it.id } + weight.map { it.id } + body.map { it.id } + fitness.map { it.id } +
            docs.map { it.id } + labs.map { it.id } + officeDays.map { it.id } +
            habits.map { it.id } + habitCompletions.map { it.id }
}

/** The reply. Identical in shape to the gym endpoint's, deliberately. */
data class EntrySyncResponse(
    val accepted: List<String> = emptyList(),
    val rejected: List<SyncRejection> = emptyList(),
    val created: Int = 0,
    val updated: Int = 0,
    val unchanged: Int = 0,
    val deleted: Int = 0
)

data class SyncRejection(val id: String, val reason: String)

// --------------------------------------------------------------------------
// Rows
// --------------------------------------------------------------------------

data class DietDto(
    val id: String,
    val name: String,
    /** The on-device path. Useless to the server, kept so a later photo upload can match. */
    @SerializedName("photo_path") val photoPath: String?,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class ExerciseDto(
    val id: String,
    @SerializedName("video_name") val videoName: String,
    @SerializedName("duration_s") val durationS: Long,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class NoteDto(
    val id: String,
    val title: String,
    val content: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class BmDto(
    val id: String,
    /** The portal calls it what it is: the Bristol Stool Scale, 1-7. */
    val bristol: Int,
    val notes: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class BpDto(
    val id: String,
    val systolic: Int,
    val diastolic: Int,
    val notes: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class WeightDto(
    val id: String,
    @SerializedName("weight_kg") val weightKg: Float,
    val notes: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class BodyDto(
    val id: String,
    @SerializedName("waist_cm") val waistCm: Double?,
    @SerializedName("hips_cm") val hipsCm: Double?,
    @SerializedName("neck_cm") val neckCm: Double?,
    @SerializedName("body_fat_pct") val bodyFatPct: Double?,
    val notes: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class FitnessDto(
    val id: String,
    @SerializedName("grip_kg") val gripKg: Double?,
    @SerializedName("single_leg_balance_s") val singleLegBalanceS: Double?,
    @SerializedName("sit_to_stand_reps") val sitToStandReps: Int?,
    @SerializedName("dead_hang_s") val deadHangS: Double?,
    val notes: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class DocDto(
    val id: String,
    val title: String,
    @SerializedName("photo_path") val photoPath: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class LabDto(
    val id: String,
    @SerializedName("marker_name") val markerName: String,
    val value: Double,
    val unit: String,
    /** The date blood was drawn, which may be well before the row was created. */
    val date: String,
    val notes: String,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class OfficeDayDto(
    val id: String,
    /**
     * The phone's table is called `wfh_entries` and lists office days — the
     * opposite of its name. The portal's model is `OfficeDay`, and this DTO is
     * named for what the rows mean rather than where they came from.
     */
    val date: String,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class HabitDto(
    val id: String,
    val name: String,
    @SerializedName("sort_order") val sortOrder: Int,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class HabitCompletionDto(
    val id: String,
    @SerializedName("habit_name") val habitName: String,
    val date: String,
    @SerializedName("completed_at") val completedAt: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

// --------------------------------------------------------------------------
// Mapping
// --------------------------------------------------------------------------

fun DietEntry.toDto() = DietDto(id, name, photoPath, timestamp, updatedAt, deletedAt != null)

fun ExerciseEntry.toDto() =
    ExerciseDto(id, videoName, durationSeconds, timestamp, updatedAt, deletedAt != null)

fun PersonalNote.toDto() = NoteDto(id, title, content, timestamp, updatedAt, deletedAt != null)

fun BmEntry.toDto() = BmDto(id, bmNumber, notes, timestamp, updatedAt, deletedAt != null)

fun BpEntry.toDto() =
    BpDto(id, systolic, diastolic, notes, timestamp, updatedAt, deletedAt != null)

fun WeightEntry.toDto() = WeightDto(id, weightKg, notes, timestamp, updatedAt, deletedAt != null)

fun BodyMeasurement.toDto() =
    BodyDto(id, waistCm, hipsCm, neckCm, bodyFatPct, notes, timestamp, updatedAt, deletedAt != null)

fun FitnessTest.toDto() = FitnessDto(
    id, gripKg, singleLegBalanceSec, sitToStandReps, deadHangSec, notes,
    timestamp, updatedAt, deletedAt != null
)

fun DocEntry.toDto() = DocDto(id, title, photoPath, timestamp, updatedAt, deletedAt != null)

fun LabResult.toDto() =
    LabDto(id, markerName, value, unit, date, notes, updatedAt, deletedAt != null)

fun WfhEntry.toDto() = OfficeDayDto(id, date, updatedAt, deletedAt != null)

fun Habit.toDto() = HabitDto(id, name, sortOrder, updatedAt, deletedAt != null)

fun HabitCompletion.toDto() =
    HabitCompletionDto(id, habitName, date, completedAt, updatedAt, deletedAt != null)
