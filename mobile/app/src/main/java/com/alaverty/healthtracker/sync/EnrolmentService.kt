package com.alaverty.healthtracker.sync

import android.os.Build
import com.alaverty.healthtracker.data.preferences.TokenStore
import com.alaverty.healthtracker.data.remote.EnrolRequest
import com.alaverty.healthtracker.data.remote.HomeApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Trades the portal account password for a device token, once.
 *
 * The password is used for this one request and never persisted. What the
 * phone keeps afterwards is a token scoped to health alone and revocable by
 * itself, so a lost phone costs one row in the portal's token table rather than
 * a password change everywhere.
 *
 * Only reachable on the home LAN, which is the point: enrolment is the one
 * moment the phone holds the account password, and requiring it to happen in
 * the house means that moment never crosses the internet.
 */
@Singleton
class EnrolmentService @Inject constructor(
    private val api: HomeApi,
    private val tokens: TokenStore
) {
    suspend fun enrol(username: String, password: String): EnrolmentResult {
        val account = username.trim()
        if (account.isEmpty() || password.isEmpty()) {
            return EnrolmentResult.Failed("Enter the username and password you use for the portal.")
        }

        return try {
            val response = api.enrol(
                EnrolRequest(username = account, password = password, deviceName = deviceName())
            )
            val body = response.body()
            when {
                response.isSuccessful && body != null -> {
                    tokens.save(body.secret, deviceName(), account)
                    EnrolmentResult.Enrolled
                }
                response.code() == 401 ->
                    EnrolmentResult.Failed("That username and password were not recognised.")
                response.code() == 429 ->
                    EnrolmentResult.Failed("Too many attempts. Wait a few minutes and try again.")
                else ->
                    EnrolmentResult.Failed("The portal answered ${response.code()}.")
            }
        } catch (e: Exception) {
            // Almost always "not on the home network". Say that, rather than
            // showing a stack-trace class name nobody can act on.
            EnrolmentResult.Failed(
                "Could not reach the portal. Check you are on the home wifi and the " +
                    "address in Server URL is right."
            )
        }
    }

    /** What the token is listed as in the portal's settings, so revoking the right one is obvious. */
    private fun deviceName(): String = "${Build.MANUFACTURER} ${Build.MODEL}".trim()
}

sealed interface EnrolmentResult {
    data object Enrolled : EnrolmentResult
    data class Failed(val message: String) : EnrolmentResult
}
