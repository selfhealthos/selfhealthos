package com.alaverty.healthtracker.ui.notes

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.PersonalNote
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID
import javax.inject.Inject

data class EditorState(
    val noteId: String? = null,
    val blocks: List<NoteBlock> = listOf(NoteBlock.Text(""))
)

@HiltViewModel
class NotesViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val repository: HealthRepository
) : ViewModel() {

    val notes = repository.getAllNotes()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _editor = MutableStateFlow<EditorState?>(null)
    val editor = _editor.asStateFlow()

    fun openNewNote() {
        _editor.value = EditorState()
    }

    fun openNote(note: PersonalNote) {
        _editor.value = EditorState(
            noteId = note.id,
            blocks = note.content.toNoteBlocks()
        )
    }

    fun closeEditor() {
        _editor.value = null
    }

    fun updateTextBlock(index: Int, text: String) {
        _editor.update { state ->
            state?.copy(blocks = state.blocks.toMutableList().also { it[index] = NoteBlock.Text(text) })
        }
    }

    fun addImageBlock(uri: Uri) {
        viewModelScope.launch {
            val path = withContext(Dispatchers.IO) { copyImageToAppStorage(uri) } ?: return@launch
            _editor.update { state ->
                state?.copy(
                    blocks = state.blocks + NoteBlock.Image(path) + NoteBlock.Text("")
                )
            }
        }
    }

    fun deleteBlock(index: Int) {
        _editor.update { state ->
            if (state == null) return@update null
            val newBlocks = state.blocks.toMutableList().also { it.removeAt(index) }
            state.copy(blocks = newBlocks.ifEmpty { listOf(NoteBlock.Text("")) })
        }
    }

    fun saveNote() {
        val state = _editor.value ?: return
        viewModelScope.launch {
            repository.insertNote(
                PersonalNote(
                    id = state.noteId ?: UUID.randomUUID().toString(),
                    title = state.blocks.extractTitle(),
                    content = state.blocks.toJson(),
                    timestamp = System.currentTimeMillis()
                )
            )
            _editor.value = null
        }
    }

    fun deleteNote(note: PersonalNote) {
        viewModelScope.launch { repository.deleteNote(note) }
    }

    private fun copyImageToAppStorage(uri: Uri): String? = try {
        val dir = File(context.filesDir, "note_images").also { it.mkdirs() }
        val dest = File(dir, "${UUID.randomUUID()}.jpg")
        context.contentResolver.openInputStream(uri)?.use { it.copyTo(dest.outputStream()) }
        dest.absolutePath
    } catch (_: Exception) { null }
}
