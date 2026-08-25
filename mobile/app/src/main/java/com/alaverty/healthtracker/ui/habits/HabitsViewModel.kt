package com.alaverty.healthtracker.ui.habits

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.Habit
import com.alaverty.healthtracker.data.local.entity.HabitCompletion
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

data class HabitRow(
    val habit: Habit,
    val completion: HabitCompletion?,  // latest completion, or null = not yet done today
    val completionCount: Int = 0       // a habit may be logged more than once a day
)

@HiltViewModel
class HabitsViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    private val _selectedDate = MutableStateFlow(LocalDate.now())
    val selectedDate = _selectedDate.asStateFlow()

    @OptIn(ExperimentalCoroutinesApi::class)
    val habitRows: StateFlow<List<HabitRow>> = _selectedDate.flatMapLatest { date ->
        combine(
            repository.getAllHabits(),
            repository.getHabitCompletionsForDate(date.toString())
        ) { habits, completions ->
            val byHabitId = completions.groupBy { it.habitId }
            habits.map { habit ->
                val comps = byHabitId[habit.id].orEmpty()
                HabitRow(habit, comps.maxByOrNull { it.completedAt }, comps.size)
            }
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun toggle(habit: Habit, complete: Boolean) {
        val dateStr = _selectedDate.value.toString()   // "YYYY-MM-DD"
        viewModelScope.launch {
            if (complete) {
                repository.insertHabitCompletion(
                    HabitCompletion(
                        habitId    = habit.id,
                        habitName  = habit.name,
                        date       = dateStr,
                        completedAt = System.currentTimeMillis()
                    )
                )
            } else {
                repository.deleteHabitCompletion(habit.id, dateStr)
            }
        }
    }

    fun goToPreviousDay() = _selectedDate.update { it.minusDays(1) }
    fun goToNextDay()     = _selectedDate.update { it.plusDays(1) }
}
