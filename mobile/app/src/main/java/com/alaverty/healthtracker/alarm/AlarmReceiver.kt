package com.alaverty.healthtracker.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.alaverty.healthtracker.data.local.entity.AlarmEntry
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Fires at the alarm's exact time: posts the heads-up notification, then re-arms
 * the same alarm for the next day (exact one-shot alarms don't repeat by themselves).
 */
@AndroidEntryPoint
class AlarmReceiver : BroadcastReceiver() {

    @Inject lateinit var scheduler: AlarmScheduler

    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getStringExtra(EXTRA_ID) ?: return
        val label = intent.getStringExtra(EXTRA_LABEL).orEmpty()
        val hour = intent.getIntExtra(EXTRA_HOUR, 0)
        val minute = intent.getIntExtra(EXTRA_MINUTE, 0)

        AlarmNotifier.notify(context, AlarmScheduler.requestCode(id), label)

        // Re-arm for tomorrow's occurrence.
        scheduler.schedule(
            AlarmEntry(id = id, label = label, hour = hour, minute = minute, enabled = true)
        )
    }

    companion object {
        private const val EXTRA_ID = "alarm_id"
        private const val EXTRA_LABEL = "alarm_label"
        private const val EXTRA_HOUR = "alarm_hour"
        private const val EXTRA_MINUTE = "alarm_minute"

        fun intent(context: Context, alarm: AlarmEntry): Intent =
            Intent(context, AlarmReceiver::class.java).apply {
                action = "com.alaverty.healthtracker.ALARM_FIRE"
                putExtra(EXTRA_ID, alarm.id)
                putExtra(EXTRA_LABEL, alarm.label)
                putExtra(EXTRA_HOUR, alarm.hour)
                putExtra(EXTRA_MINUTE, alarm.minute)
            }
    }
}
