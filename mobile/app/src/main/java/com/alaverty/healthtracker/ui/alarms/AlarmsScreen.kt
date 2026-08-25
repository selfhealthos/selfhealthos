package com.alaverty.healthtracker.ui.alarms

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.data.local.entity.AlarmEntry

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlarmsScreen(viewModel: AlarmsViewModel = hiltViewModel()) {
    val alarms by viewModel.alarms.collectAsState()
    val context = LocalContext.current
    var showAdd by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<AlarmEntry?>(null) }
    var exactAllowed by remember { mutableStateOf(viewModel.canScheduleExact()) }

    // Ask for notification permission (Android 13+) on first entry.
    val notifPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* result handled by system UI; nothing to do */ }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        exactAllowed = viewModel.canScheduleExact()
    }

    Box(modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (!exactAllowed) {
                item { ExactAlarmWarning(onFix = { openExactAlarmSettings(context) }) }
            }

            items(alarms, key = { it.id }) { alarm ->
                AlarmRow(
                    alarm = alarm,
                    onToggle = { viewModel.toggle(alarm, it) },
                    onEdit = { editing = alarm },
                    onDelete = { viewModel.delete(alarm) }
                )
            }

            if (alarms.isEmpty()) {
                item {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(top = 64.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            "No alarms yet.\nTap + to add a daily reminder.",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }

        FloatingActionButton(
            onClick = { showAdd = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Add alarm")
        }
    }

    if (showAdd) {
        AlarmDialog(
            title = "New Alarm",
            initialLabel = "",
            initialHour = 8,
            initialMinute = 0,
            onDismiss = { showAdd = false },
            onConfirm = { label, hour, minute ->
                viewModel.add(label, hour, minute)
                showAdd = false
            }
        )
    }

    editing?.let { alarm ->
        AlarmDialog(
            title = "Edit Alarm",
            initialLabel = alarm.label,
            initialHour = alarm.hour,
            initialMinute = alarm.minute,
            onDismiss = { editing = null },
            onConfirm = { label, hour, minute ->
                viewModel.update(alarm, label, hour, minute)
                editing = null
            }
        )
    }
}

@Composable
private fun ExactAlarmWarning(onFix: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                Icons.Default.Warning,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onErrorContainer
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    "Exact alarms are off",
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onErrorContainer
                )
                Text(
                    "Reminders may fire late. Tap to allow exact alarms.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onErrorContainer
                )
            }
            TextButton(onClick = onFix) { Text("Fix") }
        }
    }
}

@Composable
private fun AlarmRow(
    alarm: AlarmEntry,
    onToggle: (Boolean) -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth(), onClick = onEdit) {
        ListItem(
            headlineContent = {
                Text(
                    "%02d:%02d".format(alarm.hour, alarm.minute),
                    style = MaterialTheme.typography.headlineSmall
                )
            },
            supportingContent = {
                Text(alarm.label, style = MaterialTheme.typography.bodyMedium)
            },
            trailingContent = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(checked = alarm.enabled, onCheckedChange = onToggle)
                    IconButton(onClick = onDelete) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "Delete",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AlarmDialog(
    title: String,
    initialLabel: String,
    initialHour: Int,
    initialMinute: Int,
    onDismiss: () -> Unit,
    onConfirm: (String, Int, Int) -> Unit
) {
    var label by remember { mutableStateOf(initialLabel) }
    val timeState = rememberTimePickerState(
        initialHour = initialHour,
        initialMinute = initialMinute,
        is24Hour = true
    )

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                OutlinedTextField(
                    value = label,
                    onValueChange = { label = it },
                    label = { Text("Name") },
                    placeholder = { Text("e.g. Take blood pressure") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                TimePicker(state = timeState)
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(label, timeState.hour, timeState.minute) }) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}

private fun openExactAlarmSettings(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val intent = Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM).apply {
            data = Uri.fromParts("package", context.packageName, null)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        runCatching { context.startActivity(intent) }
    }
}
