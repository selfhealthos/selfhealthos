package com.alaverty.healthtracker.ui.bm

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import java.text.SimpleDateFormat
import java.time.format.DateTimeFormatter
import java.util.*

@Composable
fun BmScreen(viewModel: BmViewModel = hiltViewModel()) {
    val form by viewModel.form.collectAsState()
    val entries by viewModel.entries.collectAsState()
    val selectedDate by viewModel.selectedDate.collectAsState()
    val timeFormat = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                IconButton(onClick = viewModel::goToPreviousDay) {
                    Icon(Icons.Default.ChevronLeft, contentDescription = "Previous day")
                }
                Text(
                    text = selectedDate.format(DateTimeFormatter.ofPattern("EEEE, MMMM d")),
                    style = MaterialTheme.typography.titleMedium
                )
                IconButton(onClick = viewModel::goToNextDay) {
                    Icon(Icons.Default.ChevronRight, contentDescription = "Next day")
                }
            }
            HorizontalDivider()
        }

        item {
            Text("Log BM", style = MaterialTheme.typography.headlineSmall)
        }

        item {
            Text("Bristol Stool Scale", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                (1..7).forEach { n ->
                    FilterChip(
                        selected = form.selectedNumber == n,
                        onClick = { viewModel.selectNumber(n) },
                        label = {
                            Text(
                                text = "$n",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                        },
                        modifier = Modifier.size(44.dp)
                    )
                }
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
                enabled = form.selectedNumber != null,
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
                    "Entries",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }

            items(entries, key = { it.id }) { entry ->
                ListItem(
                    headlineContent = { Text("Type ${entry.bmNumber}", fontWeight = FontWeight.SemiBold) },
                    supportingContent = {
                        Column {
                            if (entry.notes.isNotBlank()) Text(entry.notes)
                            Text(
                                timeFormat.format(Date(entry.timestamp)),
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
