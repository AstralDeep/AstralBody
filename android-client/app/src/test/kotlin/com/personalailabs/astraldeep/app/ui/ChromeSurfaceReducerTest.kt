package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Feature 044 — the reducer's chrome_surface behavior: the documented blank-key
 * close frame pops the surface screen, and a mismatched-key error notice is
 * never a silent drop (FR-002). Feature 054 — a `mode:"mandatory"` surface (the
 * first-run LLM-setup gate) is accepted unsolicited and pinned until the blank
 * close frame clears it.
 */
class ChromeSurfaceReducerTest {
    private val vm = AppViewModel(OrchestratorClient("ws://localhost:9/ws"), AstralRest("http://localhost:9"))

    private fun alert(message: String): Component =
        Component(
            type = "alert",
            id = null,
            attributes = buildJsonObject { put("message", message) },
            children = emptyList(),
        )

    private fun surface(
        key: String,
        title: String = "",
        components: List<Component> = emptyList(),
        mode: String = "replace",
    ) = Inbound.ChromeSurface(surfaceKey = key, title = title, components = components, mode = mode)

    /** On the SDUI surface screen, awaiting (and holding) the "theme" surface. */
    private val onSurface =
        UiState(
            screen = Screen.Surface,
            pendingSurfaceKey = "theme",
            pendingSurface = Inbound.ChromeSurface("theme", "Theme", emptyList()),
        )

    @Test
    fun matching_surface_is_delivered() {
        val delivered = surface("theme", "Theme", listOf(alert("hi")))
        val s = vm.reduce(onSurface.copy(pendingSurface = null), delivered)
        assertEquals(delivered, s.pendingSurface)
        assertEquals(Screen.Surface, s.screen)
    }

    @Test
    fun close_frame_pops_the_surface_screen() {
        val s = vm.reduce(onSurface, surface(key = ""))
        assertEquals(Screen.Chat, s.screen)
        assertNull(s.pendingSurface)
        assertEquals("", s.pendingSurfaceKey)
        assertEquals(JsonObject(emptyMap()), s.pendingSurfaceParams)
    }

    @Test
    fun close_frame_off_the_surface_screen_is_a_noop() {
        val start = UiState(screen = Screen.Chat)
        assertEquals(start, vm.reduce(start, surface(key = "")))
    }

    @Test
    fun error_keyed_frame_on_a_surface_banners_and_keeps_the_surface_content() {
        val s = vm.reduce(onSurface, surface("error", "Not authorized", listOf(alert("Admin role required."))))
        assertEquals("Not authorized: Admin role required.", s.banner)
        assertEquals("error", s.bannerKind)
        assertEquals(Screen.Surface, s.screen)
        assertEquals(onSurface.pendingSurface, s.pendingSurface) // content untouched
    }

    @Test
    fun mismatched_frame_never_yanks_the_screen_but_is_not_silent() {
        val start = UiState(screen = Screen.Chat)
        val s = vm.reduce(start, surface("error", "Not available", listOf(alert("Unknown action: frob"))))
        assertEquals(Screen.Chat, s.screen)
        assertNull(s.pendingSurface)
        assertEquals("Not available: Unknown action: frob", s.banner)
        assertEquals("error", s.bannerKind)
    }

    @Test
    fun mandatory_surface_is_accepted_unsolicited_and_pins() {
        val start = UiState(screen = Screen.Chat)
        val gate = surface("llm", "Set up your AI provider", listOf(alert("Choose a provider.")), mode = "mandatory")
        val s = vm.reduce(start, gate)
        assertEquals(Screen.Surface, s.screen)
        assertEquals("llm", s.pendingSurfaceKey)
        assertEquals(gate, s.pendingSurface)
        assertTrue(s.mandatorySurface)
        assertNull(s.banner) // accepted, never demoted
    }

    @Test
    fun blank_close_clears_the_mandatory_pin() {
        val gated =
            UiState(
                screen = Screen.Surface,
                pendingSurfaceKey = "llm",
                pendingSurface = surface("llm", "Set up your AI provider", mode = "mandatory"),
                mandatorySurface = true,
            )
        val s = vm.reduce(gated, surface(key = ""))
        assertEquals(Screen.Chat, s.screen)
        assertNull(s.pendingSurface)
        assertFalse(s.mandatorySurface)
    }

    @Test
    fun non_mandatory_unsolicited_surface_still_demotes_to_banner() {
        val start = UiState(screen = Screen.Chat)
        val s = vm.reduce(start, surface("llm", "Set up your AI provider", listOf(alert("Choose a provider."))))
        assertEquals(Screen.Chat, s.screen)
        assertNull(s.pendingSurface)
        assertFalse(s.mandatorySurface)
        assertEquals("Set up your AI provider: Choose a provider.", s.banner)
        assertEquals("error", s.bannerKind)
    }
}
