package com.kyopenscience.astral.app.ui

import com.kyopenscience.astral.core.chrome.TopBarControl
import kotlinx.serialization.json.JsonObject

/** Which glyph a server-owned top-bar action maps to (feature 044 T037). */
enum class TopBarIcon { SPARKLE, HISTORY, GENERIC }

/**
 * A resolved, renderable view of a server-owned top-bar action control (pulse /
 * timeline, feature 042/044 T037): its glyph, label, and the surface to open. A
 * control with no actionable surface returns null (nothing to render). Pure — no
 * Compose/Android — so the mapping is JVM-unit-tested; the composable only maps
 * [icon]→drawable and dispatches [surface] via `chrome_open`.
 */
data class TopBarActionView(
    val key: String,
    val label: String,
    val icon: TopBarIcon,
    val surface: String,
    val params: JsonObject,
)

fun topBarActionView(control: TopBarControl): TopBarActionView? {
    val action = control.action ?: return null
    val surface = action.surface.takeIf { it.isNotBlank() } ?: return null
    return TopBarActionView(
        key = control.key,
        label = control.label ?: surface,
        icon =
            when (control.icon) {
                "sparkle" -> TopBarIcon.SPARKLE
                "history" -> TopBarIcon.HISTORY
                else -> TopBarIcon.GENERIC
            },
        surface = surface,
        params = action.params,
    )
}
