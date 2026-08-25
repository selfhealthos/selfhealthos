package com.alaverty.healthtracker

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.*
import com.alaverty.healthtracker.alarm.AlarmNotifier
import com.alaverty.healthtracker.alarm.AlarmScheduler
import com.alaverty.healthtracker.data.local.entity.AlarmEntry
import com.alaverty.healthtracker.data.local.entity.Habit
import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.repository.HealthRepository
import com.alaverty.healthtracker.sync.GymSyncWorker
import com.alaverty.healthtracker.sync.EntrySyncWorker
import dagger.hilt.android.HiltAndroidApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit
import javax.inject.Inject

@HiltAndroidApp
class HealthTrackerApp : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory
    @Inject lateinit var repository: HealthRepository
    @Inject lateinit var alarmScheduler: AlarmScheduler
    @Inject lateinit var settingsRepository: SettingsRepository

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()

    override fun onCreate() {
        super.onCreate()
        AlarmNotifier.ensureChannel(this)
        seedDefaultAlarms()
        seedDefaultHabits()
        cancelLegacyWebhookWorker()

        // HostSelectionInterceptor reads the server URL on OkHttp's thread,
        // where it cannot suspend. This keeps the cached copy current.
        settingsRepository.observeServerUrl(CoroutineScope(Dispatchers.IO))

        GymSyncWorker.schedulePeriodicSync(this)
        EntrySyncWorker.schedulePeriodicSync(this)
        // Catches the backlog on the first launch after coming home, without
        // waiting up to an hour for the periodic worker's first window.
        //
        // restartSync, not requestSync: a worker that has failed repeatedly is
        // sitting on a backoff of up to five hours, and the KEEP policy on
        // requestSync would leave it there — so opening the app, the one thing
        // a person does when sync looks stuck, would have no effect at all.
        GymSyncWorker.restartSync(this)
        EntrySyncWorker.restartSync(this)
    }

    /** One-time seed of the default habits, skipping any name that already exists. */
    private fun seedDefaultHabits() {
        val prefs = getSharedPreferences("app_flags", MODE_PRIVATE)
        if (prefs.getBoolean(KEY_HABITS_SEEDED, false)) return

        CoroutineScope(Dispatchers.IO).launch {
            val defaults = listOf("Magnesium", "Psyllium husk", "Sauna", "Gym", "Surf")
            val existing = repository.getAllHabitsSnapshot()
            val existingNames = existing.map { it.name.lowercase() }.toSet()
            var sortOrder = (existing.maxOfOrNull { it.sortOrder } ?: -1) + 1

            defaults.forEach { name ->
                if (name.lowercase() !in existingNames) {
                    repository.insertHabit(Habit(name = name, sortOrder = sortOrder))
                    sortOrder++
                }
            }
            prefs.edit().putBoolean(KEY_HABITS_SEEDED, true).apply()
        }
    }

    /** One-time seed of the recommended supplement/exercise/sleep alarms. */
    private fun seedDefaultAlarms() {
        val prefs = getSharedPreferences("app_flags", MODE_PRIVATE)
        if (prefs.getBoolean(KEY_ALARMS_SEEDED, false)) return

        CoroutineScope(Dispatchers.IO).launch {
            val defaults = listOf(
                AlarmEntry(label = "Blood pressure (before breakfast)",  hour = 7,  minute = 30),
                AlarmEntry(label = "Vit D + Creatine — fatty breakfast", hour = 7,  minute = 30),
                AlarmEntry(label = "Psyllium husk + big water",          hour = 12, minute = 0),
                AlarmEntry(label = "Evening workout (strength)",          hour = 18, minute = 0),
                AlarmEntry(label = "Magnesium glycinate + wind-down",     hour = 21, minute = 0),
                AlarmEntry(label = "Blood pressure (bedtime)",            hour = 21, minute = 30),
                AlarmEntry(label = "Lights out",                          hour = 22, minute = 0)
            )
            defaults.forEach { alarm ->
                repository.insertAlarm(alarm)
                alarmScheduler.schedule(alarm)
            }
            prefs.edit().putBoolean(KEY_ALARMS_SEEDED, true).apply()
        }
    }

    /**
     * Cancel the legacy webhook worker left behind by earlier installs.
     *
     * `UploadWorker` posted every type to a `webhook.site` placeholder that was
     * never configured, so it uploaded nothing — but WorkManager persists its
     * schedule across upgrades, so it would keep waking the phone hourly to
     * fail. Every type it carried now goes to the portal via [EntrySyncWorker].
     */
    private fun cancelLegacyWebhookWorker() {
        WorkManager.getInstance(this).cancelUniqueWork("health_sync")
    }

    companion object {
        private const val KEY_ALARMS_SEEDED = "default_alarms_seeded"
        private const val KEY_HABITS_SEEDED = "default_habits_seeded"
    }
}
