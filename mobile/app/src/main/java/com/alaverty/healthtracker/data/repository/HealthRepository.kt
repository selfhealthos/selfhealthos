package com.alaverty.healthtracker.data.repository

import android.content.Context
import com.alaverty.healthtracker.data.local.dao.*
import com.alaverty.healthtracker.data.local.entity.*
import com.alaverty.healthtracker.sync.EntrySyncWorker
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.time.LocalDate
import java.time.ZoneId
import javax.inject.Inject

class HealthRepository @Inject constructor(
    private val dietDao: DietDao,
    private val exerciseDao: ExerciseDao,
    private val noteDao: NoteDao,
    private val bmDao: BmDao,
    private val bpDao: BpDao,
    private val weightDao: WeightDao,
    private val habitDao: HabitDao,
    private val habitCompletionDao: HabitCompletionDao,
    private val docDao: DocDao,
    private val wfhDao: WfhDao,
    private val gymExerciseDao: GymExerciseDao,
    private val gymSetDao: GymSetDao,
    private val labResultDao: LabResultDao,
    private val bodyMeasurementDao: BodyMeasurementDao,
    private val fitnessTestDao: FitnessTestDao,
    private val alarmDao: AlarmDao,
    @ApplicationContext private val context: Context
) {

    /**
     * Ask for a portal sync after a local write.
     *
     * Here rather than in each ViewModel — the gym screen's own trigger
     * predates this — so that "every write asks for a sync" is structural
     * instead of something twelve ViewModels each have to remember. The
     * request is deduplicated and cheap, and the save has already succeeded
     * either way: this is best-effort, never a precondition.
     */
    private fun syncSoon() = EntrySyncWorker.requestSync(context)

    private fun dayRange(date: LocalDate): Pair<Long, Long> {
        val zone = ZoneId.systemDefault()
        val start = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val end = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return start to end
    }

    fun getDietEntriesForDay(date: LocalDate): Flow<List<DietEntry>> {
        val (start, end) = dayRange(date)
        return dietDao.getEntriesForDay(start, end)
    }

    fun getExerciseEntriesForDay(date: LocalDate): Flow<List<ExerciseEntry>> {
        val (start, end) = dayRange(date)
        return exerciseDao.getEntriesForDay(start, end)
    }

    fun getNoteEntriesForDay(date: LocalDate): Flow<List<PersonalNote>> {
        val (start, end) = dayRange(date)
        return noteDao.getEntriesForDay(start, end)
    }

    fun getAllNotes(): Flow<List<PersonalNote>> = noteDao.getAllNotes()
    fun getAllBmEntries(): Flow<List<BmEntry>> = bmDao.getAll()

    fun getBmEntriesForDay(date: LocalDate): Flow<List<BmEntry>> {
        val (start, end) = dayRange(date)
        return bmDao.getEntriesForDay(start, end)
    }
    fun getAllBpEntries(): Flow<List<BpEntry>> = bpDao.getAll()

    fun getBpEntriesForDay(date: LocalDate): Flow<List<BpEntry>> {
        val (start, end) = dayRange(date)
        return bpDao.getEntriesForDay(start, end)
    }

    fun getWeightEntriesForDay(date: LocalDate): Flow<List<WeightEntry>> {
        val (start, end) = dayRange(date)
        return weightDao.getEntriesForDay(start, end)
    }

    fun getBodyMeasurementsForDay(date: LocalDate): Flow<List<BodyMeasurement>> {
        val (start, end) = dayRange(date)
        return bodyMeasurementDao.getEntriesForDay(start, end)
    }

    suspend fun getExerciseEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<ExerciseEntry> {
        val (start, end) = rangeMs(startDate, endDate)
        return exerciseDao.getEntriesForRange(start, end)
    }

    suspend fun getDietEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<DietEntry> {
        val (start, end) = rangeMs(startDate, endDate)
        return dietDao.getEntriesForRange(start, end)
    }

    suspend fun getNotesForRange(startDate: LocalDate, endDate: LocalDate): List<PersonalNote> {
        val (start, end) = rangeMs(startDate, endDate)
        return noteDao.getEntriesForRange(start, end)
    }

    suspend fun getBmEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<BmEntry> {
        val (start, end) = rangeMs(startDate, endDate)
        return bmDao.getEntriesForRange(start, end)
    }

    suspend fun getBpEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<BpEntry> {
        val (start, end) = rangeMs(startDate, endDate)
        return bpDao.getEntriesForRange(start, end)
    }

    private fun rangeMs(startDate: LocalDate, endDate: LocalDate): Pair<Long, Long> {
        val zone = ZoneId.systemDefault()
        val start = startDate.atStartOfDay(zone).toInstant().toEpochMilli()
        val end = endDate.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return start to end
    }

    /**
     * The instant a tombstone was written. Also becomes `updatedAt`, which is
     * how the portal knows this delete is newer than the entry it replaces —
     * `client_updated_at` is the only conflict rule available without a
     * coordinator, so a delete stamped older than the row would be ignored.
     */
    private fun now() = System.currentTimeMillis()

    suspend fun insertDietEntry(entry: DietEntry) = dietDao.insert(entry).also { syncSoon() }
    suspend fun deleteDietEntry(entry: DietEntry) = dietDao.softDelete(entry.id, now()).also { syncSoon() }
    suspend fun insertExerciseEntry(entry: ExerciseEntry) = exerciseDao.insert(entry).also { syncSoon() }
    suspend fun deleteExerciseEntry(entry: ExerciseEntry) = exerciseDao.softDelete(entry.id, now()).also { syncSoon() }
    suspend fun insertNote(note: PersonalNote) = noteDao.insert(note).also { syncSoon() }
    suspend fun deleteNote(note: PersonalNote) = noteDao.softDelete(note.id, now()).also { syncSoon() }
    suspend fun insertBmEntry(entry: BmEntry) = bmDao.insert(entry).also { syncSoon() }
    suspend fun deleteBmEntry(entry: BmEntry) = bmDao.softDelete(entry.id, now()).also { syncSoon() }
    suspend fun insertBpEntry(entry: BpEntry) = bpDao.insert(entry).also { syncSoon() }
    suspend fun deleteBpEntry(entry: BpEntry) = bpDao.softDelete(entry.id, now()).also { syncSoon() }

    suspend fun getUnsyncedDietEntries() = dietDao.getUnsynced()
    suspend fun getUnsyncedExerciseEntries() = exerciseDao.getUnsynced()
    suspend fun getUnsyncedNotes() = noteDao.getUnsynced()
    suspend fun getUnsyncedBmEntries() = bmDao.getUnsynced()
    suspend fun getUnsyncedBpEntries() = bpDao.getUnsynced()

    suspend fun markDietEntriesSynced(ids: List<String>) = dietDao.markSynced(ids)
    suspend fun markExerciseEntriesSynced(ids: List<String>) = exerciseDao.markSynced(ids)
    suspend fun markNotesSynced(ids: List<String>) = noteDao.markSynced(ids)
    suspend fun markBmEntriesSynced(ids: List<String>) = bmDao.markSynced(ids)
    suspend fun markBpEntriesSynced(ids: List<String>) = bpDao.markSynced(ids)

    fun getAllWeightEntries(): Flow<List<WeightEntry>> = weightDao.getAll()
    suspend fun getWeightEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<WeightEntry> {
        val (start, end) = rangeMs(startDate, endDate)
        return weightDao.getEntriesForRange(start, end)
    }
    suspend fun insertWeightEntry(entry: WeightEntry) = weightDao.insert(entry).also { syncSoon() }
    suspend fun deleteWeightEntry(entry: WeightEntry) = weightDao.softDelete(entry.id, now()).also { syncSoon() }
    suspend fun getUnsyncedWeightEntries() = weightDao.getUnsynced()
    suspend fun markWeightEntriesSynced(ids: List<String>) = weightDao.markSynced(ids)

    // Habits
    fun getAllHabits(): Flow<List<Habit>> = habitDao.getAll()
    suspend fun getAllHabitsSnapshot(): List<Habit> = habitDao.getAllSnapshot()
    suspend fun insertHabit(habit: Habit) = habitDao.insert(habit).also { syncSoon() }
    suspend fun deleteHabit(habit: Habit) = habitDao.softDelete(habit.id, now()).also { syncSoon() }

    // Habit completions
    fun getHabitCompletionsForDate(date: String): Flow<List<HabitCompletion>> =
        habitCompletionDao.getForDate(date)
    suspend fun insertHabitCompletion(completion: HabitCompletion) =
        habitCompletionDao.insert(completion)
    suspend fun deleteHabitCompletion(habitId: String, date: String) =
        habitCompletionDao.softDeleteForHabitOnDate(habitId, date, now()).also { syncSoon() }
    suspend fun deleteHabitCompletion(completion: HabitCompletion) =
        habitCompletionDao.softDelete(completion.id, now()).also { syncSoon() }
    suspend fun getHabitCompletionsForRange(startDate: LocalDate, endDate: LocalDate): List<HabitCompletion> {
        val (start, end) = rangeMs(startDate, endDate)
        return habitCompletionDao.getForRange(start, end)
    }
    suspend fun getUnsyncedHabitCompletions() = habitCompletionDao.getUnsynced()
    suspend fun markHabitCompletionsSynced(ids: List<String>) = habitCompletionDao.markSynced(ids)

    // Docs
    fun getAllDocs(): Flow<List<DocEntry>> = docDao.getAll()
    suspend fun getAllDocsSnapshot(): List<DocEntry> = docDao.getAllSnapshot()
    suspend fun insertDoc(entry: DocEntry) = docDao.insert(entry).also { syncSoon() }
    suspend fun deleteDoc(entry: DocEntry) = docDao.softDelete(entry.id, now()).also { syncSoon() }
    suspend fun getDocEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<DocEntry> {
        val (start, end) = rangeMs(startDate, endDate)
        return docDao.getEntriesForRange(start, end)
    }
    suspend fun getUnsyncedDocs() = docDao.getUnsynced()
    suspend fun markDocsSynced(ids: List<String>) = docDao.markSynced(ids)

    // Gym
    fun getAllGymExercises(): kotlinx.coroutines.flow.Flow<List<GymExercise>> = gymExerciseDao.getAll()
    suspend fun getAllGymExercisesSnapshot(): List<GymExercise> = gymExerciseDao.getAllSnapshot()
    suspend fun getGymExerciseByName(name: String): GymExercise? = gymExerciseDao.getByName(name)
    suspend fun upsertGymExercise(exercise: GymExercise) = gymExerciseDao.upsert(exercise)

    fun getGymSetsForDate(date: String): kotlinx.coroutines.flow.Flow<List<GymSet>> =
        gymSetDao.getForDate(date)
    suspend fun getGymSetsForRange(startDate: LocalDate, endDate: LocalDate): List<GymSet> {
        val fmt = DateTimeFormatter.ISO_LOCAL_DATE
        return gymSetDao.getForRange(startDate.format(fmt), endDate.format(fmt))
    }
    suspend fun insertGymSet(set: GymSet) = gymSetDao.insert(set)

    /**
     * Tombstone the set so the deletion can reach the portal.
     *
     * Not a row removal: the server would otherwise keep the set forever,
     * still counting it toward gym volume, with nothing left on the phone to
     * say it went. `GymSetDao.getForDate` filters tombstones out, so it
     * disappears from the UI immediately either way.
     */
    suspend fun deleteGymSet(set: GymSet) =
        gymSetDao.softDelete(set.id, System.currentTimeMillis())

    /**
     * How many non-gym rows the server has not acknowledged.
     *
     * Exists because Settings previously counted only gym rows, so a screen
     * reading "Nothing waiting to sync" was true of gym and silent about a
     * fortnight of meals, gut entries and habit ticks queued behind a worker
     * that had been failing since July.
     */
    fun countUnsyncedEntries(): Flow<Int> = combine(
        dietDao.countUnsynced(), exerciseDao.countUnsynced(), noteDao.countUnsynced(),
        bmDao.countUnsynced(), bpDao.countUnsynced(), weightDao.countUnsynced(),
        bodyMeasurementDao.countUnsynced(), fitnessTestDao.countUnsynced(),
        docDao.countUnsynced(), labResultDao.countUnsynced(), wfhDao.countUnsynced(),
        habitDao.countUnsynced(), habitCompletionDao.countUnsynced()
    ) { counts -> counts.sum() }

    suspend fun getUnsyncedGymSets() = gymSetDao.getUnsynced()
    suspend fun markGymSetsSynced(ids: List<String>) = gymSetDao.markSynced(ids)
    suspend fun purgeSyncedGymSetTombstones() = gymSetDao.purgeSyncedTombstones()
    fun countUnsyncedGymSets() = gymSetDao.countUnsynced()

    suspend fun getUnsyncedGymExercises() = gymExerciseDao.getUnsynced()
    suspend fun markGymExercisesSynced(ids: List<String>) = gymExerciseDao.markSynced(ids)
    suspend fun purgeSyncedGymExerciseTombstones() = gymExerciseDao.purgeSyncedTombstones()
    fun countUnsyncedGymExercises() = gymExerciseDao.countUnsynced()

    // WFH (office days)
    fun getWfhEntriesForMonth(yearMonth: java.time.YearMonth): kotlinx.coroutines.flow.Flow<List<WfhEntry>> {
        val prefix = yearMonth.format(DateTimeFormatter.ofPattern("yyyy-MM"))
        return wfhDao.getEntriesForMonth(prefix)
    }
    suspend fun getWfhEntriesForRange(startDate: LocalDate, endDate: LocalDate): List<WfhEntry> {
        val fmt = DateTimeFormatter.ISO_LOCAL_DATE
        return wfhDao.getEntriesForRange(startDate.format(fmt), endDate.format(fmt))
    }
    suspend fun getAllWfhEntriesSnapshot(): List<WfhEntry> = wfhDao.getAllSnapshot()
    /**
     * Mark a day as WFH, reusing that date's existing row (tombstoned or not)
     * rather than always minting a fresh id.
     *
     * `insertWfhEntry` REPLACEs by date, so toggling a day off then back on
     * before the delete syncs would swap in a new id and lose the pending
     * tombstone - the portal's old row for that day is still live under the
     * old id, and its one-row-per-day constraint rejects the new one forever
     * since the two never share a `client_id`. Reusing the id turns the re-add
     * into an edit of the row the portal already has.
     */
    suspend fun markWfhDayPresent(date: String) {
        if (wfhDao.findByDate(date) != null) wfhDao.restore(date, now())
        else wfhDao.insert(WfhEntry(date = date))
        syncSoon()
    }
    suspend fun deleteWfhEntryByDate(date: String) = wfhDao.softDeleteByDate(date, now()).also { syncSoon() }
    suspend fun getUnsyncedWfhEntries() = wfhDao.getUnsynced()
    suspend fun markWfhEntriesSynced(ids: List<String>) = wfhDao.markSynced(ids)

    // Lab results
    fun getAllLabResults(): Flow<List<LabResult>> = labResultDao.getAll()
    suspend fun getAllLabResultsSnapshot(): List<LabResult> = labResultDao.getAllSnapshot()
    suspend fun insertLabResult(result: LabResult) = labResultDao.insert(result).also { syncSoon() }
    suspend fun deleteLabResult(result: LabResult) = labResultDao.softDelete(result.id, now()).also { syncSoon() }
    suspend fun getUnsyncedLabResults() = labResultDao.getUnsynced()
    suspend fun markLabResultsSynced(ids: List<String>) = labResultDao.markSynced(ids)

    // Body measurements
    fun getAllBodyMeasurements(): Flow<List<BodyMeasurement>> = bodyMeasurementDao.getAll()
    suspend fun getAllBodyMeasurementsSnapshot(): List<BodyMeasurement> = bodyMeasurementDao.getAllSnapshot()
    suspend fun insertBodyMeasurement(measurement: BodyMeasurement) = bodyMeasurementDao.insert(measurement).also { syncSoon() }
    suspend fun deleteBodyMeasurement(measurement: BodyMeasurement) = bodyMeasurementDao.softDelete(measurement.id, now()).also { syncSoon() }
    suspend fun getUnsyncedBodyMeasurements() = bodyMeasurementDao.getUnsynced()
    suspend fun markBodyMeasurementsSynced(ids: List<String>) = bodyMeasurementDao.markSynced(ids)

    // Fitness tests
    fun getAllFitnessTests(): Flow<List<FitnessTest>> = fitnessTestDao.getAll()
    suspend fun getAllFitnessTestsSnapshot(): List<FitnessTest> = fitnessTestDao.getAllSnapshot()
    suspend fun insertFitnessTest(test: FitnessTest) = fitnessTestDao.insert(test).also { syncSoon() }
    suspend fun deleteFitnessTest(test: FitnessTest) = fitnessTestDao.softDelete(test.id, now()).also { syncSoon() }
    suspend fun getUnsyncedFitnessTests() = fitnessTestDao.getUnsynced()
    suspend fun markFitnessTestsSynced(ids: List<String>) = fitnessTestDao.markSynced(ids)

    // Alarms (device-local reminders, not part of sync)
    fun getAllAlarms(): Flow<List<AlarmEntry>> = alarmDao.getAll()
    suspend fun getAllAlarmsSnapshot(): List<AlarmEntry> = alarmDao.getAllSnapshot()
    suspend fun getEnabledAlarms(): List<AlarmEntry> = alarmDao.getEnabledSnapshot()
    suspend fun insertAlarm(alarm: AlarmEntry) = alarmDao.insert(alarm)
    suspend fun deleteAlarm(alarm: AlarmEntry) = alarmDao.delete(alarm)

    // ----------------------------------------------------------------------
    // Portal sync queue
    //
    // One block rather than scattered through each type's section: the sync
    // manager reads all of it together, and a type missing from here is a type
    // that silently never syncs.
    // ----------------------------------------------------------------------

    suspend fun getUnsyncedHabits() = habitDao.getUnsynced()
    suspend fun markHabitsSynced(ids: List<String>) = habitDao.markSynced(ids)

    /**
     * Clear tombstones the portal has acknowledged.
     *
     * Called only after a sync has marked the rows synced. Any earlier and a
     * deletion the server never received would be gone from the phone too,
     * which is the one way this design can still lose one.
     */
    suspend fun purgeSyncedEntryTombstones() {
        dietDao.purgeSyncedTombstones()
        exerciseDao.purgeSyncedTombstones()
        noteDao.purgeSyncedTombstones()
        bmDao.purgeSyncedTombstones()
        bpDao.purgeSyncedTombstones()
        weightDao.purgeSyncedTombstones()
        bodyMeasurementDao.purgeSyncedTombstones()
        fitnessTestDao.purgeSyncedTombstones()
        docDao.purgeSyncedTombstones()
        labResultDao.purgeSyncedTombstones()
        wfhDao.purgeSyncedTombstones()
        habitCompletionDao.purgeSyncedTombstones()
        habitDao.purgeSyncedTombstones()
    }
}
