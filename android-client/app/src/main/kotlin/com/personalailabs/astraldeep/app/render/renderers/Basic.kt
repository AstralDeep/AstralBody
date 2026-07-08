package com.personalailabs.astraldeep.app.render.renderers

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.app.render.MarkdownText
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.ui.theme.AstralColors
import com.personalailabs.astraldeep.app.ui.theme.hexToColor
import com.personalailabs.astraldeep.core.sdui.Component

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

/**
 * A layout container. Honors `direction:"row"` (the web flex row) and the
 * minimal `css` subset (background/height/flex) so css-styled leaves — e.g.
 * the Theme surface's preset swatch strips — render as colored boxes instead
 * of blank space, matching the web and the Windows twin ([containerMode] is
 * the pure, unit-tested rule).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ContainerPrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    when (containerMode(c)) {
        ContainerMode.SwatchBox -> SwatchBox(c, Modifier.fillMaxWidth())
        ContainerMode.SwatchRow ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                c.children.forEach { child ->
                    SwatchBox(child, Modifier.weight(child.cssFlex(1f)))
                }
            }
        ContainerMode.WrapRow ->
            FlowRow(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                c.children.forEach { renderChild(it) }
            }
        ContainerMode.Column ->
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                c.children.forEach { renderChild(it) }
            }
    }
}

/** A css-styled colored box (swatch cell); bad hex falls back to surfaceVariant. */
@Composable
private fun SwatchBox(
    c: Component,
    modifier: Modifier,
) {
    val color = hexToColor(c.cssBackground().orEmpty()) ?: MaterialTheme.colorScheme.surfaceVariant
    Box(
        modifier =
            modifier
                .height(c.cssHeightPx(22).dp)
                .clip(RoundedCornerShape(3.dp))
                .background(color),
    )
}

@Composable
private fun AlertPrimitive(c: Component) {
    val accent =
        when (c.str("variant")) {
            "error" -> Color(0xFFEF4444)
            "warning" -> Color(0xFFEAB308)
            "success" -> Color(0xFF22C55E)
            "info" -> Color(0xFF3B82F6)
            else -> MaterialTheme.colorScheme.primary
        }
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(8.dp)) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            c.str("title")?.let { Text(it, style = MaterialTheme.typography.titleSmall, color = accent) }
            Text(text = c.str("message").orEmpty(), style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/**
 * A server button. Honors `variant` like the web/Windows renderers: `primary`
 * gradient-filled, `secondary` tonal, `danger` solid red. Rendering every variant as
 * an identical filled button hid all selected-state feedback — the active
 * guide section / personalization tab / applied theme preset were visually
 * indistinguishable, which read as "the buttons do nothing".
 */
@Composable
private fun ButtonPrimitive(
    c: Component,
    emit: Emit,
) {
    val action = c.str("action")
    val label = c.str("label") ?: "Button"
    val onClick = { if (action != null) emit.event(action, c.payload()) }
    when (c.str("variant") ?: "primary") {
        "secondary" ->
            FilledTonalButton(onClick = onClick, enabled = action != null) { Text(label) }
        "danger" ->
            Button(
                onClick = onClick,
                enabled = action != null,
                colors =
                    ButtonDefaults.buttonColors(
                        containerColor = Color(0xFFEF4444),
                        contentColor = Color.White,
                    ),
            ) { Text(label) }
        else -> {
            // Brand treatment: the primary button carries the signature
            // indigo→purple gradient (web `.astral-btn-primary`) — a transparent
            // M3 Button (keeps the ripple) over a gradient-filled shape.
            val shape = ButtonDefaults.shape
            Button(
                onClick = onClick,
                enabled = action != null,
                shape = shape,
                colors =
                    ButtonDefaults.buttonColors(
                        containerColor = Color.Transparent,
                        contentColor = Color.White,
                    ),
                modifier = Modifier.background(AstralColors.AccentBrush, shape),
            ) { Text(label) }
        }
    }
}
