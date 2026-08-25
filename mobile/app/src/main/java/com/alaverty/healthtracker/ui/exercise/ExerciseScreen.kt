package com.alaverty.healthtracker.ui.exercise

import android.content.res.Configuration
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

@Composable
fun ExerciseScreen(viewModel: ExerciseViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsState()

    if (state.selectedCategory == null) {
        CategoryListScreen(
            categories = state.categories,
            onSelect = viewModel::selectCategory
        )
    } else {
        VideoPlayerScreen(
            state = state,
            onComplete = viewModel::completeExercise,
            onSkip = viewModel::skipExercise
        )
    }
}

@Composable
private fun CategoryListScreen(
    categories: List<ExerciseCategory>,
    onSelect: (ExerciseCategory) -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        Text(
            text = "Choose Workout",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(16.dp)
        )

        if (categories.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    text = "No workout folders found.\n\nPush folders to:\n/sdcard/Android/data/com.alaverty.healthtracker/files/videos/",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            LazyColumn {
                items(categories) { category ->
                    Card(
                        onClick = { onSelect(category) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 6.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.FitnessCenter,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(32.dp)
                            )
                            Spacer(Modifier.width(16.dp))
                            Text(
                                text = category.name,
                                style = MaterialTheme.typography.titleLarge,
                                modifier = Modifier.weight(1f)
                            )
                            Icon(
                                Icons.Default.ChevronRight,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun VideoPlayerScreen(
    state: ExerciseUiState,
    onComplete: () -> Unit,
    onSkip: () -> Unit
) {
    val context = LocalContext.current
    val isLandscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE

    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            repeatMode = Player.REPEAT_MODE_ONE
            volume = 0f          // always muted
        }
    }

    LaunchedEffect(state.videoFile) {
        if (state.videoFile != null) {
            exoPlayer.setMediaItem(MediaItem.fromUri(Uri.fromFile(state.videoFile)))
            exoPlayer.prepare()
            exoPlayer.play()
        } else {
            exoPlayer.stop()
        }
    }

    DisposableEffect(Unit) {
        onDispose { exoPlayer.release() }
    }

    if (isLandscape && state.videoFile != null) {
        // ── Landscape: video fills the screen, controls overlaid at bottom ──
        Box(modifier = Modifier.fillMaxSize()) {
            AndroidView(
                factory = { ctx -> PlayerView(ctx).apply { player = exoPlayer; useController = false } },
                modifier = Modifier.fillMaxSize()
            )
            // Semi-transparent control bar at the bottom
            Column(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(Color.Black.copy(alpha = 0.55f))
                    .padding(horizontal = 24.dp, vertical = 12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = formatTimer(state.timerSeconds),
                    style = MaterialTheme.typography.displaySmall,
                    color = Color.White
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    OutlinedButton(
                        onClick = onSkip,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)
                    ) { Text("Skip") }
                    Button(onClick = onComplete, modifier = Modifier.weight(1f)) {
                        Text("Complete")
                    }
                }
            }
        }
    } else {
        // ── Portrait: original stacked layout ──────────────────────────────
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            state.selectedCategory?.let {
                Text(text = it.name, style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary)
            }

            if (state.videoFile == null) {
                Box(modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentAlignment = Alignment.Center) {
                    Text("No videos found in this folder.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                Text(text = state.videoTitle, style = MaterialTheme.typography.titleLarge)

                AndroidView(
                    factory = { ctx -> PlayerView(ctx).apply { player = exoPlayer; useController = false } },
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f)
                )

                Text(text = formatTimer(state.timerSeconds),
                    style = MaterialTheme.typography.displayMedium)

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    OutlinedButton(onClick = onSkip, modifier = Modifier.weight(1f)) {
                        Text("Skip")
                    }
                    Button(onClick = onComplete, modifier = Modifier.weight(1f)) {
                        Text("Complete")
                    }
                }
            }
        }
    }
}

private fun formatTimer(seconds: Long): String {
    val m = seconds / 60
    val s = seconds % 60
    return "%02d:%02d".format(m, s)
}
