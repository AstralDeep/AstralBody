package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import coil.compose.AsyncImage
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component

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
