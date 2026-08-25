package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.PersonalNote
import kotlinx.coroutines.flow.Flow

@Dao
interface NoteDao {
    @Query("SELECT * FROM personal_notes WHERE timestamp >= :startMs AND timestamp < :endMs AND deletedAt IS NULL ORDER BY timestamp ASC")
    fun getEntriesForDay(startMs: Long, endMs: Long): Flow<List<PersonalNote>>

    @Query("SELECT * FROM personal_notes WHERE timestamp >= :startMs AND timestamp < :endMs AND deletedAt IS NULL ORDER BY timestamp ASC")
    suspend fun getEntriesForRange(startMs: Long, endMs: Long): List<PersonalNote>

    @Query("SELECT * FROM personal_notes WHERE deletedAt IS NULL ORDER BY timestamp DESC")
    fun getAllNotes(): Flow<List<PersonalNote>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(note: PersonalNote)

    @Delete
    suspend fun delete(note: PersonalNote)

    @Query("SELECT * FROM personal_notes WHERE isSynced = 0")
    suspend fun getUnsynced(): List<PersonalNote>

    @Query("SELECT COUNT(*) FROM personal_notes WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE personal_notes SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    /**
     * Tombstone rather than remove.
     *
     * Clearing `isSynced` is what puts the row back in the queue: without it,
     * deleting an already-synced entry would be a purely local change the
     * portal never hears about.
     */
    @Query("UPDATE personal_notes SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    /**
     * Drop tombstones the server has acknowledged. Only once `isSynced` is
     * set — any earlier and there would be nothing left to resend.
     */
    @Query("DELETE FROM personal_notes WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
