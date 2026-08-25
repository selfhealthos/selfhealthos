package com.alaverty.healthtracker.sync

import android.util.Log
import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.preferences.TokenStore
import com.alaverty.healthtracker.data.remote.HomeApi
import com.alaverty.healthtracker.data.repository.HealthRepository
import java.io.File
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "PhotoSync"
private val JPEG = "image/jpeg".toMediaType()

/**
 * Uploads the photo behind a diet or doc entry, once the row itself is synced.
 *
 * A third design deliberately kept separate from [GymSyncManager] and
 * [EntrySyncManager]: a photo is a multipart body, not a JSON row, and does
 * not batch - the phone posts its pending pictures one request at a time. It
 * also has an ordering dependency neither of the others has: `/sync/photo`
 * names a row by the `client_id` `/sync/entries` gave it, so a photo can only
 * ever succeed *after* that row has been accepted. [EntrySyncManager] calls
 * this once its own batch lands, which is what makes that ordering automatic
 * rather than something every caller has to remember.
 *
 * Room is still the queue: [com.alaverty.healthtracker.data.local.entity.DietEntry.photoSynced]
 * and the doc equivalent are what the next pass reads, and nothing is
 * considered sent until the server has said so.
 */
@Singleton
class PhotoSyncManager @Inject constructor(
    private val repository: HealthRepository,
    private val api: HomeApi,
    private val tokens: TokenStore,
    private val settings: SettingsRepository
) {
    private val _status = MutableStateFlow<GymSyncStatus>(GymSyncStatus.Idle)
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

        val host = settings.primeServerUrl()

        val diet = repository.getPendingDietPhotoUploads()
        val docs = repository.getPendingDocPhotoUploads()
        if (diet.isEmpty() && docs.isEmpty()) {
            _status.value = GymSyncStatus.UpToDate(System.currentTimeMillis())
            return@withLock GymSyncResult.NothingToDo
        }

        _status.value = GymSyncStatus.Syncing
        var accepted = 0
        var rejected = 0
        var lastRejectionReason = ""

        try {
            for (entry in diet) {
                when (val outcome = upload(kind = "diet", id = entry.id, path = entry.photoPath)) {
                    Outcome.STORED -> {
                        repository.markDietPhotoSynced(entry.id)
                        accepted++
                    }
                    Outcome.MISSING_FILE -> repository.markDietPhotoSynced(entry.id)
                    Outcome.NOT_READY -> Unit // retried next pass, once the row itself lands
                    is Outcome.Rejected -> {
                        rejected++
                        lastRejectionReason = outcome.reason
                    }
                    Outcome.AUTH_FAILED -> {
                        _status.value = GymSyncStatus.TokenRejected
                        return@withLock GymSyncResult.TokenRejected
                    }
                }
            }
            for (entry in docs) {
                when (val outcome = upload(kind = "docs", id = entry.id, path = entry.photoPath)) {
                    Outcome.STORED -> {
                        repository.markDocPhotoSynced(entry.id)
                        accepted++
                    }
                    Outcome.MISSING_FILE -> repository.markDocPhotoSynced(entry.id)
                    Outcome.NOT_READY -> Unit
                    is Outcome.Rejected -> {
                        rejected++
                        lastRejectionReason = outcome.reason
                    }
                    Outcome.AUTH_FAILED -> {
                        _status.value = GymSyncStatus.TokenRejected
                        return@withLock GymSyncResult.TokenRejected
                    }
                }
            }
        } catch (e: Exception) {
            // The ordinary case: away from home, no server to reach. Whatever
            // uploaded before the failure is already marked; the rest stays
            // queued for the next pass.
            Log.w(TAG, "portal unreachable at $host: ${e.javaClass.simpleName}: ${e.message}")
            _status.value = GymSyncStatus.Offline
            return@withLock GymSyncResult.Retryable(e.message ?: "unreachable")
        }

        _status.value = if (rejected == 0) {
            GymSyncStatus.UpToDate(System.currentTimeMillis())
        } else {
            GymSyncStatus.PartiallyRejected(count = rejected, reason = lastRejectionReason)
        }
        GymSyncResult.Synced(accepted = accepted, rejected = rejected)
    }

    private sealed interface Outcome {
        object STORED : Outcome
        /** The file this row pointed to is gone - nothing left to send, ever. */
        object MISSING_FILE : Outcome
        /** The row itself has not synced yet. Not a failure - just too early. */
        object NOT_READY : Outcome
        object AUTH_FAILED : Outcome
        data class Rejected(val reason: String) : Outcome
    }

    private suspend fun upload(kind: String, id: String, path: String?): Outcome {
        val file = path?.let { File(it) }
        if (file == null || !file.exists()) return Outcome.MISSING_FILE

        val part = MultipartBody.Part.createFormData("file", file.name, file.asRequestBody(JPEG))
        val response = api.syncPhoto(
            kind = kind.toRequestBody(),
            id = id.toRequestBody(),
            file = part
        )

        if (response.code() == 401) return Outcome.AUTH_FAILED
        val body = response.body()
        if (!response.isSuccessful || body == null) {
            return Outcome.Rejected("server said ${response.code()}")
        }
        if (body.stored) return Outcome.STORED

        return if (body.reason == "entry not synced yet") {
            Outcome.NOT_READY
        } else {
            Outcome.Rejected(body.reason ?: "rejected")
        }
    }
}
