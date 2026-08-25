package com.alaverty.healthtracker.data.remote

import com.alaverty.healthtracker.data.preferences.SettingsRepository
import com.alaverty.healthtracker.data.preferences.TokenStore
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Rewrites each request onto whatever server URL is currently configured.
 *
 * Retrofit fixes its base URL when the instance is built, and the instance is
 * an application-scoped singleton — so without this, changing the address in
 * Settings would not take effect until the process restarted, which reads
 * exactly like the setting not having saved. The placeholder base URL Retrofit
 * is built with is never actually used.
 */
@Singleton
class HostSelectionInterceptor @Inject constructor(
    private val settings: SettingsRepository
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val configured = settings.serverUrlBlocking().toHttpUrlOrNull()
            ?: return chain.proceed(request)

        val rewritten = request.url.newBuilder()
            .scheme(configured.scheme)
            .host(configured.host)
            .port(configured.port)
            .build()

        return chain.proceed(request.newBuilder().url(rewritten).build())
    }
}

/**
 * Attaches the device token, and notices when the server stops accepting it.
 *
 * Enrolment is exempt: it is the endpoint that *issues* the token, so sending a
 * stale one would be pointless and, once rejected, would mark a token dead
 * during the very request meant to replace it.
 *
 * A 401 flips the store into its rejected state. It never clears the queue —
 * that distinction is the whole point. Entries stay in Room and sync resumes
 * the moment a working token is enrolled; a credential problem must surface in
 * the UI rather than quietly discard a fortnight of workouts.
 */
@Singleton
class AuthInterceptor @Inject constructor(
    private val tokens: TokenStore
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.url.encodedPath.endsWith(ENROL_PATH)) return chain.proceed(request)

        val token = tokens.token()
            ?: return chain.proceed(request)

        val response = chain.proceed(
            request.newBuilder().header("Authorization", "Bearer $token").build()
        )
        if (response.code == 401) tokens.markRejected()
        return response
    }

    private companion object {
        const val ENROL_PATH = "/tokens/enrol"
    }
}
