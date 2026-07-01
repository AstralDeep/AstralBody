package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** Register the data primitives (US2): list, table, tabs, chat_history, skeleton. */
fun Renderer.registerDataRenderers(): Renderer =
    apply {
        register("list") { c -> ListPrimitive(c) { render(it) } }
        register("table") { c -> TablePrimitive(c) }
        register("tabs") { c -> TabsPrimitive(c) { render(it) } }
        register("chat_history") { c -> ChatHistoryPrimitive(c) }
        register("skeleton") { c -> SkeletonPrimitive(c) }
    }

@Composable
private fun ListPrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (c.children.isNotEmpty()) {
            c.children.forEach { renderChild(it) }
        } else {
            c.strList("items").forEach { item ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("•")
                    Text(item, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun TablePrimitive(c: Component) {
    val headers = c.strList("headers")
    val rows = c.rows("rows")
    Column(modifier = Modifier.fillMaxWidth()) {
        if (headers.isNotEmpty()) {
            Row(modifier = Modifier.padding(vertical = 4.dp)) {
                headers.forEach { h ->
                    Text(h, modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
                }
            }
            HorizontalDivider()
        }
        rows.forEach { row ->
            Row(modifier = Modifier.padding(vertical = 4.dp)) {
                row.forEach { cell ->
                    Text(cell, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun TabsPrimitive(
    c: Component,
    renderChild: @Composable (Component) -> Unit,
) {
    val tabs = c.arr("tabs")?.mapNotNull { it as? JsonObject } ?: emptyList()
    if (tabs.isEmpty()) return
    var selected by remember { mutableIntStateOf(0) }
    Column {
        TabRow(selectedTabIndex = selected.coerceIn(0, tabs.size - 1)) {
            tabs.forEachIndexed { i, tab ->
                Tab(
                    selected = i == selected,
                    onClick = { selected = i },
                    text = { Text((tab["label"] as? JsonPrimitive)?.contentOrNull ?: "Tab ${i + 1}") },
                )
            }
        }
        val current = tabs.getOrNull(selected) ?: tabs.first()
        Column(modifier = Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Component.listFromJson(current["content"] as? JsonArray).forEach { renderChild(it) }
        }
    }
}

@Composable
private fun ChatHistoryPrimitive(c: Component) {
    val items = c.arr("items") ?: c.arr("messages")
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items?.mapNotNull { it as? JsonObject }?.forEach { o ->
            val role = (o["role"] as? JsonPrimitive)?.contentOrNull ?: ""
            val content = (o["content"] as? JsonPrimitive)?.contentOrNull ?: ""
            Text(text = if (role.isNotEmpty()) "$role: $content" else content, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun SkeletonPrimitive(c: Component) {
    // A `skeleton` is a LOADING placeholder. The native canvas commits only FINAL
    // content (the app shows its own skeleton while a query is in flight), so a
    // skeleton reaching the canvas is stray — a placeholder the model never filled.
    // Render nothing rather than dead gray bars. (The reducer also drops top-level
    // skeletons so they leave no gap; this handles any nested ones.)
}
