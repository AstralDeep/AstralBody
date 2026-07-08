package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.core.chrome.SurfaceRef
import com.personalailabs.astraldeep.core.chrome.TopBarControl
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** Feature 044 T037 — the pure server-top-bar action mapping (control → icon/label/surface). */
class TopBarActionsTest {
    @Test
    fun maps_pulse_and_timeline_to_their_icons_and_surfaces() {
        val pulse =
            topBarActionView(
                TopBarControl("pulse", "action", label = "Pulse digest", icon = "sparkle", action = SurfaceRef("pulse")),
            )!!
        assertEquals(TopBarIcon.SPARKLE, pulse.icon)
        assertEquals("pulse", pulse.surface)
        assertEquals("Pulse digest", pulse.label)

        val timeline =
            topBarActionView(
                TopBarControl("timeline", "action", label = "Workspace timeline", icon = "history", action = SurfaceRef("workspace_timeline")),
            )!!
        assertEquals(TopBarIcon.HISTORY, timeline.icon)
        assertEquals("workspace_timeline", timeline.surface)
    }

    @Test
    fun unknown_icon_is_generic_and_label_defaults_to_surface() {
        val v = topBarActionView(TopBarControl("x", "action", icon = "mystery", action = SurfaceRef("some_surface")))!!
        assertEquals(TopBarIcon.GENERIC, v.icon)
        assertEquals("some_surface", v.label)
    }

    @Test
    fun a_control_without_a_surface_is_not_renderable() {
        assertNull(topBarActionView(TopBarControl("brand", "brand")))
        assertNull(topBarActionView(TopBarControl("s", "action", action = SurfaceRef(""))))
    }

    @Test
    fun params_are_carried_through_to_the_view() {
        val params = JsonObject(mapOf("tab" to JsonPrimitive("digest")))
        val v = topBarActionView(TopBarControl("t", "action", icon = "history", action = SurfaceRef("workspace_timeline", params)))!!
        assertEquals(params, v.params)
    }
}
