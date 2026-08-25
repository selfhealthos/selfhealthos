package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(
    tableName = "habit_completions",
    // Non-unique: a habit can be completed more than once a day (e.g. a second dose).
    indices = [Index(value = ["habitId", "date"])]
)
data class HabitCompletion(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val habitId: String,
    val habitName: String,      // denormalised so export rows are self-contained
    val date: String,           // "YYYY-MM-DD" — may have multiple rows per habit per day
    val completedAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val isSynced: Boolean = false,
    /**
     * Soft delete. A row removed here must survive long enough to tell the
     * portal about it: a hard delete would leave the entry on the server
     * forever with nothing left locally to say it went. Purged once the
     * deletion has been acknowledged.
     */
    val deletedAt: Long? = null
)
