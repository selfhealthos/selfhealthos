package com.alaverty.healthtracker.ui.notes

import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun NotesScreen(viewModel: NotesViewModel = hiltViewModel()) {
    val notes by viewModel.notes.collectAsState()
    val editor by viewModel.editor.collectAsState()

    if (editor != null) {
        NoteEditorScreen(
            state = editor!!,
            onUpdateText = viewModel::updateTextBlock,
            onAddImage = viewModel::addImageBlock,
            onDeleteBlock = viewModel::deleteBlock,
            onSave = viewModel::saveNote,
            onBack = viewModel::closeEditor
        )
    } else {
        NotesListScreen(
            notes = notes,
            onNewNote = viewModel::openNewNote,
            onOpenNote = viewModel::openNote,
            onDeleteNote = viewModel::deleteNote
        )
    }
}

@Composable
private fun NotesListScreen(
    notes: List<com.alaverty.healthtracker.data.local.entity.PersonalNote>,
    onNewNote: () -> Unit,
    onOpenNote: (com.alaverty.healthtracker.data.local.entity.PersonalNote) -> Unit,
    onDeleteNote: (com.alaverty.healthtracker.data.local.entity.PersonalNote) -> Unit
) {
    val dateFormat = remember { SimpleDateFormat("MMM d, yyyy · HH:mm", Locale.getDefault()) }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = onNewNote) {
                Icon(Icons.Default.Add, contentDescription = "New note")
            }
        }
    ) { padding ->
        if (notes.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("No notes yet. Tap + to write your first entry.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                itemsIndexed(notes, key = { _, n -> n.id }) { _, note ->
                    val blocks = remember(note.content) { note.content.toNoteBlocks() }

                    Card(
                        onClick = { onOpenNote(note) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column {
                            // Header: date + delete
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(start = 16.dp, top = 8.dp, end = 4.dp, bottom = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = dateFormat.format(Date(note.timestamp)),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.weight(1f)
                                )
                                IconButton(onClick = { onDeleteNote(note) }) {
                                    Icon(Icons.Default.Delete, contentDescription = "Delete",
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }

                            // Render all blocks inline
                            blocks.forEach { block ->
                                when (block) {
                                    is NoteBlock.Text -> if (block.text.isNotBlank()) {
                                        Text(
                                            text = block.text,
                                            style = MaterialTheme.typography.bodyMedium,
                                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                                        )
                                    }
                                    is NoteBlock.Image -> AsyncFileImage(
                                        path = block.path,
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(vertical = 4.dp)
                                    )
                                }
                            }

                            Spacer(Modifier.height(8.dp))
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NoteEditorScreen(
    state: EditorState,
    onUpdateText: (Int, String) -> Unit,
    onAddImage: (android.net.Uri) -> Unit,
    onDeleteBlock: (Int) -> Unit,
    onSave: () -> Unit,
    onBack: () -> Unit
) {
    BackHandler { onBack() }

    val imagePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri -> uri?.let { onAddImage(it) } }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("New Entry") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    TextButton(onClick = onSave) {
                        Text("Save", style = MaterialTheme.typography.labelLarge)
                    }
                }
            )
        },
        bottomBar = {
            BottomAppBar(
                containerColor = MaterialTheme.colorScheme.surface,
                tonalElevation = 4.dp
            ) {
                TextButton(
                    onClick = { imagePicker.launch("image/*") },
                    modifier = Modifier.padding(horizontal = 8.dp)
                ) {
                    Icon(Icons.Default.AddPhotoAlternate, contentDescription = null,
                        modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Add Photo")
                }
            }
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(bottom = 32.dp)
        ) {
            itemsIndexed(state.blocks) { index, block ->
                when (block) {
                    is NoteBlock.Text -> TextBlockView(
                        text = block.text,
                        isFirst = index == 0,
                        onTextChange = { onUpdateText(index, it) }
                    )
                    is NoteBlock.Image -> ImageBlockView(
                        path = block.path,
                        onDelete = { onDeleteBlock(index) }
                    )
                }
            }
        }
    }
}

@Composable
private fun TextBlockView(text: String, isFirst: Boolean, onTextChange: (String) -> Unit) {
    val textColor = MaterialTheme.colorScheme.onSurface
    val hintColor = MaterialTheme.colorScheme.onSurfaceVariant
    val style = MaterialTheme.typography.bodyLarge.copy(color = textColor)

    BasicTextField(
        value = text,
        onValueChange = onTextChange,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        textStyle = style,
        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
        decorationBox = { innerTextField ->
            if (text.isEmpty()) {
                Text(
                    text = if (isFirst) "Write about your day..." else "Add more text...",
                    style = style.copy(color = hintColor)
                )
            }
            innerTextField()
        }
    )
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
    } else {
        Box(modifier = modifier.height(180.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
    }
}

@Composable
private fun ImageBlockView(path: String, onDelete: () -> Unit) {
    Box(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        AsyncFileImage(path = path, modifier = Modifier.fillMaxWidth())
        IconButton(
            onClick = onDelete,
            modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
        ) {
            Surface(
                shape = MaterialTheme.shapes.extraLarge,
                color = Color.Black.copy(alpha = 0.5f)
            ) {
                Icon(
                    Icons.Default.Close,
                    contentDescription = "Remove photo",
                    tint = Color.White,
                    modifier = Modifier.padding(4.dp).size(16.dp)
                )
            }
        }
    }
}
