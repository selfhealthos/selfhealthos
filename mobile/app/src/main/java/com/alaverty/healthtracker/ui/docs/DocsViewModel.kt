package com.alaverty.healthtracker.ui.docs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alaverty.healthtracker.data.local.entity.DocEntry
import com.alaverty.healthtracker.data.repository.HealthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId
import javax.inject.Inject

@HiltViewModel
class DocsViewModel @Inject constructor(
    private val repository: HealthRepository
) : ViewModel() {

    val docs: StateFlow<List<DocEntry>> = repository.getAllDocs()
        .stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())

    fun addDoc(title: String, tags: String, photoPath: String, documentDate: LocalDate) {
        val timestamp = documentDate.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
        viewModelScope.launch {
            repository.insertDoc(
                DocEntry(
                    title = title.trim(),
                    tags = tags,
                    photoPath = photoPath,
                    timestamp = timestamp
                )
            )
        }
    }

    fun deleteDoc(entry: DocEntry) {
        viewModelScope.launch { repository.deleteDoc(entry) }
    }

    fun undoDelete(entry: DocEntry) {
        viewModelScope.launch { repository.insertDoc(entry) }
    }
}
