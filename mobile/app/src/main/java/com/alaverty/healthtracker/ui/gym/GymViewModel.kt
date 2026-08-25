package com.alaverty.healthtracker.ui.gym

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.GymExercise
import com.alaverty.healthtracker.data.local.entity.GymSet
import com.alaverty.healthtracker.data.repository.HealthRepository
import com.alaverty.healthtracker.sync.GymSyncWorker
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class GymViewModel @Inject constructor(
    private val repository: HealthRepository,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _selectedDate = MutableStateFlow(LocalDate.now())
    val selectedDate: StateFlow<LocalDate> = _selectedDate.asStateFlow()

    private val _exerciseQuery = MutableStateFlow("")
    val exerciseQuery: StateFlow<String> = _exerciseQuery.asStateFlow()

    private val _weightKg = MutableStateFlow(0)
    val weightKg: StateFlow<Int> = _weightKg.asStateFlow()

    private val _reps = MutableStateFlow(10)
    val reps: StateFlow<Int> = _reps.asStateFlow()

    @OptIn(ExperimentalCoroutinesApi::class)
    val gymSets: StateFlow<List<GymSet>> = _selectedDate
        .flatMapLatest { date ->
            repository.getGymSetsForDate(date.format(DateTimeFormatter.ISO_LOCAL_DATE))
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun goToPreviousDay() { _selectedDate.value = _selectedDate.value.minusDays(1) }
    fun goToNextDay()     { _selectedDate.value = _selectedDate.value.plusDays(1) }

    fun onExerciseQueryChange(query: String) { _exerciseQuery.value = query }

    fun incrementWeight() { _weightKg.value = _weightKg.value + 5 }
    fun decrementWeight() { _weightKg.value = maxOf(0, _weightKg.value - 5) }
    fun onWeightChange(value: Int) { _weightKg.value = maxOf(0, value) }
    fun incrementReps()   { _reps.value = _reps.value + 1 }
    fun decrementReps()   { _reps.value = maxOf(1, _reps.value - 1) }
    fun onRepsChange(value: Int) { _reps.value = maxOf(1, value) }

    fun saveSet() {
        val name = _exerciseQuery.value.trim()
        if (name.isBlank()) return
        val weight = _weightKg.value
        val r      = _reps.value
        val date   = _selectedDate.value.format(DateTimeFormatter.ISO_LOCAL_DATE)
        val now    = System.currentTimeMillis()

        viewModelScope.launch {
            val existing = repository.getGymExerciseByName(name)
            // isSynced is reset on every edit: the catalogue row's last weight
            // and reps have changed, so the copy on the server is now stale.
            val exercise = existing?.copy(
                lastWeightKg = weight.toDouble(),
                lastReps     = r,
                updatedAt    = now,
                isSynced     = false
            ) ?: GymExercise(
                name = name, lastWeightKg = weight.toDouble(), lastReps = r,
                createdAt = now, updatedAt = now
            )
            repository.upsertGymExercise(exercise)

            repository.insertGymSet(
                GymSet(
                    exerciseName = name,
                    weightKg     = weight.toDouble(),
                    reps         = r,
                    date         = date,
                    timestamp    = now,
                    updatedAt    = now
                )
            )

            // Saved locally first, then pushed. The set is on disk before this
            // line runs, so an unreachable portal costs nothing: it stays
            // queued and goes up with the next save made at home.
            syncSoon()
        }
        // Fields stay populated so the user can quickly save another set
    }

    fun clearFields() {
        _weightKg.value = 0
        _reps.value     = 10
    }

    fun deleteSet(set: GymSet) {
        viewModelScope.launch {
            repository.deleteGymSet(set)
            // A deletion is an entry to sync like any other - it is tombstoned
            // locally, not removed, until the portal has been told.
            syncSoon()
        }
    }

    private fun syncSoon() = GymSyncWorker.requestSync(context)
}
