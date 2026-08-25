package com.alaverty.healthtracker.ui.weight

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.WeightEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class WeightViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    val entries = repository.getAllWeightEntries()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun add(weightKg: Float, notes: String) {
        viewModelScope.launch {
            repository.insertWeightEntry(
                WeightEntry(
                    weightKg  = weightKg,
                    notes     = notes.trim(),
                    timestamp = System.currentTimeMillis()
                )
            )
        }
    }

    fun delete(entry: WeightEntry) {
        viewModelScope.launch { repository.deleteWeightEntry(entry) }
    }
}
