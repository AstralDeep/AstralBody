package com.kyopenscience.astral.app.render

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.core.sdui.Component

/**
 * The SDUI canvas: a virtualized column of components keyed by component identity,
 * so in-place upserts / streaming updates preserve item state and scroll position
 * (the Compose analogue of the Windows Canvas keyed by `component_id`).
 */
@Composable
fun CanvasHost(
    components: List<Component>,
    renderer: Renderer,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(items = components, key = { it.id ?: it.hashCode().toString() }) { component ->
            renderer.render(component)
        }
    }
}
