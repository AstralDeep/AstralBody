package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.sdui.CanvasOp
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Feature 044 T025 (FR-013) — canvas convergence contract.
 *
 * The server owns two canvas channels: `ui_upsert` is the incremental
 * add/morph/remove-by-id channel, and an out-of-turn full `ui_render(target=canvas)`
 * is the AUTHORITATIVE complete canvas — a wholesale replace (components absent
 * from the frame are removed; an empty frame clears the canvas). The backend
 * full-render guarantee ensures those frames always carry the complete live set,
 * so replace never loses a legitimately-live component. This matches the web
 * reference (setHTML replace) and the Windows twin. The real "clobber" the fix
 * targets is the IN-TURN mix of upserts + overlay renders, which is buffered and
 * merged by identity so nothing is lost before the turn commits.
 */
class CanvasClobberTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    private fun comp(
        id: String,
        type: String = "card",
    ) = Component(type, id, JsonObject(emptyMap()), emptyList())

    @Test
    fun out_of_turn_full_render_is_authoritative_replace() {
        // Upsert adds A to the live canvas (out of turn).
        var s = vm.reduce(UiState(), Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        // An out-of-turn full render delivers the complete authoritative canvas [B];
        // A is absent from it, so A is REMOVED (not merged/kept). This is what makes
        // combine/condense and timeline view correct.
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = listOf(comp("B"))))
        assertEquals(listOf("B"), s.canvas.map { it.id })
    }

    @Test
    fun out_of_turn_render_updates_a_matching_id_in_place() {
        var s = vm.reduce(UiState(), Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A", "card")))))
        // A full render re-delivering A as an alert → ONE A, updated content.
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = listOf(comp("A", "alert"))))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        assertEquals("alert", s.canvas.single().type)
    }

    @Test
    fun out_of_turn_empty_render_clears_the_canvas() {
        var s = vm.reduce(UiState(), Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        // The server pushes an empty full render to CLEAR the canvas.
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = emptyList()))
        assertEquals(emptyList(), s.canvas.map { it.id })
    }

    @Test
    fun in_turn_upserts_and_overlay_renders_accumulate_then_commit() {
        // During a replacing turn, upserts + additive overlay renders buffer into
        // pendingCanvas by identity — nothing is clobbered mid-turn (the actual fix).
        var s = UiState(turnActive = true, pendingReplace = true)
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = listOf(comp("B"))))
        assertEquals(listOf("A", "B"), s.pendingCanvas.map { it.id })
        // chat_status done commits the buffered canvas.
        s = vm.reduce(s, Inbound.ChatStatus(status = "done", message = null))
        assertEquals(listOf("A", "B"), s.canvas.map { it.id })
    }
}
