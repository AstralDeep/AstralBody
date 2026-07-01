package com.kyopenscience.astral.app.ui

import com.kyopenscience.astral.app.rest.AstralRest
import com.kyopenscience.astral.app.transport.OrchestratorClient
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Feature 044 T047 — `attach_existing` is a CLIENT-LOCAL action (ui_protocol.json
 * client_local_actions): it stages the already-uploaded file as a ready chip and is
 * never forwarded to the server.
 */
class AttachExistingTest {
    private val client = OrchestratorClient("ws://localhost:9/ws")
    private val vm = AppViewModel(client, AstralRest("http://localhost:9"))

    @Test
    fun attach_existing_stages_a_ready_chip_and_sends_no_frame() {
        vm.sendEvent(
            "attach_existing",
            buildJsonObject {
                put("attachment_id", "att-1")
                put("filename", "report.pdf")
                put("category", "document")
            },
        )
        val staged = vm.state.value.staged
        assertEquals(1, staged.size)
        assertEquals("att-1", staged.first().attachmentId)
        assertEquals("report.pdf", staged.first().filename)
        assertEquals("document", staged.first().category)
        assertEquals("ready", staged.first().state)
        // A client-local action never reaches the socket / offline queue.
        assertTrue(client.pendingActions().isEmpty())
    }

    @Test
    fun a_normal_event_is_still_enqueued() {
        vm.sendEvent("discover_agents")
        assertEquals(listOf("discover_agents"), client.pendingActions())
    }

    @Test
    fun a_duplicate_attach_existing_is_ignored() {
        val payload =
            buildJsonObject {
                put("attachment_id", "att-1")
                put("filename", "a.pdf")
                put("category", "document")
            }
        vm.sendEvent("attach_existing", payload)
        vm.sendEvent("attach_existing", payload)
        assertEquals(1, vm.state.value.staged.size)
    }
}
