package com.personalailabs.astraldeep.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.personalailabs.astraldeep.app.render.CanvasHost
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.render.renderers.registerAllRenderers
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/** US2 (T037): renderer groups render; an unknown type degrades to a labeled placeholder (FR-005). */
class RenderersTest {
    @get:Rule val rule = createComposeRule()

    private fun render(components: List<Component>) {
        rule.setContent {
            val r = Renderer(Emit { _, _ -> }).registerAllRenderers()
            CanvasHost(components = components, renderer = r)
        }
    }

    @Test
    fun card_with_child_text_renders() {
        val card =
            Component("card", "card1", attrs("""{"type":"card","title":"My Card"}"""), listOf(textComponent("inside card")))
        render(listOf(card))
        rule.onNodeWithText("My Card").assertIsDisplayed()
        rule.onNodeWithText("inside card").assertIsDisplayed()
    }

    @Test
    fun unknown_type_shows_labeled_placeholder() {
        val unknown = Component("frobnicator", "u1", attrs("""{"type":"frobnicator"}"""), emptyList())
        render(listOf(unknown))
        rule.onNodeWithText("[frobnicator]").assertIsDisplayed()
    }

    /**
     * The LLM provider field is `kind:"select"` ON THE WIRE (web renders a `<select>`,
     * Windows a QComboBox): it must open a dropdown — never a box you type "openai"
     * into — and submit the picked option KEY unchanged for the `chrome_llm_*` handlers.
     */
    @Test
    fun a_select_field_opens_a_dropdown_and_submits_the_picked_key() {
        val emitted = mutableListOf<Pair<String, JsonObject>>()
        val picker =
            Component(
                "param_picker",
                "pp1",
                attrs(
                    """{"type":"param_picker","title":"LLM","submit_action":"chrome_llm_save","fields":[
                       {"name":"provider","label":"Provider","kind":"select","default":"openai",
                        "options":["openai","anthropic","xai"]}]}""",
                ),
                emptyList(),
            )
        rule.setContent {
            val r = Renderer(Emit { action, payload -> emitted += action to payload }).registerAllRenderers()
            CanvasHost(components = listOf(picker), renderer = r)
        }
        rule.onNodeWithText("openai").assertIsDisplayed() // the default is preselected, not typed
        rule.onNodeWithText("openai").performClick() // opens the menu
        rule.onNodeWithText("xai").performClick() // pick a different provider
        rule.onNodeWithText("Save").performClick()

        assertEquals(1, emitted.size)
        assertEquals("chrome_llm_save", emitted[0].first)
        val fields = emitted[0].second["fields"] as JsonObject
        assertEquals("xai", (fields["provider"] as JsonPrimitive).content)
    }
}
