package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.Habit
import kotlinx.coroutines.flow.Flow

@Dao
interface HabitDao {
    @Query("SELECT * FROM habits WHERE deletedAt IS NULL ORDER BY sortOrder ASC, createdAt ASC")
    fun getAll(): Flow<List<Habit>>

    @Query("SELECT * FROM habits WHERE deletedAt IS NULL ORDER BY sortOrder ASC, createdAt ASC")
    suspend fun getAllSnapshot(): List<Habit>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(habit: Habit)

    @Delete
    suspend fun delete(habit: Habit)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE habits SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM habits WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()

    /** Everything the server has not acknowledged, tombstones included. */
    @Query("SELECT * FROM habits WHERE isSynced = 0")
    suspend fun getUnsynced(): List<Habit>

    @Query("SELECT COUNT(*) FROM habits WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE habits SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)
}
