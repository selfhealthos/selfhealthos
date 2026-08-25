package com.alaverty.healthtracker.ui.charts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.GymSet
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.inject.Inject

// Three-line x-axis label: e.g. ["THU", "4", "JUN"]
typealias AxisLabel = List<String>

// Exercise chart: one bar per day
data class ExerciseDataPoint(val label: AxisLabel, val minutes: Float)

// BM chart: one bar per day, counts split by Bristol type (index 0 = type 1 … index 6 = type 7)
data class BmDayData(val label: AxisLabel, val countsByType: List<Int>)

// Weight trend: x = epochDay so gaps between weigh-ins keep their true width
data class WeightTrendData(
    val rawPoints: List<Pair<Long, Float>>,   // epochDay → kg (daily average)
    val maPoints: List<Pair<Long, Float>>,    // 7-day trailing moving average
    val ratePerWeek: Float?                   // kg/week slope over the last 28 days of MA
)

// Gym progressive overload for one exercise
data class GymExerciseStats(
    val e1rmByDate: List<Pair<Long, Float>>,        // epochDay → best Epley e1RM that session
    val weeklyVolume: List<Pair<LocalDate, Float>>, // week start (Mon) → total kg moved
    val maxWeightKg: Float,
    val maxWeightDate: String,
    val bestE1rm: Float,
    val bestE1rmDate: String,
    val prInLatestSession: Boolean                  // latest session set a new all-time e1RM
)

@HiltViewModel
class ChartsViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    private val _exerciseData = MutableStateFlow<List<ExerciseDataPoint>>(emptyList())
    val exerciseData = _exerciseData.asStateFlow()

    private val _bmData = MutableStateFlow<List<BmDayData>>(emptyList())
    val bmData = _bmData.asStateFlow()

    private val _weightTrend = MutableStateFlow<WeightTrendData?>(null)
    val weightTrend = _weightTrend.asStateFlow()

    private val _allGymSets = MutableStateFlow<List<GymSet>>(emptyList())

    val gymExerciseNames = _allGymSets
        .map { sets -> sets.map { it.exerciseName }.distinct().sorted() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _selectedExercise = MutableStateFlow("")
    val selectedExercise = _selectedExercise.asStateFlow()

    val gymStats = combine(_allGymSets, _selectedExercise) { sets, selected ->
        computeGymStats(sets.filter { it.exerciseName == selected })
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    init {
        loadExerciseData()
        loadBmData()
        loadWeightTrend()
        loadGymSets()
    }

    fun selectExercise(name: String) {
        _selectedExercise.value = name
    }

    // 7 days, newest first (index 0 = today)
    private fun loadExerciseData() {
        viewModelScope.launch {
            val today = LocalDate.now()
            val start = today.minusDays(6)
            val zone = ZoneId.systemDefault()
            val entries = repository.getExerciseEntriesForRange(start, today)
            _exerciseData.value = (0..6).map { offset ->
                val date = today.minusDays(offset.toLong())
                val totalSeconds = entries
                    .filter { Instant.ofEpochMilli(it.timestamp).atZone(zone).toLocalDate() == date }
                    .sumOf { it.durationSeconds }
                ExerciseDataPoint(label = axisLabel(date), minutes = totalSeconds / 60f)
            }
        }
    }

    // 14 days, newest first (index 0 = today)
    private fun loadBmData() {
        viewModelScope.launch {
            val today = LocalDate.now()
            val start = today.minusDays(13)
            val zone = ZoneId.systemDefault()
            val entries = repository.getBmEntriesForRange(start, today)
            _bmData.value = (0..13).map { offset ->
                val date = today.minusDays(offset.toLong())
                val dayEntries = entries
                    .filter { Instant.ofEpochMilli(it.timestamp).atZone(zone).toLocalDate() == date }
                BmDayData(
                    label = axisLabel(date),
                    countsByType = List(7) { i -> dayEntries.count { it.bmNumber == i + 1 } }
                )
            }
        }
    }

    // Last 90 days of weight: daily average, 7-day trailing MA, kg/week slope
    private fun loadWeightTrend() {
        viewModelScope.launch {
            val today = LocalDate.now()
            val start = today.minusDays(89)
            val zone = ZoneId.systemDefault()
            val entries = repository.getWeightEntriesForRange(start, today)
            if (entries.isEmpty()) {
                _weightTrend.value = WeightTrendData(emptyList(), emptyList(), null)
                return@launch
            }

            // Average multiple weigh-ins on the same day
            val dailyAvg = entries
                .groupBy { Instant.ofEpochMilli(it.timestamp).atZone(zone).toLocalDate() }
                .map { (date, dayEntries) -> date to dayEntries.map { it.weightKg }.average().toFloat() }
                .sortedBy { it.first }

            // Trailing MA: mean of daily averages within the 7 days ending on each weigh-in day
            val maPoints = dailyAvg.map { (date, _) ->
                val window = dailyAvg.filter { (d, _) -> !d.isBefore(date.minusDays(6)) && !d.isAfter(date) }
                date.toEpochDay() to window.map { it.second }.average().toFloat()
            }

            // Least-squares slope of MA over the last 28 days, expressed as kg/week
            val cutoff = today.minusDays(27).toEpochDay()
            val recent = maPoints.filter { it.first >= cutoff }
            val rate = if (recent.size >= 2 && recent.last().first > recent.first().first) {
                val xMean = recent.map { it.first }.average()
                val yMean = recent.map { it.second.toDouble() }.average()
                val num = recent.sumOf { (x, y) -> (x - xMean) * (y - yMean) }
                val den = recent.sumOf { (x, _) -> (x - xMean) * (x - xMean) }
                ((num / den) * 7).toFloat()
            } else null

            _weightTrend.value = WeightTrendData(
                rawPoints = dailyAvg.map { it.first.toEpochDay() to it.second },
                maPoints = maPoints,
                ratePerWeek = rate
            )
        }
    }

    private fun loadGymSets() {
        viewModelScope.launch {
            val sets = repository.getGymSetsForRange(LocalDate.of(2020, 1, 1), LocalDate.now())
            _allGymSets.value = sets
            if (_selectedExercise.value.isBlank()) {
                // Default to the most recently trained exercise
                sets.maxByOrNull { it.date }?.let { _selectedExercise.value = it.exerciseName }
            }
        }
    }

    // Epley estimated 1RM: weight × (1 + reps/30)
    private fun epley(set: GymSet): Float =
        (set.weightKg * (1 + set.reps / 30.0)).toFloat()

    private fun computeGymStats(sets: List<GymSet>): GymExerciseStats? {
        val valid = sets.filter { it.weightKg > 0 && it.reps > 0 }
        if (valid.isEmpty()) return null

        val e1rmByDate = valid
            .groupBy { it.date }
            .map { (date, daySets) -> LocalDate.parse(date).toEpochDay() to daySets.maxOf { epley(it) } }
            .sortedBy { it.first }

        // Last 8 weeks of volume (sets × reps × weight), Monday-anchored
        val thisWeek = LocalDate.now().with(DayOfWeek.MONDAY)
        val weeklyVolume = (7 downTo 0).map { weeksAgo ->
            val weekStart = thisWeek.minusWeeks(weeksAgo.toLong())
            val weekEnd = weekStart.plusDays(6)
            val volume = valid
                .filter { val d = LocalDate.parse(it.date); !d.isBefore(weekStart) && !d.isAfter(weekEnd) }
                .sumOf { it.weightKg * it.reps }
                .toFloat()
            weekStart to volume
        }

        val maxWeightSet = valid.maxBy { it.weightKg }
        val bestE1rmEntry = e1rmByDate.maxBy { it.second }
        val latestSessionDay = e1rmByDate.last().first

        return GymExerciseStats(
            e1rmByDate = e1rmByDate,
            weeklyVolume = weeklyVolume,
            maxWeightKg = maxWeightSet.weightKg.toFloat(),
            maxWeightDate = maxWeightSet.date,
            bestE1rm = bestE1rmEntry.second,
            bestE1rmDate = LocalDate.ofEpochDay(bestE1rmEntry.first).toString(),
            prInLatestSession = bestE1rmEntry.first == latestSessionDay && e1rmByDate.size > 1
        )
    }

    // ["THU", "4", "JUN"]
    private fun axisLabel(date: LocalDate): AxisLabel = listOf(
        date.format(DateTimeFormatter.ofPattern("EEE", Locale.getDefault())).uppercase(),
        date.dayOfMonth.toString(),
        date.format(DateTimeFormatter.ofPattern("MMM", Locale.getDefault())).uppercase()
    )
}
