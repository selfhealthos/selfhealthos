package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

// Monthly functional fitness self-test. All fields optional — record whichever tests were done.
@Entity(tableName = "fitness_tests")
data class FitnessTest(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val gripKg: Double? = null,
    val singleLegBalanceSec: Double? = null,
    val sitToStandReps: Int? = null,    // reps in 30 seconds
    val deadHangSec: Double? = null,
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
