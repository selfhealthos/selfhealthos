package com.alaverty.healthtracker.alarm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.alaverty.healthtracker.ui.MainActivity

/**
 * Owns the high-importance "reminders" channel and posts a single heads-up
 * notification (banner + ding + vibrate, auto-dismissed) — no ongoing alarm.
 */
object AlarmNotifier {

    const val CHANNEL_ID = "reminders"

    fun ensureChannel(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return

        val sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Reminders",
            NotificationManager.IMPORTANCE_HIGH   // heads-up banner + sound + vibrate
        ).apply {
            description = "One-off reminder dings"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 250, 150, 250)
            setSound(
                sound,
                AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .build()
            )
        }
        manager.createNotificationChannel(channel)
    }

    fun notify(context: Context, notificationId: Int, label: String) {
        ensureChannel(context)

        val tapIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0
        val contentIntent = PendingIntent.getActivity(context, notificationId, tapIntent, flags)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(label.ifBlank { "Reminder" })
            .setContentText("Reminder")
            .setPriority(NotificationCompat.PRIORITY_HIGH)      // heads-up pre-Android 8
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setDefaults(NotificationCompat.DEFAULT_ALL)        // sound + vibrate pre-Android 8
            .setAutoCancel(true)                                // tap clears it
            .setTimeoutAfter(60_000)                            // clears itself if ignored
            .setContentIntent(contentIntent)
            .build()

        try {
            NotificationManagerCompat.from(context).notify(notificationId, notification)
        } catch (_: SecurityException) {
            // POST_NOTIFICATIONS not granted (Android 13+); nothing we can do from here.
        }
    }
}
