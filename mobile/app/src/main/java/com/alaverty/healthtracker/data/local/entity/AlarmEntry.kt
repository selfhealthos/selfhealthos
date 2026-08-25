package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

/**
 * A daily recurring reminder that fires at an exact [hour]:[minute] each day.
 * Device-local config (not part of the GitHub/webhook health-data sync).
 */
@Entity(tableName = "alarms")
data class AlarmEntry(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val label: String,
    val hour: Int,          // 0-23
    val minute: Int,        // 0-59
    val enabled: Boolean = true,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis()
)
