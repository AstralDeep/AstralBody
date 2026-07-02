package com.kyopenscience.astral.app.auth

/** Where the auth state routes after a silent-refresh attempt (feature 044 T016). */
data class AuthRoute(val token: String?, val error: String?)

/**
 * Pure decision (unit-tested): a successful silent refresh keeps the session; ANY
 * failure routes to the sign-in screen with an explanation — a dead session is
 * never a log-only stall (FR-012/SC-004).
 */
fun routeAfterRefresh(result: Result<String>): AuthRoute =
    result.fold(
        onSuccess = { AuthRoute(token = it, error = null) },
        onFailure = { AuthRoute(token = null, error = "Session expired — sign in again") },
    )
