package com.alaverty.healthtracker.ui.bp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.BpEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class BpFormState(
    val systolic: String = "",
    val diastolic: String = "",
    val notes: String = "",
    val saved: Boolean = false
)

@HiltViewModel
class BpViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    val entries = repository.getAllBpEntries()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _form = MutableStateFlow(BpFormState())
    val form = _form.asStateFlow()

    fun updateSystolic(v: String) = _form.update { it.copy(systolic = v.filter { c -> c.isDigit() }, saved = false) }
    fun updateDiastolic(v: String) = _form.update { it.copy(diastolic = v.filter { c -> c.isDigit() }, saved = false) }
    fun updateNotes(v: String) = _form.update { it.copy(notes = v) }

    fun save() {
        val state = _form.value
        val sys = state.systolic.toIntOrNull() ?: return
        val dia = state.diastolic.toIntOrNull() ?: return
        viewModelScope.launch {
            repository.insertBpEntry(
                BpEntry(
                    systolic = sys,
                    diastolic = dia,
                    notes = state.notes,
                    timestamp = System.currentTimeMillis()
                )
            )
            _form.value = BpFormState(saved = true)
        }
    }

    fun deleteEntry(entry: BpEntry) {
        viewModelScope.launch { repository.deleteBpEntry(entry) }
    }
}
