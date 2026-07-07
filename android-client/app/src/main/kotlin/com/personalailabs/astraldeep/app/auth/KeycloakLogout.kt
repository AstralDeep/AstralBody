package com.personalailabs.astraldeep.app.auth

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * Sign-out ladder rung 2 (feature 044): direct RFC-style Keycloak logout —
 * `POST {authority}/protocol/openid-connect/logout` with `client_id` +
 * `refresh_token` form fields (a public client needs no secret). Used when the
 * backend logout endpoint is unreachable. The endpoint is injected (from
 * [keycloakEndpoints]) so tests can point it at a local server.
 */
class KeycloakLogout(
    private val logoutEndpoint: String,
    private val client: OkHttpClient = OkHttpClient(),
) {
    /** Best-effort revocation: true on a 2xx (Keycloak replies 204), never throws. */
    suspend fun revoke(
        clientId: String,
        refreshToken: String,
    ): Boolean =
        withContext(Dispatchers.IO) {
            val body =
                FormBody.Builder()
                    .add("client_id", clientId)
                    .add("refresh_token", refreshToken)
                    .build()
            val request = Request.Builder().url(logoutEndpoint).post(body).build()
            runCatching { client.newCall(request).execute().use { it.isSuccessful } }.getOrDefault(false)
        }
}
