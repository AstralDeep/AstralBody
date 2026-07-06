package com.kyopenscience.astral.app.ui

import com.kyopenscience.astral.app.rest.AstralRest
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Feature 044 — the reducer's chrome_surface behavior: the documented blank-key
 * close frame pops the surface screen, and a mismatched-key error notice is
 * never a silent drop (FR-002).
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
    ) = Inbound.ChromeSurface(surfaceKey = key, title = title, components = components)

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
}
