package com.alaverty.healthtracker.ui.body

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.BodyMeasurement
import com.alaverty.healthtracker.data.local.entity.FitnessTest
import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class BodyViewModel @Inject constructor(
    private val repository: HealthRepository,
    settingsRepository: SettingsRepository
) : ViewModel() {

    val measurements = repository.getAllBodyMeasurements()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val fitnessTests = repository.getAllFitnessTests()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val heightCm = settingsRepository.settings
        .map { it.heightCm }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0f)

    fun addMeasurement(waistCm: Double?, hipsCm: Double?, neckCm: Double?, bodyFatPct: Double?, notes: String) {
        if (waistCm == null && hipsCm == null && neckCm == null && bodyFatPct == null) return
        viewModelScope.launch {
            repository.insertBodyMeasurement(
                BodyMeasurement(
                    waistCm    = waistCm,
                    hipsCm     = hipsCm,
                    neckCm     = neckCm,
                    bodyFatPct = bodyFatPct,
                    notes      = notes.trim(),
                    timestamp  = System.currentTimeMillis()
                )
            )
        }
    }

    fun deleteMeasurement(measurement: BodyMeasurement) {
        viewModelScope.launch { repository.deleteBodyMeasurement(measurement) }
    }

    fun addFitnessTest(gripKg: Double?, balanceSec: Double?, sitToStandReps: Int?, deadHangSec: Double?, notes: String) {
        if (gripKg == null && balanceSec == null && sitToStandReps == null && deadHangSec == null) return
        viewModelScope.launch {
            repository.insertFitnessTest(
                FitnessTest(
                    gripKg              = gripKg,
                    singleLegBalanceSec = balanceSec,
                    sitToStandReps      = sitToStandReps,
                    deadHangSec         = deadHangSec,
                    notes               = notes.trim(),
                    timestamp           = System.currentTimeMillis()
                )
            )
        }
    }

    fun deleteFitnessTest(test: FitnessTest) {
        viewModelScope.launch { repository.deleteFitnessTest(test) }
    }
}
