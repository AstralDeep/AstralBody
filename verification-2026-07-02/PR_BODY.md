## Summary

Fixes the long-standing broken Android settings cog and brings the settings menu + every settings page to full, verified parity across web / Windows / Android — plus four settings-surface UX bugs found while verifying (raw-HTML LLM errors + stuck form, theme presets not restyling the running app, "dead" user-guide buttons, and the attachments library's Attach button giving no feedback).

### Root causes fixed

| Symptom | Root cause | Fix |
|---|---|---|
| Cog renders as a lopsided spiky star | `ic_settings.xml` gear path had its right-side tooth segment hand-truncated (closed with a flat `V15 z` chord); the old 0.88 inset group was a misdiagnosed "clipping" fix | Exact Feather gear the web ships (`topbar.py _GEAR_SVG`), inset hack removed |
| Theme swatches blank / tabs stacked on native | Both native container renderers ignored `direction:"row"` and the astralprims `css` field | Minimal css subset (background/height/flex) + row handling on both clients, pure unit-tested rules |
| LLM form: raw `<!doctype html>` error, then stuck on "Saving…" with no buttons | Notice embedded the upstream body verbatim; a re-delivered component equal to its predecessor kept stale Compose state | `error_class`-specific actionable hints + sanitized snippets server-side; per-delivery item-state reset + scroll-to-top + 12 s failsafe on Android |
| Theme preset saved but app never restyled (native) | The `theme_apply` side effect only existed inside the web notice HTML | `theme.components()` leads with a `theme_apply` of the effective theme; Android palette mapping also fills M3 `surfaceContainer*`/`secondaryContainer` roles so light presets restyle fully |
| Guide buttons "do nothing" | They worked on the wire — but every variant rendered identical (no active state), content sat below 13 TOC chips, and the list never scrolled | Button `variant` support (primary/secondary/danger), content-first guide for native surfaces, scroll-to-top per delivery |
| Attach (library) button "doesn't work" | `attach_existing` staged the chip invisibly and left the user on the surface (leaving via **+ New** wiped it) | Attach returns to the chat with the chip visible + a confirmation banner |
| Windows menu: "Agents  permissions", no ACCOUNT/HELP headers; surfaces stacked on switch | Qt mnemonic `&`-swallowing; Fusion drops `addSection` text; `_clear_body` relied on `deleteLater` alone | `&&` escaping at every server-label site, styled header actions, reparent-before-delete |

Windows/Android render identical settings menus and pages from the single server-owned model — side-by-side evidence in `verification-2026-07-02/` (local, untracked): `settings-parity-android-vs-windows.png`, `cog-old-vs-fixed-vs-web.png`, and `fixes-round-2/` on-device captures of all four behavior fixes.

### Tests (all green)

| Suite | Result |
|---|---|
| Backend `tests/chrome` (in the astralbody container) | **275 passed** (+6 new) |
| Windows client `pytest tests -q` | **235 passed** (+8 new) |
| Android `:core:test` / `:app:testDebugUnitTest` | **58 / 84+ passed** (new ContainerCssTest, extended AttachExistingTest) |
| Android `:app:connectedDebugAndroidTest` (emulator) | **10 passed** (incl. menu-matches-web UI test) |
| ktlint (`:app` + `:core`) / ruff (changed files) | clean |

### Notes for review

- **Zero new runtime dependencies** on any tier (Constitution V). No schema, no wire changes — `chrome_surface`/`theme_apply` are existing frame/component types.
- Web `render()` paths untouched except `chrome_events._strip_html` (native notice text: tags→spaces so sentences don't fuse) — web modals unaffected.
- First commit is the local AGP 9.2.1 / Kotlin 2.2.10 toolchain bump (Gradle 9.6 wrapper was already committed); every Android build/test above ran on it.
- `windows-client/tests/screenshot_settings.py` is a new evidence harness following the 044 T052 conventions (native fonts, tofu gate, opaque composited grabs).
- Windows client rebuilt from this branch: `dist/AstralBody.exe` (52 MB, PyInstaller 6.21 via `.venv`), smoke-launched against the dev orchestrator.
