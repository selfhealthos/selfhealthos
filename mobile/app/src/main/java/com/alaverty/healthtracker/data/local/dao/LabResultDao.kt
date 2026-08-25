package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.LabResult
import kotlinx.coroutines.flow.Flow

@Dao
interface LabResultDao {
    @Query("SELECT * FROM lab_results WHERE deletedAt IS NULL ORDER BY date DESC, markerName ASC")
    fun getAll(): Flow<List<LabResult>>

    @Query("SELECT * FROM lab_results WHERE deletedAt IS NULL ORDER BY date ASC")
    suspend fun getAllSnapshot(): List<LabResult>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(result: LabResult)

    @Delete
    suspend fun delete(result: LabResult)

    @Query("SELECT * FROM lab_results WHERE isSynced = 0")
    suspend fun getUnsynced(): List<LabResult>

    @Query("SELECT COUNT(*) FROM lab_results WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE lab_results SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE lab_results SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM lab_results WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
