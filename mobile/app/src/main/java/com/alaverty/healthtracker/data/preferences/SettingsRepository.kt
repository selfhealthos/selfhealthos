package com.alaverty.healthtracker.data.preferences

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

data class AppSettings(
    val githubRepo: String = "",
    val githubToken: String = "",
    val syncAll: Boolean = false,
    val syncDays: Int = 14,
    val heightCm: Float = 0f,   // 0 = not set; used for waist-to-height ratio
    /** The home portal. Configurable so a rebuild is not needed to move it. */
    val serverUrl: String = DEFAULT_SERVER_URL
)

/**
 * The IP, not the name: `health.laverty` doesn't reliably resolve on the
 * phone, which is exactly why the address here is the fallback that does. See
 * `network_security_config.xml` for the certificate trust that makes HTTPS to
 * this address work.
 */
const val DEFAULT_SERVER_URL = "https://192.168.1.111/"

@Singleton
class SettingsRepository @Inject constructor(
    private val dataStore: DataStore<Preferences>
) {
    companion object {
        private val KEY_GITHUB_REPO  = stringPreferencesKey("github_repo")
        private val KEY_GITHUB_TOKEN = stringPreferencesKey("github_token")
        private val KEY_SYNC_ALL     = booleanPreferencesKey("sync_all")
        private val KEY_SYNC_DAYS    = intPreferencesKey("sync_days")
        private val KEY_HEIGHT_CM    = floatPreferencesKey("height_cm")
        private val KEY_SERVER_URL   = stringPreferencesKey("server_url")
    }

    val settings: Flow<AppSettings> = dataStore.data.map { prefs ->
        AppSettings(
            githubRepo  = prefs[KEY_GITHUB_REPO]  ?: "",
            githubToken = prefs[KEY_GITHUB_TOKEN] ?: "",
            syncAll     = prefs[KEY_SYNC_ALL]     ?: false,
            syncDays    = prefs[KEY_SYNC_DAYS]    ?: 14,
            heightCm    = prefs[KEY_HEIGHT_CM]    ?: 0f,
            serverUrl   = prefs[KEY_SERVER_URL]?.takeIf { it.isNotBlank() } ?: DEFAULT_SERVER_URL
        )
    }

    suspend fun save(settings: AppSettings) {
        dataStore.edit { prefs ->
            prefs[KEY_GITHUB_REPO]  = settings.githubRepo
            prefs[KEY_GITHUB_TOKEN] = settings.githubToken
            prefs[KEY_SYNC_ALL]     = settings.syncAll
            prefs[KEY_SYNC_DAYS]    = settings.syncDays
            prefs[KEY_HEIGHT_CM]    = settings.heightCm
            prefs[KEY_SERVER_URL]   = settings.serverUrl.trim()
        }
    }

    /**
     * The server URL, read synchronously.
     *
     * `HostSelectionInterceptor` runs on OkHttp's own thread inside a call that
     * is already inside a coroutine; suspending there is not available, and
     * blocking OkHttp's dispatcher on a DataStore read would be. Kept as a
     * cached value updated by [observeServerUrl], so the interceptor's path is
     * a field read.
     */
    fun serverUrlBlocking(): String = cachedServerUrl

    @Volatile
    private var cachedServerUrl: String = DEFAULT_SERVER_URL

    /**
     * Load the configured URL into the cache, and return it.
     *
     * [observeServerUrl] alone is not enough, and the gap it leaves is not
     * theoretical: it starts during `Application.onCreate` and its first
     * emission is a DataStore *file read*, so a worker waking a cold process
     * reaches [serverUrlBlocking] before that lands and gets the
     * [DEFAULT_SERVER_URL] initialiser. Every request then went to
     * `home.laverty` — a name that does not resolve on the phone, which is
     * precisely why the address in Settings had been replaced with an IP.
     * The result was `UnknownHostException` on every attempt, logged as the
     * routine "portal unreachable" and retried into a five-hour backoff, with
     * nothing ever reaching the server.
     *
     * Called by the sync managers, which have a coroutine to suspend in — so
     * the URL is read properly rather than blocking OkHttp's dispatcher on
     * DataStore, which is what [serverUrlBlocking] exists to avoid.
     */
    suspend fun primeServerUrl(): String =
        settings.first().serverUrl.also { cachedServerUrl = it }

    /** Started once at app boot; keeps [serverUrlBlocking] honest. */
    fun observeServerUrl(scope: CoroutineScope) {
        scope.launch {
            settings.map { it.serverUrl }.distinctUntilChanged().collect { cachedServerUrl = it }
        }
    }
}
