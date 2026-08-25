package com.alaverty.healthtracker.alarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.os.Build
import com.alaverty.healthtracker.data.local.entity.AlarmEntry
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Schedules exact, daily-recurring alarms via [AlarmManager]. Each fire is a
 * one-shot exact alarm; [AlarmReceiver] re-arms the next day after it triggers.
 */
@Singleton
class AlarmScheduler @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val alarmManager = context.getSystemService(AlarmManager::class.java)

    /** Whether the OS will honour exact alarms for this app right now. */
    fun canScheduleExact(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            alarmManager?.canScheduleExactAlarms() == true
        else true

    fun schedule(alarm: AlarmEntry) {
        if (!alarm.enabled) return
        val am = alarmManager ?: return
        val triggerAt = nextTriggerMillis(alarm.hour, alarm.minute)
        val pending = pendingIntent(alarm)

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pending)
            } else {
                am.setExact(AlarmManager.RTC_WAKEUP, triggerAt, pending)
            }
        } catch (_: SecurityException) {
            // Exact-alarm permission revoked mid-flight; ignore.
        }
    }

    fun cancel(alarm: AlarmEntry) {
        alarmManager?.cancel(pendingIntent(alarm))
    }

    fun rescheduleAll(alarms: List<AlarmEntry>) {
        alarms.forEach { schedule(it) }
    }

    private fun pendingIntent(alarm: AlarmEntry): PendingIntent {
        val intent = AlarmReceiver.intent(context, alarm)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0
        return PendingIntent.getBroadcast(context, requestCode(alarm.id), intent, flags)
    }

    companion object {
        fun requestCode(id: String): Int = id.hashCode()

        /** Next epoch-milli at [hour]:[minute] — today if still ahead, else tomorrow. */
        fun nextTriggerMillis(hour: Int, minute: Int): Long {
            val zone = ZoneId.systemDefault()
            val now = java.time.LocalDateTime.now(zone)
            val time = LocalTime.of(hour, minute)
            var next = LocalDate.now(zone).atTime(time)
            if (!next.isAfter(now)) next = next.plusDays(1)
            return next.atZone(zone).toInstant().toEpochMilli()
        }
    }
}
