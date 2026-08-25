package com.alaverty.healthtracker.sync

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Runs [EntrySyncManager] under WorkManager.
 *
 * A separate worker from [GymSyncWorker] rather than one that does both: the
 * two endpoints fail independently, and WorkManager's retry is per worker. One
 * worker would put a weight reading behind a gym set the server is refusing,
 * retrying both forever because one of them can never succeed.
 */
@HiltWorker
class EntrySyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val syncManager: EntrySyncManager
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = when (val outcome = syncManager.sync()) {
        is GymSyncResult.Synced -> {
            // Anything saved while this run was in flight was not in the batch
            // it read; re-enqueueing stops it waiting for the next save.
            if (outcome.accepted > 0) requestSync(applicationContext)
            Result.success()
        }
        GymSyncResult.NothingToDo -> Result.success()

        // No credential will work until a person intervenes. Retrying would
        // burn battery to fail identically, and Settings already says why.
        GymSyncResult.NotEnrolled, GymSyncResult.TokenRejected -> Result.success()

        is GymSyncResult.Retryable -> Result.retry()
    }

    companion object {
        private const val IMMEDIATE_WORK = "entry_sync_now"
        private const val PERIODIC_WORK = "entry_sync_periodic"

        /**
         * Try to sync now. Called after every save and delete on the screens
         * whose types have been migrated.
         *
         * [ExistingWorkPolicy.KEEP], for the reason in [GymSyncWorker]: a run
         * already queued will read the queue when it starts and pick this
         * entry up too, and replacing would cancel a request that may already
         * have reached the server.
         */
        fun requestSync(context: Context) {
            val request = OneTimeWorkRequestBuilder<EntrySyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(IMMEDIATE_WORK, ExistingWorkPolicy.KEEP, request)
        }

        /**
         * Start a fresh attempt, discarding any backoff the queued one has
         * accumulated. For app start only.
         *
         * [ExistingWorkPolicy.KEEP] is right for the per-save path and wrong
         * as the only path: a worker that fails enough times backs off to
         * WorkManager's five-hour ceiling, and KEEP then silently drops every
         * [requestSync] a save makes until that window comes round. Seventeen
         * failed attempts is how a fortnight of entries sat queued while the
         * app went on calling requestSync after each one.
         *
         * REPLACE is safe here specifically because it is app start: there is
         * no save-triggered request in flight worth preserving, and a resend
         * is free anyway — rows are identified by the UUID the phone gave
         * them, and only ids the server names are marked synced.
         */
        fun restartSync(context: Context) {
            val request = OneTimeWorkRequestBuilder<EntrySyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(IMMEDIATE_WORK, ExistingWorkPolicy.REPLACE, request)
        }

        /** The safety net: coming home and logging nothing, with a backlog queued. */
        fun schedulePeriodicSync(context: Context) {
            val request = PeriodicWorkRequestBuilder<EntrySyncWorker>(1, TimeUnit.HOURS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 5, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC_WORK,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
        }
    }
}
