package com.alaverty.healthtracker.ui.bp

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun BpScreen(viewModel: BpViewModel = hiltViewModel()) {
    val form by viewModel.form.collectAsState()
    val entries by viewModel.entries.collectAsState()
    val dateFormat = remember { SimpleDateFormat("MMM d, yyyy  HH:mm", Locale.getDefault()) }

    val isValid = form.systolic.isNotBlank() && form.diastolic.isNotBlank()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text("Log Blood Pressure", style = MaterialTheme.typography.headlineSmall)
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedTextField(
                    value = form.systolic,
                    onValueChange = viewModel::updateSystolic,
                    label = { Text("Systolic") },
                    suffix = { Text("mmHg") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                    modifier = Modifier.weight(1f)
                )
                OutlinedTextField(
                    value = form.diastolic,
                    onValueChange = viewModel::updateDiastolic,
                    label = { Text("Diastolic") },
                    suffix = { Text("mmHg") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            if (form.systolic.isNotBlank() && form.diastolic.isNotBlank()) {
                Text(
                    text = "${form.systolic} / ${form.diastolic} mmHg",
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Light,
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }

        item {
            OutlinedTextField(
                value = form.notes,
                onValueChange = viewModel::updateNotes,
                label = { Text("Notes (optional)") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2
            )
        }

        item {
            Button(
                onClick = viewModel::save,
                enabled = isValid,
                modifier = Modifier.fillMaxWidth()
            ) { Text("Save") }

            if (form.saved) {
                Text(
                    "Saved ✓",
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }

        if (entries.isNotEmpty()) {
            item {
                HorizontalDivider()
                Text(
                    "History",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }

            items(entries, key = { it.id }) { entry ->
                ListItem(
                    headlineContent = {
                        Text(
                            "${entry.systolic} / ${entry.diastolic} mmHg",
                            fontWeight = FontWeight.SemiBold
                        )
                    },
                    supportingContent = {
                        Column {
                            if (entry.notes.isNotBlank()) Text(entry.notes)
                            Text(
                                dateFormat.format(Date(entry.timestamp)),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    },
                    trailingContent = {
                        IconButton(onClick = { viewModel.deleteEntry(entry) }) {
                            Icon(Icons.Default.Delete, contentDescription = "Delete",
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                )
                HorizontalDivider()
            }
        }
    }
}
