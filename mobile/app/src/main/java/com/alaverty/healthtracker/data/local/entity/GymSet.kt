package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "gym_sets")
data class GymSet(
    /**
     * Generated here, on the phone, when the set is first saved — offline,
     * possibly days before the server hears about it. It is the identity the
     * portal merges on, which is what makes a resend safe: the same set sent
     * twice is one row, not two.
     */
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val exerciseName: String,
    val weightKg: Double,
    val reps: Int,
    val date: String,
    val timestamp: Long,
    val updatedAt: Long = System.currentTimeMillis(),
    val isSynced: Boolean = false,
    /**
     * Soft delete. A row removed here has to survive long enough to tell the
     * server about it: a hard delete would leave the set on the portal forever,
     * still counting toward gym volume, with nothing left locally to say it
     * ever went. Cleared from the table by [com.alaverty.healthtracker.data.local.dao.GymSetDao.purgeSyncedTombstones]
     * once the deletion has been acknowledged.
     */
    val deletedAt: Long? = null
)
