package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.core.protocol.Inbound
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Cross-device background-task continuity (audit item 12) — chat-scoped task
 * frame folding plus the pure "which chat to reload" rule the collect loop
 * drives load_chat from.
 */
class BackgroundContinuityTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    /** A turn in flight in chat c1 — the state a FOREIGN task frame must not disturb. */
    private val midTurnC1 =
        UiState(
            activeChatId = "c1",
            turnActive = true,
            pendingReplace = true,
            statusText = "Thinking…",
        )

    @Test
    fun task_started_for_the_open_chat_relaxes_into_background() {
        val s = vm.reduce(midTurnC1, Inbound.TaskStarted("t1", "c1"))
        assertTrue(s.asyncDetached)
        assertEquals("Working in the background…", s.statusText)
    }

    @Test
    fun task_started_in_another_chat_is_an_unobtrusive_banner_only() {
        val s = vm.reduce(midTurnC1, Inbound.TaskStarted("t1", "c2"))
        assertEquals("Background task started in another chat", s.banner)
        assertEquals("info", s.bannerKind)
        // This chat's in-flight turn is untouched.
        assertTrue(s.turnActive)
        assertFalse(s.asyncDetached)
        assertEquals("Thinking…", s.statusText)
    }

    @Test
    fun task_completed_for_the_open_chat_resolves_the_turn() {
        val s = vm.reduce(midTurnC1.copy(asyncDetached = true), Inbound.TaskCompleted("t1", "c1"))
        assertFalse(s.turnActive)
        assertFalse(s.asyncDetached)
        assertEquals("Background task finished", s.banner)
        assertEquals("info", s.bannerKind)
    }

    @Test
    fun task_completed_in_another_chat_banners_without_resolving_the_turn() {
        val s = vm.reduce(midTurnC1, Inbound.TaskCompleted("t1", "c2"))
        assertEquals("Background task finished in another chat — open it from History", s.banner)
        assertEquals("info", s.bannerKind)
        assertTrue(s.turnActive)
        assertTrue(s.pendingReplace)
    }

    @Test
    fun task_frames_without_a_chat_id_count_as_the_open_chat() {
        // Legacy flat frames carry no chat_id — behave exactly as before.
        val started = vm.reduce(midTurnC1, Inbound.TaskStarted("t1"))
        assertTrue(started.asyncDetached)
        val done = vm.reduce(midTurnC1, Inbound.TaskCompleted("t1", null))
        assertFalse(done.turnActive)
    }

    @Test
    fun task_frames_before_the_chat_is_acked_count_as_the_open_chat() {
        // First turn: activeChatId may not be set yet (mirrors the UiUpsert guard).
        val s = vm.reduce(midTurnC1.copy(activeChatId = null), Inbound.TaskCompleted("t1", "c1"))
        assertFalse(s.turnActive)
        assertEquals("Background task finished", s.banner)
    }

    @Test
    fun reload_targets_the_open_chat_on_task_completed() {
        assertEquals("c1", vm.continuityReloadTarget(midTurnC1, Inbound.TaskCompleted("t1", "c1")))
    }

    @Test
    fun reload_targets_the_open_chat_on_a_notification_for_it() {
        val n = Inbound.Notification(title = "Daily brief", body = "Ready", level = "info", chatId = "c1")
        assertEquals("c1", vm.continuityReloadTarget(midTurnC1, n))
    }

    @Test
    fun no_reload_for_another_chat_or_an_unnamed_one() {
        assertNull(vm.continuityReloadTarget(midTurnC1, Inbound.TaskCompleted("t1", "c2")))
        assertNull(vm.continuityReloadTarget(midTurnC1, Inbound.TaskCompleted("t1", null)))
        val foreign = Inbound.Notification(title = "Job", body = "Done", level = "info", chatId = "c2")
        assertNull(vm.continuityReloadTarget(midTurnC1, foreign))
        val unnamed = Inbound.Notification(title = "Job", body = "Done", level = "info")
        assertNull(vm.continuityReloadTarget(midTurnC1, unnamed))
    }

    @Test
    fun no_reload_when_no_chat_is_open_or_for_other_frames() {
        assertNull(vm.continuityReloadTarget(UiState(), Inbound.TaskCompleted("t1", "c1")))
        assertNull(vm.continuityReloadTarget(midTurnC1, Inbound.ChatStatus("done", null)))
        assertNull(vm.continuityReloadTarget(midTurnC1, Inbound.TaskStarted("t1", "c1")))
    }
}
