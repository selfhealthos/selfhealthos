package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.DietEntry
import kotlinx.coroutines.flow.Flow

@Dao
interface DietDao {
    @Query("SELECT * FROM diet_entries WHERE timestamp >= :startMs AND timestamp < :endMs AND deletedAt IS NULL ORDER BY timestamp ASC")
    fun getEntriesForDay(startMs: Long, endMs: Long): Flow<List<DietEntry>>

    @Query("SELECT * FROM diet_entries WHERE timestamp >= :startMs AND timestamp < :endMs AND deletedAt IS NULL ORDER BY timestamp ASC")
    suspend fun getEntriesForRange(startMs: Long, endMs: Long): List<DietEntry>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entry: DietEntry)

    @Delete
    suspend fun delete(entry: DietEntry)

    @Query("SELECT * FROM diet_entries WHERE isSynced = 0")
    suspend fun getUnsynced(): List<DietEntry>

    @Query("SELECT COUNT(*) FROM diet_entries WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE diet_entries SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE diet_entries SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM diet_entries WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
