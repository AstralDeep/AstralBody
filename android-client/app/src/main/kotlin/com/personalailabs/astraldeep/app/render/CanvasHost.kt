package com.personalailabs.astraldeep.app.render

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.personalailabs.astraldeep.app.render.renderers.ArtifactFooter
import com.personalailabs.astraldeep.core.sdui.Component

/**
 * Canvas-level context for the per-component artifact chrome (055 US4/US5):
 * the chat the export URLs are scoped to, and whether a read-only view has
 * mutations paused (hides Refine). Null renders bare components — chrome
 * surfaces and previews keep today's markup exactly.
 */
@Immutable
data class CanvasChrome(
    val chatId: String?,
    val mutationsLocked: Boolean,
)

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
    chrome: CanvasChrome? = null,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(items = components, key = { it.id ?: it.hashCode().toString() }) { component ->
            if (chrome == null) {
                renderer.render(component)
            } else {
                Column(modifier = Modifier.fillMaxWidth()) {
                    renderer.render(component)
                    ArtifactFooter(
                        c = component,
                        emit = renderer.emit,
                        download = renderer.download,
                        chatId = chrome.chatId,
                        mutationsLocked = chrome.mutationsLocked,
                    )
                }
            }
        }
    }
}
