package com.kyopenscience.astral.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

// Mirrors the web + Windows palette: indigo→purple accent, near-black bg,
// layered translucent surfaces. The client is dark-first to match the brand.

/**
 * Brand palette exposed for the surfaces that need explicit colors beyond the
 * Material scheme (the sign-in screen's gradient, the skeleton shimmer, the
 * canvas/messages chrome). Kept in one place so every surface stays on-brand.
 */
object AstralColors {
    val Indigo = Color(0xFF6366F1)
    val Purple = Color(0xFF8B5CF6)
    val Cyan = Color(0xFF06B6D4)
    val Bg = Color(0xFF0F1221)
    val BgElevated = Color(0xFF12162A)
    val Surface = Color(0xFF161A2E)
    val SurfaceVariant = Color(0xFF1E2338)
    val Border = Color(0xFF2A2F49)
    val Text = Color(0xFFE5E7EB)
    val Muted = Color(0xFF9AA1B9)

    /** Signature indigo→purple sweep used on the brand button and accents. */
    val AccentBrush = Brush.horizontalGradient(listOf(Indigo, Purple))

    /** A deep vertical wash for full-screen backdrops (sign-in). */
    val BackdropBrush =
        Brush.verticalGradient(listOf(Color(0xFF0F1221), Color(0xFF141A33), Color(0xFF0F1221)))
}

private val AstralDarkColors =
    darkColorScheme(
        primary = AstralColors.Indigo,
        onPrimary = Color.White,
        secondary = AstralColors.Purple,
        tertiary = AstralColors.Cyan,
        background = AstralColors.Bg,
        onBackground = AstralColors.Text,
        surface = AstralColors.Surface,
        onSurface = AstralColors.Text,
        surfaceVariant = AstralColors.SurfaceVariant,
        onSurfaceVariant = AstralColors.Muted,
        outline = AstralColors.Border,
        outlineVariant = AstralColors.Border,
    )

/** Material 3 theme for the AstralBody client (dark-first, mirroring the web/Windows look). */
@Composable
fun AstralTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AstralDarkColors, content = content)
}
