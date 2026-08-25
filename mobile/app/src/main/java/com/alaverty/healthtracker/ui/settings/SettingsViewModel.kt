package com.alaverty.healthtracker.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.github.GitHubExportService
import com.alaverty.healthtracker.data.local.entity.Habit
import com.alaverty.healthtracker.data.preferences.AppSettings
import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.preferences.TokenState
import com.alaverty.healthtracker.data.preferences.TokenStore
import com.alaverty.healthtracker.data.repository.HealthRepository
import com.alaverty.healthtracker.sync.EnrolmentResult
import com.alaverty.healthtracker.sync.EnrolmentService
import com.alaverty.healthtracker.sync.EntrySyncManager
import com.alaverty.healthtracker.sync.GymSyncManager
import com.alaverty.healthtracker.sync.GymSyncStatus
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed class ExportStatus {
    object Idle : ExportStatus()
    data class Running(val message: String) : ExportStatus()
    data class Success(val message: String) : ExportStatus()
    data class Error(val message: String) : ExportStatus()
}

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository,
    private val exportService: GitHubExportService,
    private val healthRepository: HealthRepository,
    private val enrolmentService: EnrolmentService,
    private val gymSyncManager: GymSyncManager,
    private val entrySyncManager: EntrySyncManager,
    tokenStore: TokenStore
) : ViewModel() {

    val settings = settingsRepository.settings
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), AppSettings())

    val habits = healthRepository.getAllHabits()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _exportStatus = MutableStateFlow<ExportStatus>(ExportStatus.Idle)
    val exportStatus = _exportStatus.asStateFlow()

    // -- Home portal --------------------------------------------------------

    val tokenState = tokenStore.state
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), TokenState())

    /**
     * Both syncs in one line, showing whichever is in the worse state.
     *
     * Deliberately pessimistic. This flow used to be `gymSyncManager.status`
     * alone, so the screen reported "Up to date — nothing waiting" on the
     * strength of gym while entry sync had been failing every attempt since
     * July, with twenty rows queued behind it. A status line that speaks for
     * two independent syncs has to report the unhealthier one, or it is not
     * reporting at all.
     */
    val syncStatus = combine(gymSyncManager.status, entrySyncManager.status) { gym, entry ->
        if (severity(gym) >= severity(entry)) gym else entry
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), GymSyncStatus.Idle)

    /**
     * How many rows are waiting, across both syncs.
     *
     * Shown because it is the one number that says whether the design is
     * working. A count that climbs while at home means sync is broken; a count
     * that is non-zero after a week away is exactly what should happen. It
     * counts entry rows as well as gym ones — omitting them is what let a
     * genuine backlog read as an empty queue.
     */
    val pendingGymCount = combine(
        healthRepository.countUnsyncedGymSets(),
        healthRepository.countUnsyncedGymExercises(),
        healthRepository.countUnsyncedEntries()
    ) { sets, exercises, entries -> sets + exercises + entries }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0)

    private val _enrolmentError = MutableStateFlow("")
    val enrolmentError = _enrolmentError.asStateFlow()

    private val _enrolling = MutableStateFlow(false)
    val enrolling = _enrolling.asStateFlow()

    fun enrol(username: String, password: String) {
        if (_enrolling.value) return
        viewModelScope.launch {
            _enrolling.value = true
            _enrolmentError.value = ""
            when (val result = enrolmentService.enrol(username, password)) {
                is EnrolmentResult.Enrolled -> {
                    _enrolmentError.value = ""
                    // Anything queued from before enrolment goes up now, rather
                    // than waiting for the next set to be logged.
                    syncGymNow()
                }
                is EnrolmentResult.Failed -> _enrolmentError.value = result.message
            }
            _enrolling.value = false
        }
    }

    /**
     * Run both syncs.
     *
     * Was gym-only, which is why the button appeared to do nothing for a
     * queue of meals and gut entries: it was never asking the manager that
     * owns them. Calling the managers directly rather than enqueueing the
     * workers is also what makes this button a way out of a stuck backoff —
     * `EntrySyncWorker.requestSync` keeps existing work, so once a worker has
     * retried into its five-hour window every later save is dropped.
     */
    fun syncGymNow() {
        viewModelScope.launch { gymSyncManager.sync() }
        viewModelScope.launch { entrySyncManager.sync() }
    }

    fun saveSettings(settings: AppSettings) {
        viewModelScope.launch { settingsRepository.save(settings) }
    }

    fun addHabit(name: String) {
        if (name.isBlank()) return
        viewModelScope.launch { healthRepository.insertHabit(Habit(name = name.trim())) }
    }

    fun deleteHabit(habit: Habit) {
        viewModelScope.launch { healthRepository.deleteHabit(habit) }
    }

    fun export(settings: AppSettings) {
        if (_exportStatus.value is ExportStatus.Running) return
        viewModelScope.launch {
            saveSettings(settings)
            _exportStatus.value = ExportStatus.Running("Starting…")
            val result = exportService.export(
                githubRepo  = settings.githubRepo,
                githubToken = settings.githubToken,
                syncAll     = settings.syncAll,
                syncDays    = settings.syncDays,
                onProgress  = { msg -> _exportStatus.value = ExportStatus.Running(msg) }
            )
            _exportStatus.value = result.fold(
                onSuccess = { ExportStatus.Success(it) },
                onFailure = { ExportStatus.Error(it.message ?: "Export failed") }
            )
        }
    }
}

/**
 * How much a status deserves the user's attention.
 *
 * Used to pick which of the two syncs the one status line describes. Ordered
 * by what a person needs to act on: a dead token needs re-enrolment, an
 * unreachable portal usually needs nothing but going home, and being up to
 * date needs nothing at all.
 */
private fun severity(status: GymSyncStatus): Int = when (status) {
    GymSyncStatus.TokenRejected      -> 6
    GymSyncStatus.NotEnrolled        -> 5
    is GymSyncStatus.Failed          -> 4
    is GymSyncStatus.PartiallyRejected -> 3
    GymSyncStatus.Offline            -> 2
    GymSyncStatus.Syncing            -> 1
    is GymSyncStatus.UpToDate        -> 0
    GymSyncStatus.Idle               -> 0
}
