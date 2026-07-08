package com.personalailabs.astraldeep.app.render.renderers

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.ui.theme.AstralColors
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** Register the layout/content primitives (US2). */
fun Renderer.registerLayoutRenderers(): Renderer =
    apply {
        register("grid") { c -> GridPrimitive(c) { render(it) } }
        register("hero") { c -> HeroPrimitive(c) }
        register("badge") { c -> BadgePrimitive(c) }
        register("metric") { c -> MetricPrimitive(c) }
        register("keyvalue") { c -> KeyValuePrimitive(c) }
        register("timeline") { c -> TimelinePrimitive(c) }
        register("rating") { c -> RatingPrimitive(c) }
        register("divider") { HorizontalDivider() }
        register("progress") { c -> ProgressPrimitive(c) }
        register("collapsible") { c -> CollapsiblePrimitive(c) { render(it) } }
    }

@Composable
private fun GridPrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    val cols = (c.int("columns") ?: 2).coerceAtLeast(1)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        c.children.chunked(cols).forEach { rowItems ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                rowItems.forEach { Box(Modifier.weight(1f)) { renderChild(it) } }
            }
        }
    }
}

/**
 * The hero banner. Mirrors the web renderer (`render_hero`): optional uppercase
 * `eyebrow` caption above the title, optional string `badges` capsule row below
 * the subtitle, and a `gradient` variant that adds a diagonal primary→secondary
 * wash plus an AccentBrush top bar; the default variant stays a plain card.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HeroPrimitive(c: Component) {
    val gradient = c.str("variant") == "gradient"
    val primary = MaterialTheme.colorScheme.primary
    Card(modifier = Modifier.fillMaxWidth()) {
        Column {
            if (gradient) {
                Box(Modifier.fillMaxWidth().height(3.dp).background(AstralColors.AccentBrush))
            }
            Column(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .then(
                            if (gradient) {
                                Modifier.background(
                                    Brush.linearGradient(
                                        listOf(
                                            primary.copy(alpha = 0.18f),
                                            MaterialTheme.colorScheme.secondary.copy(alpha = 0.08f),
                                        ),
                                        start = Offset.Zero,
                                        end = Offset.Infinite,
                                    ),
                                )
                            } else {
                                Modifier
                            },
                        )
                        .padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                c.str("eyebrow")?.let {
                    Text(
                        it.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = primary,
                    )
                }
                c.str("title")?.let { Text(it, style = MaterialTheme.typography.headlineSmall) }
                c.str(
                    "subtitle",
                )?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                val badges = c.arr("badges")?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull?.takeIf(String::isNotBlank) }.orEmpty()
                if (badges.isNotEmpty()) {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        badges.forEach { badge ->
                            Text(
                                badge,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                                modifier =
                                    Modifier
                                        .clip(RoundedCornerShape(50))
                                        .background(primary.copy(alpha = 0.18f))
                                        .padding(horizontal = 8.dp, vertical = 3.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun BadgePrimitive(c: Component) {
    Surface(shape = RoundedCornerShape(50), color = MaterialTheme.colorScheme.secondaryContainer) {
        Text(
            text = c.str("label") ?: c.str("text").orEmpty(),
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun MetricPrimitive(c: Component) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(c.str("value") ?: "—", style = MaterialTheme.typography.headlineMedium)
            c.str(
                "label",
            )?.let { Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

private fun pairLabel(o: JsonObject): String = (o["key"] ?: o["label"]).let { (it as? JsonPrimitive)?.contentOrNull } ?: ""

private fun pairValue(o: JsonObject): String = (o["value"] as? JsonPrimitive)?.contentOrNull ?: ""

@Composable
private fun KeyValuePrimitive(c: Component) {
    val items = c.arr("items") ?: c.arr("pairs")
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items?.forEach { el ->
            (el as? JsonObject)?.let { o ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(pairLabel(o), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(pairValue(o), style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun TimelinePrimitive(c: Component) {
    val items = c.arr("items")
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items?.forEach { el ->
            (el as? JsonObject)?.let { o ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("•", color = MaterialTheme.colorScheme.primary)
                    Text(
                        ((o["title"] ?: o["label"] ?: o["text"]) as? JsonPrimitive)?.contentOrNull ?: "",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
    }
}

@Composable
private fun RatingPrimitive(c: Component) {
    val max = c.int("max") ?: 5
    val value = (c.dbl("value") ?: 0.0).toInt().coerceIn(0, max)
    Text(text = "★".repeat(value) + "☆".repeat(max - value), color = MaterialTheme.colorScheme.primary)
}

@Composable
private fun ProgressPrimitive(c: Component) {
    val raw = c.dbl("value") ?: c.dbl("progress") ?: 0.0
    val fraction = (if (raw > 1.0) raw / 100.0 else raw).toFloat().coerceIn(0f, 1f)
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        c.str("label")?.let { Text(it, style = MaterialTheme.typography.labelMedium) }
        LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun CollapsiblePrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = (if (expanded) "▼ " else "▶ ") + (c.str("title") ?: "Details"),
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded },
            )
            if (expanded) c.children.forEach { renderChild(it) }
        }
    }
}
