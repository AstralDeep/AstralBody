package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Feature 055 US3 (T030) — the eight workspace verb acks, promoted from ignored
 * to handled (wire-contract §4): deletion/combine/condense results reconcile the
 * canvas by identity, save/combine acks surface as status/banner, and
 * `saved_components_list` is an accepted no-op (no native surface consumes it).
 */
class WorkspaceVerbReducerTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    private fun comp(
        id: String,
        type: String = "card",
    ) = Component(type, id, JsonObject(emptyMap()), emptyList())

    private fun canvasWith(vararg ids: String) = UiState(canvas = ids.map { comp(it) })

    @Test
    fun component_deleted_removes_by_identity() {
        val s = vm.reduce(canvasWith("A", "B"), Inbound.ComponentDeleted("A"))
        assertEquals(listOf("B"), s.canvas.map { it.id })
    }

    @Test
    fun component_deleted_unknown_or_missing_id_is_a_noop() {
        val before = canvasWith("A")
        assertEquals(before.canvas, vm.reduce(before, Inbound.ComponentDeleted("nope")).canvas)
        assertEquals(before.canvas, vm.reduce(before, Inbound.ComponentDeleted(null)).canvas)
    }

    @Test
    fun components_combined_applies_results_and_removes_consumed_identities() {
        val s0 = canvasWith("A", "B", "C")
        val s = vm.reduce(s0, Inbound.ComponentsReplaced(removedIds = listOf("A", "B"), newComponents = listOf(comp("D", "table"))))
        assertEquals(listOf("C", "D"), s.canvas.map { it.id })
        assertEquals("table", s.canvas.last().type)
    }

    @Test
    fun components_replaced_clears_the_combine_status() {
        val s0 = canvasWith("A", "B").copy(statusText = "Condensing 2 components...")
        val s = vm.reduce(s0, Inbound.ComponentsReplaced(listOf("A", "B"), listOf(comp("D"))))
        assertNull(s.statusText)
    }

    @Test
    fun combine_status_shows_progress_then_error_banners_and_clears_it() {
        var s = vm.reduce(UiState(), Inbound.CombineStatus(status = "combining", message = "Combining A with B..."))
        assertEquals("Combining A with B...", s.statusText)
        s = vm.reduce(s, Inbound.CombineError("LLM unavailable"))
        assertNull(s.statusText)
        assertEquals("LLM unavailable", s.banner)
        assertEquals("error", s.bannerKind)
    }

    @Test
    fun combine_status_falls_back_to_the_status_word() {
        val s = vm.reduce(UiState(), Inbound.CombineStatus(status = "condensing", message = null))
        assertEquals("condensing", s.statusText)
    }

    @Test
    fun component_saved_banners_info_with_the_title() {
        val s = vm.reduce(UiState(), Inbound.ComponentSaved("Chart"))
        assertEquals("Saved Chart", s.banner)
        assertEquals("info", s.bannerKind)
        assertEquals("Component saved", vm.reduce(UiState(), Inbound.ComponentSaved(null)).banner)
    }

    @Test
    fun component_save_error_banners_error() {
        val s = vm.reduce(UiState(), Inbound.ComponentSaveError("Component not found"))
        assertEquals("Component not found", s.banner)
        assertEquals("error", s.bannerKind)
    }

    @Test
    fun saved_components_list_is_a_state_noop() {
        val before = canvasWith("A")
        assertEquals(before, vm.reduce(before, Inbound.SavedComponentsList(3)))
    }

    @Test
    fun mid_turn_verb_acks_route_to_the_pending_buffer() {
        // A verb ack landing mid replacing-turn reconciles the buffered canvas
        // (same routing as every canvas op), never the committed one.
        val s0 =
            UiState(
                turnActive = true,
                pendingReplace = true,
                pendingCanvas = listOf(comp("A"), comp("B")),
                canvas = listOf(comp("Z")),
            )
        val s = vm.reduce(s0, Inbound.ComponentDeleted("A"))
        assertEquals(listOf("B"), s.pendingCanvas.map { it.id })
        assertEquals(listOf("Z"), s.canvas.map { it.id })
    }
}
