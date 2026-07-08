package com.personalailabs.astraldeep.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.personalailabs.astraldeep.app.render.CanvasHost
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.render.renderers.registerAllRenderers
import com.personalailabs.astraldeep.core.sdui.Component
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
}
