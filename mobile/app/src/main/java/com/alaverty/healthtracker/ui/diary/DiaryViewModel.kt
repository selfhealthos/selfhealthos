package com.alaverty.healthtracker.ui.diary

import android.util.Log
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
import java.time.Instant
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

private const val TAG = "DiaryViewModel"

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
     * Saves an edited entry over the row it came from.
     *
     * Room's inserts are `OnConflictStrategy.REPLACE` and the id is unchanged,
     * so this is an update, not a second row. `isSynced = false` puts it back
     * in the queue and `updatedAt` is what decides the merge on the portal —
     * without both, a correction stays on the phone forever.
     */
    fun updateEntry(item: DiaryItem) {
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            when (item) {
                is DiaryItem.Diet -> repository.insertDietEntry(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                is DiaryItem.Exercise -> repository.insertExerciseEntry(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                is DiaryItem.Note -> repository.insertNote(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                is DiaryItem.Bm -> repository.insertBmEntry(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                is DiaryItem.Bp -> repository.insertBpEntry(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                is DiaryItem.Weight -> repository.insertWeightEntry(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                is DiaryItem.Body -> repository.insertBodyMeasurement(
                    item.entry.copy(updatedAt = now, isSynced = false)
                )
                // `date` is stored, not computed from `completedAt`, and it is
                // what the diary queries habits by — the same trap
                // `duplicateEntry` hit. Moving the time has to move it too, or
                // the edit vanishes from the day it was moved to.
                is DiaryItem.Habit -> repository.insertHabitCompletion(
                    item.entry.copy(
                        date = Instant.ofEpochMilli(item.entry.completedAt)
                            .atZone(ZoneId.systemDefault())
                            .toLocalDate()
                            .format(DateTimeFormatter.ISO_LOCAL_DATE),
                        updatedAt = now,
                        isSynced = false
                    )
                )
            }
        }
    }

    /**
     * Copies an entry to a new record dated today at the current time — regardless of
     * which day is currently being viewed — so a repeat of the same thing (e.g. a second
     * coffee or a second magnesium dose) can be logged with one swipe from any day's view.
     */
    fun duplicateEntry(item: DiaryItem) {
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            val ts = now
            Log.d(
                TAG,
                "duplicate: viewing=${_selectedDate.value} -> today=${LocalDate.now()} " +
                    "ts=$ts zone=${ZoneId.systemDefault()}"
            )
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
                // `date` is stored, not computed from `completedAt`, and it is what the
                // diary actually queries by — moving only `completedAt` leaves the copy
                // sitting on the day being viewed. Both have to move together.
                is DiaryItem.Habit -> repository.insertHabitCompletion(
                    item.entry.copy(
                        id = UUID.randomUUID().toString(),
                        date = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE),
                        completedAt = ts,
                        updatedAt = now,
                        isSynced = false
                    )
                )
            }
        }
    }

    /**
     * The time a new entry starts out at: the current clock time, on the day
     * being viewed. Paging back to Saturday and adding a meal files it on
     * Saturday, which is the only reading of the + button that makes sense
     * while a past day is on screen — and the picker can still move it.
     */
    fun defaultTimestampForNewEntry(): Long {
        val zone = ZoneId.systemDefault()
        return _selectedDate.value
            .atTime(LocalTime.now(zone))
            .atZone(zone)
            .toInstant()
            .toEpochMilli()
    }

    fun addDietEntry(name: String, photoPath: String?, timestamp: Long) {
        viewModelScope.launch {
            repository.insertDietEntry(
                DietEntry(name = name, photoPath = photoPath, timestamp = timestamp)
            )
        }
    }
}
