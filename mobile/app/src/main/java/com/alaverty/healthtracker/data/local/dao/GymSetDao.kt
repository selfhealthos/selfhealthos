package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.GymSet
import kotlinx.coroutines.flow.Flow

@Dao
interface GymSetDao {
    /** Live rows only — a tombstone is still in the table until it has synced. */
    @Query("SELECT * FROM gym_sets WHERE date = :date AND deletedAt IS NULL ORDER BY timestamp DESC")
    fun getForDate(date: String): Flow<List<GymSet>>

    @Query(
        """SELECT * FROM gym_sets
           WHERE date >= :startDate AND date <= :endDate AND deletedAt IS NULL
           ORDER BY timestamp ASC"""
    )
    suspend fun getForRange(startDate: String, endDate: String): List<GymSet>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(set: GymSet)

    /**
     * Tombstone rather than remove.
     *
     * Also clears `isSynced`, which is what puts the row back in the sync
     * queue: without it, deleting an already-synced set would be a purely local
     * change the portal never hears about.
     */
    @Query("UPDATE gym_sets SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /** Everything the server has not acknowledged, tombstones included. */
    @Query("SELECT * FROM gym_sets WHERE isSynced = 0")
    suspend fun getUnsynced(): List<GymSet>

    @Query("SELECT COUNT(*) FROM gym_sets WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE gym_sets SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Drop tombstones the server has acknowledged.
     *
     * Only once `isSynced` is set: deleting them any earlier is the one way
     * this design can still lose a deletion, because there would be nothing
     * left to resend.
     */
    @Query("DELETE FROM gym_sets WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
