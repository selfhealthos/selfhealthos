package com.alaverty.healthtracker.sync

import android.util.Log
import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.preferences.TokenStore
import com.alaverty.healthtracker.data.remote.EntrySyncRequest
import com.alaverty.healthtracker.data.remote.HomeApi
import com.alaverty.healthtracker.data.remote.toDto
import com.alaverty.healthtracker.data.repository.HealthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "EntrySync"

/**
 * Pushes every queued entry type except gym to the home portal.
 *
 * The sibling of [GymSyncManager], and the same design in one line: **Room is
 * the queue, and the server's reply is the only thing that empties it.**
 *
 * Kept as a second manager rather than folded into the gym one because the two
 * endpoints can fail independently. A malformed gym set must not stop a weight
 * reading from syncing, and merging them would put both behind one reply.
 *
 * Deliberately no wifi detection, for the reason in [GymSyncManager]: reading
 * the SSID needs location permission and would still answer the wrong
 * question. Away from home the request fails fast and everything stays queued.
 */
@Singleton
class EntrySyncManager @Inject constructor(
    private val repository: HealthRepository,
    private val api: HomeApi,
    private val tokens: TokenStore,
    private val settings: SettingsRepository,
    private val photoSyncManager: PhotoSyncManager
) {
    private val _status = MutableStateFlow<GymSyncStatus>(GymSyncStatus.Idle)

    /** Reuses [GymSyncStatus]: the states are identical and Settings shows both. */
    val status: StateFlow<GymSyncStatus> = _status.asStateFlow()

    private val mutex = Mutex()

    suspend fun sync(): GymSyncResult = mutex.withLock {
        if (!tokens.state.value.enrolled) {
            _status.value = GymSyncStatus.NotEnrolled
            return@withLock GymSyncResult.NotEnrolled
        }
        if (tokens.state.value.rejected) {
            _status.value = GymSyncStatus.TokenRejected
            return@withLock GymSyncResult.TokenRejected
        }

        // Before anything is sent: this worker usually runs in a cold process,
        // where the cached URL is still the compiled-in default rather than
        // the one configured in Settings. See [SettingsRepository.primeServerUrl].
        val host = settings.primeServerUrl()

        val request = collect()
        if (request.isEmpty) {
            _status.value = GymSyncStatus.UpToDate(System.currentTimeMillis())
            // A photo can be stuck here with no entry row waiting behind it -
            // its row synced on an earlier pass, the picture itself failed
            // (offline, most likely) and there is nothing else in this batch
            // to bring the retry along. Without this call the only way to
            // retry it is the Settings button; the hourly sweep would never
            // find an empty entries batch worth acting on and stop here.
            photoSyncManager.sync()
            return@withLock GymSyncResult.NothingToDo
        }

        _status.value = GymSyncStatus.Syncing
        return@withLock try {
            val response = api.syncEntries(request)
            val body = response.body()

            if (!response.isSuccessful || body == null) {
                if (response.code() == 401) {
                    // AuthInterceptor has already flagged the token. The queue
                    // is untouched and resumes after re-enrolment.
                    _status.value = GymSyncStatus.TokenRejected
                    return@withLock GymSyncResult.TokenRejected
                }
                val reason = "server said ${response.code()}"
                Log.w(TAG, "sync failed: $reason")
                _status.value = GymSyncStatus.Failed(reason)
                return@withLock GymSyncResult.Retryable(reason)
            }

            markAccepted(request, body.accepted.toSet())

            // Safe only now the server has acknowledged the deletions. Any
            // earlier and a delete it never received would be gone from here
            // too, with nothing left to resend.
            repository.purgeSyncedEntryTombstones()

            // A diet or doc row's photo can only attach once the row itself
            // exists server-side, which this call just confirmed. Running it
            // here rather than leaving every caller to remember it is the
            // same reasoning as `HealthRepository.syncSoon()`.
            photoSyncManager.sync()

            if (body.rejected.isNotEmpty()) {
                // Surfaced rather than retried into oblivion, and left
                // unsynced on purpose: the row is still the only copy, and
                // dropping it to tidy the queue is the loss this design avoids.
                Log.w(TAG, "server rejected ${body.rejected.size}: ${body.rejected.take(5)}")
            }

            _status.value = if (body.rejected.isEmpty()) {
                GymSyncStatus.UpToDate(System.currentTimeMillis())
            } else {
                GymSyncStatus.PartiallyRejected(
                    count = body.rejected.size,
                    reason = body.rejected.first().reason
                )
            }
            GymSyncResult.Synced(accepted = body.accepted.size, rejected = body.rejected.size)
        } catch (e: Exception) {
            // Usually the ordinary case — away from home there is no server to
            // reach — but not always, so it names the host it actually tried.
            // Without that, a permanent misconfiguration (posting at a default
            // hostname the phone cannot resolve) is indistinguishable from
            // being out of the house, and reads as routine in the log forever.
            Log.w(TAG, "portal unreachable at $host: ${e.javaClass.simpleName}: ${e.message}")
            _status.value = GymSyncStatus.Offline
            GymSyncResult.Retryable(e.message ?: "unreachable")
        }
    }

    /** Everything the server has not acknowledged, tombstones included. */
    private suspend fun collect() = EntrySyncRequest(
        diet = repository.getUnsyncedDietEntries().map { it.toDto() },
        exercise = repository.getUnsyncedExerciseEntries().map { it.toDto() },
        notes = repository.getUnsyncedNotes().map { it.toDto() },
        bm = repository.getUnsyncedBmEntries().map { it.toDto() },
        bp = repository.getUnsyncedBpEntries().map { it.toDto() },
        weight = repository.getUnsyncedWeightEntries().map { it.toDto() },
        body = repository.getUnsyncedBodyMeasurements().map { it.toDto() },
        fitness = repository.getUnsyncedFitnessTests().map { it.toDto() },
        docs = repository.getUnsyncedDocs().map { it.toDto() },
        labs = repository.getUnsyncedLabResults().map { it.toDto() },
        officeDays = repository.getUnsyncedWfhEntries().map { it.toDto() },
        habits = repository.getUnsyncedHabits().map { it.toDto() },
        habitCompletions = repository.getUnsyncedHabitCompletions().map { it.toDto() }
    )

    /**
     * Mark synced exactly what the server named, and nothing else.
     *
     * Anything absent from `accepted` stays queued and goes again next time.
     * Marking everything on a 2xx is how one rejected row gets dropped from the
     * phone forever with a success in the log.
     */
    private suspend fun markAccepted(request: EntrySyncRequest, accepted: Set<String>) {
        suspend fun mark(ids: List<String>, apply: suspend (List<String>) -> Unit) {
            val kept = ids.filter { it in accepted }
            if (kept.isNotEmpty()) apply(kept)
        }

        mark(request.diet.map { it.id }, repository::markDietEntriesSynced)
        mark(request.exercise.map { it.id }, repository::markExerciseEntriesSynced)
        mark(request.notes.map { it.id }, repository::markNotesSynced)
        mark(request.bm.map { it.id }, repository::markBmEntriesSynced)
        mark(request.bp.map { it.id }, repository::markBpEntriesSynced)
        mark(request.weight.map { it.id }, repository::markWeightEntriesSynced)
        mark(request.body.map { it.id }, repository::markBodyMeasurementsSynced)
        mark(request.fitness.map { it.id }, repository::markFitnessTestsSynced)
        mark(request.docs.map { it.id }, repository::markDocsSynced)
        mark(request.labs.map { it.id }, repository::markLabResultsSynced)
        mark(request.officeDays.map { it.id }, repository::markWfhEntriesSynced)
        mark(request.habits.map { it.id }, repository::markHabitsSynced)
        mark(request.habitCompletions.map { it.id }, repository::markHabitCompletionsSynced)
    }
}
