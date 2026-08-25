package com.alaverty.healthtracker.ui.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.data.preferences.AppSettings
import com.alaverty.healthtracker.data.preferences.DEFAULT_SERVER_URL
import com.alaverty.healthtracker.data.preferences.TokenState
import com.alaverty.healthtracker.sync.GymSyncStatus
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.ui.text.input.ImeAction

@Composable
fun SettingsScreen(viewModel: SettingsViewModel = hiltViewModel()) {
    val savedSettings   by viewModel.settings.collectAsState()
    val exportStatus    by viewModel.exportStatus.collectAsState()
    val habits          by viewModel.habits.collectAsState()
    val tokenState      by viewModel.tokenState.collectAsState()
    val syncStatus      by viewModel.syncStatus.collectAsState()
    val pendingGymCount by viewModel.pendingGymCount.collectAsState()
    val enrolling       by viewModel.enrolling.collectAsState()
    val enrolmentError  by viewModel.enrolmentError.collectAsState()

    // Local form state — initialised once from DataStore, then edited freely
    var githubRepo  by remember(savedSettings.githubRepo)  { mutableStateOf(savedSettings.githubRepo) }
    var githubToken by remember(savedSettings.githubToken) { mutableStateOf(savedSettings.githubToken) }
    var syncAll     by remember(savedSettings.syncAll)     { mutableStateOf(savedSettings.syncAll) }
    var syncDays    by remember(savedSettings.syncDays)    { mutableStateOf(savedSettings.syncDays.toString()) }
    var heightCm    by remember(savedSettings.heightCm)    {
        mutableStateOf(if (savedSettings.heightCm > 0f) "%.0f".format(savedSettings.heightCm) else "")
    }
    var tokenVisible by remember { mutableStateOf(false) }
    var serverUrl by remember(savedSettings.serverUrl) { mutableStateOf(savedSettings.serverUrl) }

    fun currentSettings() = AppSettings(
        githubRepo  = githubRepo,
        githubToken = githubToken,
        syncAll     = syncAll,
        syncDays    = syncDays.toIntOrNull()?.coerceAtLeast(1) ?: 14,
        heightCm    = heightCm.toFloatOrNull() ?: 0f,
        serverUrl   = serverUrl.ifBlank { DEFAULT_SERVER_URL }
    )

    val isRunning = exportStatus is ExportStatus.Running

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineSmall)

        HorizontalDivider()

        // ── Profile ───────────────────────────────────────────────────────
        Text("Profile", style = MaterialTheme.typography.titleMedium)

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            OutlinedTextField(
                value = heightCm,
                onValueChange = { heightCm = it.filter { c -> c.isDigit() || c == '.' } },
                label = { Text("Height (cm)") },
                placeholder = { Text("e.g. 178") },
                supportingText = { Text("Used for waist-to-height ratio on the Body screen") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.weight(1f)
            )
            Button(
                onClick = { viewModel.saveSettings(currentSettings()) },
                enabled = heightCm.toFloatOrNull() != null
            ) { Text("Save") }
        }

        HorizontalDivider()

        HomePortalSection(
            serverUrl = serverUrl,
            onServerUrlChange = { serverUrl = it },
            onSaveServerUrl = { viewModel.saveSettings(currentSettings()) },
            tokenState = tokenState,
            syncStatus = syncStatus,
            pending = pendingGymCount,
            enrolling = enrolling,
            enrolmentError = enrolmentError,
            onEnrol = viewModel::enrol,
            onSyncNow = viewModel::syncGymNow
        )

        HorizontalDivider()

        Text("GitHub Export", style = MaterialTheme.typography.titleMedium)

        OutlinedTextField(
            value = githubRepo,
            onValueChange = { githubRepo = it },
            label = { Text("Repository") },
            placeholder = { Text("owner/repo") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        OutlinedTextField(
            value = githubToken,
            onValueChange = { githubToken = it },
            label = { Text("Personal Access Token") },
            singleLine = true,
            visualTransformation = if (tokenVisible) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = {
                IconButton(onClick = { tokenVisible = !tokenVisible }) {
                    Icon(
                        imageVector = if (tokenVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                        contentDescription = if (tokenVisible) "Hide token" else "Show token"
                    )
                }
            },
            modifier = Modifier.fillMaxWidth()
        )

        HorizontalDivider()

        Text("Sync Range", style = MaterialTheme.typography.titleMedium)

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth()
        ) {
            RadioButton(selected = syncAll, onClick = { syncAll = true })
            Spacer(Modifier.width(4.dp))
            Text("All data")
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth()
        ) {
            RadioButton(selected = !syncAll, onClick = { syncAll = false })
            Spacer(Modifier.width(4.dp))
            Text("Last N days")
        }

        if (!syncAll) {
            OutlinedTextField(
                value = syncDays,
                onValueChange = { syncDays = it.filter { c -> c.isDigit() } },
                label = { Text("Number of days") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.width(160.dp)
            )
        }

        HorizontalDivider()

        Button(
            onClick = { viewModel.export(currentSettings()) },
            enabled = !isRunning && githubRepo.isNotBlank() && githubToken.isNotBlank(),
            modifier = Modifier.fillMaxWidth()
        ) {
            if (isRunning) {
                CircularProgressIndicator(
                    modifier = Modifier.size(18.dp),
                    strokeWidth = 2.dp,
                    color = MaterialTheme.colorScheme.onPrimary
                )
                Spacer(Modifier.width(8.dp))
            }
            Text(if (isRunning) "Exporting…" else "Export to GitHub")
        }

        when (val status = exportStatus) {
            is ExportStatus.Running -> {
                Text(
                    text = status.message,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            is ExportStatus.Success -> {
                Text(
                    text = status.message,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary
                )
            }
            is ExportStatus.Error -> {
                Text(
                    text = status.message,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error
                )
            }
            is ExportStatus.Idle -> {}
        }

        HorizontalDivider()

        // ── Manage Habits ─────────────────────────────────────────────────
        Text("Manage Habits", style = MaterialTheme.typography.titleMedium)

        var newHabitName by remember { mutableStateOf("") }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            OutlinedTextField(
                value = newHabitName,
                onValueChange = { newHabitName = it },
                label = { Text("New habit") },
                singleLine = true,
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = {
                    viewModel.addHabit(newHabitName)
                    newHabitName = ""
                })
            )
            Button(
                onClick = {
                    viewModel.addHabit(newHabitName)
                    newHabitName = ""
                },
                enabled = newHabitName.isNotBlank()
            ) {
                Icon(Icons.Default.Add, contentDescription = null)
            }
        }

        if (habits.isEmpty()) {
            Text(
                "No habits yet.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        } else {
            habits.forEach { habit ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = habit.name,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.weight(1f)
                    )
                    IconButton(onClick = { viewModel.deleteHabit(habit) }) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "Delete habit",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))
    }
}

/**
 * Enrolment and sync state for the home portal.
 *
 * Deliberately verbose about state. Sync is invisible when it works, so the
 * only way to trust it is to be able to see that it is working - hence the
 * pending count and the last outcome, both of which are the numbers that would
 * expose the failure modes this design is built to avoid.
 */
@Composable
private fun HomePortalSection(
    serverUrl: String,
    onServerUrlChange: (String) -> Unit,
    onSaveServerUrl: () -> Unit,
    tokenState: TokenState,
    syncStatus: GymSyncStatus,
    pending: Int,
    enrolling: Boolean,
    enrolmentError: String,
    onEnrol: (String, String) -> Unit,
    onSyncNow: () -> Unit
) {
    var username by remember { mutableStateOf(tokenState.account) }
    var password by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }

    Text("Home Portal", style = MaterialTheme.typography.titleMedium)

    OutlinedTextField(
        value = serverUrl,
        onValueChange = onServerUrlChange,
        label = { Text("Server URL") },
        placeholder = { Text(DEFAULT_SERVER_URL) },
        supportingText = { Text("Reachable on the home wifi only. Entries queue elsewhere.") },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        trailingIcon = {
            TextButton(onClick = onSaveServerUrl) { Text("Save") }
        },
        modifier = Modifier.fillMaxWidth()
    )

    // ── Status ────────────────────────────────────────────────────────────
    val (statusText, statusColor) = statusLine(tokenState, syncStatus, pending)
    Card(
        colors = CardDefaults.cardColors(containerColor = statusColor.copy(alpha = 0.12f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(statusText, style = MaterialTheme.typography.bodyMedium, color = statusColor)
            Text(
                if (pending == 0) "Nothing waiting to sync."
                // `pending` is gym sets + gym exercises + every other entry
                // type combined (see SettingsViewModel.pendingGymCount) - not
                // gym alone, so the label must not say "gym" or a backlog of
                // ordinary entries reads as a gym-sync problem.
                else "$pending ${if (pending == 1) "entry" else "entries"} waiting to sync.",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }

    if (tokenState.enrolled && !tokenState.rejected) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                "Enrolled as ${tokenState.account}",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.weight(1f)
            )
            Button(onClick = onSyncNow, enabled = syncStatus !is GymSyncStatus.Syncing) {
                Text(if (syncStatus is GymSyncStatus.Syncing) "Syncing…" else "Sync now")
            }
        }
    }

    // ── Enrolment ─────────────────────────────────────────────────────────
    if (!tokenState.enrolled || tokenState.rejected) {
        Text(
            if (tokenState.rejected)
                "The portal refused this device's credential. Sign in again to restore syncing — " +
                    "nothing queued has been lost."
            else
                "Sign in once with your portal account. The password is used to collect a device " +
                    "token and is never stored on the phone.",
            style = MaterialTheme.typography.bodySmall
        )

        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Username") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            modifier = Modifier.fillMaxWidth()
        )

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            singleLine = true,
            visualTransformation =
                if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            trailingIcon = {
                IconButton(onClick = { passwordVisible = !passwordVisible }) {
                    Icon(
                        imageVector =
                            if (passwordVisible) Icons.Default.VisibilityOff
                            else Icons.Default.Visibility,
                        contentDescription = if (passwordVisible) "Hide password" else "Show password"
                    )
                }
            },
            modifier = Modifier.fillMaxWidth()
        )

        if (enrolmentError.isNotBlank()) {
            Text(
                enrolmentError,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error
            )
        }

        // Never disabled for want of input: a greyed-out button absorbs the tap
        // and explains nothing. It validates on press and says what is missing.
        Button(
            onClick = {
                onEnrol(username, password)
                password = ""
            },
            enabled = !enrolling,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (enrolling) "Signing in…" else "Enrol this device")
        }
    }
}

@Composable
private fun statusLine(
    token: TokenState,
    status: GymSyncStatus,
    pending: Int
): Pair<String, Color> = when {
    token.rejected ->
        "Credential rejected — re-enrol below" to MaterialTheme.colorScheme.error
    !token.enrolled ->
        "Not enrolled — entries are saving locally only" to MaterialTheme.colorScheme.error
    else -> when (status) {
        is GymSyncStatus.Syncing -> "Syncing…" to MaterialTheme.colorScheme.primary
        is GymSyncStatus.UpToDate ->
            "Up to date — last synced ${timeAgo(status.at)}" to MaterialTheme.colorScheme.primary
        is GymSyncStatus.Offline ->
            "Portal unreachable — will sync at home" to MaterialTheme.colorScheme.onSurfaceVariant
        is GymSyncStatus.PartiallyRejected ->
            "${status.count} rejected: ${status.reason}" to MaterialTheme.colorScheme.error
        is GymSyncStatus.Failed -> "Sync failed: ${status.reason}" to MaterialTheme.colorScheme.error
        GymSyncStatus.NotEnrolled ->
            "Not enrolled" to MaterialTheme.colorScheme.error
        GymSyncStatus.TokenRejected ->
            "Credential rejected" to MaterialTheme.colorScheme.error
        GymSyncStatus.Idle ->
            if (pending == 0) "Up to date" to MaterialTheme.colorScheme.primary
            else "Waiting to sync" to MaterialTheme.colorScheme.onSurfaceVariant
    }
}

private fun timeAgo(epochMs: Long): String {
    val seconds = (System.currentTimeMillis() - epochMs) / 1000
    return when {
        seconds < 60 -> "just now"
        seconds < 3600 -> "${seconds / 60}m ago"
        seconds < 86400 -> "${seconds / 3600}h ago"
        else -> "${seconds / 86400}d ago"
    }
}
