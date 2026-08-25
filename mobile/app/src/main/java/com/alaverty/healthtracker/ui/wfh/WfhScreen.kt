package com.alaverty.healthtracker.ui.wfh

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

@Composable
fun WfhScreen(viewModel: WfhViewModel = hiltViewModel()) {
    val yearMonth by viewModel.yearMonth.collectAsState()
    val officeDays by viewModel.officeDays.collectAsState()

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        // Month navigation
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            IconButton(onClick = viewModel::goToPreviousMonth) {
                Icon(Icons.Default.ChevronLeft, contentDescription = "Previous month")
            }
            Text(
                text = yearMonth.format(DateTimeFormatter.ofPattern("MMMM yyyy")),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold
            )
            IconButton(onClick = viewModel::goToNextMonth) {
                Icon(Icons.Default.ChevronRight, contentDescription = "Next month")
            }
        }

        Spacer(Modifier.height(8.dp))

        // Legend
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.primary)
            )
            Spacer(Modifier.width(4.dp))
            Text(
                "Office",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.width(12.dp))
            val officeCount = officeDays.size
            Text(
                "$officeCount day${if (officeCount != 1) "s" else ""} in office",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        Spacer(Modifier.height(12.dp))

        CalendarGrid(
            yearMonth = yearMonth,
            officeDays = officeDays,
            onDayClick = viewModel::toggleDay
        )
    }
}

@Composable
private fun CalendarGrid(
    yearMonth: YearMonth,
    officeDays: Set<String>,
    onDayClick: (LocalDate) -> Unit
) {
    val today = LocalDate.now()
    val firstDay = yearMonth.atDay(1)
    // Monday-first: 0 = Mon, 6 = Sun
    val startOffset = (firstDay.dayOfWeek.value - DayOfWeek.MONDAY.value + 7) % 7
    val daysInMonth = yearMonth.lengthOfMonth()

    // Day-of-week headers
    val dayHeaders = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    Row(modifier = Modifier.fillMaxWidth()) {
        dayHeaders.forEach { label ->
            val isWeekend = label == "Sat" || label == "Sun"
            Text(
                text = label,
                modifier = Modifier.weight(1f),
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Medium,
                color = if (isWeekend)
                    MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                else
                    MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }

    Spacer(Modifier.height(4.dp))

    // Build cells: leading blanks + day cells
    val totalCells = startOffset + daysInMonth
    val rows = (totalCells + 6) / 7

    for (row in 0 until rows) {
        Row(modifier = Modifier.fillMaxWidth()) {
            for (col in 0 until 7) {
                val cellIndex = row * 7 + col
                val dayNumber = cellIndex - startOffset + 1
                if (dayNumber < 1 || dayNumber > daysInMonth) {
                    Box(modifier = Modifier.weight(1f).aspectRatio(1f))
                } else {
                    val date = yearMonth.atDay(dayNumber)
                    val dateStr = date.toString()
                    val isOffice = dateStr in officeDays
                    val isToday = date == today
                    val isWeekend = date.dayOfWeek == DayOfWeek.SATURDAY ||
                            date.dayOfWeek == DayOfWeek.SUNDAY

                    DayCell(
                        day = dayNumber,
                        isOffice = isOffice,
                        isToday = isToday,
                        isWeekend = isWeekend,
                        onClick = { onDayClick(date) },
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun DayCell(
    day: Int,
    isOffice: Boolean,
    isToday: Boolean,
    isWeekend: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val bgColor = when {
        isOffice -> MaterialTheme.colorScheme.primary
        else     -> MaterialTheme.colorScheme.surface
    }
    val textColor = when {
        isOffice  -> MaterialTheme.colorScheme.onPrimary
        isWeekend -> MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f)
        else      -> MaterialTheme.colorScheme.onSurface
    }
    val borderColor = when {
        isToday  -> MaterialTheme.colorScheme.primary
        else     -> MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f)
    }

    Box(
        modifier = modifier
            .aspectRatio(1f)
            .padding(2.dp)
            .clip(CircleShape)
            .background(bgColor)
            .border(
                width = if (isToday && !isOffice) 2.dp else 0.dp,
                color = borderColor,
                shape = CircleShape
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = day.toString(),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (isOffice || isToday) FontWeight.Bold else FontWeight.Normal,
            color = textColor,
            textAlign = TextAlign.Center
        )
    }
}
