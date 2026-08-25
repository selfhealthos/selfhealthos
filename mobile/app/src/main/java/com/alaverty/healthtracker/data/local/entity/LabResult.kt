package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "lab_results")
data class LabResult(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val markerName: String,
    val value: Double,
    val unit: String,
    val date: String,           // YYYY-MM-DD test date — may be backdated to when blood was drawn
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
