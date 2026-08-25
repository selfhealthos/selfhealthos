package com.alaverty.healthtracker.ui.diary

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.BmEntry
import com.alaverty.healthtracker.data.local.entity.BodyMeasurement
import com.alaverty.healthtracker.data.local.entity.BpEntry
import com.alaverty.healthtracker.data.local.entity.DietEntry
import com.alaverty.healthtracker.data.local.entity.ExerciseEntry
import com.alaverty.healthtracker.data.local.entity.HabitCompletion
import com.alaverty.healthtracker.data.local.entity.PersonalNote
import com.alaverty.healthtracker.data.local.entity.WeightEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID
import javax.inject.Inject

sealed class DiaryItem {
    abstract val timestamp: Long

    data class Diet(val entry: DietEntry) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Exercise(val entry: ExerciseEntry) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Note(val entry: PersonalNote) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Bm(val entry: BmEntry) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Bp(val entry: BpEntry) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Weight(val entry: WeightEntry) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Body(val entry: BodyMeasurement) : DiaryItem() {
        override val timestamp get() = entry.timestamp
    }
    data class Habit(val entry: HabitCompletion) : DiaryItem() {
        override val timestamp get() = entry.completedAt
    }
}

@HiltViewModel
class DiaryViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    private val _selectedDate = MutableStateFlow(LocalDate.now())
    val selectedDate = _selectedDate.asStateFlow()

    @OptIn(ExperimentalCoroutinesApi::class)
    val diaryItems: StateFlow<List<DiaryItem>> = _selectedDate.flatMapLatest { date ->
        val sources: List<Flow<List<DiaryItem>>> = listOf(
            repository.getDietEntriesForDay(date).map { list -> list.map(DiaryItem::Diet) },
            repository.getExerciseEntriesForDay(date).map { list -> list.map(DiaryItem::Exercise) },
            repository.getNoteEntriesForDay(date).map { list -> list.map(DiaryItem::Note) },
            repository.getBmEntriesForDay(date).map { list -> list.map(DiaryItem::Bm) },
            repository.getBpEntriesForDay(date).map { list -> list.map(DiaryItem::Bp) },
            repository.getWeightEntriesForDay(date).map { list -> list.map(DiaryItem::Weight) },
            repository.getBodyMeasurementsForDay(date).map { list -> list.map(DiaryItem::Body) },
            repository.getHabitCompletionsForDate(date.format(DateTimeFormatter.ISO_LOCAL_DATE))
                .map { list -> list.map(DiaryItem::Habit) }
        )
        combine(sources) { arrays ->
            arrays.flatMap { it }.sortedByDescending(DiaryItem::timestamp)
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun goToPreviousDay() = _selectedDate.update { it.minusDays(1) }
    fun goToNextDay() = _selectedDate.update { it.plusDays(1) }

    fun deleteEntry(item: DiaryItem) {
        viewModelScope.launch {
            when (item) {
                is DiaryItem.Diet     -> repository.deleteDietEntry(item.entry)
                is DiaryItem.Exercise -> repository.deleteExerciseEntry(item.entry)
                is DiaryItem.Note     -> repository.deleteNote(item.entry)
                is DiaryItem.Bm       -> repository.deleteBmEntry(item.entry)
                is DiaryItem.Bp       -> repository.deleteBpEntry(item.entry)
                is DiaryItem.Weight   -> repository.deleteWeightEntry(item.entry)
                is DiaryItem.Body     -> repository.deleteBodyMeasurement(item.entry)
                is DiaryItem.Habit    -> repository.deleteHabitCompletion(item.entry)
            }
        }
    }

    fun undoDelete(item: DiaryItem) {
        viewModelScope.launch {
            when (item) {
                is DiaryItem.Diet     -> repository.insertDietEntry(item.entry)
                is DiaryItem.Exercise -> repository.insertExerciseEntry(item.entry)
                is DiaryItem.Note     -> repository.insertNote(item.entry)
                is DiaryItem.Bm       -> repository.insertBmEntry(item.entry)
                is DiaryItem.Bp       -> repository.insertBpEntry(item.entry)
                is DiaryItem.Weight   -> repository.insertWeightEntry(item.entry)
                is DiaryItem.Body     -> repository.insertBodyMeasurement(item.entry)
                is DiaryItem.Habit    -> repository.insertHabitCompletion(item.entry)
            }
        }
    }

    /**
     * Copies an entry to a new record at the current time (on the day being viewed),
     * so a repeat of the same thing — e.g. a second coffee or a second magnesium dose —
     * can be logged with one swipe.
     */
    fun duplicateEntry(item: DiaryItem) {
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            val ts = nowTimestampOnSelectedDate()
            when (item) {
                is DiaryItem.Diet -> repository.insertDietEntry(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Exercise -> repository.insertExerciseEntry(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Note -> repository.insertNote(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Bm -> repository.insertBmEntry(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Bp -> repository.insertBpEntry(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Weight -> repository.insertWeightEntry(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Body -> repository.insertBodyMeasurement(
                    item.entry.copy(id = UUID.randomUUID().toString(), timestamp = ts, updatedAt = now, isSynced = false)
                )
                is DiaryItem.Habit -> repository.insertHabitCompletion(
                    item.entry.copy(id = UUID.randomUUID().toString(), completedAt = ts, updatedAt = now, isSynced = false)
                )
            }
        }
    }

    private fun nowTimestampOnSelectedDate(): Long {
        val zone = ZoneId.systemDefault()
        return _selectedDate.value
            .atTime(LocalTime.now(zone))
            .atZone(zone)
            .toInstant()
            .toEpochMilli()
    }

    fun addDietEntry(name: String, photoPath: String?) {
        viewModelScope.launch {
            val zone = ZoneId.systemDefault()
            val timestamp = _selectedDate.value
                .atTime(LocalTime.now(zone))
                .atZone(zone)
                .toInstant()
                .toEpochMilli()
            repository.insertDietEntry(
                DietEntry(name = name, photoPath = photoPath, timestamp = timestamp)
            )
        }
    }
}
