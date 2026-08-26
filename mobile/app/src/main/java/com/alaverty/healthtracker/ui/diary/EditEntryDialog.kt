package com.alaverty.healthtracker.ui.diary

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * One editable field on an entry. Three is the most any type needs (blood
 * pressure: systolic, diastolic, notes), so the dialog holds three slots
 * rather than growing a form builder for a fixed, small set of shapes.
 */
private data class FieldSpec(
    val label: String,
    val initial: String,
    val numeric: Boolean = false,
    val multiline: Boolean = false
)

/**
 * What each diary type lets you change, mirroring the portal's
 * `services._ENTRY_EDITABLE`. An empty list means datetime-only: the values
 * came from a device or a dedicated screen, and the correction wanted here is
 * the clock.
 */
private fun fieldsFor(item: DiaryItem): List<FieldSpec> = when (item) {
    is DiaryItem.Diet -> listOf(FieldSpec("Food", item.entry.name))
    is DiaryItem.Note -> listOf(
        FieldSpec("Title", item.entry.title),
        FieldSpec("Note", item.entry.content, multiline = true)
    )
    is DiaryItem.Bm -> listOf(
        FieldSpec("BM number", item.entry.bmNumber.toString(), numeric = true),
        FieldSpec("Notes", item.entry.notes)
    )
    is DiaryItem.Bp -> listOf(
        FieldSpec("Systolic", item.entry.systolic.toString(), numeric = true),
        FieldSpec("Diastolic", item.entry.diastolic.toString(), numeric = true),
        FieldSpec("Notes", item.entry.notes)
    )
    is DiaryItem.Weight -> listOf(
        FieldSpec("Weight (kg)", item.entry.weightKg.toString(), numeric = true),
        FieldSpec("Notes", item.entry.notes)
    )
    is DiaryItem.Exercise, is DiaryItem.Body, is DiaryItem.Habit -> emptyList()
}

private fun titleFor(item: DiaryItem): String = when (item) {
    is DiaryItem.Diet -> "Edit food entry"
    is DiaryItem.Note -> "Edit note"
    is DiaryItem.Bm -> "Edit BM entry"
    is DiaryItem.Bp -> "Edit blood pressure"
    is DiaryItem.Weight -> "Edit weight"
    is DiaryItem.Exercise -> "Edit exercise time"
    is DiaryItem.Body -> "Edit measurement time"
    is DiaryItem.Habit -> "Edit habit time"
}

/**
 * Rebuilds the item with the edited values. Returns null when something typed
 * into a numeric field is not a number, so the dialog can refuse to save
 * rather than silently writing a zero over a real reading.
 *
 * `timestamp` is set here for every type. For habits it is `completedAt` -
 * and `date` moves with it in the view model, because that field is stored
 * rather than derived (the same trap `duplicateEntry` hit).
 */
private fun applyEdits(item: DiaryItem, values: List<String>, ts: Long): DiaryItem? = when (item) {
    is DiaryItem.Diet -> {
        val name = values[0].trim()
        if (name.isEmpty()) null
        else DiaryItem.Diet(item.entry.copy(name = name, timestamp = ts))
    }
    is DiaryItem.Note ->
        DiaryItem.Note(item.entry.copy(title = values[0].trim(), content = values[1], timestamp = ts))
    is DiaryItem.Bm -> values[0].trim().toIntOrNull()?.let {
        DiaryItem.Bm(item.entry.copy(bmNumber = it, notes = values[1], timestamp = ts))
    }
    is DiaryItem.Bp -> {
        val systolic = values[0].trim().toIntOrNull()
        val diastolic = values[1].trim().toIntOrNull()
        if (systolic == null || diastolic == null) null
        else DiaryItem.Bp(
            item.entry.copy(
                systolic = systolic, diastolic = diastolic, notes = values[2], timestamp = ts
            )
        )
    }
    is DiaryItem.Weight -> values[0].trim().toFloatOrNull()?.let {
        DiaryItem.Weight(item.entry.copy(weightKg = it, notes = values[1], timestamp = ts))
    }
    is DiaryItem.Exercise -> DiaryItem.Exercise(item.entry.copy(timestamp = ts))
    is DiaryItem.Body -> DiaryItem.Body(item.entry.copy(timestamp = ts))
    is DiaryItem.Habit -> DiaryItem.Habit(item.entry.copy(completedAt = ts))
}

@Composable
fun EditEntryDialog(
    item: DiaryItem,
    onDismiss: () -> Unit,
    onSave: (DiaryItem) -> Unit
) {
    val specs = remember(item) { fieldsFor(item) }
    var values by remember(item) { mutableStateOf(specs.map { it.initial }) }
    var timestamp by remember(item) { mutableStateOf(item.timestamp) }
    var invalid by remember(item) { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(titleFor(item)) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.verticalScroll(rememberScrollState())
            ) {
                specs.forEachIndexed { i, spec ->
                    OutlinedTextField(
                        value = values[i],
                        onValueChange = { new ->
                            values = values.toMutableList().also { it[i] = new }
                            invalid = false
                        },
                        label = { Text(spec.label) },
                        singleLine = !spec.multiline,
                        minLines = if (spec.multiline) 3 else 1,
                        keyboardOptions = KeyboardOptions(
                            keyboardType = if (spec.numeric) KeyboardType.Number else KeyboardType.Text,
                            imeAction = ImeAction.Next
                        ),
                        modifier = Modifier.fillMaxWidth()
                    )
                }

                DateTimeField(millis = timestamp, onChange = { timestamp = it })

                if (invalid) {
                    Text(
                        "Check the values above.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val edited = applyEdits(item, values, timestamp)
                if (edited == null) invalid = true else onSave(edited)
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

/**
 * A date and a time, as two buttons over one epoch-millis value.
 *
 * Two separate pickers rather than one combined control because Material3
 * ships `DatePickerDialog` and `TimePicker` and nothing that does both - and
 * a hand-rolled combined dialog would be a bigger surface than the two taps
 * it saves.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateTimeField(
    millis: Long,
    onChange: (Long) -> Unit,
    label: String = "When"
) {
    var showDate by remember { mutableStateOf(false) }
    var showTime by remember { mutableStateOf(false) }
    val dateFmt = remember { SimpleDateFormat("EEE d MMM yyyy", Locale.getDefault()) }
    val timeFmt = remember { SimpleDateFormat("h:mm a", Locale.getDefault()) }

    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedButton(onClick = { showDate = true }, modifier = Modifier.weight(1.6f)) {
                Text(dateFmt.format(Date(millis)))
            }
            OutlinedButton(onClick = { showTime = true }, modifier = Modifier.weight(1f)) {
                Text(timeFmt.format(Date(millis)))
            }
        }
    }

    if (showDate) {
        val state = rememberDatePickerState(initialSelectedDateMillis = millis)
        DatePickerDialog(
            onDismissRequest = { showDate = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { picked ->
                        // The picker answers in UTC midnight. Keeping the
                        // existing clock time means changing the day never
                        // silently moves the entry to midnight, and never
                        // drags it across a day boundary by a timezone offset.
                        val chosen = Calendar.getInstance().apply { timeInMillis = picked }
                        onChange(
                            Calendar.getInstance().apply {
                                timeInMillis = millis
                                set(Calendar.YEAR, chosen.get(Calendar.YEAR))
                                set(Calendar.MONTH, chosen.get(Calendar.MONTH))
                                set(Calendar.DAY_OF_MONTH, chosen.get(Calendar.DAY_OF_MONTH))
                            }.timeInMillis
                        )
                    }
                    showDate = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDate = false }) { Text("Cancel") } }
        ) {
            DatePicker(state = state)
        }
    }

    if (showTime) {
        val now = Calendar.getInstance().apply { timeInMillis = millis }
        val state = rememberTimePickerState(
            initialHour = now.get(Calendar.HOUR_OF_DAY),
            initialMinute = now.get(Calendar.MINUTE),
            is24Hour = false
        )
        AlertDialog(
            onDismissRequest = { showTime = false },
            title = { Text("Time") },
            text = { TimePicker(state = state) },
            confirmButton = {
                TextButton(onClick = {
                    onChange(
                        Calendar.getInstance().apply {
                            timeInMillis = millis
                            set(Calendar.HOUR_OF_DAY, state.hour)
                            set(Calendar.MINUTE, state.minute)
                            set(Calendar.SECOND, 0)
                            set(Calendar.MILLISECOND, 0)
                        }.timeInMillis
                    )
                    showTime = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showTime = false }) { Text("Cancel") } }
        )
    }
}
