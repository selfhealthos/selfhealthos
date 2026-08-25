package com.alaverty.healthtracker.ui.labs

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
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
import com.alaverty.healthtracker.data.local.entity.LabResult
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@Composable
fun LabsScreen(viewModel: LabsViewModel = hiltViewModel()) {
    val markerGroups by viewModel.markerGroups.collectAsState()
    var showDialog by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Text("Lab Results", style = MaterialTheme.typography.headlineSmall)
            }

            items(markerGroups, key = { it.name.lowercase() }) { group ->
                MarkerCard(group = group, onDelete = { viewModel.delete(it) })
            }

            if (markerGroups.isEmpty()) {
                item {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(top = 64.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            "No lab results yet.\nTap + to log a blood test result.",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            item { Spacer(Modifier.height(72.dp)) }   // keep last card clear of the FAB
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Add lab result")
        }
    }

    if (showDialog) {
        AddLabResultDialog(
            existingMarkers = markerGroups.map { it.name },
            onDismiss = { showDialog = false },
            onConfirm = { marker, value, unit, date, notes ->
                viewModel.add(marker, value, unit, date, notes)
                showDialog = false
            }
        )
    }
}

@Composable
private fun MarkerCard(group: MarkerGroup, onDelete: (LabResult) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val latest = group.entries.first()
    val prev   = group.entries.getOrNull(1)
    val change = prev?.let { latest.value - it.value }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded }
                .padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(group.name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        latest.date,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        "${formatValue(latest.value)} ${latest.unit}",
                        style = MaterialTheme.typography.titleLarge
                    )
                    if (change != null) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            val icon = when {
                                change > 0  -> Icons.Default.TrendingUp
                                change < 0  -> Icons.Default.TrendingDown
                                else        -> Icons.Default.TrendingFlat
                            }
                            // Direction colouring is neutral: "better" depends on the marker
                            Icon(
                                icon, contentDescription = null,
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(Modifier.width(2.dp))
                            val prefix = if (change > 0) "+" else ""
                            Text(
                                "$prefix${formatValue(change)} since ${prev.date}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
                Spacer(Modifier.width(4.dp))
                Icon(
                    if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (expanded) {
                Spacer(Modifier.height(8.dp))
                HorizontalDivider()
                group.entries.forEach { entry ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                "${entry.date}   ${formatValue(entry.value)} ${entry.unit}",
                                style = MaterialTheme.typography.bodyMedium
                            )
                            if (entry.notes.isNotBlank()) {
                                Text(
                                    entry.notes,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        IconButton(onClick = { onDelete(entry) }) {
                            Icon(
                                Icons.Default.Delete, contentDescription = "Delete",
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun formatValue(v: Double): String =
    if (v % 1.0 == 0.0) "%.0f".format(v) else "%.2f".format(v).trimEnd('0').trimEnd('.')

@Composable
private fun AddLabResultDialog(
    existingMarkers: List<String>,
    onDismiss: () -> Unit,
    onConfirm: (marker: String, value: Double, unit: String, date: String, notes: String) -> Unit
) {
    var marker     by remember { mutableStateOf("") }
    var valueInput by remember { mutableStateOf("") }
    var unit       by remember { mutableStateOf("") }
    var dateInput  by remember { mutableStateOf(LocalDate.now().toString()) }
    var notes      by remember { mutableStateOf("") }

    val value     = valueInput.toDoubleOrNull()
    val dateValid = runCatching { LocalDate.parse(dateInput, DateTimeFormatter.ISO_LOCAL_DATE) }.isSuccess
    val canSave   = marker.isNotBlank() && value != null && dateValid

    // Tapping a previously used marker pre-fills its name and unit
    val markerSuggestions = if (marker.isBlank()) existingMarkers.take(6) else
        existingMarkers.filter { it.contains(marker, ignoreCase = true) && !it.equals(marker, ignoreCase = true) }.take(6)

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Lab Result") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = marker,
                    onValueChange = { marker = it },
                    label = { Text("Marker") },
                    placeholder = { Text("e.g. ApoB, HbA1c, Vitamin D") },
                    singleLine = true
                )
                if (markerSuggestions.isNotEmpty()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        markerSuggestions.take(3).forEach { suggestion ->
                            SuggestionChip(
                                onClick = { marker = suggestion },
                                label = { Text(suggestion, style = MaterialTheme.typography.labelSmall) }
                            )
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = valueInput,
                        onValueChange = { valueInput = it },
                        label = { Text("Value") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        isError = valueInput.isNotBlank() && value == null,
                        modifier = Modifier.weight(1f)
                    )
                    OutlinedTextField(
                        value = unit,
                        onValueChange = { unit = it },
                        label = { Text("Unit") },
                        placeholder = { Text("mmol/L") },
                        singleLine = true,
                        modifier = Modifier.weight(1f)
                    )
                }
                OutlinedTextField(
                    value = dateInput,
                    onValueChange = { dateInput = it },
                    label = { Text("Test date") },
                    placeholder = { Text("YYYY-MM-DD") },
                    singleLine = true,
                    isError = dateInput.isNotBlank() && !dateValid
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes (optional)") },
                    singleLine = true
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { value?.let { onConfirm(marker, it, unit, dateInput, notes) } },
                enabled = canSave
            ) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
