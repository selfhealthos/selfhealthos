package com.alaverty.healthtracker.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import androidx.room.Room
import com.alaverty.healthtracker.data.github.GitHubApiService
import com.alaverty.healthtracker.data.local.AppDatabase
import com.alaverty.healthtracker.data.local.dao.AlarmDao
import com.alaverty.healthtracker.data.local.dao.BmDao
import com.alaverty.healthtracker.data.local.dao.BpDao
import com.alaverty.healthtracker.data.local.dao.DietDao
import com.alaverty.healthtracker.data.local.dao.DocDao
import com.alaverty.healthtracker.data.local.dao.ExerciseDao
import com.alaverty.healthtracker.data.local.dao.BodyMeasurementDao
import com.alaverty.healthtracker.data.local.dao.FitnessTestDao
import com.alaverty.healthtracker.data.local.dao.GymExerciseDao
import com.alaverty.healthtracker.data.local.dao.GymSetDao
import com.alaverty.healthtracker.data.local.dao.LabResultDao
import com.alaverty.healthtracker.data.local.dao.HabitCompletionDao
import com.alaverty.healthtracker.data.local.dao.HabitDao
import com.alaverty.healthtracker.data.local.dao.NoteDao
import com.alaverty.healthtracker.data.local.dao.WeightDao
import com.alaverty.healthtracker.data.local.dao.WfhDao
import com.alaverty.healthtracker.BuildConfig
import com.alaverty.healthtracker.data.preferences.DEFAULT_SERVER_URL
import com.alaverty.healthtracker.data.remote.AuthInterceptor
import com.alaverty.healthtracker.data.remote.HomeApi
import com.alaverty.healthtracker.data.remote.HostSelectionInterceptor
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Named
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "app_settings")

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "health_tracker.db")
            .addMigrations(
                AppDatabase.MIGRATION_1_2, AppDatabase.MIGRATION_2_3,
                AppDatabase.MIGRATION_3_4, AppDatabase.MIGRATION_4_5, AppDatabase.MIGRATION_5_6,
                AppDatabase.MIGRATION_6_7, AppDatabase.MIGRATION_7_8, AppDatabase.MIGRATION_8_9,
                AppDatabase.MIGRATION_9_10, AppDatabase.MIGRATION_10_11,
                AppDatabase.MIGRATION_11_12, AppDatabase.MIGRATION_12_13,
                AppDatabase.MIGRATION_13_14, AppDatabase.MIGRATION_14_15
            )
            .build()

    @Provides fun provideDietDao(db: AppDatabase): DietDao = db.dietDao()
    @Provides fun provideExerciseDao(db: AppDatabase): ExerciseDao = db.exerciseDao()
    @Provides fun provideNoteDao(db: AppDatabase): NoteDao = db.noteDao()
    @Provides fun provideBmDao(db: AppDatabase): BmDao = db.bmDao()
    @Provides fun provideBpDao(db: AppDatabase): BpDao = db.bpDao()
    @Provides fun provideWeightDao(db: AppDatabase): WeightDao = db.weightDao()
    @Provides fun provideHabitDao(db: AppDatabase): HabitDao = db.habitDao()
    @Provides fun provideHabitCompletionDao(db: AppDatabase): HabitCompletionDao = db.habitCompletionDao()
    @Provides fun provideDocDao(db: AppDatabase): DocDao = db.docDao()
    @Provides fun provideWfhDao(db: AppDatabase): WfhDao = db.wfhDao()
    @Provides fun provideGymExerciseDao(db: AppDatabase): GymExerciseDao = db.gymExerciseDao()
    @Provides fun provideGymSetDao(db: AppDatabase): GymSetDao = db.gymSetDao()
    @Provides fun provideLabResultDao(db: AppDatabase): LabResultDao = db.labResultDao()
    @Provides fun provideBodyMeasurementDao(db: AppDatabase): BodyMeasurementDao = db.bodyMeasurementDao()
    @Provides fun provideFitnessTestDao(db: AppDatabase): FitnessTestDao = db.fitnessTestDao()
    @Provides fun provideAlarmDao(db: AppDatabase): AlarmDao = db.alarmDao()

    @Provides
    @Singleton
    @Named("github")
    fun provideGitHubRetrofit(): Retrofit = Retrofit.Builder()
        .baseUrl("https://api.github.com/")
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    @Provides
    @Singleton
    fun provideGitHubApiService(@Named("github") retrofit: Retrofit): GitHubApiService =
        retrofit.create(GitHubApiService::class.java)

    @Provides
    @Singleton
    fun provideDataStore(@ApplicationContext context: Context): DataStore<Preferences> =
        context.dataStore

    // -- The home portal ----------------------------------------------------

    @Provides
    @Singleton
    @Named("home")
    fun provideHomeOkHttp(
        hostSelection: HostSelectionInterceptor,
        auth: AuthInterceptor
    ): OkHttpClient = OkHttpClient.Builder()
        // Order matters: the host is rewritten before the token is attached,
        // so AuthInterceptor sees the real destination when it decides whether
        // this is the enrolment endpoint.
        .addInterceptor(hostSelection)
        .addInterceptor(auth)
        .apply {
            if (BuildConfig.DEBUG) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        // BASIC, not BODY: the enrolment request carries the
                        // account password and the reply carries the token,
                        // and neither belongs in logcat.
                        level = HttpLoggingInterceptor.Level.BASIC
                    }
                )
            }
        }
        // Short by design. Away from home the portal is simply not there, and
        // the useful outcome is a fast failure that leaves the entry queued -
        // not a save that appears to hang.
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    @Named("home")
    fun provideHomeRetrofit(@Named("home") client: OkHttpClient): Retrofit = Retrofit.Builder()
        // Overridden per request by HostSelectionInterceptor. Retrofit demands
        // a syntactically valid base URL at build time; this is never the one
        // actually used.
        .baseUrl(DEFAULT_SERVER_URL)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    @Provides
    @Singleton
    fun provideHomeApi(@Named("home") retrofit: Retrofit): HomeApi =
        retrofit.create(HomeApi::class.java)
}
