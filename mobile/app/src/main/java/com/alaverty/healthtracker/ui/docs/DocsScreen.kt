package com.alaverty.healthtracker.ui.docs

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import com.alaverty.healthtracker.data.local.entity.DocEntry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.UUID

@Composable
fun DocsScreen(viewModel: DocsViewModel = hiltViewModel()) {
    val docs by viewModel.docs.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }
    var viewingDoc by remember { mutableStateOf<DocEntry?>(null) }
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    fun onDelete(doc: DocEntry) {
        viewModel.deleteDoc(doc)
        scope.launch {
            val result = snackbarHostState.showSnackbar(
                message = "Document deleted",
                actionLabel = "Undo",
                duration = SnackbarDuration.Short
            )
            if (result == SnackbarResult.ActionPerformed) {
                viewModel.undoDelete(doc)
            }
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        if (docs.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "No documents yet",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(items = docs, key = { it.id }) { doc ->
                    DocRow(
                        doc = doc,
                        onClick = { viewingDoc = doc },
                        onDelete = { onDelete(doc) },
                        modifier = Modifier.animateItem()
                    )
                }
            }
        }

        FloatingActionButton(
            onClick = { showAddDialog = true },
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp)
        ) {
            Icon(Icons.Default.Add, contentDescription = "Add document")
        }

        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 72.dp)
        )
    }

    if (showAddDialog) {
        AddDocDialog(
            onDismiss = { showAddDialog = false },
            onConfirm = { title, tags, photoPath, date ->
                viewModel.addDoc(title, tags, photoPath, date)
                showAddDialog = false
            }
        )
    }

    viewingDoc?.let { doc ->
        DocImageDialog(doc = doc, onDismiss = { viewingDoc = null })
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DocRow(
    doc: DocEntry,
    onClick: () -> Unit,
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
        state = dismissState,
        enableDismissFromStartToEnd = false,
        modifier = modifier,
        backgroundContent = {
            Box(
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
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .clickable { onClick() }
        ) {
            val date = Instant.ofEpochMilli(doc.timestamp)
                .atZone(ZoneId.systemDefault())
                .toLocalDate()
            val tagDisplay = doc.tags
                .split(",")
                .map { it.trim() }
                .filter { it.isNotBlank() }
                .joinToString("  ") { "#$it" }

            ListItem(
                headlineContent = { Text(doc.title) },
                supportingContent = {
                    if (tagDisplay.isNotBlank()) {
                        Text(
                            text = tagDisplay,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                },
                trailingContent = {
                    Text(
                        text = date.format(DateTimeFormatter.ofPattern("MMM d, yyyy")),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                },
                leadingContent = {
                    Icon(Icons.Default.Article, contentDescription = null)
                }
            )
            HorizontalDivider()
        }
    }
}

@Composable
private fun DocImageDialog(doc: DocEntry, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(doc.title, style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f))
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }

                val tagDisplay = doc.tags
                    .split(",")
                    .map { it.trim() }
                    .filter { it.isNotBlank() }
                    .joinToString("  ") { "#$it" }
                if (tagDisplay.isNotBlank()) {
                    Text(
                        text = tagDisplay,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                }

                AsyncDocImage(
                    path = doc.photoPath,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddDocDialog(
    onDismiss: () -> Unit,
    onConfirm: (title: String, tags: String, photoPath: String, date: LocalDate) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var title by remember { mutableStateOf("") }
    var tagsInput by remember { mutableStateOf("") }
    var photoPath by remember { mutableStateOf<String?>(null) }
    var selectedDate by remember { mutableStateOf(LocalDate.now()) }
    var showDatePicker by remember { mutableStateOf(false) }

    val photoFile = remember {
        File(context.filesDir, "doc_images/${UUID.randomUUID()}.jpg")
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
                processDocImage(photoFile)
                withContext(Dispatchers.Main) { photoPath = photoFile.absolutePath }
            }
        }
    }

    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        uri?.let {
            scope.launch(Dispatchers.IO) {
                val dest = File(context.filesDir, "doc_images/${UUID.randomUUID()}.jpg")
                    .also { f -> f.parentFile?.mkdirs() }
                context.contentResolver.openInputStream(uri)?.use { stream ->
                    stream.copyTo(dest.outputStream())
                }
                processDocImage(dest)
                withContext(Dispatchers.Main) { photoPath = dest.absolutePath }
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Document") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Title") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = tagsInput,
                    onValueChange = { tagsInput = it },
                    label = { Text("Tags (comma-separated)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedButton(
                    onClick = { showDatePicker = true },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        Icons.Default.CalendarToday,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(selectedDate.format(DateTimeFormatter.ofPattern("MMM d, yyyy")))
                }
                if (photoPath != null) {
                    Box {
                        AsyncDocImage(
                            path = photoPath!!,
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(max = 200.dp)
                                .clip(RoundedCornerShape(8.dp))
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
                            Icon(
                                Icons.Default.CameraAlt,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(Modifier.width(4.dp))
                            Text("Camera")
                        }
                        OutlinedButton(
                            onClick = { galleryLauncher.launch("image/*") },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(
                                Icons.Default.Photo,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(Modifier.width(4.dp))
                            Text("Gallery")
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    photoPath?.let { path ->
                        if (title.isNotBlank()) onConfirm(title, tagsInput, path, selectedDate)
                    }
                },
                enabled = title.isNotBlank() && photoPath != null
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )

    if (showDatePicker) {
        val initialMs = selectedDate.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
        val datePickerState = rememberDatePickerState(initialSelectedDateMillis = initialMs)
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    datePickerState.selectedDateMillis?.let { ms ->
                        selectedDate = Instant.ofEpochMilli(ms)
                            .atZone(ZoneOffset.UTC)
                            .toLocalDate()
                    }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("Cancel") }
            }
        ) {
            DatePicker(state = datePickerState)
        }
    }
}

@Composable
private fun AsyncDocImage(path: String, modifier: Modifier = Modifier) {
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

private const val DOC_MAX_DIM = 1280

private fun processDocImage(file: File) {
    try {
        val rotation = readDocExifRotation(file.absolutePath)
        val sampleSize = calcDocSampleSize(file.absolutePath, DOC_MAX_DIM)
        val opts = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        var bmp = BitmapFactory.decodeFile(file.absolutePath, opts) ?: return

        if (rotation != 0f) {
            val rotated = Bitmap.createBitmap(
                bmp, 0, 0, bmp.width, bmp.height,
                Matrix().apply { postRotate(rotation) }, true
            )
            bmp.recycle()
            bmp = rotated
        }

        val scale = DOC_MAX_DIM.toFloat() / maxOf(bmp.width, bmp.height)
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

private fun readDocExifRotation(path: String): Float = try {
    when (ExifInterface(path).getAttributeInt(
        ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL
    )) {
        ExifInterface.ORIENTATION_ROTATE_90  -> 90f
        ExifInterface.ORIENTATION_ROTATE_180 -> 180f
        ExifInterface.ORIENTATION_ROTATE_270 -> 270f
        else -> 0f
    }
} catch (_: Exception) { 0f }

private fun calcDocSampleSize(path: String, maxDim: Int): Int {
    val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(path, opts)
    var sample = 1
    while (opts.outWidth / (sample * 2) >= maxDim || opts.outHeight / (sample * 2) >= maxDim) {
        sample *= 2
    }
    return sample
}
