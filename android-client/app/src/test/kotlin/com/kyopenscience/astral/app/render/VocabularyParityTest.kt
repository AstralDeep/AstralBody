package com.kyopenscience.astral.app.render

import com.kyopenscience.astral.app.render.renderers.registerAllRenderers
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Guards the advertised vocabulary (the Android twin of the Windows
 * `test_no_silent_backend_vocabulary_drift`): the client advertises exactly the
 * types it registers, and the web-only / not-yet-implemented types stay excluded
 * (so ROTE substitutes them). Pure JVM — the @Composable renderers are stored,
 * not invoked.
 */
class VocabularyParityTest {
    private val expected =
        setOf(
            "text", "card", "container", "alert", "button",
            "grid", "hero", "badge", "metric", "keyvalue", "timeline", "rating", "divider", "progress", "collapsible",
            "list", "table", "tabs", "chat_history", "skeleton",
            "input", "param_picker", "code", "file_upload", "file_download", "download_card",
            "bar_chart", "line_chart", "pie_chart",
            "image",
        )

    private val excluded = setOf("plotly_chart", "audio", "color_picker", "theme_apply", "generative")

    private fun renderer() = Renderer(Emit { _, _ -> }).registerAllRenderers()

    @Test
    fun registers_exactly_the_expected_vocabulary() {
        assertEquals(expected, renderer().supportedTypes)
    }

    @Test
    fun excludes_web_only_or_unimplemented_types() {
        val supported = renderer().supportedTypes
        excluded.forEach { assertTrue(it !in supported, "$it must not be advertised") }
    }
}
