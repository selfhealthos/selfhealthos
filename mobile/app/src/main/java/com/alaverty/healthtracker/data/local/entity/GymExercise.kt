package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

/**
 * One movement in the catalogue, remembering what was last lifted on it.
 *
 * Synced alongside the sets rather than left local: `GymSet.exercise` on the
 * server is a foreign key to this, so without the catalogue every set arrives
 * unlinked and the portal's per-exercise history has nothing to group by.
 */
@Entity(
    tableName = "gym_exercises",
    indices = [Index(value = ["name"], unique = true)]
)
data class GymExercise(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val name: String,
    val lastWeightKg: Double = 0.0,
    val lastReps: Int = 10,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val isSynced: Boolean = false,
    val deletedAt: Long? = null
)
