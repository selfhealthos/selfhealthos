package com.alaverty.healthtracker.ui.notes

import org.json.JSONArray
import org.json.JSONObject

sealed class NoteBlock {
    data class Text(val text: String) : NoteBlock()
    data class Image(val path: String) : NoteBlock()
}

fun List<NoteBlock>.toJson(): String {
    val array = JSONArray()
    forEach { block ->
        val obj = JSONObject()
        when (block) {
            is NoteBlock.Text -> { obj.put("t", "text"); obj.put("v", block.text) }
            is NoteBlock.Image -> { obj.put("t", "image"); obj.put("v", block.path) }
        }
        array.put(obj)
    }
    return array.toString()
}

fun String.toNoteBlocks(): List<NoteBlock> = try {
    val array = JSONArray(this)
    (0 until array.length()).mapNotNull { i ->
        val obj = array.getJSONObject(i)
        when (obj.getString("t")) {
            "text" -> NoteBlock.Text(obj.getString("v"))
            "image" -> NoteBlock.Image(obj.getString("v"))
            else -> null
        }
    }
} catch (_: Exception) {
    listOf(NoteBlock.Text(this)) // handle legacy plain-text notes
}

fun List<NoteBlock>.extractTitle(): String =
    filterIsInstance<NoteBlock.Text>()
        .firstOrNull()?.text
        ?.take(60)?.trim()
        ?.ifBlank { "Note" } ?: "Note"
