package com.personalailabs.astraldeep.app.ui.theme

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Feature 044 T050 — the pure theme model: hex parsing, spec folding, scheme build. */
class ThemeTest {
    @Test
    fun hex_parses_valid_and_rejects_malformed() {
        assertNotNull(hexToColor("#0F1221"))
        assertNotNull(hexToColor("0F1221"))
        assertNull(hexToColor("#12"))
        assertNull(hexToColor("nothex"))
        assertNull(hexToColor(null))
    }

    @Test
    fun a_preset_spec_replaces_the_whole_palette() {
        assertEquals(THEME_PRESETS["ocean"], themePaletteForSpec(null, buildJsonObject { put("preset", "ocean") }))
    }

    @Test
    fun a_colors_spec_overlays_named_channels_onto_current() {
        val start = THEME_PRESETS.getValue("midnight")
        val p = themePaletteForSpec(start, buildJsonObject { putJsonObject("colors") { put("primary", "#123456") } })
        assertEquals("#123456", p?.primary)
        assertEquals(start.bg, p?.bg) // an untouched channel is preserved
    }

    @Test
    fun a_single_key_spec_overlays_one_channel() {
        val p =
            themePaletteForSpec(
                THEME_PRESETS.getValue("midnight"),
                buildJsonObject {
                    put("color_key", "accent")
                    put("color_value", "#ABCDEF")
                },
            )
        assertEquals("#ABCDEF", p?.accent)
    }

    @Test
    fun explicit_colors_win_over_an_unknown_preset_name() {
        // The backend sends the fully-resolved channel map alongside the preset
        // name — a preset the client doesn't know must still apply via `colors`.
        val p =
            themePaletteForSpec(
                null,
                buildJsonObject {
                    put("preset", "solarpunk")
                    putJsonObject("colors") {
                        put("bg", "#101010")
                        put("surface", "#202020")
                        put("primary", "#303030")
                        put("secondary", "#404040")
                        put("text", "#505050")
                        put("muted", "#606060")
                        put("accent", "#707070")
                    }
                },
            )
        assertEquals(
            ThemePalette("#101010", "#202020", "#303030", "#404040", "#505050", "#606060", "#707070"),
            p,
        )
    }

    @Test
    fun explicit_colors_win_over_a_known_preset_name() {
        val p =
            themePaletteForSpec(
                THEME_PRESETS.getValue("midnight"),
                buildJsonObject {
                    put("preset", "ocean")
                    putJsonObject("colors") { put("primary", "#123456") }
                },
            )
        assertEquals("#123456", p?.primary)
    }

    @Test
    fun an_unknown_preset_or_empty_spec_leaves_current_unchanged() {
        val start = THEME_PRESETS.getValue("forest")
        assertEquals(start, themePaletteForSpec(start, buildJsonObject { put("preset", "chartreuse") }))
        assertEquals(start, themePaletteForSpec(start, JsonObject(emptyMap())))
        assertEquals(start, themePaletteForSpec(start, null))
    }

    @Test
    fun palette_maps_to_the_expected_color_scheme_channels() {
        val scheme = paletteToColorScheme(THEME_PRESETS.getValue("ocean"))
        assertEquals(hexToColor("#0EA5E9"), scheme.primary)
        assertEquals(hexToColor("#0C1222"), scheme.background)
        assertEquals(hexToColor("#2DD4BF"), scheme.tertiary)
    }

    @Test
    fun channel_swatch_options_lead_with_current_and_include_presets() {
        val opts = channelSwatchOptions("bg", "#000000")
        assertEquals("#000000", opts.first())
        assertTrue(opts.contains(THEME_PRESETS.getValue("ocean").bg))
    }
}
