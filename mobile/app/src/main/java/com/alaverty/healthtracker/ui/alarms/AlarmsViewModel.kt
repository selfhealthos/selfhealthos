package com.alaverty.healthtracker.ui.alarms

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.alarm.AlarmScheduler
import com.alaverty.healthtracker.data.local.entity.AlarmEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AlarmsViewModel @Inject constructor(
    private val repository: HealthRepository,
    private val scheduler: AlarmScheduler
) : ViewModel() {

    val alarms = repository.getAllAlarms()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    /** True when the OS will honour exact alarms; screen prompts if false. */
    fun canScheduleExact(): Boolean = scheduler.canScheduleExact()

    fun add(label: String, hour: Int, minute: Int) {
        viewModelScope.launch {
            val alarm = AlarmEntry(
                label  = label.trim().ifBlank { "Reminder" },
                hour   = hour,
                minute = minute
            )
            repository.insertAlarm(alarm)
            scheduler.schedule(alarm)
        }
    }

    fun update(alarm: AlarmEntry, label: String, hour: Int, minute: Int) {
        viewModelScope.launch {
            val updated = alarm.copy(
                label     = label.trim().ifBlank { "Reminder" },
                hour      = hour,
                minute    = minute,
                updatedAt = System.currentTimeMillis()
            )
            repository.insertAlarm(updated)
            scheduler.cancel(updated)                 // clear the old trigger
            if (updated.enabled) scheduler.schedule(updated)
        }
    }

    fun toggle(alarm: AlarmEntry, enabled: Boolean) {
        viewModelScope.launch {
            val updated = alarm.copy(enabled = enabled, updatedAt = System.currentTimeMillis())
            repository.insertAlarm(updated)
            if (enabled) scheduler.schedule(updated) else scheduler.cancel(updated)
        }
    }

    fun delete(alarm: AlarmEntry) {
        viewModelScope.launch {
            scheduler.cancel(alarm)
            repository.deleteAlarm(alarm)
        }
    }
}
