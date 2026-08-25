package com.alaverty.healthtracker.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

// Bristol type colours: dark-brown (hard) → green (ideal) → red (watery)
private val bmTypeColors = listOf(
    Color(0xFF4E342E), // 1 — separate hard lumps
    Color(0xFF8D6E63), // 2 — lumpy sausage
    Color(0xFFD4A574), // 3 — cracked sausage
    Color(0xFF4CAF50), // 4 — smooth (ideal)
    Color(0xFFFFC107), // 5 — soft blobs
    Color(0xFFFF9800), // 6 — fluffy/mushy
    Color(0xFFF44336), // 7 — watery
)

@Composable
fun ChartsScreen(viewModel: ChartsViewModel = hiltViewModel()) {
    val exerciseData by viewModel.exerciseData.collectAsState()
    val bmData       by viewModel.bmData.collectAsState()
    val weightTrend  by viewModel.weightTrend.collectAsState()
    val gymExercises by viewModel.gymExerciseNames.collectAsState()
    val selectedExercise by viewModel.selectedExercise.collectAsState()
    val gymStats     by viewModel.gymStats.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp)
    ) {
        // ── Exercise ─────────────────────────────────────────────────────────
        Text("Exercise — last 7 days", style = MaterialTheme.typography.titleMedium)
        if (exerciseData.isEmpty()) {
            LoadingBox()
        } else {
            SimpleBarChart(
                labels  = exerciseData.map { it.label },
                values  = exerciseData.map { it.minutes },
                barColor = MaterialTheme.colorScheme.primary,
                yLabel  = "min",
                modifier = Modifier.fillMaxWidth().height(220.dp)
            )
        }

        HorizontalDivider()

        // ── BM ───────────────────────────────────────────────────────────────
        Text("Bowel Movements — last 14 days", style = MaterialTheme.typography.titleMedium)
        if (bmData.isEmpty()) {
            LoadingBox()
        } else {
            StackedBarChart(
                data     = bmData,
                modifier = Modifier.fillMaxWidth().height(220.dp)
            )
            BmLegend()
        }

        HorizontalDivider()

        // ── Weight trend ─────────────────────────────────────────────────────
        Text("Weight — last 90 days", style = MaterialTheme.typography.titleMedium)
        val trend = weightTrend
        when {
            trend == null -> LoadingBox()
            trend.rawPoints.size < 2 ->
                Text(
                    "Not enough weight entries yet — log a few weigh-ins to see the trend.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            else -> {
                trend.ratePerWeek?.let { rate ->
                    val color = when {
                        rate < -0.05f -> MaterialTheme.colorScheme.primary
                        rate >  0.05f -> MaterialTheme.colorScheme.error
                        else          -> MaterialTheme.colorScheme.onSurfaceVariant
                    }
                    Text(
                        "Trend: %+.2f kg/week (7-day average)".format(rate),
                        style = MaterialTheme.typography.bodyMedium,
                        color = color
                    )
                }
                LineChart(
                    rawPoints  = trend.rawPoints,
                    linePoints = trend.maPoints,
                    yUnit      = "kg",
                    modifier   = Modifier.fillMaxWidth().height(220.dp)
                )
                Text(
                    "Dots: daily weigh-ins · Line: 7-day moving average",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        HorizontalDivider()

        // ── Gym progressive overload ─────────────────────────────────────────
        Text("Gym — progressive overload", style = MaterialTheme.typography.titleMedium)
        if (gymExercises.isEmpty()) {
            Text(
                "No gym sets logged yet.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        } else {
            ExerciseSelector(
                exercises = gymExercises,
                selected  = selectedExercise,
                onSelect  = { viewModel.selectExercise(it) }
            )

            val stats = gymStats
            if (stats == null) {
                Text(
                    "No sets for this exercise yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                PrCard(stats)

                Text("Estimated 1RM (Epley)", style = MaterialTheme.typography.titleSmall)
                LineChart(
                    rawPoints  = stats.e1rmByDate,
                    linePoints = stats.e1rmByDate,
                    yUnit      = "kg",
                    modifier   = Modifier.fillMaxWidth().height(200.dp)
                )

                Text("Weekly volume — last 8 weeks", style = MaterialTheme.typography.titleSmall)
                SimpleBarChart(
                    labels = stats.weeklyVolume.map { (weekStart, _) ->
                        listOf(
                            "W/C",
                            weekStart.dayOfMonth.toString(),
                            weekStart.format(DateTimeFormatter.ofPattern("MMM", Locale.getDefault())).uppercase()
                        )
                    },
                    values   = stats.weeklyVolume.map { it.second },
                    barColor = MaterialTheme.colorScheme.tertiary,
                    yLabel   = "",
                    modifier = Modifier.fillMaxWidth().height(200.dp)
                )
                Text(
                    "Volume = weight × reps summed across all sets (kg)",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Spacer(Modifier.height(8.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ExerciseSelector(
    exercises: List<String>,
    selected: String,
    onSelect: (String) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }

    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = selected,
            onValueChange = {},
            readOnly = true,
            label = { Text("Exercise") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.fillMaxWidth().menuAnchor()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            exercises.forEach { name ->
                DropdownMenuItem(
                    text = { Text(name) },
                    onClick = {
                        onSelect(name)
                        expanded = false
                    }
                )
            }
        }
    }
}

@Composable
private fun PrCard(stats: GymExerciseStats) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (stats.prInLatestSession)
                MaterialTheme.colorScheme.primaryContainer
            else
                MaterialTheme.colorScheme.surfaceContainerHigh
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            if (stats.prInLatestSession) {
                Text(
                    "New PR! 🎉",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Spacer(Modifier.height(4.dp))
            }
            Text(
                "Best e1RM: ${"%.1f".format(stats.bestE1rm)} kg  (${stats.bestE1rmDate})",
                style = MaterialTheme.typography.bodyMedium
            )
            Text(
                "Top weight: ${"%.1f".format(stats.maxWeightKg)} kg  (${stats.maxWeightDate})",
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

// ── Line chart with raw-value dots and a trend line ──────────────────────────

@Composable
private fun LineChart(
    rawPoints: List<Pair<Long, Float>>,    // x = epochDay, y = value
    linePoints: List<Pair<Long, Float>>,
    yUnit: String,
    modifier: Modifier = Modifier
) {
    val axisColor    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.25f)
    val labelColor   = MaterialTheme.colorScheme.onSurface
    val lineColor    = MaterialTheme.colorScheme.primary
    val pointColor   = MaterialTheme.colorScheme.primary.copy(alpha = 0.45f)
    val textMeasurer = rememberTextMeasurer()
    val labelStyle   = TextStyle(fontSize = 10.sp, color = labelColor)

    Canvas(modifier = modifier) {
        val all = rawPoints + linePoints
        if (all.isEmpty()) return@Canvas

        val xMinDay = all.minOf { it.first }
        val xMaxDay = all.maxOf { it.first }.coerceAtLeast(xMinDay + 1)
        var yMin = all.minOf { it.second }
        var yMax = all.maxOf { it.second }
        val yPad = ((yMax - yMin) * 0.1f).coerceAtLeast(0.5f)
        yMin -= yPad
        yMax += yPad

        val padLeft   = 44.dp.toPx()
        val padBottom = 24.dp.toPx()
        val padTop    = 8.dp.toPx()
        val chartW    = size.width - padLeft
        val chartH    = size.height - padBottom - padTop

        fun px(p: Pair<Long, Float>) = Offset(
            padLeft + chartW * (p.first - xMinDay).toFloat() / (xMaxDay - xMinDay).toFloat(),
            padTop + chartH * (1f - (p.second - yMin) / (yMax - yMin))
        )

        // Grid + Y labels
        repeat(5) { i ->
            val frac = i / 4f
            val y    = padTop + chartH * (1f - frac)
            drawLine(axisColor, Offset(padLeft, y), Offset(size.width, y), 1.dp.toPx())
            val txt = textMeasurer.measure("%.1f$yUnit".format(yMin + (yMax - yMin) * frac), labelStyle)
            drawText(txt, topLeft = Offset(0f, y - txt.size.height / 2f))
        }

        // X labels: first, middle, last date in the domain
        val xLabelDays = listOf(xMinDay, (xMinDay + xMaxDay) / 2, xMaxDay).distinct()
        val xFmt = DateTimeFormatter.ofPattern("d MMM", Locale.getDefault())
        xLabelDays.forEach { day ->
            val cx  = padLeft + chartW * (day - xMinDay).toFloat() / (xMaxDay - xMinDay).toFloat()
            val txt = textMeasurer.measure(LocalDate.ofEpochDay(day).format(xFmt), labelStyle)
            val x   = (cx - txt.size.width / 2f).coerceIn(padLeft, size.width - txt.size.width)
            drawText(txt, topLeft = Offset(x, padTop + chartH + 4.dp.toPx()))
        }

        // Trend line
        if (linePoints.size >= 2) {
            val path = Path()
            linePoints.sortedBy { it.first }.forEachIndexed { idx, p ->
                val o = px(p)
                if (idx == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y)
            }
            drawPath(path, lineColor, style = Stroke(width = 2.dp.toPx()))
        }

        // Raw points
        rawPoints.forEach { p ->
            drawCircle(pointColor, radius = 3.dp.toPx(), center = px(p))
        }

        // X axis
        drawLine(axisColor, Offset(padLeft, padTop + chartH), Offset(size.width, padTop + chartH), 1.dp.toPx())
    }
}

@Composable
private fun LoadingBox() {
    Box(Modifier.fillMaxWidth().height(220.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

// ── Shared helper: draw a 3-line axis label centred on cx ────────────────────

private fun DrawScope.drawAxisLabel(
    lines: List<String>,
    cx: Float,
    yStart: Float,
    measurer: TextMeasurer,
    style: TextStyle,
    alpha: Float = 1f
) {
    var y = yStart
    lines.forEach { line ->
        val lm = measurer.measure(line, style)
        drawText(lm, topLeft = Offset(cx - lm.size.width / 2f, y), alpha = alpha)
        y += lm.size.height + 1.dp.toPx()
    }
}

// ── Simple (single-colour) bar chart ─────────────────────────────────────────

@Composable
private fun SimpleBarChart(
    labels:   List<AxisLabel>,
    values:   List<Float>,
    barColor: Color,
    yLabel:   String,
    modifier: Modifier = Modifier
) {
    val axisColor    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.25f)
    val labelColor   = MaterialTheme.colorScheme.onSurface
    val textMeasurer = rememberTextMeasurer()
    val labelStyle   = TextStyle(fontSize = 10.sp, color = labelColor)

    Canvas(modifier = modifier) {
        val maxVal     = values.maxOrNull()?.coerceAtLeast(1f) ?: 1f
        val padLeft    = 36.dp.toPx()
        val padBottom  = 48.dp.toPx()   // room for 3-line label
        val padTop     = 8.dp.toPx()
        val chartW     = size.width - padLeft
        val chartH     = size.height - padBottom - padTop
        val barSpacing = chartW / labels.size
        val barW       = barSpacing * 0.55f

        // Grid + Y labels
        repeat(5) { i ->
            val frac = i / 4f
            val y    = padTop + chartH * (1f - frac)
            drawLine(axisColor, Offset(padLeft, y), Offset(size.width, y), 1.dp.toPx())
            val txt = textMeasurer.measure("%.0f$yLabel".format(maxVal * frac), labelStyle)
            drawText(txt, topLeft = Offset(0f, y - txt.size.height / 2f))
        }

        // Bars + 3-line X labels
        labels.forEachIndexed { idx, labelLines ->
            val v    = values[idx]
            val barH = (chartH * (v / maxVal)).coerceAtLeast(if (v > 0f) 2.dp.toPx() else 0f)
            val cx   = padLeft + idx * barSpacing + barSpacing / 2f
            val left = cx - barW / 2f
            if (barH > 0f) {
                drawRect(barColor, topLeft = Offset(left, padTop + chartH - barH), size = Size(barW, barH))
            }
            drawAxisLabel(labelLines, cx, padTop + chartH + 4.dp.toPx(), textMeasurer, labelStyle)
        }

        // X axis
        drawLine(axisColor, Offset(padLeft, padTop + chartH), Offset(size.width, padTop + chartH), 1.dp.toPx())
    }
}

// ── Stacked bar chart for BM Bristol types ────────────────────────────────────

@Composable
private fun StackedBarChart(data: List<BmDayData>, modifier: Modifier = Modifier) {
    val axisColor    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.25f)
    val labelColor   = MaterialTheme.colorScheme.onSurface
    val textMeasurer = rememberTextMeasurer()
    val labelStyle   = TextStyle(fontSize = 9.sp, color = labelColor)

    Canvas(modifier = modifier) {
        val maxTotal   = data.maxOf { it.countsByType.sum() }.coerceAtLeast(1)
        val padLeft    = 24.dp.toPx()
        val padBottom  = 48.dp.toPx()   // room for 3-line label
        val padTop     = 8.dp.toPx()
        val chartW     = size.width - padLeft
        val chartH     = size.height - padBottom - padTop
        val barSpacing = chartW / data.size
        val barW       = barSpacing * 0.55f

        // Grid + Y labels
        repeat(maxTotal.coerceAtMost(5) + 1) { i ->
            val frac = i.toFloat() / maxTotal
            val y    = padTop + chartH * (1f - frac)
            drawLine(axisColor, Offset(padLeft, y), Offset(size.width, y), 1.dp.toPx())
            if (i > 0) {
                val lm = textMeasurer.measure("$i", labelStyle)
                drawText(lm, topLeft = Offset(0f, y - lm.size.height / 2f))
            }
        }

        // Stacked bars + 3-line X labels
        data.forEachIndexed { idx, day ->
            val cx   = padLeft + idx * barSpacing + barSpacing / 2f
            val left = cx - barW / 2f
            var stackedPx = 0f

            day.countsByType.forEachIndexed { typeIdx, count ->
                if (count > 0) {
                    val segH = chartH * (count.toFloat() / maxTotal)
                    val top  = padTop + chartH - stackedPx - segH
                    drawRect(bmTypeColors[typeIdx], topLeft = Offset(left, top),
                        size = Size(barW, segH.coerceAtLeast(1.dp.toPx())))
                    stackedPx += segH
                }
            }

            val hasData = day.countsByType.sum() > 0
            drawAxisLabel(
                day.label, cx, padTop + chartH + 4.dp.toPx(),
                textMeasurer, labelStyle, alpha = if (hasData) 1f else 0.35f
            )
        }

        // X axis
        drawLine(axisColor, Offset(padLeft, padTop + chartH), Offset(size.width, padTop + chartH), 1.dp.toPx())
    }
}

// ── BM legend ─────────────────────────────────────────────────────────────────

private val bmTypeLabels = listOf(
    "1 Separate lumps",
    "2 Lumpy sausage",
    "3 Cracked sausage",
    "4 Smooth (ideal)",
    "5 Soft blobs",
    "6 Fluffy/mushy",
    "7 Watery"
)

@Composable
private fun BmLegend() {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        bmTypeLabels.chunked(2).forEachIndexed { rowIdx, pair ->
            Row(modifier = Modifier.fillMaxWidth()) {
                pair.forEachIndexed { colIdx, label ->
                    val typeIdx = rowIdx * 2 + colIdx
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.weight(1f)
                    ) {
                        Canvas(modifier = Modifier.size(10.dp)) {
                            drawRect(bmTypeColors[typeIdx])
                        }
                        Spacer(Modifier.width(4.dp))
                        Text(label, style = MaterialTheme.typography.labelSmall)
                    }
                }
                // pad last row if odd number of items
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}
