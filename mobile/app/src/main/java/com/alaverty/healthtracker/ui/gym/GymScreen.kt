package com.alaverty.healthtracker.ui.gym

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.data.local.entity.GymSet
import java.text.NumberFormat
import java.time.format.DateTimeFormatter

@Composable
fun GymScreen(viewModel: GymViewModel = hiltViewModel()) {
    val selectedDate  by viewModel.selectedDate.collectAsState()
    val exerciseQuery by viewModel.exerciseQuery.collectAsState()
    val weightKg: Int by viewModel.weightKg.collectAsState()
    val reps          by viewModel.reps.collectAsState()
    val gymSets       by viewModel.gymSets.collectAsState()

    val totalVolume   = gymSets.sumOf { it.weightKg * it.reps }
    val exerciseCount = gymSets.map { it.exerciseName }.distinct().size

    val listState = rememberLazyListState()

    // Scroll to top after Room delivers the newly-inserted item
    LaunchedEffect(gymSets.size) {
        if (gymSets.isNotEmpty()) listState.scrollToItem(0)
    }

    var weightText by remember { mutableStateOf(weightKg.toString()) }
    var repsText   by remember { mutableStateOf(reps.toString()) }

    // Keep text fields in sync when +/- buttons or clearFields() change the ViewModel state
    LaunchedEffect(weightKg) {
        if (weightText.toIntOrNull() != weightKg) weightText = weightKg.toString()
    }
    LaunchedEffect(reps) {
        if (repsText.toIntOrNull() != reps) repsText = reps.toString()
    }

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
                text  = selectedDate.format(DateTimeFormatter.ofPattern("EEEE, MMMM d")),
                style = MaterialTheme.typography.titleMedium
            )
            IconButton(onClick = viewModel::goToNextDay) {
                Icon(Icons.Default.ChevronRight, contentDescription = "Next day")
            }
        }

        // ── Stats ──────────────────────────────────────────────────────────
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                text  = "$exerciseCount ${if (exerciseCount == 1) "exercise" else "exercises"}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text  = "Volume: ${formatVolume(totalVolume)} kg",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        HorizontalDivider()

        // ── Input form ─────────────────────────────────────────────────────
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            ExerciseNameField(
                query         = exerciseQuery,
                onQueryChange = viewModel::onExerciseQueryChange
            )

            Spacer(Modifier.height(4.dp))

            // Weight
            Text(
                text  = "WEIGHT (KG)",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.primary, thickness = 2.dp)
            Row(
                modifier              = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment     = Alignment.CenterVertically
            ) {
                StepButton(icon = Icons.Default.Remove, onClick = viewModel::decrementWeight)
                OutlinedTextField(
                    value         = weightText,
                    onValueChange = { text ->
                        weightText = text
                        text.toIntOrNull()?.let { viewModel.onWeightChange(it) }
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    textStyle = MaterialTheme.typography.displaySmall.copy(textAlign = TextAlign.Center),
                    singleLine = true,
                    modifier   = Modifier.width(130.dp)
                )
                StepButton(icon = Icons.Default.Add, onClick = viewModel::incrementWeight)
            }

            // Reps
            Text(
                text  = "REPS",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.primary, thickness = 2.dp)
            Row(
                modifier              = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment     = Alignment.CenterVertically
            ) {
                StepButton(icon = Icons.Default.Remove, onClick = viewModel::decrementReps)
                OutlinedTextField(
                    value         = repsText,
                    onValueChange = { text ->
                        repsText = text
                        text.toIntOrNull()?.let { viewModel.onRepsChange(it) }
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    textStyle = MaterialTheme.typography.displaySmall.copy(textAlign = TextAlign.Center),
                    singleLine = true,
                    modifier   = Modifier.width(130.dp)
                )
                StepButton(icon = Icons.Default.Add, onClick = viewModel::incrementReps)
            }

            // Save
            Button(
                onClick  = { viewModel.saveSet() },
                enabled  = exerciseQuery.isNotBlank(),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(44.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1BAA79))
            ) {
                Text(
                    "SAVE",
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleSmall
                )
            }
        }

        HorizontalDivider()

        // ── Set list ───────────────────────────────────────────────────────
        if (gymSets.isEmpty()) {
            Box(
                modifier         = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text  = "No sets logged yet",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            LazyColumn(state = listState, modifier = Modifier.weight(1f)) {
                items(gymSets, key = { it.id }) { set ->
                    SwipeToDeleteGymSet(
                        set      = set,
                        onDelete = { viewModel.deleteSet(set) },
                        modifier = Modifier.animateItem()
                    )
                }
            }
        }
    }
}

@Composable
private fun ExerciseNameField(
    query: String,
    onQueryChange: (String) -> Unit
) {
    OutlinedTextField(
        value           = query,
        onValueChange   = onQueryChange,
        label           = { Text("Exercise") },
        placeholder     = { Text("Type an exercise name…") },
        singleLine      = true,
        keyboardOptions = KeyboardOptions(
            capitalization = KeyboardCapitalization.Words,
            autoCorrectEnabled = false
        ),
        modifier        = Modifier.fillMaxWidth()
    )
}

@Composable
private fun StepButton(icon: ImageVector, onClick: () -> Unit) {
    FilledTonalIconButton(
        onClick  = onClick,
        modifier = Modifier.size(48.dp),
        shape    = MaterialTheme.shapes.medium
    ) {
        Icon(
            imageVector        = icon,
            contentDescription = null,
            modifier           = Modifier.size(20.dp)
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeToDeleteGymSet(
    set: GymSet,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier
) {
    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { it == SwipeToDismissBoxValue.EndToStart }
    )

    LaunchedEffect(dismissState.currentValue) {
        if (dismissState.currentValue == SwipeToDismissBoxValue.EndToStart) {
            onDelete()
        }
    }

    SwipeToDismissBox(
        state                    = dismissState,
        enableDismissFromStartToEnd = false,
        modifier                 = modifier,
        backgroundContent        = {
            Box(
                modifier         = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.errorContainer)
                    .padding(end = 20.dp),
                contentAlignment = Alignment.CenterEnd
            ) {
                Icon(
                    imageVector        = Icons.Default.Delete,
                    contentDescription = "Delete",
                    tint               = MaterialTheme.colorScheme.onErrorContainer
                )
            }
        }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
        ) {
            GymSetRow(set)
            HorizontalDivider()
        }
    }
}

@Composable
private fun GymSetRow(set: GymSet) {
    Row(
        modifier          = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text     = set.exerciseName,
            style    = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.weight(1f)
        )
        Text(
            text  = "${set.weightKg.toInt()} kg",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.width(12.dp))
        Text(
            text  = "${set.reps} reps",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

private fun formatVolume(volume: Double): String =
    NumberFormat.getNumberInstance().apply { maximumFractionDigits = 0 }.format(volume)
