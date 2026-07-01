package com.kyopenscience.astral.app.auth

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.kyopenscience.astral.app.AppConfig
import kotlinx.coroutines.suspendCancellableCoroutine
import net.openid.appauth.AuthState
import net.openid.appauth.AuthorizationException
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationResponse
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.ResponseTypeValues
import net.openid.appauth.TokenResponse

/**
 * Real Keycloak OIDC Authorization-Code + PKCE via AppAuth (RFC 8252 — the system
 * browser / Custom Tab). Public client `astral-mobile`, redirect
 * `com.kyopenscience.astral:/oauth2redirect`. The Activity launches
 * [authorizeIntent] and feeds the result back to [exchange]; [freshToken]
 * transparently refreshes.
 */
class OidcAuth(context: Context) {
    val service = AuthorizationService(context)

    private val config: AuthorizationServiceConfiguration by lazy {
        val e = keycloakEndpoints(AppConfig.KEYCLOAK_AUTHORITY)
        AuthorizationServiceConfiguration(
            Uri.parse(e.authorizationEndpoint),
            Uri.parse(e.tokenEndpoint),
            null,
            Uri.parse(e.endSessionEndpoint),
        )
    }

    /** The intent that opens the system browser for sign-in (PKCE added by AppAuth). */
    fun authorizeIntent(): Intent {
        val request =
            AuthorizationRequest.Builder(
                config,
                AppConfig.OIDC_CLIENT_ID,
                ResponseTypeValues.CODE,
                Uri.parse(AppConfig.OIDC_REDIRECT_URI),
            )
                // `offline_access` yields a DURABLE (offline) refresh token whose
                // lifetime is the realm's offline-session setting rather than the
                // short interactive SSO session — the basis for the "sign in once a
                // year" policy. Its rotation is persisted after every refresh.
                .setScope("openid profile email offline_access")
                .build()
        return service.getAuthorizationRequestIntent(request)
    }

    /** Exchange the redirect's authorization code for tokens; returns a populated AuthState. */
    suspend fun exchange(intent: Intent): AuthState {
        val response = AuthorizationResponse.fromIntent(intent)
        val authEx = AuthorizationException.fromIntent(intent)
        requireNotNull(response) { authEx?.message ?: "no authorization response" }
        val state = AuthState(response, authEx)
        val tokenResponse =
            suspendCancellableCoroutine { cont ->
                service.performTokenRequest(response.createTokenExchangeRequest()) { tr: TokenResponse?, e ->
                    if (tr != null) {
                        cont.resumeWith(Result.success(tr))
                    } else {
                        cont.resumeWith(Result.failure(e ?: IllegalStateException("token exchange failed")))
                    }
                }
            }
        state.update(tokenResponse, null)
        return state
    }

    /** A fresh access token, refreshing via the refresh token when needed. */
    suspend fun freshToken(state: AuthState): String =
        suspendCancellableCoroutine { cont ->
            state.performActionWithFreshTokens(service) { accessToken, _, e ->
                if (accessToken != null) {
                    cont.resumeWith(Result.success(accessToken))
                } else {
                    cont.resumeWith(Result.failure(e ?: IllegalStateException("token refresh failed")))
                }
            }
        }

    fun dispose() = service.dispose()
}
