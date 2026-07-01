package com.kyopenscience.astral.app.ui

import com.kyopenscience.astral.app.rest.AstralRest
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.core.protocol.Inbound
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Feature 044 T041 — the read-only workspace timeline locks mutating affordances. */
class TimelineModeTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    @Test
    fun the_frame_toggles_the_read_only_flag() {
        val on = vm.reduce(UiState(), Inbound.WorkspaceTimelineMode(active = true))
        assertTrue(on.timelineReadOnly)
        assertTrue(on.mutationsLocked)
        val off = vm.reduce(on, Inbound.WorkspaceTimelineMode(active = false))
        assertFalse(off.timelineReadOnly)
        assertFalse(off.mutationsLocked)
    }

    @Test
    fun the_guard_blocks_mutations_but_not_navigation() {
        assertTrue(isTimelineMutation("chat_message"))
        assertTrue(isTimelineMutation("component_action"))
        assertFalse(isTimelineMutation("chrome_open"))
        assertFalse(isTimelineMutation("load_chat"))
        assertFalse(isTimelineMutation("discover_agents"))
    }
}
