# Settings cog + settings menu parity — verification (2026-07-02)

## What was broken

1. **Android settings cog** (`android-client/app/src/main/res/drawable/ic_settings.xml`)
   The vector path was a hand-truncated Feather gear: the entire right-side tooth
   segment (`…V9 a1.65,1.65 0 0 0 1.51,1 H21 a2,2 … h-0.09 …`) had been dropped and
   the outline closed with a straight `V15 z` chord — rendering a lopsided spiky
   star with a flat right edge. The old `scaleX/Y=0.88` inset group was a
   misdiagnosed "clipping" fix for that missing geometry. **Fix:** transcribed the
   exact Feather gear the web top bar ships (`webrender/chrome/topbar.py
   _GEAR_SVG`, hub circle + full 8-tooth outline), removed the inset hack.
   Pre-build render diff vs the web glyph: identical (see
   `cog-old-vs-fixed-vs-web.png`; on-device: `cog-on-device-zoom.png`).
   Note: the emulator had been running a stale APK, which is why earlier "fixes"
   never appeared — the icon is fixed in source and verified on-device now.

2. **Settings pages (both native clients)** — the menu itself is fully
   server-owned (`webrender/chrome/menu_model.py` → `chrome_menu`) and both
   clients already render it, but page content had real defects:
   - **Android** `container` renderer ignored `direction:"row"` and the
     astralprims `css` field → Theme preset swatch strips rendered as blank
     space; Personalization tabs stacked vertically. Form action buttons
     rendered in a non-wrapping Row → the LLM form's "Save" squeezed into a
     vertical letter stack.
   - **Windows** `_r_container` had the same direction/css gaps; switching
     surfaces stacked pages on top of each other (`SurfaceDialog._clear_body`
     relied on `deleteLater()` alone — stale widgets kept painting during
     nested/synthetic event processing); Qt swallowed `&` in every
     server-provided label ("Agents  permissions", "Attachments  files"); the
     ACCOUNT/HELP group headers were invisible (`QMenu.addSection` text is
     dropped by Fusion).

## Changes

Android (`android-client/`):
- `res/drawable/ic_settings.xml` — correct full Feather gear path.
- `render/renderers/Attrs.kt` — `obj()` accessor; minimal native `css` subset
  (`cssBackground`/`cssHeightPx`/`cssFlex`); pure `containerMode()` rules.
- `render/renderers/Basic.kt` — `container` honors `direction:"row"`
  (proportional swatch Row / wrapping FlowRow) and css-styled leaf boxes.
- `render/renderers/Input.kt` — ParamPicker action buttons wrap (FlowRow).
- NEW `app/src/test/...renderers/ContainerCssTest.kt` (7 JVM tests).

Windows (`windows-client/`):
- `astral_client/renderer.py` — `_r_container` direction/css support
  (`_css_of`/`_css_px`/`_css_flex`/`_css_swatch`); `_btn_label()` escapes `&`
  at every server-label button site.
- `astral_client/app.py` — `SurfaceDialog._clear_body` reparents before
  `deleteLater()` (no page stacking); `TopBar._rebuild_menu` renders visible
  ACCOUNT/HELP headers (styled QWidgetAction) and literal `&` in items.
- `tests/test_renderer.py` +6, `tests/test_message_routing.py` +2 regression
  tests; NEW `tests/screenshot_settings.py` parity-evidence harness.

Backend: **no changes** (menu model + all six surfaces already served native
components; chrome suite run as regression proof).

## Green tests

| Suite | Result |
|---|---|
| Android `:core:test` (JVM) | 58 tests, 0 failures |
| Android `:app:testDebugUnitTest` (JVM, incl. new ContainerCssTest) | 81 tests, 0 failures |
| Android `:app:connectedDebugAndroidTest` on emulator-5554 (incl. ChromeMenuUiTest — dropdown shows every model item) | 10 tests, 0 failures |
| Android `ktlintCheck` (`:app` + `:core`) | pass |
| Windows `pytest tests -q` | 235 passed |
| Backend `pytest tests/chrome -q` (in `astralbody` container) | 269 passed |

Android builds/tests ran with the updated toolchain (AGP 9.2.1 / Kotlin 2.2.10 /
Gradle 9.6) — `BUILD SUCCESSFUL`.

## Round 2 (same day) — settings-page behavior fixes

Three user-reported defects, all verified fixed on-device (`fixes-round-2/`):

1. **LLM settings: raw HTML error + stuck form.** A mistyped Base URL dumped
   the endpoint's `<!doctype html>…` page into the notice, and after a failed
   submit the form stayed on "Saving…" with its buttons gone (a re-delivered
   component equal to its predecessor kept stale Compose state).
   Fixes: `llm.py _failure_notice` now maps `error_class` to actionable copy
   and sanitizes upstream snippets (an HTML page is never dumped);
   `SurfaceContent` keys items per delivered `chrome_surface` (state reset +
   scroll-to-top so the notice is seen); ParamPicker adds a 12 s "Saving…"
   failsafe. Evidence: `l3-error-friendly.png` (friendly error at top, all
   buttons recovered, values retained).
2. **Theme preset didn't restyle the app.** The `theme_apply` side effect only
   existed in the web notice HTML — native re-renders never carried it.
   `theme.py components()` now leads with a `theme_apply` of the effective
   theme (skipped when nothing saved); Android's palette mapping also fills
   the M3 `surfaceContainer*`/`secondaryContainer` roles so light presets
   restyle cards/menus too, and `chrome_events._strip_html` keeps notice
   sentences spaced. Evidence: `t2-daylight-applied.png` (instant light
   restyle), `t3-daylight-boot.png` (persists across restart),
   `t5-midnight-back.png` (round-trip back, "Midnight theme saved. Theme
   applied").
3. **User-guide buttons "did nothing".** They worked at the wire level — but
   every button rendered as an identical filled primary (Android ignored
   `variant`), the newly delivered section body sat below 13 TOC chips, and
   the list never scrolled: nothing visibly changed. Fixes: Android
   `ButtonPrimitive` honors `primary`/`secondary`/`danger`;
   `guide.py components()` is content-first (TOC after the body) for BOTH
   native clients; each surface delivery scrolls to top. Evidence:
   `g4/g5/g6` (Android: content-first, tonal inactive chips, visible section
   switch), `win-guide-content-first.png` (Windows twin).

4. **Attachments library: Attach button "didn't work".** `attach_existing`
   staged the chip correctly — but invisibly: the user stayed on the surface
   with zero feedback, and leaving via "+ New" wiped the chip. Attach now
   returns to the chat with the staged chip visible and a confirmation banner
   (the native twin of the web modal closing). Evidence:
   `a2-attachments-surface.png` → `a3-attached-back-in-chat.png`.
   Tests: AttachExistingTest +3 (navigate-back, duplicate, malformed payload).

Round-2 suites: backend `tests/chrome` **275 passed** (6 new: sanitizer,
HTML-page notice, theme_apply presence/shape/absence, guide ordering);
Windows **235 passed**; Android `:core:test` 58 + `:app:testDebugUnitTest` 81
+ ktlint — all green with the round-2 code. The Windows evidence harness
gained `grab_opaque` (grabs composited over the palette background —
`QWidget.grab` doesn't paint the top-level backing store, which previewed as
a "washed out" dialog; capture artifact only, not a product defect).

## Screenshot evidence (this folder)

- `cog-old-vs-fixed-vs-web.png` — old broken path vs fixed vs web reference.
- `cog-on-device-zoom.png` — the fixed cog rendered on the emulator.
- `settings-parity-android-vs-windows.png` — side-by-side: Settings menu, LLM
  settings, Personalization, Theme, User guide, Agents & permissions, Audit log
  on both clients (same server model, same content).
- `android/`, `win/` — raw captures (Android also includes the full-page
  contact sheet and the final installed-state shot).
