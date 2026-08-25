package com.alaverty.healthtracker.ui.exercise

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.ExerciseEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

data class ExerciseCategory(val name: String, val dir: File)

data class ExerciseUiState(
    val categories: List<ExerciseCategory> = emptyList(),
    val selectedCategory: ExerciseCategory? = null,
    val videoFile: File? = null,
    val videoTitle: String = "",
    val timerSeconds: Long = 0L,
    val isRunning: Boolean = false
)

@HiltViewModel
class ExerciseViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val repository: HealthRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ExerciseUiState())
    val uiState = _uiState.asStateFlow()

    private var timerJob: Job? = null

    init { loadCategories() }

    private fun loadCategories() {
        val root = context.getExternalFilesDir("videos")
        val cats = root
            ?.listFiles { f -> f.isDirectory }
            ?.sortedBy { it.name }
            ?.map { ExerciseCategory(name = it.name, dir = it) }
            ?: emptyList()
        _uiState.update { it.copy(categories = cats) }
    }

    fun selectCategory(category: ExerciseCategory) {
        timerJob?.cancel()
        val video = category.dir
            .walkTopDown()
            .filter { it.isFile && it.extension.equals("mp4", ignoreCase = true) }
            .toList()
            .randomOrNull()
        _uiState.update {
            it.copy(
                selectedCategory = category,
                videoFile = video,
                videoTitle = video?.let { f -> resolveTitle(f) } ?: "",
                timerSeconds = 0L,
                isRunning = video != null
            )
        }
        if (video != null) startTimer()
    }

    private fun startTimer() {
        timerJob = viewModelScope.launch {
            while (true) {
                delay(1000)
                if (_uiState.value.isRunning) {
                    _uiState.update { it.copy(timerSeconds = it.timerSeconds + 1) }
                }
            }
        }
    }

    fun completeExercise() {
        val state = _uiState.value
        val category = state.selectedCategory ?: return
        timerJob?.cancel()
        _uiState.update { it.copy(isRunning = false) }
        viewModelScope.launch {
            repository.insertExerciseEntry(
                ExerciseEntry(
                    videoName = state.videoTitle.ifBlank { "Unknown" },
                    durationSeconds = state.timerSeconds,
                    timestamp = System.currentTimeMillis()
                )
            )
            selectCategory(category)
        }
    }

    fun skipExercise() {
        val category = _uiState.value.selectedCategory ?: return
        timerJob?.cancel()
        selectCategory(category)
    }

    private fun resetToCategories() {
        _uiState.update {
            it.copy(
                selectedCategory = null,
                videoFile = null,
                videoTitle = "",
                timerSeconds = 0L,
                isRunning = false
            )
        }
    }

    // Read title from yt-dlp .info.json sidecar, or clean the filename as fallback
    private fun resolveTitle(videoFile: File): String {
        val jsonFile = File(videoFile.parent, "${videoFile.nameWithoutExtension}.info.json")
        if (jsonFile.exists()) {
            val match = """"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"""".toRegex()
                .find(jsonFile.readText())
            if (match != null) return match.groupValues[1]
        }
        // Strip trailing [YouTubeID] added by yt-dlp
        return videoFile.nameWithoutExtension
            .replace(Regex("""\s*\[[A-Za-z0-9_\-]{6,15}]$"""), "")
            .trim()
    }

    override fun onCleared() {
        super.onCleared()
        timerJob?.cancel()
    }
}
