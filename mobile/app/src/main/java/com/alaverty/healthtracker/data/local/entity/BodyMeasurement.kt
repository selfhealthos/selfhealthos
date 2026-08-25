package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

// All measurement fields optional — log whichever were taken; at least one enforced in UI
@Entity(tableName = "body_measurements")
data class BodyMeasurement(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val waistCm: Double? = null,
    val hipsCm: Double? = null,
    val neckCm: Double? = null,
    val bodyFatPct: Double? = null,
    val notes: String = "",
    val timestamp: Long,
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
