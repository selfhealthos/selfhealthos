package com.alaverty.healthtracker.data.preferences

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.security.KeyStore
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The portal device token, held under the Android Keystore.
 *
 * Deliberately *not* in the DataStore where the GitHub PAT sits. DataStore is a
 * plaintext file in app-private storage: adequate against another app, useless
 * against anyone holding the unlocked phone or an ADB backup. This token is the
 * one credential that leaves the house, so it is encrypted with a key the
 * Keystore will not export.
 *
 * The token is long-lived by design — six months of idle, slid forward on every
 * use — so re-enrolment should never happen to a phone in regular service.
 * Which is exactly why [markRejected] exists rather than silently clearing it:
 * a 401 means something changed on the server (revoked, expired, account gone),
 * and the person needs to be told rather than have sync quietly stop.
 */
@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext context: Context
) {
    private val prefs: SharedPreferences = createPrefs(context)

    private val _state = MutableStateFlow(read())

    /** Enrolment state, for the settings screen to render without polling. */
    val state: StateFlow<TokenState> = _state.asStateFlow()

    fun token(): String? = prefs.getString(KEY_TOKEN, null)?.takeIf { it.isNotBlank() }

    fun save(token: String, deviceName: String, account: String) {
        prefs.edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_DEVICE_NAME, deviceName)
            .putString(KEY_ACCOUNT, account)
            .putBoolean(KEY_REJECTED, false)
            .apply()
        _state.value = read()
    }

    /**
     * Record that the server refused this token.
     *
     * The token is kept, not deleted. Erasing it would leave the settings
     * screen indistinguishable from "never enrolled", and the useful thing to
     * show is "the credential for alex@… stopped working" — which names both
     * the problem and the fix.
     */
    fun markRejected() {
        prefs.edit().putBoolean(KEY_REJECTED, true).apply()
        _state.value = read()
    }

    fun clear() {
        prefs.edit().clear().apply()
        _state.value = read()
    }

    private fun read() = TokenState(
        enrolled = !prefs.getString(KEY_TOKEN, null).isNullOrBlank(),
        rejected = prefs.getBoolean(KEY_REJECTED, false),
        deviceName = prefs.getString(KEY_DEVICE_NAME, "") ?: "",
        account = prefs.getString(KEY_ACCOUNT, "") ?: ""
    )

    /**
     * Build the encrypted store, self-healing a Keystore key that no longer
     * matches its own ciphertext.
     *
     * Seen on real devices after a plain redeploy from Android Studio (not a
     * full uninstall): the Keystore-backed master key gets invalidated —
     * TEE/StrongBox reset, OS keystore hiccup after reboot — while the app's
     * data directory, including the encrypted prefs file it wrapped, survives.
     * [EncryptedSharedPreferences.create] then throws `AEADBadTagException`
     * out of this constructor on every single launch, since Hilt builds this
     * singleton eagerly for the sync workers. There is no way to decrypt that
     * ciphertext without the original key, so recovery is to drop the unusable
     * key and the file it wrapped and start a fresh store — the person just
     * re-enrols, which is already the documented flow for a rejected token.
     */
    private fun createPrefs(context: Context): SharedPreferences = try {
        buildPrefs(context)
    } catch (e: Exception) {
        Log.w("TokenStore", "Encrypted prefs unreadable, resetting store", e)
        resetKeystoreEntry()
        context.deleteSharedPreferences(FILE_NAME)
        buildPrefs(context)
    }

    private fun buildPrefs(context: Context): SharedPreferences = EncryptedSharedPreferences.create(
        context,
        FILE_NAME,
        MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    private fun resetKeystoreEntry() {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (keyStore.containsAlias(MasterKey.DEFAULT_MASTER_KEY_ALIAS)) {
            keyStore.deleteEntry(MasterKey.DEFAULT_MASTER_KEY_ALIAS)
        }
    }

    private companion object {
        const val FILE_NAME = "home_portal_token"
        const val KEY_TOKEN = "token"
        const val KEY_DEVICE_NAME = "device_name"
        const val KEY_ACCOUNT = "account"
        const val KEY_REJECTED = "rejected"
    }
}

data class TokenState(
    val enrolled: Boolean = false,
    /** The server refused it. Sync is stopped until the phone re-enrols. */
    val rejected: Boolean = false,
    val deviceName: String = "",
    /** The email it was enrolled with. Shown so the right account is obvious. */
    val account: String = ""
)
