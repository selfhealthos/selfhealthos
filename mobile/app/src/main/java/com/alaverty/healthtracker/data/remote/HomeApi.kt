package com.alaverty.healthtracker.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

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
}
