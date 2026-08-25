package com.alaverty.healthtracker.data.github

import android.util.Base64
import com.alaverty.healthtracker.data.repository.HealthRepository
import com.alaverty.healthtracker.ui.notes.NoteBlock
import com.alaverty.healthtracker.ui.notes.toNoteBlocks
import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GitHubExportService @Inject constructor(
    private val repository: HealthRepository,
    private val api: GitHubApiService
) {
    private val gson = Gson()

    suspend fun export(
        githubRepo: String,
        githubToken: String,
        syncAll: Boolean,
        syncDays: Int,
        onProgress: (String) -> Unit
    ): Result<String> = runCatching {
        val parts = githubRepo.trim().split("/")
        require(parts.size == 2 && parts.all { it.isNotBlank() }) {
            "Repository must be in owner/repo format"
        }
        val (owner, repo) = parts
        val auth = "Bearer ${githubToken.trim()}"
        val zone = ZoneId.systemDefault()

        val today = LocalDate.now()
        val startDate = if (syncAll) LocalDate.of(2020, 1, 1) else today.minusDays(syncDays.toLong() - 1)

        onProgress("Loading entries from device…")

        val allDiet             = repository.getDietEntriesForRange(startDate, today)
        val allExercise         = repository.getExerciseEntriesForRange(startDate, today)
        val allNotes            = repository.getNotesForRange(startDate, today)
        val allBm               = repository.getBmEntriesForRange(startDate, today)
        val allBp               = repository.getBpEntriesForRange(startDate, today)
        val allWeight           = repository.getWeightEntriesForRange(startDate, today)
        val allHabitCompletions = repository.getHabitCompletionsForRange(startDate, today)
        val unsyncedDocs        = repository.getUnsyncedDocs()
        val allGymSets          = repository.getGymSetsForRange(startDate, today)

        fun Long.toDate() = Instant.ofEpochMilli(this).atZone(zone).toLocalDate()

        val dietByDate              = allDiet.groupBy             { it.timestamp.toDate() }
        val exerciseByDate          = allExercise.groupBy         { it.timestamp.toDate() }
        val notesByDate             = allNotes.groupBy            { it.timestamp.toDate() }
        val bmByDate                = allBm.groupBy               { it.timestamp.toDate() }
        val bpByDate                = allBp.groupBy               { it.timestamp.toDate() }
        val weightByDate            = allWeight.groupBy           { it.timestamp.toDate() }
        val habitCompletionsByDate  = allHabitCompletions.groupBy { LocalDate.parse(it.date) }
        val unsyncedDocsByDate      = unsyncedDocs.groupBy        { it.timestamp.toDate() }
        val gymSetsByDate           = allGymSets.groupBy          { LocalDate.parse(it.date) }

        val allDates = (dietByDate.keys + exerciseByDate.keys + notesByDate.keys +
                bmByDate.keys + bpByDate.keys + weightByDate.keys +
                habitCompletionsByDate.keys + unsyncedDocsByDate.keys +
                gymSetsByDate.keys).toSortedSet()

        var totalEntries = 0

        allDates.forEachIndexed { idx, date ->
            val dateStr = "%d/%02d/%02d".format(date.year, date.monthValue, date.dayOfMonth)
            onProgress("Syncing $dateStr (${idx + 1}/${allDates.size})…")
            val base = "data/$dateStr"

            dietByDate[date]?.also     { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/diet.ndjson",     it) }
            exerciseByDate[date]?.also { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/exercise.ndjson", it) }
            notesByDate[date]?.also    { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/notes.ndjson",    it) }
            bmByDate[date]?.also       { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/bm.ndjson",       it) }
            bpByDate[date]?.also       { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/bp.ndjson",       it) }
            weightByDate[date]?.also          { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/weight.ndjson",           it) }
            habitCompletionsByDate[date]?.also { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/habit_completions.ndjson", it) }
            gymSetsByDate[date]?.also          { totalEntries += it.size; syncNdjson(auth, owner, repo, "$base/gym_sets.ndjson",           it) }

            unsyncedDocsByDate[date]?.also { dateDocs ->
                totalEntries += dateDocs.size
                syncNdjson(auth, owner, repo, "$base/docs.ndjson", dateDocs)
                dateDocs.forEach { entry ->
                    uploadImage(auth, owner, repo, entry.photoPath, "$base/docs/${File(entry.photoPath).name}")
                }
                repository.markDocsSynced(dateDocs.map { it.id })
            }

            // Images: diet photos
            dietByDate[date]?.forEach { entry ->
                entry.photoPath?.let { uploadImage(auth, owner, repo, it, "$base/images/${File(it).name}") }
            }

            // Images: note inline images
            notesByDate[date]?.forEach { note ->
                note.content.toNoteBlocks()
                    .filterIsInstance<NoteBlock.Image>()
                    .forEach { block ->
                        uploadImage(auth, owner, repo, block.path, "$base/images/${File(block.path).name}")
                    }
            }
        }

        // Habit definitions are not date-scoped — export to data/habits.ndjson
        val allHabits = repository.getAllHabitsSnapshot()
        if (allHabits.isNotEmpty()) {
            onProgress("Syncing habit definitions…")
            syncNdjson(auth, owner, repo, "data/habits.ndjson", allHabits)
        }

        // Gym exercise definitions are not date-scoped — export to data/gym_exercises.ndjson
        val allGymExercises = repository.getAllGymExercisesSnapshot()
        if (allGymExercises.isNotEmpty()) {
            onProgress("Syncing gym exercises…")
            syncNdjson(auth, owner, repo, "data/gym_exercises.ndjson", allGymExercises)
        }

        // WFH office days are not date-scoped — export the full set to data/wfh.ndjson.
        // Replace rather than merge so unticked (locally deleted) days disappear remotely.
        val allWfh = repository.getAllWfhEntriesSnapshot()
        if (allWfh.isNotEmpty()) {
            onProgress("Syncing WFH days…")
            totalEntries += allWfh.size
            syncNdjson(auth, owner, repo, "data/wfh.ndjson", allWfh, replaceRemote = true)
        }

        // Sparse full-snapshot types — root files, replaced on every export so deletes propagate
        val allLabs = repository.getAllLabResultsSnapshot()
        if (allLabs.isNotEmpty()) {
            onProgress("Syncing lab results…")
            totalEntries += allLabs.size
            syncNdjson(auth, owner, repo, "data/labs.ndjson", allLabs, replaceRemote = true)
        }

        val allMeasurements = repository.getAllBodyMeasurementsSnapshot()
        if (allMeasurements.isNotEmpty()) {
            onProgress("Syncing body measurements…")
            totalEntries += allMeasurements.size
            syncNdjson(auth, owner, repo, "data/body_measurements.ndjson", allMeasurements, replaceRemote = true)
        }

        val allFitnessTests = repository.getAllFitnessTestsSnapshot()
        if (allFitnessTests.isNotEmpty()) {
            onProgress("Syncing fitness tests…")
            totalEntries += allFitnessTests.size
            syncNdjson(auth, owner, repo, "data/fitness_tests.ndjson", allFitnessTests, replaceRemote = true)
        }

        "Exported $totalEntries entries across ${allDates.size} days"
    }

    private suspend fun syncNdjson(
        auth: String, owner: String, repo: String,
        filePath: String,
        localEntries: List<Any>,
        replaceRemote: Boolean = false
    ) {
        // Fetch existing file (may 404 on first sync)
        val getResponse = runCatching { api.getFile(auth, owner, repo, filePath) }.getOrNull()
        val existingSha: String?
        val remoteById: MutableMap<String, JsonObject>

        if (getResponse?.isSuccessful == true && getResponse.body() != null) {
            val body = getResponse.body()!!
            existingSha = body.sha
            // replaceRemote: local entries are the complete dataset, so drop remote
            // lines instead of merging — this lets local deletions propagate.
            remoteById = if (replaceRemote) mutableMapOf() else {
                val decoded = Base64.decode(body.content.replace("\n", ""), Base64.DEFAULT)
                    .toString(Charsets.UTF_8)
                decoded.lines()
                    .filter { it.isNotBlank() }
                    .mapNotNull { runCatching { gson.fromJson(it, JsonObject::class.java) }.getOrNull() }
                    .associateByTo(mutableMapOf()) { it.get("id").asString }
            }
        } else {
            existingSha = null
            remoteById = mutableMapOf()
        }

        // Merge: newest updatedAt wins for same ID
        for (entry in localEntries) {
            val json = gson.toJsonTree(entry).asJsonObject
            val id = json.get("id").asString
            val updatedAt = json.get("updatedAt")?.asLong ?: 0L
            val remote = remoteById[id]
            if (remote == null || (remote.get("updatedAt")?.asLong ?: 0L) < updatedAt) {
                remoteById[id] = json
            }
        }

        if (remoteById.isEmpty()) return

        val ndjson = remoteById.values
            .sortedBy { it.get("timestamp")?.asLong ?: it.get("createdAt")?.asLong ?: 0L }
            .joinToString("\n") { gson.toJson(it) }
        val encoded = Base64.encodeToString(ndjson.toByteArray(Charsets.UTF_8), Base64.NO_WRAP)

        api.putFile(
            auth, owner, repo, filePath,
            GitHubPutRequest(message = "health-tracker sync", content = encoded, sha = existingSha)
        )
    }

    private suspend fun uploadImage(
        auth: String, owner: String, repo: String,
        localPath: String,
        githubPath: String
    ) {
        val file = File(localPath)
        if (!file.exists()) return

        val getResponse = runCatching { api.getFile(auth, owner, repo, githubPath) }.getOrNull()
        val existingSha = if (getResponse?.isSuccessful == true) getResponse.body()?.sha else null

        runCatching {
            val encoded = Base64.encodeToString(file.readBytes(), Base64.NO_WRAP)
            api.putFile(
                auth, owner, repo, githubPath,
                GitHubPutRequest(message = "image sync", content = encoded, sha = existingSha)
            )
        }
    }
}
