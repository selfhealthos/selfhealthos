package com.alaverty.healthtracker.data.local.dao

import androidx.room.*
import com.alaverty.healthtracker.data.local.entity.GymExercise
import kotlinx.coroutines.flow.Flow

@Dao
interface GymExerciseDao {
    @Query("SELECT * FROM gym_exercises WHERE deletedAt IS NULL ORDER BY name ASC")
    fun getAll(): Flow<List<GymExercise>>

    @Query("SELECT * FROM gym_exercises WHERE deletedAt IS NULL ORDER BY name ASC")
    suspend fun getAllSnapshot(): List<GymExercise>

    @Query("SELECT * FROM gym_exercises WHERE name = :name AND deletedAt IS NULL LIMIT 1")
    suspend fun getByName(name: String): GymExercise?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(exercise: GymExercise)

    @Query("UPDATE gym_exercises SET deletedAt = :at, updatedAt = :at, isSynced = 0 WHERE id = :id")
    suspend fun softDelete(id: String, at: Long)

    @Query("SELECT * FROM gym_exercises WHERE isSynced = 0")
    suspend fun getUnsynced(): List<GymExercise>

    @Query("SELECT COUNT(*) FROM gym_exercises WHERE isSynced = 0")
    fun countUnsynced(): Flow<Int>

    @Query("UPDATE gym_exercises SET isSynced = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    @Query("DELETE FROM gym_exercises WHERE deletedAt IS NOT NULL AND isSynced = 1")
    suspend fun purgeSyncedTombstones()
}
