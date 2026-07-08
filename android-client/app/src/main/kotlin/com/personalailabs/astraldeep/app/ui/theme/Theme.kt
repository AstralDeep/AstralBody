package com.personalailabs.astraldeep.app.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

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
    val Surface = Color(0xFF1A1E2E)
    val SurfaceVariant = Color(0xFF1E2338)
    val Border = Color(0xFF2A2F49)
    val Text = Color(0xFFF3F4F6)
    val Muted = Color(0xFF9CA3AF)

    /** Signature indigo→purple 135° diagonal sweep (top-left → bottom-right)
     *  used on the brand button and accents — matches the web `--astral-accent`
     *  linear-gradient(135deg, …). */
    val AccentBrush =
        Brush.linearGradient(listOf(Indigo, Purple), start = Offset.Zero, end = Offset.Infinite)

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

/**
 * The seven theme channels (feature 044 US5) — hex strings mirroring the backend
 * theme surface (`webrender/chrome/surfaces/theme.py`) and `client.js` PRESETS. A
 * null [com.personalailabs.astraldeep.app.ui.UiState.themePalette] means the brand dark
 * scheme; a non-null palette drives [paletteToColorScheme] so a theme change
 * restyles the whole app live (recomposition), matching the web/Windows clients.
 */
data class ThemePalette(
    val bg: String,
    val surface: String,
    val primary: String,
    val secondary: String,
    val text: String,
    val muted: String,
    val accent: String,
) {
    /** Overlay a single channel (a `color_key`/`color_value` change) onto this palette. */
    fun withChannel(
        key: String,
        hex: String,
    ): ThemePalette =
        when (key) {
            "bg" -> copy(bg = hex)
            "surface" -> copy(surface = hex)
            "primary" -> copy(primary = hex)
            "secondary" -> copy(secondary = hex)
            "text" -> copy(text = hex)
            "muted" -> copy(muted = hex)
            "accent" -> copy(accent = hex)
            else -> this
        }

    /** The current hex for a channel key (null for an unknown key). */
    fun channel(key: String): String? =
        when (key) {
            "bg" -> bg
            "surface" -> surface
            "primary" -> primary
            "secondary" -> secondary
            "text" -> text
            "muted" -> muted
            "accent" -> accent
            else -> null
        }
}

/** The five named presets — hexes match backend theme.py PRESETS + client.js. */
val THEME_PRESETS: Map<String, ThemePalette> =
    mapOf(
        "midnight" to ThemePalette("#0F1221", "#1A1E2E", "#6366F1", "#8B5CF6", "#F3F4F6", "#9CA3AF", "#06B6D4"),
        "daylight" to ThemePalette("#F8FAFC", "#FFFFFF", "#4F46E5", "#7C3AED", "#1E293B", "#64748B", "#0891B2"),
        "ocean" to ThemePalette("#0C1222", "#132038", "#0EA5E9", "#06B6D4", "#E2E8F0", "#94A3B8", "#2DD4BF"),
        "sunset" to ThemePalette("#1C1017", "#2D1B24", "#F97316", "#EF4444", "#FEF2F2", "#A8A29E", "#FBBF24"),
        "forest" to ThemePalette("#0F1A14", "#1A2E22", "#22C55E", "#10B981", "#ECFDF5", "#86EFAC", "#A3E635"),
    )

/** The root default (matches backend `_DEFAULT_PRESET`), the overlay base for partial specs. */
private val DEFAULT_PALETTE = THEME_PRESETS.getValue("midnight")

/**
 * Candidate hex values offered when tapping an interactive `color_picker` for
 * channel [key] (T050): the current value first, then each preset's value for that
 * channel, de-duplicated. Gives a meaningful on-brand choice without a full picker.
 */
fun channelSwatchOptions(
    key: String,
    current: String?,
): List<String> {
    val cur = current?.takeIf { hexToColor(it) != null }
    val fromPresets = THEME_PRESETS.values.mapNotNull { it.channel(key) }
    return (listOfNotNull(cur) + fromPresets).distinct()
}

/** Parse `#RRGGBB` (or bare `RRGGBB`) into an opaque [Color]; null when malformed. */
fun hexToColor(hex: String?): Color? {
    val s = (hex ?: "").trim().removePrefix("#")
    if (s.length != 6 || s.any { it.digitToIntOrNull(16) == null }) return null
    return Color(0xFF000000L or s.toLong(16))
}

/**
 * Fold a `theme_apply` / `preferences.theme` spec onto [current] — an explicit
 * `colors` map wins (the backend sends the fully-resolved channel map alongside
 * the preset name, so an unrecognized preset still applies), else a named `preset`
 * falls back to the local [THEME_PRESETS] table (old servers), else a single
 * `color_key`+`color_value` overlays one channel. Returns [current] unchanged
 * when the spec carries nothing usable.
 */
fun themePaletteForSpec(
    current: ThemePalette?,
    spec: JsonObject?,
): ThemePalette? {
    if (spec == null) return current
    val base = current ?: DEFAULT_PALETTE
    val colors = spec["colors"] as? JsonObject
    if (!colors.isNullOrEmpty()) {
        var next = base
        for ((k, v) in colors) {
            val hex = (v as? JsonPrimitive)?.contentOrNull ?: continue
            if (hexToColor(hex) != null) next = next.withChannel(k, hex)
        }
        return next
    }
    val preset = (spec["preset"] as? JsonPrimitive)?.contentOrNull
    if (preset != null && THEME_PRESETS.containsKey(preset)) return THEME_PRESETS[preset]
    val key = (spec["color_key"] as? JsonPrimitive)?.contentOrNull
    val value =
        (spec["color_value"] as? JsonPrimitive)?.contentOrNull
            ?: (spec["value"] as? JsonPrimitive)?.contentOrNull
    if (key != null && value != null && hexToColor(value) != null) return base.withChannel(key, value)
    return current
}

/**
 * Build a Material [ColorScheme] from a [ThemePalette]: bg→background,
 * surface→surface(+variant), primary/secondary→primary/secondary, text→on-bg/on-
 * surface, muted→onSurfaceVariant, accent→tertiary. Any malformed channel falls
 * back to the brand dark value, so a bad hex never blanks the UI.
 */
fun paletteToColorScheme(palette: ThemePalette): ColorScheme {
    val base = AstralDarkColors
    val surface = hexToColor(palette.surface) ?: base.surface
    val text = hexToColor(palette.text) ?: base.onSurface
    val secondary = hexToColor(palette.secondary) ?: base.secondary
    return darkColorScheme(
        primary = hexToColor(palette.primary) ?: base.primary,
        onPrimary = base.onPrimary,
        secondary = secondary,
        tertiary = hexToColor(palette.accent) ?: base.tertiary,
        background = hexToColor(palette.bg) ?: base.background,
        onBackground = hexToColor(palette.text) ?: base.onBackground,
        surface = surface,
        onSurface = text,
        surfaceVariant = surface,
        onSurfaceVariant = hexToColor(palette.muted) ?: base.onSurfaceVariant,
        outline = base.outline,
        outlineVariant = base.outlineVariant,
        // M3 components (Card, DropdownMenu, tonal buttons) actually draw on
        // the container roles — left at the dark baseline they kept cards and
        // menus DARK inside a light preset, so Daylight looked half-applied.
        surfaceContainerLowest = surface,
        surfaceContainerLow = surface,
        surfaceContainer = surface,
        surfaceContainerHigh = surface,
        surfaceContainerHighest = surface,
        secondaryContainer = tint(secondary, surface, 0.24f),
        onSecondaryContainer = text,
    )
}

/** [fg] composited over [bg] at [alpha] — a subtle on-palette tint for tonal roles. */
private fun tint(
    fg: Color,
    bg: Color,
    alpha: Float,
): Color =
    Color(
        red = fg.red * alpha + bg.red * (1 - alpha),
        green = fg.green * alpha + bg.green * (1 - alpha),
        blue = fg.blue * alpha + bg.blue * (1 - alpha),
    )

/**
 * Material 3 theme for the AstralBody client (dark-first, mirroring the web/Windows
 * look). When [palette] is non-null the scheme is derived from it (US5 live
 * restyle); a null palette uses the default brand dark scheme.
 */
@Composable
fun AstralTheme(
    palette: ThemePalette? = null,
    content: @Composable () -> Unit,
) {
    val scheme = palette?.let { paletteToColorScheme(it) } ?: AstralDarkColors
    MaterialTheme(colorScheme = scheme, content = content)
}
