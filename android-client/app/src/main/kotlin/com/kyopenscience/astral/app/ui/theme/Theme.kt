package com.kyopenscience.astral.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Mirrors the web + Windows palette: indigo→purple accent, near-black bg,
// layered translucent surfaces. The client is dark-first to match the brand.
private val Indigo = Color(0xFF6366F1)
private val Purple = Color(0xFF8B5CF6)
private val Cyan = Color(0xFF06B6D4)
private val Bg = Color(0xFF0F1221)
private val SurfaceColor = Color(0xFF161A2E)
private val OnSurfaceColor = Color(0xFFE5E7EB)

private val AstralDarkColors =
    darkColorScheme(
        primary = Indigo,
        secondary = Purple,
        tertiary = Cyan,
        background = Bg,
        surface = SurfaceColor,
        onPrimary = Color.White,
        onBackground = OnSurfaceColor,
        onSurface = OnSurfaceColor,
    )

/** Material 3 theme for the AstralBody client (dark-first, mirroring the web/Windows look). */
@Composable
fun AstralTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AstralDarkColors, content = content)
}
