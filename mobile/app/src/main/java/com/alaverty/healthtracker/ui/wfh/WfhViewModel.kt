package com.alaverty.healthtracker.ui.wfh

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class WfhViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    private val dateFmt = DateTimeFormatter.ISO_LOCAL_DATE

    private val _yearMonth = MutableStateFlow(YearMonth.now())
    val yearMonth = _yearMonth.asStateFlow()

    @OptIn(ExperimentalCoroutinesApi::class)
    val officeDays: kotlinx.coroutines.flow.StateFlow<Set<String>> = _yearMonth
        .flatMapLatest { ym -> repository.getWfhEntriesForMonth(ym) }
        .map { entries -> entries.map { it.date }.toSet() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptySet())

    fun goToPreviousMonth() = _yearMonth.update { it.minusMonths(1) }
    fun goToNextMonth() = _yearMonth.update { it.plusMonths(1) }

    fun toggleDay(date: java.time.LocalDate) {
        val dateStr = date.format(dateFmt)
        viewModelScope.launch {
            if (dateStr in officeDays.value) {
                repository.deleteWfhEntryByDate(dateStr)
            } else {
                repository.markWfhDayPresent(dateStr)
            }
        }
    }
}
