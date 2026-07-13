package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.sdui.CanvasOp
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Feature 055 T015 — the uniform welcome rule (wire-contract §1). Welcome
 * components arrive with "wel_"-prefixed identities and are turn-scoped: purged
 * from the committed canvas the moment a turn arms, and never archived into the
 * read-only canvas timeline. The purge is UNCONDITIONAL (no client-side flag) —
 * when the server flag is off the welcome arrives id-less, nothing matches
 * "wel_", and the purge is a byte-equivalent no-op.
 */
class WelcomePurgeTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    private fun comp(
        id: String?,
        type: String = "card",
    ) = Component(type, id, JsonObject(emptyMap()), emptyList())

    private val welcome = listOf(comp("wel_hero", "hero"), comp("wel_examples"), comp("wel_enable"))

    @Test
    fun turn_start_arming_purges_welcome_from_the_canvas() {
        // sendChat / the chat_message ui_event both arm through armTurn: the
        // welcome goes in the same copy that sets pendingReplace.
        val s = vm.armTurn(UiState(canvas = welcome + comp("A")))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        assertTrue(s.turnActive)
        assertTrue(s.pendingReplace)
    }

    @Test
    fun commit_never_archives_a_welcome_only_canvas() {
        // The "Canvas 1" leak regression: even if a welcome-only canvas survives
        // to commit (arming is the first line of defense), the archive guard
        // drops it — the timeline never shows a welcome snapshot.
        var s = UiState(canvas = welcome, turnActive = true, pendingReplace = true)
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        s = vm.reduce(s, Inbound.ChatStatus(status = "done", message = null))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        assertTrue(s.canvasHistory.isEmpty())
    }

    @Test
    fun commit_archives_only_the_non_welcome_components() {
        var s = UiState(canvas = welcome + comp("old"), canvasLabel = "old turn", turnActive = true, pendingReplace = true)
        s = vm.reduce(s, Inbound.UiUpsert(chatId = null, ops = listOf(CanvasOp("upsert", "A", comp("A")))))
        s = vm.reduce(s, Inbound.ChatStatus(status = "done", message = null))
        assertEquals(listOf(listOf("old")), s.canvasHistory.map { snap -> snap.components.map { it.id } })
        assertEquals("old turn", s.canvasHistory.single().label)
    }

    @Test
    fun a_text_only_turn_does_not_resurrect_welcome() {
        // Empty pendingCanvas at done keeps the canvas — minus welcome (belt-and-
        // braces; arming already purged it on the normal path).
        var s = UiState(canvas = welcome + comp("A"), turnActive = true, pendingReplace = true)
        s = vm.reduce(s, Inbound.ChatStatus(status = "done", message = null))
        assertEquals(listOf("A"), s.canvas.map { it.id })
        assertTrue(s.canvasHistory.isEmpty())
    }

    @Test
    fun non_welcome_ids_are_never_dropped() {
        // "welcome" (no underscore), "wc_…" fingerprints, and id-less components
        // all survive — only the exact "wel_" prefix is turn-scoped.
        val keep = listOf(comp("welcome"), comp("wc_abc123"), comp(null, "text"))
        val s = vm.armTurn(UiState(canvas = keep))
        assertEquals(listOf("welcome", "wc_abc123", null), s.canvas.map { it.id })
    }
}
