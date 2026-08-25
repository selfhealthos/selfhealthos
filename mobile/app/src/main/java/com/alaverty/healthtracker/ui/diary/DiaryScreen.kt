package com.alaverty.healthtracker.ui.diary

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.ui.notes.NoteBlock
import com.alaverty.healthtracker.ui.notes.toNoteBlocks
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.format.DateTimeFormatter
import java.util.UUID

@Composable
fun DiaryScreen(viewModel: DiaryViewModel = hiltViewModel()) {
    val selectedDate by viewModel.selectedDate.collectAsState()
    val items by viewModel.diaryItems.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    fun onDeleteItem(item: DiaryItem) {
        viewModel.deleteEntry(item)
        scope.launch {
            val result = snackbarHostState.showSnackbar(
                message = "Entry deleted",
                actionLabel = "Undo",
                duration = SnackbarDuration.Short
            )
            if (result == SnackbarResult.ActionPerformed) {
                viewModel.undoDelete(item)
            }
        }
    }

    fun onDuplicateItem(item: DiaryItem) {
        viewModel.duplicateEntry(item)
        scope.launch {
            snackbarHostState.showSnackbar(
                message = "Entry duplicated at current time",
                duration = SnackbarDuration.Short
            )
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
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

            if (items.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "No entries yet",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            } else {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(
                        items = items,
                        key = { item ->
                            when (item) {
                                is DiaryItem.Diet     -> "diet-${item.entry.id}"
                                is DiaryItem.Exercise -> "exercise-${item.entry.id}"
                                is DiaryItem.Note     -> "note-${item.entry.id}"
                                is DiaryItem.Bm       -> "bm-${item.entry.id}"
                                is DiaryItem.Bp       -> "bp-${item.entry.id}"
                                is DiaryItem.Weight   -> "weight-${item.entry.id}"
                                is DiaryItem.Body     -> "body-${item.entry.id}"
                                is DiaryItem.Habit    -> "habit-${item.entry.id}"
                            }
                        }
                    ) { item ->
                        SwipeToDeleteRow(
                            item = item,
                            onDelete = { onDeleteItem(item) },
                            onDuplicate = { onDuplicateItem(item) },
                            modifier = Modifier.animateItem()
                        )
                    }
                }
            }
        }

        FloatingActionButton(
            onClick = { showAddDialog = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Add food entry")
        }

        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 72.dp)   // clear the FAB
        )
    }

    if (showAddDialog) {
        AddDietEntryDialog(
            onDismiss = { showAddDialog = false },
            onConfirm = { name, photoPath ->
                viewModel.addDietEntry(name, photoPath)
                showAddDialog = false
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeToDeleteRow(
    item: DiaryItem,
    onDelete: () -> Unit,
    onDuplicate: () -> Unit,
    modifier: Modifier = Modifier
) {
    val currentOnDelete by rememberUpdatedState(onDelete)
    val currentOnDuplicate by rememberUpdatedState(onDuplicate)

    val dismissState = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            when (value) {
                // swipe left → delete: confirm so the row leaves the list (the DB update removes it)
                SwipeToDismissBoxValue.EndToStart -> { currentOnDelete(); true }
                // swipe right → duplicate at current time, then snap back (original stays)
                SwipeToDismissBoxValue.StartToEnd -> { currentOnDuplicate(); false }
                else -> false
            }
        }
    )

    SwipeToDismissBox(
        state = dismissState,
        enableDismissFromStartToEnd = true,
        enableDismissFromEndToStart = true,
        modifier = modifier,
        backgroundContent = {
            when (dismissState.dismissDirection) {
                SwipeToDismissBoxValue.StartToEnd -> Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(MaterialTheme.colorScheme.primaryContainer)
                        .padding(start = 20.dp),
                    contentAlignment = Alignment.CenterStart
                ) {
                    Icon(
                        imageVector = Icons.Default.ContentCopy,
                        contentDescription = "Duplicate at current time",
                        tint = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
                else -> Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(MaterialTheme.colorScheme.errorContainer)
                        .padding(end = 20.dp),
                    contentAlignment = Alignment.CenterEnd
                ) {
                    Icon(
                        imageVector = Icons.Default.Delete,
                        contentDescription = "Delete",
                        tint = MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }
        }
    ) {
        // Surface background is required — without it the red errorContainer
        // bleeds through wherever the content has transparent areas (e.g. below images).
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
        ) {
            DiaryItemRow(item)
            HorizontalDivider()
        }
    }
}

@Composable
private fun DiaryItemRow(item: DiaryItem) {
    // Always call remember unconditionally to satisfy Compose rules
    val noteBlocks = remember(item) {
        if (item is DiaryItem.Note) item.entry.content.toNoteBlocks() else emptyList()
    }

    Column {
        ListItem(
            headlineContent = {
                when (item) {
                    is DiaryItem.Diet -> Text(item.entry.name)
                    is DiaryItem.Exercise -> Text(item.entry.videoName)
                    is DiaryItem.Note -> Text(item.entry.title)
                    is DiaryItem.Bm -> Text("BM #${item.entry.bmNumber}")
                    is DiaryItem.Bp -> Text("BP ${item.entry.systolic}/${item.entry.diastolic}")
                    is DiaryItem.Weight -> Text("Weight ${item.entry.weightKg} kg")
                    is DiaryItem.Body -> Text("Body measurement")
                    is DiaryItem.Habit -> Text(item.entry.habitName)
                }
            },
            supportingContent = {
                when (item) {
                    is DiaryItem.Diet -> null
                    is DiaryItem.Exercise -> Text("${item.entry.durationSeconds}s exercise")
                    is DiaryItem.Note -> {
                        val preview = noteBlocks
                            .filterIsInstance<NoteBlock.Text>()
                            .firstOrNull()?.text?.take(120) ?: ""
                        if (preview.isNotBlank()) Text(preview, maxLines = 2)
                    }
                    is DiaryItem.Bm -> {
                        if (item.entry.notes.isNotBlank()) Text(item.entry.notes, maxLines = 2)
                        else null
                    }
                    is DiaryItem.Bp -> {
                        if (item.entry.notes.isNotBlank()) Text(item.entry.notes, maxLines = 2)
                        else null
                    }
                    is DiaryItem.Weight -> {
                        if (item.entry.notes.isNotBlank()) Text(item.entry.notes, maxLines = 2)
                        else null
                    }
                    is DiaryItem.Body -> {
                        val parts = buildList {
                            item.entry.waistCm?.let { add("Waist ${it} cm") }
                            item.entry.hipsCm?.let { add("Hips ${it} cm") }
                            item.entry.neckCm?.let { add("Neck ${it} cm") }
                            item.entry.bodyFatPct?.let { add("Body fat ${it}%") }
                        }
                        val summary = parts.joinToString(" · ")
                        if (summary.isNotBlank()) Text(summary, maxLines = 2)
                        else null
                    }
                    is DiaryItem.Habit -> Text("Habit completed")
                }
            },
            leadingContent = {
                val icon = when (item) {
                    is DiaryItem.Diet -> Icons.Default.Restaurant
                    is DiaryItem.Exercise -> Icons.Default.PlayArrow
                    is DiaryItem.Note -> Icons.Default.Create
                    is DiaryItem.Bm -> Icons.Default.FormatListNumbered
                    is DiaryItem.Bp -> Icons.Default.Favorite
                    is DiaryItem.Weight -> Icons.Default.MonitorWeight
                    is DiaryItem.Body -> Icons.Default.Straighten
                    is DiaryItem.Habit -> Icons.Default.CheckCircle
                }
                Icon(icon, contentDescription = null)
            }
        )

        // Food photo
        if (item is DiaryItem.Diet && !item.entry.photoPath.isNullOrEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                contentAlignment = Alignment.Center
            ) {
                AsyncFileImage(
                    path = item.entry.photoPath,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                )
            }
        }

        // First image from note entry
        if (item is DiaryItem.Note) {
            noteBlocks.filterIsInstance<NoteBlock.Image>().firstOrNull()?.let { block ->
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    contentAlignment = Alignment.Center
                ) {
                    AsyncFileImage(
                        path = block.path,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                    )
                }
            }
        }
    }
}

@Composable
private fun AsyncFileImage(path: String, modifier: Modifier = Modifier) {
    val bitmap by produceState<ImageBitmap?>(null, path) {
        value = withContext(Dispatchers.IO) {
            runCatching { BitmapFactory.decodeFile(path)?.asImageBitmap() }.getOrNull()
        }
    }
    if (bitmap != null) {
        Image(
            bitmap = bitmap!!,
            contentDescription = null,
            modifier = modifier,
            contentScale = ContentScale.FillWidth
        )
    }
}

@Composable
private fun AddDietEntryDialog(
    onDismiss: () -> Unit,
    onConfirm: (String, String?) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var photoPath by remember { mutableStateOf<String?>(null) }

    // Prepare a file for camera capture
    val photoFile = remember {
        File(context.filesDir, "food_images/${UUID.randomUUID()}.jpg")
            .also { it.parentFile?.mkdirs() }
    }
    val photoUri = remember {
        FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", photoFile)
    }

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) {
            scope.launch(Dispatchers.IO) {
                processAndSaveImage(photoFile)
                withContext(Dispatchers.Main) { photoPath = photoFile.absolutePath }
            }
        }
    }

    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        uri?.let {
            scope.launch(Dispatchers.IO) {
                val dest = File(context.filesDir, "food_images/${UUID.randomUUID()}.jpg")
                    .also { f -> f.parentFile?.mkdirs() }
                context.contentResolver.openInputStream(uri)?.use { it.copyTo(dest.outputStream()) }
                processAndSaveImage(dest)
                withContext(Dispatchers.Main) { photoPath = dest.absolutePath }
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Food Entry") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Food name") },
                    singleLine = true
                )
                if (photoPath != null) {
                    Box {
                        AsyncFileImage(
                            path = photoPath!!,
                            modifier = Modifier.fillMaxWidth().heightIn(max = 180.dp)
                        )
                        IconButton(
                            onClick = { photoPath = null },
                            modifier = Modifier.align(Alignment.TopEnd)
                        ) {
                            Icon(Icons.Default.Close, contentDescription = "Remove photo")
                        }
                    }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { cameraLauncher.launch(photoUri) },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(Icons.Default.CameraAlt, contentDescription = null,
                                modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Camera")
                        }
                        OutlinedButton(
                            onClick = { galleryLauncher.launch("image/*") },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(Icons.Default.Photo, contentDescription = null,
                                modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Gallery")
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { if (name.isNotBlank()) onConfirm(name, photoPath) },
                enabled = name.isNotBlank()
            ) { Text("Add") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

// ── Image processing ──────────────────────────────────────────────────────────

private const val MAX_IMAGE_DIM = 1280  // longest side in pixels after processing

/**
 * Reads EXIF rotation, rotates the bitmap to the correct orientation,
 * scales it down so neither dimension exceeds MAX_IMAGE_DIM, then
 * overwrites the file at JPEG 85 % quality.
 */
private fun processAndSaveImage(file: File) {
    try {
        val rotation = readExifRotation(file.absolutePath)
        val sampleSize = calculateInSampleSize(file.absolutePath, MAX_IMAGE_DIM)

        val decodeOpts = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        var bmp = BitmapFactory.decodeFile(file.absolutePath, decodeOpts) ?: return

        // Rotate to match EXIF orientation
        if (rotation != 0f) {
            val rotated = Bitmap.createBitmap(
                bmp, 0, 0, bmp.width, bmp.height,
                Matrix().apply { postRotate(rotation) }, true
            )
            bmp.recycle()
            bmp = rotated
        }

        // Scale down if either dimension still exceeds the limit
        val scale = MAX_IMAGE_DIM.toFloat() / maxOf(bmp.width, bmp.height)
        if (scale < 1f) {
            val scaled = Bitmap.createScaledBitmap(
                bmp, (bmp.width * scale).toInt(), (bmp.height * scale).toInt(), true
            )
            bmp.recycle()
            bmp = scaled
        }

        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 85, it) }
        bmp.recycle()
    } catch (_: Exception) { }
}

private fun readExifRotation(path: String): Float = try {
    when (ExifInterface(path).getAttributeInt(
        ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL
    )) {
        ExifInterface.ORIENTATION_ROTATE_90  -> 90f
        ExifInterface.ORIENTATION_ROTATE_180 -> 180f
        ExifInterface.ORIENTATION_ROTATE_270 -> 270f
        else -> 0f
    }
} catch (_: Exception) { 0f }

private fun calculateInSampleSize(path: String, maxDim: Int): Int {
    val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(path, opts)
    var sample = 1
    while (opts.outWidth / (sample * 2) >= maxDim || opts.outHeight / (sample * 2) >= maxDim) {
        sample *= 2
    }
    return sample
}
