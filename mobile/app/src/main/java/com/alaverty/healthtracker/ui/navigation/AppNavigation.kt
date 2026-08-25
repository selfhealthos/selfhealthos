package com.alaverty.healthtracker.ui.navigation

import android.content.res.Configuration
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.alaverty.healthtracker.ui.alarms.AlarmsScreen
import com.alaverty.healthtracker.ui.bm.BmScreen
import com.alaverty.healthtracker.ui.body.BodyScreen
import com.alaverty.healthtracker.ui.bp.BpScreen
import com.alaverty.healthtracker.ui.charts.ChartsScreen
import com.alaverty.healthtracker.ui.diary.DiaryScreen
import com.alaverty.healthtracker.ui.docs.DocsScreen
import com.alaverty.healthtracker.ui.exercise.ExerciseScreen
import com.alaverty.healthtracker.ui.gym.GymScreen
import com.alaverty.healthtracker.ui.habits.HabitsScreen
import com.alaverty.healthtracker.ui.labs.LabsScreen
import com.alaverty.healthtracker.ui.notes.NotesScreen
import com.alaverty.healthtracker.ui.settings.SettingsScreen
import com.alaverty.healthtracker.ui.weight.WeightScreen
import com.alaverty.healthtracker.ui.wfh.WfhScreen

sealed class Screen(val route: String, val label: String, val icon: ImageVector) {
    object Diary    : Screen("diary",    "Diary",    Icons.Default.DateRange)
    object Gym      : Screen("gym",      "Gym",      Icons.Default.FitnessCenter)
    object Exercise : Screen("exercise", "Exercise", Icons.Default.PlayArrow)
    object Notes    : Screen("notes",    "Notes",    Icons.Default.Create)
    object Charts   : Screen("charts",   "Charts",   Icons.Default.BarChart)
    object Bm       : Screen("bm",       "BM",       Icons.Default.FormatListNumbered)
    object Bp       : Screen("bp",       "BP",       Icons.Default.Favorite)
    object Weight   : Screen("weight",   "Weight",   Icons.Default.MonitorWeight)
    object Habits   : Screen("habits",   "Habits",   Icons.Default.CheckCircle)
    object Docs     : Screen("docs",     "Docs",     Icons.Default.Article)
    object Wfh      : Screen("wfh",      "WFH",      Icons.Default.HomeWork)
    object Labs     : Screen("labs",     "Labs",     Icons.Default.Biotech)
    object Body     : Screen("body",     "Body",     Icons.Default.Straighten)
    object Alarms   : Screen("alarms",   "Alarms",   Icons.Default.Alarm)
    object Settings : Screen("settings", "Settings", Icons.Default.Settings)
}

private val screens = listOf(
    Screen.Diary,
    Screen.Gym,
    Screen.Habits,
    Screen.Bm,
    Screen.Exercise,
    Screen.Notes,
    Screen.Charts,
    Screen.Bp,
    Screen.Weight,
    Screen.Body,
    Screen.Labs,
    Screen.Docs,
    Screen.Wfh,
    Screen.Alarms,
    Screen.Settings
)

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route

    // Hide the bottom nav in landscape while the exercise player is active
    val isLandscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE
    val hideBottomNav = isLandscape && currentRoute == Screen.Exercise.route

    Scaffold(
        bottomBar = {
            if (!hideBottomNav) {
                ScrollableBottomNav(
                    screens = screens,
                    currentRoute = currentRoute,
                    onNavigate = { route ->
                        navController.navigate(route) {
                            popUpTo(Screen.Diary.route) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                )
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Diary.route,
            modifier = Modifier.padding(innerPadding)
        ) {
            composable(Screen.Diary.route)    { DiaryScreen() }
            composable(Screen.Gym.route)      { GymScreen() }
            composable(Screen.Exercise.route) { ExerciseScreen() }
            composable(Screen.Notes.route)    { NotesScreen() }
            composable(Screen.Charts.route)   { ChartsScreen() }
            composable(Screen.Bm.route)       { BmScreen() }
            composable(Screen.Bp.route)       { BpScreen() }
            composable(Screen.Weight.route)   { WeightScreen() }
            composable(Screen.Habits.route)   { HabitsScreen() }
            composable(Screen.Docs.route)     { DocsScreen() }
            composable(Screen.Wfh.route)      { WfhScreen() }
            composable(Screen.Labs.route)     { LabsScreen() }
            composable(Screen.Body.route)     { BodyScreen() }
            composable(Screen.Alarms.route)   { AlarmsScreen() }
            composable(Screen.Settings.route) { SettingsScreen() }
        }
    }
}

@Composable
private fun ScrollableBottomNav(
    screens: List<Screen>,
    currentRoute: String?,
    onNavigate: (String) -> Unit
) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceContainer,
        tonalElevation = 3.dp,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .windowInsetsPadding(WindowInsets.navigationBars)
                .height(72.dp)
        ) {
            screens.forEach { screen ->
                val selected = currentRoute == screen.route
                val contentColor = if (selected)
                    MaterialTheme.colorScheme.onSecondaryContainer
                else
                    MaterialTheme.colorScheme.onSurfaceVariant

                Column(
                    modifier = Modifier
                        .width(80.dp)
                        .fillMaxHeight()
                        .clickable { onNavigate(screen.route) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    if (selected) {
                        Surface(
                            color = MaterialTheme.colorScheme.secondaryContainer,
                            shape = MaterialTheme.shapes.extraLarge
                        ) {
                            Icon(
                                imageVector = screen.icon,
                                contentDescription = screen.label,
                                tint = contentColor,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                            )
                        }
                    } else {
                        Icon(
                            imageVector = screen.icon,
                            contentDescription = screen.label,
                            tint = contentColor
                        )
                    }
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = screen.label,
                        style = MaterialTheme.typography.labelSmall,
                        color = contentColor,
                        textAlign = TextAlign.Center,
                        maxLines = 1
                    )
                }
            }
        }
    }
}
