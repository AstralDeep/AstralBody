package com.personalailabs.astraldeep.app.auth

import net.openid.appauth.AuthorizationException
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Feature 044 T016 — a DEFINITIVE refresh rejection routes to sign-in (never a
 * log-only stall); a TRANSIENT failure (offline, IdP down) keeps the cached
 * session instead of kicking a valid year-long session out at cold start.
 */
class AuthRoutingTest {
    @Test
    fun successful_refresh_keeps_the_session() {
        val r = routeAfterRefresh(Result.success("tok"))
        assertEquals("tok", r.token)
        assertNull(r.error)
    }

    @Test
    fun failed_refresh_routes_to_sign_in_with_a_message() {
        val r = routeAfterRefresh(Result.failure(RuntimeException("invalid_grant")))
        assertNull(r.token)
        assertEquals("Session expired — sign in again", r.error)
    }

    @Test
    fun network_error_keeps_the_cached_token() {
        val r =
            routeAfterRefresh(
                Result.failure(AuthorizationException.GeneralErrors.NETWORK_ERROR),
                cachedToken = "cached",
            )
        assertEquals("cached", r.token)
        assertNull(r.error)
    }

    @Test
    fun io_failure_keeps_the_cached_token() {
        val r = routeAfterRefresh(Result.failure(IOException("timeout")), cachedToken = "cached")
        assertEquals("cached", r.token)
        assertNull(r.error)
    }

    @Test
    fun invalid_grant_routes_to_sign_in_even_with_a_cached_token() {
        val r =
            routeAfterRefresh(
                Result.failure(AuthorizationException.TokenRequestErrors.INVALID_GRANT),
                cachedToken = "cached",
            )
        assertNull(r.token)
        assertEquals("Session expired — sign in again", r.error)
    }

    @Test
    fun transient_failure_without_a_cached_token_still_routes_to_sign_in() {
        val r = routeAfterRefresh(Result.failure(AuthorizationException.GeneralErrors.NETWORK_ERROR))
        assertNull(r.token)
        assertEquals("Session expired — sign in again", r.error)
    }
}
