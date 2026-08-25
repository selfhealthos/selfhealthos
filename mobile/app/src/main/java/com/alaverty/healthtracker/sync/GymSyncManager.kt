package com.alaverty.healthtracker.sync

import android.util.Log
import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.preferences.TokenStore
import com.alaverty.healthtracker.data.remote.GymSyncRequest
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

private const val TAG = "GymSync"

/**
 * Pushes queued gym rows to the home portal.
 *
 * The design in one line: **the phone's Room database is the queue, and the
 * server's reply is the only thing that empties it.**
 *
 * Everything else follows from that. Saving a set writes it locally first and
 * unconditionally, so a save can never fail for want of a network. The sync
 * attempt that follows is best-effort: at home it succeeds in a few hundred
 * milliseconds, and anywhere else it fails and nothing is lost, because the row
 * is already on disk marked unsynced. The next save that happens to be on the
 * home wifi drains the whole backlog, oldest included.
 *
 * There is deliberately no wifi or SSID detection. Reading the connected
 * network's name needs location permission on Android 10+, and it would still
 * answer the wrong question — the portal is reachable or it is not, and the
 * only way to know is to ask it. A failed attempt on mobile data costs one
 * timed-out socket.
 */
@Singleton
class GymSyncManager @Inject constructor(
    private val repository: HealthRepository,
    private val api: HomeApi,
    private val tokens: TokenStore,
    private val settings: SettingsRepository
) {
    private val _status = MutableStateFlow<GymSyncStatus>(GymSyncStatus.Idle)
    val status: StateFlow<GymSyncStatus> = _status.asStateFlow()

    /**
     * One sync at a time.
     *
     * Two overlapping runs would both read the same unsynced rows and both
     * send them. The server would merge them to the same entries — identity is
     * the row's UUID — so nothing would duplicate, but it is wasted work on a
     * link that is often the slow part.
     */
    private val mutex = Mutex()

    /**
     * Send everything the server has not acknowledged.
     *
     * Returns what happened, for the worker to decide whether to retry and for
     * Settings to show. Never throws: a sync failure is an expected state of
     * this app, not an error.
     */
    suspend fun sync(): GymSyncResult = mutex.withLock {
        if (!tokens.state.value.enrolled) {
            _status.value = GymSyncStatus.NotEnrolled
            return@withLock GymSyncResult.NotEnrolled
        }
        if (tokens.state.value.rejected) {
            // Retrying a credential the server has already refused cannot
            // succeed, and would hammer the endpoint on every save.
            _status.value = GymSyncStatus.TokenRejected
            return@withLock GymSyncResult.TokenRejected
        }

        // Cold-process safety, as in EntrySyncManager: without this the
        // interceptor can still be holding the compiled-in default URL.
        val host = settings.primeServerUrl()

        val exercises = repository.getUnsyncedGymExercises()
        val sets = repository.getUnsyncedGymSets()
        if (exercises.isEmpty() && sets.isEmpty()) {
            _status.value = GymSyncStatus.UpToDate(System.currentTimeMillis())
            return@withLock GymSyncResult.NothingToDo
        }

        _status.value = GymSyncStatus.Syncing
        return@withLock try {
            val response = api.syncGym(
                GymSyncRequest(
                    exercises = exercises.map { it.toDto() },
                    sets = sets.map { it.toDto() }
                )
            )
            val body = response.body()

            if (!response.isSuccessful || body == null) {
                if (response.code() == 401) {
                    // AuthInterceptor has already marked the token dead. The
                    // queue is untouched and resumes after re-enrolment.
                    _status.value = GymSyncStatus.TokenRejected
                    return@withLock GymSyncResult.TokenRejected
                }
                val reason = "server said ${response.code()}"
                Log.w(TAG, "sync failed: $reason")
                _status.value = GymSyncStatus.Failed(reason)
                return@withLock GymSyncResult.Retryable(reason)
            }

            // The contract: mark synced exactly what the server named, and
            // nothing else. Anything absent from `accepted` stays queued and
            // goes again next time.
            val accepted = body.accepted.toSet()
            val exerciseIds = exercises.map { it.id }.filter { it in accepted }
            val setIds = sets.map { it.id }.filter { it in accepted }
            if (exerciseIds.isNotEmpty()) repository.markGymExercisesSynced(exerciseIds)
            if (setIds.isNotEmpty()) repository.markGymSetsSynced(setIds)

            // Safe only now that the server has acknowledged the deletions;
            // any earlier and there would be nothing left to resend.
            repository.purgeSyncedGymExerciseTombstones()
            repository.purgeSyncedGymSetTombstones()

            if (body.rejected.isNotEmpty()) {
                // These will never succeed, so they are surfaced rather than
                // retried into oblivion. They stay unsynced on purpose: the
                // row is still the only copy, and dropping it to tidy the
                // queue would be the data loss this whole design avoids.
                Log.w(TAG, "server rejected ${body.rejected.size}: ${body.rejected.take(5)}")
            }

            val outcome = GymSyncResult.Synced(
                accepted = accepted.size,
                rejected = body.rejected.size
            )
            _status.value = if (body.rejected.isEmpty()) {
                GymSyncStatus.UpToDate(System.currentTimeMillis())
            } else {
                GymSyncStatus.PartiallyRejected(
                    count = body.rejected.size,
                    reason = body.rejected.first().reason
                )
            }
            outcome
        } catch (e: Exception) {
            // The ordinary case, not an error: away from home there is no
            // server to reach. Everything stays queued.
            Log.w(TAG, "portal unreachable at $host: ${e.javaClass.simpleName}: ${e.message}")
            _status.value = GymSyncStatus.Offline
            GymSyncResult.Retryable(e.message ?: "unreachable")
        }
    }
}

sealed interface GymSyncResult {
    data class Synced(val accepted: Int, val rejected: Int) : GymSyncResult
    data object NothingToDo : GymSyncResult
    data object NotEnrolled : GymSyncResult
    data object TokenRejected : GymSyncResult
    /** Worth trying again later — the portal was unreachable or erroring. */
    data class Retryable(val reason: String) : GymSyncResult
}

/** What Settings shows. Every state names what to do about it. */
sealed interface GymSyncStatus {
    data object Idle : GymSyncStatus
    data object Syncing : GymSyncStatus
    data class UpToDate(val at: Long) : GymSyncStatus
    data object Offline : GymSyncStatus
    data object NotEnrolled : GymSyncStatus
    data object TokenRejected : GymSyncStatus
    data class PartiallyRejected(val count: Int, val reason: String) : GymSyncStatus
    data class Failed(val reason: String) : GymSyncStatus
}
