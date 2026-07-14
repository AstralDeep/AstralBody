package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.sdui.CanvasOp
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Feature 044 T025 (FR-013), revised by the 055 live-op rule — canvas
 * convergence contract.
 *
 * The server owns two canvas channels. `ui_upsert` is the incremental
 * add/morph/remove-by-id channel and applies to the LIVE canvas immediately —
 * even mid-turn — so the originating device renders partial output exactly like
 * co-viewing devices (no accumulate-then-commit divergence), and the first live
 * op clears the query skeleton. An out-of-turn full `ui_render(target=canvas)`
 * is the AUTHORITATIVE complete canvas — a wholesale replace (components absent
 * from the frame are removed; an empty frame clears the canvas). The one
 * mid-turn hazard 044 still buffers is the FULL render: an authoritative
 * replace landing mid-accumulation would clobber the live canvas, so in-turn
 * renders buffer and win per identity at `done` — the committed state always
 * equals what the user is looking at when the turn ends.
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
    fun in_turn_upsert_applies_live_and_clears_the_skeleton() {
        // The originating device shows partial output the moment it arrives —
        // identical to a co-viewing device — instead of buffering until done.
        var s = vm.armTurn(UiState())
        assertTrue(s.showSkeleton)
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        assertEquals(listOf("A"), s.visibleCanvas.map { it.id })
        assertTrue(s.pendingCanvas.isEmpty())
        // First canvas content of the turn hides the skeleton (web parity).
        assertFalse(s.showSkeleton)
    }

    @Test
    fun in_turn_full_render_stays_buffered_and_wins_at_done() {
        var s = vm.armTurn(UiState())
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A", "card")))))
        s = vm.reduce(s, Inbound.UiRender(target = "canvas", components = listOf(comp("A", "alert"), comp("B"))))
        // The render is invisible mid-turn (the actual clobber hazard)…
        assertEquals(listOf("A"), s.canvas.map { it.id })
        assertEquals("card", s.canvas.single().type)
        assertEquals(listOf("A", "B"), s.pendingCanvas.map { it.id })
        // …and commits at done, winning per identity; live-only components survive.
        s = vm.reduce(s, Inbound.ChatStatus(status = "done", message = null))
        assertEquals(listOf("A", "B"), s.canvas.map { it.id })
        assertEquals("alert", s.canvas.first().type)
        assertFalse(s.pendingReplace)
    }

    @Test
    fun ops_only_turn_commits_the_live_canvas_no_double_apply() {
        // No full render this turn: the live canvas (which already carries the
        // applied upserts) IS the committed state, and the pre-turn canvas is
        // what the timeline archives.
        var s = vm.armTurn(UiState(canvas = listOf(comp("old")), canvasLabel = "before"))
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        assertEquals(listOf("old", "A"), s.visibleCanvas.map { it.id })
        s = vm.reduce(s, Inbound.ChatStatus(status = "done", message = null))
        assertEquals(listOf("old", "A"), s.canvas.map { it.id })
        assertEquals(listOf(listOf("old")), s.canvasHistory.map { snap -> snap.components.map { it.id } })
        assertEquals("before", s.canvasHistory.single().label)
        assertFalse(s.pendingReplace)
    }

    @Test
    fun mid_turn_stream_ops_go_live_and_the_join_guard_reads_the_live_canvas() {
        var s = vm.armTurn(UiState())
        // Retained content lands under identity wc_abc via a live in-turn upsert…
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "wc_abc", comp("wc_abc", "card")))))
        assertFalse(s.showSkeleton)
        // …so a mid-stream join ack for the same identity must NOT blank it: the
        // existing-ids guard reads the LIVE canvas (what the user sees), not the
        // render buffer.
        s = vm.reduce(s, Inbound.StreamSubscribed("s1", "ticker", "wc_abc"))
        assertEquals(listOf("wc_abc"), s.canvas.map { it.id })
        assertEquals("card", s.canvas.single().type)
    }
}
