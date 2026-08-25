package com.alaverty.healthtracker.data.github

import com.google.gson.JsonObject
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PUT
import retrofit2.http.Path

data class GitHubFileResponse(
    val content: String,
    val sha: String
)

data class GitHubPutRequest(
    val message: String,
    val content: String,
    val sha: String? = null
)

interface GitHubApiService {
    @GET("repos/{owner}/{repo}/contents/{path}")
    suspend fun getFile(
        @Header("Authorization") auth: String,
        @Path("owner") owner: String,
        @Path("repo") repo: String,
        @Path("path", encoded = true) path: String
    ): Response<GitHubFileResponse>

    @PUT("repos/{owner}/{repo}/contents/{path}")
    suspend fun putFile(
        @Header("Authorization") auth: String,
        @Path("owner") owner: String,
        @Path("repo") repo: String,
        @Path("path", encoded = true) path: String,
        @Body request: GitHubPutRequest
    ): Response<JsonObject>
}
