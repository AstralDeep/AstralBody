package com.personalailabs.astraldeep.app.render.renderers

import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Settings-surface parity — the pure container layout rules behind
 * [ContainerPrimitive]: the minimal native `css` subset (background / height /
 * flex) and the `direction:"row"` handling that render the Theme surface's
 * preset swatch strips as colored proportional boxes (never blank space) and
 * wrap plain rows (tab bars / form actions) instead of overflowing a phone
 * width. Mirrors the Windows twin's tests (test_renderer.py).
 */
class ContainerCssTest {
    private fun comp(json: String): Component = Component.fromJson(Json.parseToJsonElement(json) as JsonObject)

    private val swatch =
        """{"type":"container","children":[],"css":{"background":"#22C55E","height":"22px","flex":"1"}}"""

    @Test
    fun css_background_height_flex_parse() {
        val c = comp(swatch)
        assertEquals("#22C55E", c.cssBackground())
        assertEquals(22, c.cssHeightPx(0))
        assertEquals(1f, c.cssFlex(0f))
    }

    @Test
    fun css_parsing_is_tolerant_of_garbage() {
        val c = comp("""{"type":"container","children":[],"css":{"background":"","height":"tall","flex":"wide"}}""")
        assertNull(c.cssBackground())
        assertEquals(22, c.cssHeightPx(22)) // default kept
        assertEquals(1f, c.cssFlex(1f)) // default kept
        val noCss = comp("""{"type":"container","children":[]}""")
        assertNull(noCss.cssBackground())
    }

    @Test
    fun childless_css_styled_container_is_a_swatch_box() {
        assertEquals(ContainerMode.SwatchBox, containerMode(comp(swatch)))
    }

    @Test
    fun row_of_styled_leaves_is_a_proportional_swatch_strip() {
        val strip = comp("""{"type":"container","direction":"row","children":[$swatch,$swatch,$swatch]}""")
        assertEquals(ContainerMode.SwatchRow, containerMode(strip))
    }

    @Test
    fun row_of_ordinary_children_wraps() {
        val tabs =
            comp(
                """{"type":"container","direction":"row","children":[
                     {"type":"button","label":"Soul","action":"chrome_open"},
                     {"type":"button","label":"Memory","action":"chrome_open"}]}""",
            )
        assertEquals(ContainerMode.WrapRow, containerMode(tabs))
    }

    @Test
    fun mixed_row_with_a_non_swatch_child_wraps_not_strips() {
        val mixed =
            comp(
                """{"type":"container","direction":"row","children":[
                     $swatch, {"type":"text","content":"hi"}]}""",
            )
        assertEquals(ContainerMode.WrapRow, containerMode(mixed))
    }

    @Test
    fun default_container_stays_a_column() {
        assertEquals(
            ContainerMode.Column,
            containerMode(comp("""{"type":"container","children":[{"type":"text","content":"hi"}]}""")),
        )
        // An EMPTY row container is a (childless) wrap-row, never a strip.
        assertEquals(
            ContainerMode.WrapRow,
            containerMode(comp("""{"type":"container","direction":"row","children":[]}""")),
        )
    }
}
