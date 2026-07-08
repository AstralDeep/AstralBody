package com.personalailabs.astraldeep.app.render.renderers

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import coil.compose.AsyncImage
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.core.sdui.Component

/** Register media primitives (US2). `image` is a native improvement over the
 *  Windows placeholder; `audio` stays excluded (placeholder) until added. */
fun Renderer.registerMediaRenderers(): Renderer =
    apply {
        register("image") { c -> ImagePrimitive(c) }
    }

@Composable
private fun ImagePrimitive(c: Component) {
    AsyncImage(
        model = c.str("url") ?: c.str("src"),
        contentDescription = c.str("alt") ?: c.str("caption"),
        modifier = Modifier.fillMaxWidth(),
    )
}
