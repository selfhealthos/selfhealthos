package com.alaverty.healthtracker.ui.weight

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.TrendingDown
import androidx.compose.material.icons.filled.TrendingFlat
import androidx.compose.material.icons.filled.TrendingUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.data.local.entity.WeightEntry
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun WeightScreen(viewModel: WeightViewModel = hiltViewModel()) {
    val entries by viewModel.entries.collectAsState()
    var showDialog by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Current weight summary card
            if (entries.isNotEmpty()) {
                item {
                    CurrentWeightCard(entries)
                }
            }

            // History header
            if (entries.isNotEmpty()) {
                item {
                    Text("History", style = MaterialTheme.typography.titleMedium)
                }
            }

            items(entries) { entry ->
                val prev = entries.getOrNull(entries.indexOf(entry) + 1)
                WeightEntryRow(
                    entry   = entry,
                    prev    = prev,
                    onDelete = { viewModel.delete(entry) }
                )
            }

            if (entries.isEmpty()) {
                item {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(top = 64.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            "No weight entries yet.\nTap + to log your weight.",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Log weight")
        }
    }

    if (showDialog) {
        AddWeightDialog(
            onDismiss = { showDialog = false },
            onConfirm = { kg, notes ->
                viewModel.add(kg, notes)
                showDialog = false
            }
        )
    }
}

@Composable
private fun CurrentWeightCard(entries: List<WeightEntry>) {
    val latest = entries.first()
    val prev   = entries.getOrNull(1)
    val change = prev?.let { latest.weightKg - it.weightKg }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors   = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text("Current Weight", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer)
            Spacer(Modifier.height(4.dp))
            Text(
                "${"%.1f".format(latest.weightKg)} kg",
                style = MaterialTheme.typography.displaySmall,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )
            if (change != null) {
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val (icon, color, prefix) = when {
                        change < 0f  -> Triple(Icons.Default.TrendingDown, MaterialTheme.colorScheme.primary, "")
                        change > 0f  -> Triple(Icons.Default.TrendingUp,   MaterialTheme.colorScheme.error,   "+")
                        else         -> Triple(Icons.Default.TrendingFlat,  MaterialTheme.colorScheme.onPrimaryContainer, "")
                    }
                    Icon(icon, contentDescription = null, tint = color,
                        modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(
                        "$prefix${"%.1f".format(change)} kg from last entry",
                        style = MaterialTheme.typography.bodyMedium,
                        color = color
                    )
                }
            }
        }
    }
}

@Composable
private fun WeightEntryRow(
    entry:    WeightEntry,
    prev:     WeightEntry?,
    onDelete: () -> Unit
) {
    val fmt    = remember { SimpleDateFormat("EEE, MMM d  HH:mm", Locale.getDefault()) }
    val change = prev?.let { entry.weightKg - it.weightKg }

    Card(modifier = Modifier.fillMaxWidth()) {
        ListItem(
            headlineContent = {
                Text("${"%.1f".format(entry.weightKg)} kg",
                    style = MaterialTheme.typography.titleMedium)
            },
            supportingContent = {
                Column {
                    Text(fmt.format(Date(entry.timestamp)),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (change != null) {
                        val prefix = if (change >= 0f) "+" else ""
                        val color  = if (change <= 0f) MaterialTheme.colorScheme.primary
                                     else MaterialTheme.colorScheme.error
                        Text("$prefix${"%.1f".format(change)} kg",
                            style = MaterialTheme.typography.bodySmall,
                            color = color)
                    }
                    if (entry.notes.isNotBlank()) {
                        Text(entry.notes,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            },
            trailingContent = {
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        )
    }
}

@Composable
private fun AddWeightDialog(
    onDismiss: () -> Unit,
    onConfirm: (Float, String) -> Unit
) {
    var weightInput by remember { mutableStateOf("") }
    var notes       by remember { mutableStateOf("") }
    val weightKg    = weightInput.toFloatOrNull()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Weight") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value         = weightInput,
                    onValueChange = { weightInput = it },
                    label         = { Text("Weight (kg)") },
                    placeholder   = { Text("e.g. 75.5") },
                    singleLine    = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    isError       = weightInput.isNotBlank() && weightKg == null
                )
                OutlinedTextField(
                    value         = notes,
                    onValueChange = { notes = it },
                    label         = { Text("Notes (optional)") },
                    singleLine    = true
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick  = { weightKg?.let { onConfirm(it, notes) } },
                enabled  = weightKg != null
            ) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
