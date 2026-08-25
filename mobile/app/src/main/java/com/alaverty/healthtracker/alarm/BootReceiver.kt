package com.alaverty.healthtracker.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Exact alarms are cleared by the OS on reboot; re-arm every enabled alarm.
 */
@AndroidEntryPoint
class BootReceiver : BroadcastReceiver() {

    @Inject lateinit var repository: HealthRepository
    @Inject lateinit var scheduler: AlarmScheduler

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != "android.intent.action.QUICKBOOT_POWERON"
        ) return

        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                scheduler.rescheduleAll(repository.getEnabledAlarms())
            } finally {
                pending.finish()
            }
        }
    }
}
