package com.personalailabs.astraldeep.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.personalailabs.astraldeep.app.render.CanvasHost
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.render.renderers.registerAllRenderers
import org.junit.Rule
import org.junit.Test

/** US1 (T027): a basic response renders natively in the canvas. */
class ChatRenderTest {
    @get:Rule val rule = createComposeRule()

    @Test
    fun text_component_renders_natively() {
        rule.setContent {
            val r = Renderer(Emit { _, _ -> }).registerAllRenderers()
            CanvasHost(components = listOf(textComponent("Hello from Astral")), renderer = r)
        }
        rule.onNodeWithText("Hello from Astral").assertIsDisplayed()
    }
}
