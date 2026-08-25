package com.alaverty.healthtracker.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "habits")
data class Habit(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val name: String,
    val sortOrder: Int = 0,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    /**
     * Habit *definitions* were export-only until portal sync: no queue flag
     * and no tombstone, so a renamed or deleted habit never left the phone.
     */
    val isSynced: Boolean = false,
    val deletedAt: Long? = null
)
