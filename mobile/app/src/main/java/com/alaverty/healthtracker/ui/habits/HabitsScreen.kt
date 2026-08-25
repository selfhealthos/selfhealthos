package com.alaverty.healthtracker.ui.habits

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import java.time.format.DateTimeFormatter
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun HabitsScreen(viewModel: HabitsViewModel = hiltViewModel()) {
    val selectedDate by viewModel.selectedDate.collectAsState()
    val rows         by viewModel.habitRows.collectAsState()

    val completed = rows.count { it.completion != null }
    val total     = rows.size

    Column(modifier = Modifier.fillMaxSize()) {

        // ── Date navigation ────────────────────────────────────────────────
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp, vertical = 4.dp),
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

        // ── Progress summary ───────────────────────────────────────────────
        if (total > 0) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "$completed / $total completed",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (total > 0) {
                    LinearProgressIndicator(
                        progress = { completed.toFloat() / total },
                        modifier = Modifier.width(120.dp)
                    )
                }
            }
            HorizontalDivider()
        }

        // ── Habit list ─────────────────────────────────────────────────────
        when {
            rows.isEmpty() -> {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        text = "No habits configured.\nAdd some in Settings.",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            else -> {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(rows, key = { it.habit.id }) { row ->
                        HabitRowItem(
                            row      = row,
                            onToggle = { viewModel.toggle(row.habit, it) }
                        )
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

@Composable
private fun HabitRowItem(
    row: HabitRow,
    onToggle: (Boolean) -> Unit
) {
    val timeFmt = remember { SimpleDateFormat("h:mm a", Locale.getDefault()) }
    val done    = row.completion != null

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onToggle(!done) }
            .padding(horizontal = 16.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Checkbox(
            checked  = done,
            onCheckedChange = onToggle
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text     = row.habit.name,
            style    = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.weight(1f),
            color    = if (done) MaterialTheme.colorScheme.onSurfaceVariant
                       else MaterialTheme.colorScheme.onSurface
        )
        row.completion?.let {
            Text(
                text  = buildString {
                    if (row.completionCount > 1) append("×${row.completionCount}  ")
                    append(timeFmt.format(Date(it.completedAt)))
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary
            )
        }
    }
}
