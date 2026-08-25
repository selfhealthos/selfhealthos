package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "diet_entries")
data class DietEntry(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val name: String,
    val photoPath: String? = null,
    val timestamp: Long,
    val updatedAt: Long = System.currentTimeMillis(),
    val isSynced: Boolean = false,
    /**
     * Whether [photoPath]'s file has reached the portal. Separate from
     * [isSynced]: the row's fields go up in the JSON batch, but the actual
     * bytes are a second, multipart request that can only succeed once the
     * row exists server-side - see `PhotoSyncManager`. Meaningless when
     * [photoPath] is null.
     */
    val photoSynced: Boolean = false,
    /**
     * Soft delete. A row removed here must survive long enough to tell the
     * portal about it: a hard delete would leave the entry on the server
     * forever with nothing left locally to say it went. Purged once the
     * deletion has been acknowledged.
     */
    val deletedAt: Long? = null
)
