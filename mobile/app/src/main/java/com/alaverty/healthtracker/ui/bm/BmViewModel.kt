package com.alaverty.healthtracker.ui.bm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.BmEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import javax.inject.Inject

data class BmFormState(
    val selectedNumber: Int? = null,
    val notes: String = "",
    val saved: Boolean = false
)

@HiltViewModel
class BmViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    private val _selectedDate = MutableStateFlow(LocalDate.now())
    val selectedDate = _selectedDate.asStateFlow()

    @OptIn(ExperimentalCoroutinesApi::class)
    val entries = _selectedDate.flatMapLatest { date ->
        repository.getBmEntriesForDay(date)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _form = MutableStateFlow(BmFormState())
    val form = _form.asStateFlow()

    fun goToPreviousDay() = _selectedDate.update { it.minusDays(1) }
    fun goToNextDay() = _selectedDate.update { it.plusDays(1) }

    fun selectNumber(n: Int) = _form.update { it.copy(selectedNumber = n, saved = false) }
    fun updateNotes(text: String) = _form.update { it.copy(notes = text) }

    fun save() {
        val state = _form.value
        if (state.selectedNumber == null) return
        viewModelScope.launch {
            val zone = ZoneId.systemDefault()
            val timestamp = _selectedDate.value
                .atTime(LocalTime.now(zone))
                .atZone(zone)
                .toInstant()
                .toEpochMilli()
            repository.insertBmEntry(
                BmEntry(
                    bmNumber = state.selectedNumber,
                    notes = state.notes,
                    timestamp = timestamp
                )
            )
            _form.value = BmFormState(saved = true)
        }
    }

    fun deleteEntry(entry: BmEntry) {
        viewModelScope.launch { repository.deleteBmEntry(entry) }
    }
}
