package com.kyopenscience.astral.app.auth

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** Feature 044 T016 — refresh failure routes to sign-in, never a log-only stall. */
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
}
