package com.alaverty.healthtracker.ui.body

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.data.local.entity.BodyMeasurement
import com.alaverty.healthtracker.data.local.entity.FitnessTest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun BodyScreen(viewModel: BodyViewModel = hiltViewModel()) {
    val measurements by viewModel.measurements.collectAsState()
    val fitnessTests by viewModel.fitnessTests.collectAsState()
    val heightCm     by viewModel.heightCm.collectAsState()

    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var showDialog  by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
            TabRow(selectedTabIndex = selectedTab) {
                Tab(selected = selectedTab == 0, onClick = { selectedTab = 0},
                    text = { Text("Measurements") })
                Tab(selected = selectedTab == 1, onClick = { selectedTab = 1},
                    text = { Text("Fitness Tests") })
            }

            when (selectedTab) {
                0 -> MeasurementsTab(
                    measurements = measurements,
                    heightCm     = heightCm,
                    onDelete     = { viewModel.deleteMeasurement(it) }
                )
                1 -> FitnessTestsTab(
                    tests    = fitnessTests,
                    onDelete = { viewModel.deleteFitnessTest(it) }
                )
            }
        }

        FloatingActionButton(
            onClick = { showDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Add entry")
        }
    }

    if (showDialog) {
        if (selectedTab == 0) {
            AddMeasurementDialog(
                onDismiss = { showDialog = false },
                onConfirm = { waist, hips, neck, fat, notes ->
                    viewModel.addMeasurement(waist, hips, neck, fat, notes)
                    showDialog = false
                }
            )
        } else {
            AddFitnessTestDialog(
                onDismiss = { showDialog = false },
                onConfirm = { grip, balance, sitToStand, deadHang, notes ->
                    viewModel.addFitnessTest(grip, balance, sitToStand, deadHang, notes)
                    showDialog = false
                }
            )
        }
    }
}

private val dateFmt = SimpleDateFormat("EEE, MMM d yyyy", Locale.getDefault())

private fun fmt(v: Double): String =
    if (v % 1.0 == 0.0) "%.0f".format(v) else "%.1f".format(v)

// ── Measurements tab ──────────────────────────────────────────────────────────

@Composable
private fun MeasurementsTab(
    measurements: List<BodyMeasurement>,
    heightCm: Float,
    onDelete: (BodyMeasurement) -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        val latestWaist = measurements.firstOrNull { it.waistCm != null }?.waistCm

        if (latestWaist != null) {
            item { WaistToHeightCard(latestWaist, heightCm) }
        }

        items(measurements, key = { it.id }) { m ->
            val prev = measurements.getOrNull(measurements.indexOf(m) + 1)
            MeasurementRow(m, prev, onDelete = { onDelete(m) })
        }

        if (measurements.isEmpty()) {
            item { EmptyHint("No measurements yet.\nTap + to log waist, hips, neck or body fat.") }
        }

        item { Spacer(Modifier.height(72.dp)) }
    }
}

@Composable
private fun WaistToHeightCard(waistCm: Double, heightCm: Float) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text("Waist-to-Height Ratio", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer)
            Spacer(Modifier.height(4.dp))
            if (heightCm > 0f) {
                val ratio = waistCm / heightCm
                val (verdict, color) = when {
                    ratio < 0.5  -> "Healthy (< 0.5)" to Color(0xFF2E7D32)
                    ratio <= 0.6 -> "Elevated (0.5–0.6)" to Color(0xFFF9A825)
                    else         -> "High (> 0.6)" to MaterialTheme.colorScheme.error
                }
                Text(
                    "%.2f".format(ratio),
                    style = MaterialTheme.typography.displaySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Text(verdict, style = MaterialTheme.typography.bodyMedium, color = color)
                Text(
                    "Waist ${fmt(waistCm)} cm / height ${"%.0f".format(heightCm)} cm",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            } else {
                Text(
                    "Set your height in Settings to see your waist-to-height ratio.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }
    }
}

@Composable
private fun MeasurementRow(
    m: BodyMeasurement,
    prev: BodyMeasurement?,
    onDelete: () -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        ListItem(
            headlineContent = {
                val parts = buildList {
                    m.waistCm?.let    { add("Waist ${fmt(it)} cm") }
                    m.hipsCm?.let     { add("Hips ${fmt(it)} cm") }
                    m.neckCm?.let     { add("Neck ${fmt(it)} cm") }
                    m.bodyFatPct?.let { add("Body fat ${fmt(it)}%") }
                }
                Text(parts.joinToString("  ·  "), style = MaterialTheme.typography.bodyLarge)
            },
            supportingContent = {
                Column {
                    Text(dateFmt.format(Date(m.timestamp)),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    val waistChange = if (m.waistCm != null && prev?.waistCm != null)
                        m.waistCm - prev.waistCm else null
                    if (waistChange != null && waistChange != 0.0) {
                        val prefix = if (waistChange > 0) "+" else ""
                        val color = if (waistChange < 0) MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.error
                        Text("$prefix${fmt(waistChange)} cm waist",
                            style = MaterialTheme.typography.bodySmall, color = color)
                    }
                    if (m.notes.isNotBlank()) {
                        Text(m.notes, style = MaterialTheme.typography.bodySmall,
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
private fun AddMeasurementDialog(
    onDismiss: () -> Unit,
    onConfirm: (waist: Double?, hips: Double?, neck: Double?, fat: Double?, notes: String) -> Unit
) {
    var waist by remember { mutableStateOf("") }
    var hips  by remember { mutableStateOf("") }
    var neck  by remember { mutableStateOf("") }
    var fat   by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    val anyValue = listOf(waist, hips, neck, fat).any { it.toDoubleOrNull() != null }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Measurements") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Fill in whichever you measured.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DecimalField(waist, { waist = it }, "Waist (cm)", Modifier.weight(1f))
                    DecimalField(hips,  { hips = it },  "Hips (cm)",  Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DecimalField(neck, { neck = it }, "Neck (cm)",     Modifier.weight(1f))
                    DecimalField(fat,  { fat = it },  "Body fat (%)",  Modifier.weight(1f))
                }
                OutlinedTextField(
                    value = notes, onValueChange = { notes = it },
                    label = { Text("Notes (optional)") }, singleLine = true
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onConfirm(waist.toDoubleOrNull(), hips.toDoubleOrNull(),
                        neck.toDoubleOrNull(), fat.toDoubleOrNull(), notes)
                },
                enabled = anyValue
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Fitness tests tab ─────────────────────────────────────────────────────────

@Composable
private fun FitnessTestsTab(
    tests: List<FitnessTest>,
    onDelete: (FitnessTest) -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        items(tests, key = { it.id }) { test ->
            val prev = tests.getOrNull(tests.indexOf(test) + 1)
            FitnessTestRow(test, prev, onDelete = { onDelete(test) })
        }

        if (tests.isEmpty()) {
            item {
                EmptyHint(
                    "No fitness tests yet.\nTap + to log a monthly self-test:\n" +
                    "grip strength, single-leg balance,\nsit-to-stand reps, dead hang."
                )
            }
        }

        item { Spacer(Modifier.height(72.dp)) }
    }
}

@Composable
private fun FitnessTestRow(
    test: FitnessTest,
    prev: FitnessTest?,
    onDelete: () -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    dateFmt.format(Date(test.timestamp)),
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.weight(1f)
                )
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            TestValueRow("Grip strength",      test.gripKg,                       prev?.gripKg,              "kg")
            TestValueRow("Single-leg balance", test.singleLegBalanceSec,          prev?.singleLegBalanceSec, "sec")
            TestValueRow("Sit-to-stand (30s)", test.sitToStandReps?.toDouble(),   prev?.sitToStandReps?.toDouble(), "reps")
            TestValueRow("Dead hang",          test.deadHangSec,                  prev?.deadHangSec,         "sec")
            if (test.notes.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(test.notes, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun TestValueRow(label: String, value: Double?, prevValue: Double?, unit: String) {
    if (value == null) return
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        Text("${fmt(value)} $unit", style = MaterialTheme.typography.bodyMedium)
        if (prevValue != null && value != prevValue) {
            // Higher is better for every fitness test
            val change = value - prevValue
            val prefix = if (change > 0) "+" else ""
            val color  = if (change > 0) MaterialTheme.colorScheme.primary
                         else MaterialTheme.colorScheme.error
            Spacer(Modifier.width(6.dp))
            Text("$prefix${fmt(change)}", style = MaterialTheme.typography.labelSmall, color = color)
        }
    }
}

@Composable
private fun AddFitnessTestDialog(
    onDismiss: () -> Unit,
    onConfirm: (grip: Double?, balance: Double?, sitToStand: Int?, deadHang: Double?, notes: String) -> Unit
) {
    var grip       by remember { mutableStateOf("") }
    var balance    by remember { mutableStateOf("") }
    var sitToStand by remember { mutableStateOf("") }
    var deadHang   by remember { mutableStateOf("") }
    var notes      by remember { mutableStateOf("") }

    val anyValue = grip.toDoubleOrNull() != null || balance.toDoubleOrNull() != null ||
        sitToStand.toIntOrNull() != null || deadHang.toDoubleOrNull() != null

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log Fitness Test") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Fill in whichever tests you did.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DecimalField(grip,    { grip = it },    "Grip (kg)",     Modifier.weight(1f))
                    DecimalField(balance, { balance = it }, "Balance (sec)", Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = sitToStand,
                        onValueChange = { sitToStand = it.filter { c -> c.isDigit() } },
                        label = { Text("Sit-to-stand") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f)
                    )
                    DecimalField(deadHang, { deadHang = it }, "Dead hang (sec)", Modifier.weight(1f))
                }
                OutlinedTextField(
                    value = notes, onValueChange = { notes = it },
                    label = { Text("Notes (optional)") }, singleLine = true
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onConfirm(grip.toDoubleOrNull(), balance.toDoubleOrNull(),
                        sitToStand.toIntOrNull(), deadHang.toDoubleOrNull(), notes)
                },
                enabled = anyValue
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Shared bits ───────────────────────────────────────────────────────────────

@Composable
private fun DecimalField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier
) {
    OutlinedTextField(
        value = value,
        onValueChange = { onValueChange(it.filter { c -> c.isDigit() || c == '.' }) },
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        modifier = modifier
    )
}

@Composable
private fun EmptyHint(text: String) {
    Box(
        modifier = Modifier.fillMaxWidth().padding(top = 64.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
