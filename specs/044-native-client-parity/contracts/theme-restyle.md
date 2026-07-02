# Contract — Theme Tokens & Live Restyle (044)

**Satisfies**: FR-019, US5 | **Research**: R9

## 1. Token model (existing, now normative for natives)

Seven channels — `bg, surface, primary, secondary, text, muted, accent` — carried as hex
strings. Server presets: `midnight` (default), `daylight`, `ocean`, `sunset`, `forest`
(`webrender/chrome/surfaces/theme.py::PRESETS`). Persisted server-side in
`user_preferences.theme` as `{"preset": name}` or `{"colors": {…}}` or a single
`{"color_key", "color_value"}` patch.

## 2. Application sources (priority = latest event wins)

| Source | Frame/component | When |
|---|---|---|
| Boot | `user_preferences {preferences:{theme:…}}` | pushed at `register_ui` — **both natives must now handle this frame** (currently ignored by both) so the choice survives restart |
| Apply preset | `theme_apply {preset|colors|color_key+color_value, message}` component, arriving inside the re-pushed Theme `chrome_surface` after `chrome_theme_preset` | on surface apply |
| Fine-tune | client emits `ui_event save_theme {theme:{color_key, color_value}}` (server persists silently) + applies locally (local echo) | on color-picker edit |

`theme_apply` stops being a no-op on both natives: on encounter, apply the spec to the live
palette (Windows `_r_theme_apply`; Android `Input.kt` theme_apply branch feeding `UiState`).

## 3. Per-client application

### Windows (PySide6)
- `astral_client/theme.py` becomes a mutable `Palette` (7 channels + derived tokens
  `SURFACE_2/BORDER/PRIMARY_SOFT/VARIANT_COLORS/GRAD` computed from channels) +
  `build_stylesheet(palette)`.
- Apply = mutate palette → `app.setStyleSheet(build_stylesheet(…))` → repolish chrome widgets
  → re-render canvas from retained component dicts. Construction-baked inline styles migrate
  to palette-driven styling where practical.
- **Disclosure clause (FR-019)**: any element that only restyles on next render (e.g. existing
  transcript bubbles) is disclosed on the Theme surface ("some existing messages restyle as
  the conversation continues") — never silently ignored.

### Android (Compose)
- `UiState.themePalette` → `AstralTheme` derives `ColorScheme` at its single `MaterialTheme`
  call site (mapping per [data-model.md §7](../data-model.md)); recomposition restyles chrome
  + canvas live. Static defaults when unset. No disclosure needed.

### Web (baseline, unchanged)
- CSS custom properties `--astral-<channel>` set as RGB channel triplets (verified
  `client.js applyTheme`); already live.

## 4. Interactive color pickers (fine-tune parity)

`color_picker {color_key, value, label}` becomes interactive on both natives (native color
dialog), emitting `save_theme` per §2 and applying locally — replacing today's read-only
swatches. (Web already does this.)

## 5. Acceptance mapping

- US5.1: apply preset on each client → immediate visible restyle of chrome + canvas; restart
  → `user_preferences` re-applies it.
- US5.2: Windows discloses non-live elements on the surface; Android/web restyle fully.
