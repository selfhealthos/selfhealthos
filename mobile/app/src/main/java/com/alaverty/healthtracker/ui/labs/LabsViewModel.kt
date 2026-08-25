package com.alaverty.healthtracker.ui.labs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.LabResult
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

// One marker's history, newest first
data class MarkerGroup(
    val name: String,
    val entries: List<LabResult>
)

@HiltViewModel
class LabsViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    // Grouped by marker name (case-insensitive), newest entry first within each group;
    // groups ordered by most recently tested marker first
    val markerGroups = repository.getAllLabResults()
        .map { results ->
            results
                .groupBy { it.markerName.trim().lowercase() }
                .map { (_, entries) ->
                    val sorted = entries.sortedByDescending { it.date }
                    MarkerGroup(name = sorted.first().markerName.trim(), entries = sorted)
                }
                .sortedByDescending { it.entries.first().date }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun add(markerName: String, value: Double, unit: String, date: String, notes: String) {
        viewModelScope.launch {
            repository.insertLabResult(
                LabResult(
                    markerName = markerName.trim(),
                    value      = value,
                    unit       = unit.trim(),
                    date       = date,
                    notes      = notes.trim(),
                    timestamp  = System.currentTimeMillis()
                )
            )
        }
    }

    fun delete(result: LabResult) {
        viewModelScope.launch { repository.deleteLabResult(result) }
    }
}
