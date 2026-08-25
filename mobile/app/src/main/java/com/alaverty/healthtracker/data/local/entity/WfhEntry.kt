package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(
    tableName = "wfh_entries",
    indices = [Index(value = ["date"], unique = true)]
)
data class WfhEntry(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val date: String,           // YYYY-MM-DD, office day
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
