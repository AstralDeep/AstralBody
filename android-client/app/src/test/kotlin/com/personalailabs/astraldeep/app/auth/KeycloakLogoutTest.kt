package com.personalailabs.astraldeep.app.auth

import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Feature 044 T019 — sign-out ladder rung 2: the direct-Keycloak logout fallback. */
class KeycloakLogoutTest {
    @Test
    fun revoke_posts_the_rfc_form_and_is_true_on_204() =
        runTest {
            val server = MockWebServer()
            server.enqueue(MockResponse().setResponseCode(204))
            server.start()
            val endpoint = server.url("/realms/Astral/protocol/openid-connect/logout").toString()
            assertTrue(KeycloakLogout(endpoint).revoke("astral-mobile", "refr"))
            val req = server.takeRequest()
            assertEquals("POST", req.method)
            assertEquals("/realms/Astral/protocol/openid-connect/logout", req.path)
            assertEquals("application/x-www-form-urlencoded", req.getHeader("Content-Type"))
            val form = req.body.readUtf8()
            assertTrue("client_id=astral-mobile" in form)
            assertTrue("refresh_token=refr" in form)
            server.shutdown()
        }

    @Test
    fun revoke_is_false_on_server_error() =
        runTest {
            val server = MockWebServer()
            server.enqueue(MockResponse().setResponseCode(400))
            server.start()
            assertFalse(KeycloakLogout(server.url("/logout").toString()).revoke("astral-mobile", "refr"))
            server.shutdown()
        }

    @Test
    fun revoke_is_false_when_unreachable_not_thrown() =
        runTest {
            assertFalse(KeycloakLogout("http://127.0.0.1:59991/logout").revoke("astral-mobile", "refr"))
        }
}
