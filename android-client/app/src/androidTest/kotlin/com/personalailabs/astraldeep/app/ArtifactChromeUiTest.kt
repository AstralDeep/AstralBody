package com.personalailabs.astraldeep.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.personalailabs.astraldeep.app.render.CanvasChrome
import com.personalailabs.astraldeep.app.render.CanvasHost
import com.personalailabs.astraldeep.app.render.Download
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.render.renderers.registerAllRenderers
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/**
 * Feature 055 US4/US5 (T036/T040/T045) — the per-component chrome end to end:
 * the provenance badge renders from the stamped field, the overflow's Refine…
 * entry sends `component_refine`, and an export entry hits the download path.
 */
class ArtifactChromeUiTest {
    @get:Rule val rule = createComposeRule()

    private val emitted = mutableListOf<Pair<String, JsonObject>>()
    private val downloads = mutableListOf<String>()

    private fun host(vararg components: Component) {
        rule.setContent {
            val r =
                Renderer(
                    Emit { a, p -> emitted.add(a to p) },
                    Download { url, _ -> downloads.add(url) },
                ).registerAllRenderers()
            CanvasHost(
                components = components.toList(),
                renderer = r,
                chrome = CanvasChrome(chatId = "chat-1", mutationsLocked = false),
            )
        }
    }

    private fun table() =
        Component.fromJson(
            attrs("""{"type":"table","component_id":"wc_abc","title":"Sales","headers":["a"],"rows":[["1"]],"provenance":"grounded"}"""),
        )

    @Test
    fun stamped_provenance_renders_the_badge() {
        host(table())
        rule.onNodeWithText("✓ tool data").assertIsDisplayed()
        rule.onNodeWithContentDescription("Component actions").assertIsDisplayed()
    }

    @Test
    fun unstamped_component_shows_no_badge() {
        host(Component.fromJson(attrs("""{"type":"card","component_id":"wc_c","title":"Plain"}""")))
        rule.onNodeWithText("✓ tool data").assertDoesNotExist()
        rule.onNodeWithText("✦ AI-generated").assertDoesNotExist()
    }

    @Test
    fun refine_dialog_sends_component_refine_with_the_instruction() {
        host(table())
        rule.onNodeWithContentDescription("Component actions").performClick()
        rule.onNodeWithText("Refine…").performClick()
        rule.onNode(hasSetTextAction()).performTextInput("make it a bar chart")
        rule.onNodeWithText("Refine").performClick()
        assertEquals(1, emitted.size)
        val (action, payload) = emitted.single()
        assertEquals("component_refine", action)
        assertEquals("wc_abc", (payload["component_id"] as JsonPrimitive).content)
        assertEquals("make it a bar chart", (payload["instruction"] as JsonPrimitive).content)
    }

    @Test
    fun export_entry_routes_through_the_download_path() {
        host(table())
        rule.onNodeWithContentDescription("Component actions").performClick()
        rule.onNodeWithText("Export table (CSV)").performClick()
        assertEquals(listOf("/api/export/component/wc_abc.csv?chat_id=chat-1"), downloads)
    }
}
