package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.FitnessTest
import kotlinx.coroutines.flow.Flow

@Dao
interface FitnessTestDao {
    @Query("SELECT * FROM fitness_tests WHERE deletedAt IS NULL ORDER BY timestamp DESC")
    fun getAll(): Flow<List<FitnessTest>>

    @Query("SELECT * FROM fitness_tests WHERE deletedAt IS NULL ORDER BY timestamp ASC")
    suspend fun getAllSnapshot(): List<FitnessTest>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(test: FitnessTest)

    @Delete
    suspend fun delete(test: FitnessTest)

    @Query("SELECT * FROM fitness_tests WHERE isSynced = 0")
    suspend fun getUnsynced(): List<FitnessTest>

    @Query("SELECT COUNT(*) FROM fitness_tests WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE fitness_tests SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE fitness_tests SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM fitness_tests WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
