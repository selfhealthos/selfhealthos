package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.WfhEntry
import kotlinx.coroutines.flow.Flow

@Dao
interface WfhDao {
    @Query("SELECT * FROM wfh_entries WHERE date LIKE :monthPrefix || '%' AND deletedAt IS NULL ORDER BY date ASC")
    fun getEntriesForMonth(monthPrefix: String): Flow<List<WfhEntry>>

    @Query("SELECT * FROM wfh_entries WHERE date >= :startDate AND date <= :endDate AND deletedAt IS NULL ORDER BY date ASC")
    suspend fun getEntriesForRange(startDate: String, endDate: String): List<WfhEntry>

    @Query("SELECT * FROM wfh_entries WHERE deletedAt IS NULL ORDER BY date ASC")
    suspend fun getAllSnapshot(): List<WfhEntry>

    @Query("SELECT * FROM wfh_entries WHERE isSynced = 0")
    suspend fun getUnsynced(): List<WfhEntry>

    @Query("SELECT COUNT(*) FROM wfh_entries WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entry: WfhEntry)

    /**
     * Tombstone the office day rather than dropping the row.
     *
     * Unmarking a day is a real edit — the portal has to hear that the day it
     * was told about is no longer an office day, or the correction only ever
     * exists on the phone.
     */
    @Query("UPDATE wfh_entries SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE date = :date")
    suspend fun softDeleteByDate(date: String, at: Long)

    @Query("DELETE FROM wfh_entries WHERE date = :date")
    suspend fun deleteByDate(date: String)

    @Query("UPDATE wfh_entries SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE wfh_entries SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM wfh_entries WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
