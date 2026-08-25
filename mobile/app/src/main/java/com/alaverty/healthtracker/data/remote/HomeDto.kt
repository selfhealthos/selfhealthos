package com.alaverty.healthtracker.data.remote

import com.alaverty.healthtracker.data.local.entity.GymExercise
import com.alaverty.healthtracker.data.local.entity.GymSet
import com.google.gson.annotations.SerializedName

/**
 * Wire shapes for the portal.
 *
 * Written out rather than serialising the Room entities directly. Gson would
 * happily post a `GymSet` as-is, and the field names would then be part of the
 * API contract: renaming a column, or adding a local-only one like `isSynced`,
 * would change what the server receives. Mapping explicitly costs one function
 * and makes the boundary visible.
 *
 * `@SerializedName` throughout because the portal speaks snake_case and Kotlin
 * does not.
 */

data class EnrolRequest(
    val username: String,
    val password: String,
    @SerializedName("device_name") val deviceName: String,
    /** Server-side bundle (see `apps.tokens.scopes.PRESETS`): health:read, health:write. */
    val preset: String = "claude-write"
)

data class EnrolResponse(
    /** Returned exactly once, on enrolment. There is no endpoint to re-read it. */
    val secret: String,
    val name: String = "",
    val scopes: List<String> = emptyList()
)

data class GymSyncRequest(
    val exercises: List<GymExerciseDto> = emptyList(),
    val sets: List<GymSetDto> = emptyList()
)

data class GymExerciseDto(
    val id: String,
    val name: String,
    @SerializedName("last_weight_kg") val lastWeightKg: Double?,
    @SerializedName("last_reps") val lastReps: Int?,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class GymSetDto(
    val id: String,
    @SerializedName("exercise_name") val exerciseName: String,
    @SerializedName("weight_kg") val weightKg: Double,
    val reps: Int,
    /**
     * "YYYY-MM-DD" as the phone sees it. Sent rather than derived from
     * [timestamp] server-side: a set logged at 11pm belongs to that evening's
     * workout even where the server reads the instant in UTC and calls it the
     * next day.
     */
    val date: String,
    val timestamp: Long,
    @SerializedName("updated_at") val updatedAt: Long,
    val deleted: Boolean
)

data class GymSyncResponse(
    /**
     * The ids the server stored. The *only* thing that may be marked synced.
     *
     * Defaulted to empty rather than left null: a malformed or truncated reply
     * must mark nothing, not everything. The failure this protocol exists to
     * prevent is the phone forgetting a row the server never received.
     */
    val accepted: List<String> = emptyList(),
    /** Rows the server will never accept. Retrying them forever is the bug. */
    val rejected: List<GymSyncRejection> = emptyList(),
    val created: Int = 0,
    val updated: Int = 0,
    val unchanged: Int = 0,
    val deleted: Int = 0
)

data class GymSyncRejection(
    val id: String,
    val reason: String
)

fun GymExercise.toDto() = GymExerciseDto(
    id = id,
    name = name,
    lastWeightKg = lastWeightKg,
    lastReps = lastReps,
    updatedAt = updatedAt,
    deleted = deletedAt != null
)

fun GymSet.toDto() = GymSetDto(
    id = id,
    exerciseName = exerciseName,
    weightKg = weightKg,
    reps = reps,
    date = date,
    timestamp = timestamp,
    updatedAt = updatedAt,
    deleted = deletedAt != null
)
