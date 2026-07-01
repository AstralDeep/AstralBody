package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.MarkdownText
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component

/**
 * Register the basic primitive renderers (US1 MVP): text, card, container, alert,
 * button. The remaining vocabulary (tables, charts, lists, …) lands in US2.
 */
fun Renderer.registerBasicRenderers(): Renderer =
    apply {
        register("text") { c -> TextPrimitive(c) }
        register("card") { c -> CardPrimitive(c) { child -> render(child) } }
        register("container") { c -> ContainerPrimitive(c) { child -> render(child) } }
        register("alert") { c -> AlertPrimitive(c) }
        register("button") { c -> ButtonPrimitive(c, emit) }
    }

@Composable
private fun TextPrimitive(c: Component) {
    MarkdownText(text = c.str("content") ?: c.str("text").orEmpty())
}

@Composable
private fun CardPrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            c.str("title")?.let { Text(it, style = MaterialTheme.typography.titleMedium) }
            c.children.forEach { renderChild(it) }
        }
    }
}

@Composable
private fun ContainerPrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        c.children.forEach { renderChild(it) }
    }
}

@Composable
private fun AlertPrimitive(c: Component) {
    val accent =
        when (c.str("variant")) {
            "error" -> Color(0xFFEF4444)
            "warning" -> Color(0xFFEAB308)
            "success" -> Color(0xFF22C55E)
            else -> MaterialTheme.colorScheme.primary
        }
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(8.dp)) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            c.str("title")?.let { Text(it, style = MaterialTheme.typography.titleSmall, color = accent) }
            Text(text = c.str("message").orEmpty(), style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun ButtonPrimitive(
    c: Component,
    emit: Emit,
) {
    val action = c.str("action")
    Button(
        onClick = { if (action != null) emit.event(action, c.payload()) },
        enabled = action != null,
    ) {
        Text(c.str("label") ?: "Button")
    }
}
