package com.alaverty.healthtracker.data.remote

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

/**
 * The home portal's REST surface, as far as this app uses it.
 *
 * Paths are relative and carry no leading slash so the base URL's path prefix
 * survives — a base URL of `https://home.laverty/` and a path of
 * `api/v1/...` compose; a leading slash would discard everything but the host.
 */
interface HomeApi {

    /**
     * Trade an email and password for a device token, once.
     *
     * The password is used here and never stored. What the phone keeps is a
     * token scoped to health and revocable on its own, so a lost phone costs
     * one row on the server rather than a password change everywhere.
     */
    @POST("api/v1/tokens/enrol")
    suspend fun enrol(@Body body: EnrolRequest): Response<EnrolResponse>

    /**
     * Push queued gym rows.
     *
     * Returns per-row outcomes, not 204. Only the ids named in
     * [GymSyncResponse.accepted] may be marked synced locally.
     */
    @POST("api/v1/health/sync/gym")
    suspend fun syncGym(@Body body: GymSyncRequest): Response<GymSyncResponse>

    /**
     * Push every other queued entry type in one batch.
     *
     * Separate from [syncGym] because gym sets have to be merged after the
     * exercise catalogue they link to; nothing here has that ordering problem,
     * so the remaining twelve types share one round trip.
     *
     * Same contract: only the ids named in [EntrySyncResponse.accepted] may be
     * marked synced locally.
     */
    @POST("api/v1/health/sync/entries")
    suspend fun syncEntries(@Body body: EntrySyncRequest): Response<EntrySyncResponse>

    /**
     * Attach one photo to a row [syncEntries] has already stored.
     *
     * Multipart, not JSON, because the body is raw image bytes. One file per
     * request for the same reason: multipart bodies do not batch the way JSON
     * rows do, and a phone with several pending photos already sends them one
     * at a time - see [com.alaverty.healthtracker.sync.PhotoSyncManager].
     */
    @Multipart
    @POST("api/v1/health/sync/photo")
    suspend fun syncPhoto(
        @Part("kind") kind: RequestBody,
        @Part("id") id: RequestBody,
        @Part file: MultipartBody.Part
    ): Response<PhotoSyncResponse>
}
