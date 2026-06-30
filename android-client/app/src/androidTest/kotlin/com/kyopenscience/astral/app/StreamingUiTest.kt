package com.kyopenscience.astral.app

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.kyopenscience.astral.app.render.CanvasHost
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.render.renderers.registerAllRenderers
import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.sdui.Canvas
import com.kyopenscience.astral.core.sdui.Component
import com.kyopenscience.astral.core.streaming.streamFrameToOps
import org.junit.Rule
import org.junit.Test

/** US2 (T037): a stream's later frame replaces the earlier one in place. */
class StreamingUiTest {
    @get:Rule val rule = createComposeRule()

    private fun frame(seq: Int, text: String) =
        Inbound.UiStreamData("s1", null, seq, listOf(textComponent(text)), false, null, null)

    @Test
    fun stream_updates_in_place() {
        rule.setContent {
            val seq = remember { mutableMapOf<String, Int>() }
            var canvas by remember { mutableStateOf(emptyList<Component>()) }
            val r = Renderer(Emit { _, _ -> }).registerAllRenderers()
            LaunchedEffect(Unit) {
                canvas = Canvas.apply(canvas, streamFrameToOps(frame(1, "first"), null, seq))
                canvas = Canvas.apply(canvas, streamFrameToOps(frame(2, "second"), null, seq))
            }
            CanvasHost(components = canvas, renderer = r)
        }
        rule.onNodeWithText("second").assertIsDisplayed()
    }
}
