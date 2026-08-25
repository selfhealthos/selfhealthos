package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.HabitCompletion
import kotlinx.coroutines.flow.Flow

@Dao
interface HabitCompletionDao {
    @Query("SELECT * FROM habit_completions WHERE date = :date AND deletedAt IS NULL ORDER BY completedAt ASC")
    fun getForDate(date: String): Flow<List<HabitCompletion>>

    @Query("SELECT * FROM habit_completions WHERE completedAt >= :startMs AND completedAt < :endMs AND deletedAt IS NULL")
    suspend fun getForRange(startMs: Long, endMs: Long): List<HabitCompletion>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(completion: HabitCompletion)

    @Delete
    suspend fun delete(completion: HabitCompletion)

    /**
     * Tombstones every completion of this habit on this day — un-ticking.
     *
     * Not a row removal: the tick has already been sent to the portal, and
     * without a tombstone the day stays ticked there forever while the phone
     * shows it clear.
     */
    @Query(
        """UPDATE habit_completions SET deletedAt = :at, updatedAt = :at, isSynced = 0
           WHERE habitId = :habitId AND date = :date AND deletedAt IS NULL"""
    )
    suspend fun softDeleteForHabitOnDate(habitId: String, date: String, at: Long)

    // Removes every completion of this habit on this day (used when un-ticking).
    @Query("DELETE FROM habit_completions WHERE habitId = :habitId AND date = :date")
    suspend fun deleteByHabitAndDate(habitId: String, date: String)

    @Query("SELECT * FROM habit_completions WHERE isSynced = 0")
    suspend fun getUnsynced(): List<HabitCompletion>

    @Query("SELECT COUNT(*) FROM habit_completions WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE habit_completions SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE habit_completions SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM habit_completions WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
