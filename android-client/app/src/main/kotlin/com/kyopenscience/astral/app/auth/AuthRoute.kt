package com.kyopenscience.astral.app.auth

import net.openid.appauth.AuthorizationException
import java.io.IOException

/** Where the auth state routes after a silent-refresh attempt (feature 044 T016). */
data class AuthRoute(val token: String?, val error: String?)

/**
 * Pure decision (unit-tested): a successful silent refresh keeps the session; a
 * DEFINITIVE OAuth rejection (e.g. `invalid_grant` — the refresh token is dead)
 * routes to the sign-in screen with an explanation — a dead session is never a
 * log-only stall (FR-012/SC-004). A TRANSIENT failure (network error, IdP briefly
 * down) with a [cachedToken] in hand keeps the cached session instead of kicking a
 * valid year-long session to sign-in while offline — if the session is genuinely
 * dead the mid-session `auth_required` handler (no cached token) catches it later.
 */
fun routeAfterRefresh(
    result: Result<String>,
    cachedToken: String? = null,
): AuthRoute =
    result.fold(
        onSuccess = { AuthRoute(token = it, error = null) },
        onFailure = { e ->
            if (cachedToken != null && isTransientRefreshFailure(e)) {
                AuthRoute(token = cachedToken, error = null)
            } else {
                AuthRoute(token = null, error = "Session expired — sign in again")
            }
        },
    )

/**
 * Transient = the refresh could not be ATTEMPTED or ANSWERED (AppAuth
 * general/network/server errors, plain IO failures) — only an OAuth token-endpoint
 * rejection ([AuthorizationException.TYPE_OAUTH_TOKEN_ERROR]) proves the session dead.
 */
private fun isTransientRefreshFailure(e: Throwable): Boolean =
    when (e) {
        is AuthorizationException -> e.type != AuthorizationException.TYPE_OAUTH_TOKEN_ERROR
        is IOException -> true
        else -> false
    }
