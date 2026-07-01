package com.kyopenscience.astral.app.ui

import com.kyopenscience.astral.app.rest.AstralRest
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.sdui.CanvasOp
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Feature 044 T025 (FR-013) — an out-of-turn full canvas `ui_render` reconciles by
 * component identity rather than wholesale-replacing the canvas, so earlier
 * `ui_upsert`-added components are not clobbered by a render that omits them.
 */
class CanvasClobberTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    private fun comp(
        id: String,
        type: String = "card",
    ) = Component(type, id, JsonObject(emptyMap()), emptyList())

    @Test
    fun out_of_turn_render_does_not_clobber_earlier_upserts() {
        // An upsert adds A to the live canvas (out of turn, not a replacing turn).
        var s = vm.reduce(UiState(), Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        // An out-of-turn full render delivers only [B]; A must survive (not dropped).
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = listOf(comp("B"))))
        assertEquals(listOf("A", "B"), s.canvas.map { it.id })
    }

    @Test
    fun out_of_turn_render_updates_a_matching_id_in_place() {
        var s = vm.reduce(UiState(), Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A", "card")))))
        // A full render re-delivers A as an alert → ONE A, updated in place.
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = listOf(comp("A", "alert"))))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        assertEquals("alert", s.canvas.single().type)
    }
}
