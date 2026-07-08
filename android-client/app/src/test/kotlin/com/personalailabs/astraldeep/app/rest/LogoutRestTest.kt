package com.personalailabs.astraldeep.app.rest

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Feature 044 T019 — sign-out ladder rung 1: the backend logout endpoint call. */
class LogoutRestTest {
    @Test
    fun logout_posts_bearer_and_body_and_is_true_on_2xx() =
        runTest {
            val server = MockWebServer()
            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"outcome":"revoked","revoked":true,"queued":false}"""))
            server.start()
            val ok = AstralRest(server.url("/").toString()).logout("tok", "refr", "astral-mobile")
            assertTrue(ok)
            val req = server.takeRequest()
            assertEquals("POST", req.method)
            assertEquals("/api/auth/logout", req.path)
            assertEquals("Bearer tok", req.getHeader("Authorization"))
            val body = Json.parseToJsonElement(req.body.readUtf8()).jsonObject
            assertEquals("refr", body["refresh_token"]?.jsonPrimitive?.content)
            assertEquals("astral-mobile", body["client_id"]?.jsonPrimitive?.content)
            server.shutdown()
        }

    @Test
    fun logout_is_false_on_500() =
        runTest {
            val server = MockWebServer()
            server.enqueue(MockResponse().setResponseCode(500))
            server.start()
            assertFalse(AstralRest(server.url("/").toString()).logout("tok", "refr", "astral-mobile"))
            server.shutdown()
        }

    @Test
    fun logout_is_false_when_unreachable_not_thrown() =
        runTest {
            // Nothing listens here — the ladder rung must swallow and report false.
            assertFalse(AstralRest("http://127.0.0.1:59993").logout("tok", "refr", "astral-mobile"))
        }
}
