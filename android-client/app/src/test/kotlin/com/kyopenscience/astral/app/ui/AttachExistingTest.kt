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

    @Test
    fun attach_from_the_library_returns_to_the_chat_with_a_banner() {
        // The user is ON the attachments surface (paperclip → "Your files").
        vm.openSurface("attachments")
        assertEquals(Screen.Surface, vm.state.value.screen)
        vm.sendEvent(
            "attach_existing",
            buildJsonObject {
                put("attachment_id", "att-9")
                put("filename", "data.csv")
                put("category", "spreadsheet")
            },
        )
        // Attach navigates back to the composer (the web modal closes on Attach)
        // and confirms what was staged — staying on the surface read as a dead
        // button, and leaving via "+ New" would wipe the staged chip.
        assertEquals(Screen.Chat, vm.state.value.screen)
        assertEquals(1, vm.state.value.staged.size)
        assertTrue(vm.state.value.banner.orEmpty().contains("data.csv"))
        assertEquals("info", vm.state.value.bannerKind)
    }

    @Test
    fun a_duplicate_attach_still_returns_to_the_chat() {
        val payload =
            buildJsonObject {
                put("attachment_id", "att-1")
                put("filename", "a.pdf")
                put("category", "document")
            }
        vm.sendEvent("attach_existing", payload) // staged from the chat
        vm.openSurface("attachments")
        vm.sendEvent("attach_existing", payload) // duplicate, from the library
        assertEquals(1, vm.state.value.staged.size)
        assertEquals(Screen.Chat, vm.state.value.screen) // intent satisfied → composer
    }

    @Test
    fun a_malformed_attach_payload_stages_nothing_and_stays_put() {
        vm.openSurface("attachments")
        vm.sendEvent("attach_existing", buildJsonObject { put("filename", "x.pdf") })
        assertEquals(0, vm.state.value.staged.size)
        assertEquals(Screen.Surface, vm.state.value.screen)
    }
}
