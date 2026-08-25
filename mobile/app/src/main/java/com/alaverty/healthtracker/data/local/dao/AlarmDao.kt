package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.AlarmEntry
import kotlinx.coroutines.flow.Flow

@Dao
interface AlarmDao {
    @Query("SELECT * FROM alarms ORDER BY hour ASC, minute ASC")
    fun getAll(): Flow<List<AlarmEntry>>

    @Query("SELECT * FROM alarms")
    suspend fun getAllSnapshot(): List<AlarmEntry>

    @Query("SELECT * FROM alarms WHERE enabled = 1")
    suspend fun getEnabledSnapshot(): List<AlarmEntry>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(alarm: AlarmEntry)

    @Delete
    suspend fun delete(alarm: AlarmEntry)
}
