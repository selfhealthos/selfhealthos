package com.alaverty.healthtracker.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.alaverty.healthtracker.data.local.dao.*
import com.alaverty.healthtracker.data.local.entity.*

@Database(
    entities = [DietEntry::class, ExerciseEntry::class, PersonalNote::class, BmEntry::class,
        BpEntry::class, WeightEntry::class, Habit::class, HabitCompletion::class, DocEntry::class,
        WfhEntry::class, GymExercise::class, GymSet::class, LabResult::class,
        BodyMeasurement::class, FitnessTest::class, AlarmEntry::class],
    version = 15,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun dietDao(): DietDao
    abstract fun exerciseDao(): ExerciseDao
    abstract fun noteDao(): NoteDao
    abstract fun bmDao(): BmDao
    abstract fun bpDao(): BpDao
    abstract fun weightDao(): WeightDao
    abstract fun habitDao(): HabitDao
    abstract fun habitCompletionDao(): HabitCompletionDao
    abstract fun docDao(): DocDao
    abstract fun wfhDao(): WfhDao
    abstract fun gymExerciseDao(): GymExerciseDao
    abstract fun gymSetDao(): GymSetDao
    abstract fun labResultDao(): LabResultDao
    abstract fun bodyMeasurementDao(): BodyMeasurementDao
    abstract fun fitnessTestDao(): FitnessTestDao
    abstract fun alarmDao(): AlarmDao

    companion object {
        /**
         * Photo upload for diet and doc entries.
         *
         * `isSynced` says the row's fields have reached the portal; it says
         * nothing about the photo, which travels separately over
         * `/sync/photo` once the row exists there to attach it to. Existing
         * rows with a photo default to `photoSynced = 0` for the same reason
         * every other migration here defaults new sync columns to unsynced:
         * a picture already on this phone that the portal has never seen
         * must be offered, not skipped because the row it belongs to happens
         * to predate this column.
         */
        val MIGRATION_14_15 = object : Migration(14, 15) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    "ALTER TABLE diet_entries ADD COLUMN photoSynced INTEGER NOT NULL DEFAULT 0"
                )
                database.execSQL(
                    "ALTER TABLE doc_entries ADD COLUMN photoSynced INTEGER NOT NULL DEFAULT 0"
                )
            }
        }

        /**
         * Portal sync for every remaining entry type.
         *
         * Gym proved the protocol in 12→13; this extends the same two columns
         * to everything else, so `/api/v1/health/sync/entries` can carry the
         * lot. Three things are worth spelling out:
         *
         * **`deletedAt` everywhere.** Every one of these types could be
         * hard-deleted, which is invisible to the server: the entry stays on
         * the portal forever with nothing left on the phone to say it went.
         * The column is what turns a delete into something that can be sent.
         *
         * **`isSynced` on habits.** Habit *definitions* had neither column, so
         * they could not be queued at all — the table was export-only. A
         * completion means little without the habit it ticks off.
         *
         * **Existing rows default to unsynced.** The portal merges on each
         * row's own UUID, so the first sync re-offers the whole local history
         * and lands exactly what the server is missing. Defaulting to *synced*
         * is the silent-loss case: anything this phone holds that the server
         * does not would never be sent.
         */
        val MIGRATION_13_14 = object : Migration(13, 14) {
            override fun migrate(database: SupportSQLiteDatabase) {
                val tombstoned = listOf(
                    "diet_entries", "exercise_entries", "personal_notes", "bm_entries",
                    "bp_entries", "weight_entries", "habit_completions", "doc_entries",
                    "wfh_entries", "lab_results", "body_measurements", "fitness_tests"
                )
                tombstoned.forEach {
                    database.execSQL("ALTER TABLE $it ADD COLUMN deletedAt INTEGER")
                }
                // Habits had neither column: no tombstone and no queue flag.
                database.execSQL("ALTER TABLE habits ADD COLUMN isSynced INTEGER NOT NULL DEFAULT 0")
                database.execSQL("ALTER TABLE habits ADD COLUMN deletedAt INTEGER")
            }
        }

        /**
         * Gym sync against the home portal.
         *
         * `isSynced` on the catalogue, and a `deletedAt` tombstone on both
         * tables so a set removed on the phone can be removed on the server
         * too. Existing rows default to unsynced deliberately: the portal
         * merges on the row's own UUID, so the first sync re-offers the whole
         * local history and lands exactly the entries the server is missing.
         * Defaulting them to *synced* would be the silent-loss case — anything
         * this phone holds that the server does not would never be sent.
         */
        val MIGRATION_12_13 = object : Migration(12, 13) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("ALTER TABLE gym_sets ADD COLUMN deletedAt INTEGER")
                database.execSQL("ALTER TABLE gym_exercises ADD COLUMN isSynced INTEGER NOT NULL DEFAULT 0")
                database.execSQL("ALTER TABLE gym_exercises ADD COLUMN deletedAt INTEGER")
            }
        }

        val MIGRATION_11_12 = object : Migration(11, 12) {
            override fun migrate(database: SupportSQLiteDatabase) {
                // Allow multiple completions per habit per day: replace the unique
                // (habitId, date) index with a non-unique one of the same name.
                database.execSQL("DROP INDEX IF EXISTS index_habit_completions_habitId_date")
                database.execSQL(
                    """CREATE INDEX IF NOT EXISTS index_habit_completions_habitId_date
                        ON habit_completions(habitId, date)"""
                )
            }
        }

        val MIGRATION_10_11 = object : Migration(10, 11) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS alarms (
                        id TEXT NOT NULL PRIMARY KEY,
                        label TEXT NOT NULL,
                        hour INTEGER NOT NULL,
                        minute INTEGER NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        createdAt INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL
                    )"""
                )
            }
        }

        val MIGRATION_9_10 = object : Migration(9, 10) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS lab_results (
                        id TEXT NOT NULL PRIMARY KEY,
                        markerName TEXT NOT NULL,
                        value REAL NOT NULL,
                        unit TEXT NOT NULL,
                        date TEXT NOT NULL,
                        notes TEXT NOT NULL DEFAULT '',
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS body_measurements (
                        id TEXT NOT NULL PRIMARY KEY,
                        waistCm REAL,
                        hipsCm REAL,
                        neckCm REAL,
                        bodyFatPct REAL,
                        notes TEXT NOT NULL DEFAULT '',
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS fitness_tests (
                        id TEXT NOT NULL PRIMARY KEY,
                        gripKg REAL,
                        singleLegBalanceSec REAL,
                        sitToStandReps INTEGER,
                        deadHangSec REAL,
                        notes TEXT NOT NULL DEFAULT '',
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
            }
        }

        val MIGRATION_8_9 = object : Migration(8, 9) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS gym_exercises (
                        id TEXT NOT NULL PRIMARY KEY,
                        name TEXT NOT NULL,
                        lastWeightKg REAL NOT NULL DEFAULT 0.0,
                        lastReps INTEGER NOT NULL DEFAULT 10,
                        createdAt INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL
                    )"""
                )
                database.execSQL(
                    "CREATE UNIQUE INDEX IF NOT EXISTS index_gym_exercises_name ON gym_exercises(name)"
                )
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS gym_sets (
                        id TEXT NOT NULL PRIMARY KEY,
                        exerciseName TEXT NOT NULL,
                        weightKg REAL NOT NULL,
                        reps INTEGER NOT NULL,
                        date TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
            }
        }

        val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS wfh_entries (
                        id TEXT NOT NULL PRIMARY KEY,
                        date TEXT NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                database.execSQL(
                    "CREATE UNIQUE INDEX IF NOT EXISTS index_wfh_entries_date ON wfh_entries(date)"
                )
            }
        }

        val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS doc_entries (
                        id TEXT NOT NULL PRIMARY KEY,
                        title TEXT NOT NULL,
                        tags TEXT NOT NULL DEFAULT '',
                        photoPath TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
            }
        }

        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("ALTER TABLE diet_entries ADD COLUMN photoPath TEXT DEFAULT NULL")
            }
        }

        val MIGRATION_5_6 = object : Migration(5, 6) {
            override fun migrate(database: SupportSQLiteDatabase) {
                // SQLite <3.35 has no DROP COLUMN; recreate the table without calories
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS diet_entries_new (
                        id TEXT NOT NULL PRIMARY KEY,
                        name TEXT NOT NULL,
                        photoPath TEXT DEFAULT NULL,
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                database.execSQL(
                    """INSERT INTO diet_entries_new (id, name, photoPath, timestamp, updatedAt, isSynced)
                       SELECT id, name, photoPath, timestamp, updatedAt, isSynced
                       FROM diet_entries"""
                )
                database.execSQL("DROP TABLE diet_entries")
                database.execSQL("ALTER TABLE diet_entries_new RENAME TO diet_entries")
            }
        }

        val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS habits (
                        id TEXT NOT NULL PRIMARY KEY,
                        name TEXT NOT NULL,
                        sortOrder INTEGER NOT NULL DEFAULT 0,
                        createdAt INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL
                    )"""
                )
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS habit_completions (
                        id TEXT NOT NULL PRIMARY KEY,
                        habitId TEXT NOT NULL,
                        habitName TEXT NOT NULL,
                        date TEXT NOT NULL,
                        completedAt INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                database.execSQL(
                    """CREATE UNIQUE INDEX IF NOT EXISTS index_habit_completions_habitId_date
                        ON habit_completions(habitId, date)"""
                )
            }
        }

        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS weight_entries (
                        id TEXT NOT NULL PRIMARY KEY,
                        weightKg REAL NOT NULL,
                        notes TEXT NOT NULL DEFAULT '',
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
            }
        }

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS bm_entries (
                        id TEXT NOT NULL PRIMARY KEY,
                        bmNumber INTEGER NOT NULL,
                        notes TEXT NOT NULL DEFAULT '',
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                database.execSQL(
                    """CREATE TABLE IF NOT EXISTS bp_entries (
                        id TEXT NOT NULL PRIMARY KEY,
                        systolic INTEGER NOT NULL,
                        diastolic INTEGER NOT NULL,
                        notes TEXT NOT NULL DEFAULT '',
                        timestamp INTEGER NOT NULL,
                        updatedAt INTEGER NOT NULL,
                        isSynced INTEGER NOT NULL DEFAULT 0
                    )"""
                )
            }
        }
    }
}
