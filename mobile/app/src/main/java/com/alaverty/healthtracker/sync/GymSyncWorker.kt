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
 * Runs [GymSyncManager] under WorkManager.
 *
 * A plain coroutine on the ViewModel scope would be simpler and would lose the
 * sync the moment the screen closed or Android killed the process — which is
 * precisely when a phone in a gym, on a bad connection, is most likely to be
 * doing both. WorkManager persists the request and retries it with backoff.
 */
@HiltWorker
class GymSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val syncManager: GymSyncManager
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = when (val outcome = syncManager.sync()) {
        is GymSyncResult.Synced -> {
            // Anything saved while this run was in flight was not in the batch
            // it read. Re-enqueueing is what stops that entry waiting for the
            // next save or the hourly sweep to notice it.
            if (outcome.accepted > 0) requestSync(applicationContext)
            Result.success()
        }
        GymSyncResult.NothingToDo -> Result.success()

        // Both mean no credential will work until a person intervenes.
        // Retrying would burn battery to fail identically, and the settings
        // screen is already showing why.
        GymSyncResult.NotEnrolled, GymSyncResult.TokenRejected -> Result.success()

        is GymSyncResult.Retryable -> Result.retry()
    }

    companion object {
        private const val IMMEDIATE_WORK = "gym_sync_now"
        private const val PERIODIC_WORK = "gym_sync_periodic"

        /**
         * Try to sync now. Called after every save and delete.
         *
         * [ExistingWorkPolicy.KEEP] rather than REPLACE: a run already queued
         * will read the queue when it starts, so it will pick up this entry
         * too, and replacing would cancel a request that may already have
         * reached the server. The lost-wakeup case — an entry saved *during* a
         * run, after that run read the queue — is handled by the worker
         * re-enqueueing itself when it succeeds.
         */
        fun requestSync(context: Context) {
            val request = OneTimeWorkRequestBuilder<GymSyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        // CONNECTED, not UNMETERED: the portal is reachable
                        // over any network the phone is actually on at home,
                        // and a phone whose wifi is metered would otherwise
                        // never sync at all.
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                // Expedited so a set logged mid-workout goes up while the phone
                // is still awake, falling back to a normal job when the app has
                // spent its quota rather than throwing.
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(IMMEDIATE_WORK, ExistingWorkPolicy.KEEP, request)
        }

        /**
         * Start a fresh attempt, discarding accumulated backoff. App start only.
         *
         * The sibling of [EntrySyncWorker.restartSync], and there for the same
         * reason: KEEP is correct per save and traps the queue when a worker
         * has backed off to the five-hour ceiling, because every later
         * [requestSync] is then dropped. Safe at app start, where no
         * save-triggered request is in flight and a resend costs nothing.
         */
        fun restartSync(context: Context) {
            val request = OneTimeWorkRequestBuilder<GymSyncWorker>()
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

        /**
         * The safety net.
         *
         * Save-triggered sync covers the described workflow — walk in the door,
         * log a set, the backlog goes with it. This catches the case that
         * workflow misses: coming home and *not* logging anything, with a week
         * of entries still queued.
         */
        fun schedulePeriodicSync(context: Context) {
            val request = PeriodicWorkRequestBuilder<GymSyncWorker>(1, TimeUnit.HOURS)
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
