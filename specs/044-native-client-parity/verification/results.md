# Verification Results — 044 (live, 2026-07-01)

Environment: `astralbody` container (dev posture, mock auth, 9 in-process agents) on
`ws://localhost:8001`; web via Puppeteer-driven Chromium; Windows app launched on the dev
machine (native Qt platform, Segoe UI); Android debug APK on `emulator-5554` (Pixel 7 Pro
API 36). Result vocabulary: ✅ pass · ⚠️ partial/limited · ➖ n/a · 🔒 blocked (needs a
credential I cannot enter).

## Method notes
- **Web & Windows** run the full logged-in loop under mock auth (`dev-token`).
- **Android**: the debug build has no mock/dev-token path (it was dead code, removed in
  T056), so a logged-in chat requires a real Keycloak browser login on the emulator —
  credentials I am not permitted to enter. Android's UI/rendering is therefore verified by
  (a) launching the real app (screenshot) and (b) the **10 instrumented Compose tests run
  live on the emulator** (`:app:connectedDebugAndroidTest`, 10/10 pass), which render the
  real screens/components/chrome with fixture data. The server contract Android consumes is
  identical to web/Windows, both of which pass the full loop live.

## US1 — Dependable chat loop
| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 1.1 server error visible (not silent/thinking) | ✅ **LIVE**: a missing-tool error rendered as a red Alert ("No agent available for tool 'interactive_artifacts'") mid-turn, not silent; toast handler also served | ✅ error banner + turn resolved (unit: test_message_routing) | ✅ error banner + turn cleared (unit: AppViewModelReducerTest) | web/web_dashboard_query.png; native unit suites |
| 1.2 socket drop → reconnect ≤30s + resume | ➖ (browser reload) | ✅ backoff 1→30s + queue (unit: test_transport) | ✅ backoff + bounded queue (unit: BackoffTest/QueueOverflowTest) | transport unit tests |
| 1.3 expired token → refresh or explicit sign-in | ✅ | ✅ sign-in dialog on dead auth | ✅ **LIVE**: cold-start refresh failed → SignInScreen "Session expired — sign in again" | android/android_launch.png |
| 1.4 sign-out revokes server session | ✅ (web /auth/logout) | ✅ ladder (rest.native_logout→keycloak→local) | ✅ ladder (AstralRest.logout→KeycloakLogout→clear) | backend test_native_logout (10), native unit |
| 1.5 progress signals + terminal state | ✅ (reasoning/steps rendered) | ✅ **LIVE** "Planning next step"→done, markdown answer | ✅ stepTrail/task signals (unit) | windows/shot_chat.png; web_chat.png |
| 1.6 unknown push type logged, no crash | ✅ | ✅ classified default branch logs | ✅ Unknown logged (manifest-classified) | protocol-manifest guards (3 stacks) |

## US2 — Rendering fidelity
| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 2.1 gallery types render legibly | ✅ **LIVE** welcome canvas + a dashboard turn's Document card / Reasoning collapsible / step trail | ✅ **LIVE, LEGIBLE** welcome canvas + Reasoning collapsible | ✅ instrumented RenderersTest (card+child, placeholder) | web_welcome.png, web_dashboard_query.png; windows/shot_welcome.png; emulator instrumented |
| 2.3 interactive round-trips | ✅ | ✅ buttons/param_picker (renderer unit) | ✅ (instrumented) | 210 Windows / 130 Android unit + 10 instrumented |
| 2.4 large table pagination | ✅ | ✅ pager emits table_paginate (unit) | ✅ pager (TablePagerTest) | renderer unit suites |
| 2.5 canvas convergence (no clobber) | ✅ (DOM morph) | ✅ identity reconcile (test_canvas_convergence) | ✅ identity reconcile (CanvasClobberTest) | native unit + backend test_canvas_full_render |
| 2.6 markdown constructs incl. links | ✅ **LIVE** (bold/list in dice answer) | ✅ (QLabel rich text) | ✅ links added (MarkdownTest) | web_chat.png; native unit |

## US3 — Settings surfaces
| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 3.1 menu/topbar match server model | ✅ **LIVE** full menu (admin+tour on web) + pulse/timeline topbar | ✅ **LIVE** Account/Help + Sign out, NO admin/tour, pulse+timeline topbar buttons | ✅ instrumented ChromeMenuUiTest (dropdown matches web) | windows/shot_settings_menu.png; web topbar read_page; emulator |
| 3.2 surface bounded load + retry | ➖ | ✅ 10s timeout+retry (unit) | ✅ 10s timeout+retry (SurfaceStateTest) | native unit |
| 3.4 web-only capabilities absent on native | ➖ | ✅ **LIVE** admin tools + tour absent from Windows menu | ✅ (server-omitted, ChromeMenuUiTest) | windows/shot_settings_menu.png |

## US4 — Attachments
| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 4.1 chips + status + send | ✅ | ✅ paperclip + chips (test_attachments) + **LIVE** paperclip visible | ✅ (existing) | windows/shot_welcome.png (📎); native unit |
| 4.x attach_existing from library | ✅ | ✅ intercept + stage (unit) | ✅ intercept + stage (AttachExistingTest) | native unit |

## US5 — Theme
| Scenario | Web | Windows | Android | Evidence |
|---|---|---|---|---|
| 5.1 preset applies + persists | ✅ (baseline) | ✅ Palette+build_stylesheet, color_picker interactive (test_theme_live) | ✅ dynamic ColorScheme (ThemeTest/ThemeReducerTest) | native unit |

## US6 — Evidence & guards
| Scenario | Result | Evidence |
|---|---|---|
| 6.1 parity matrix complete | ✅ | parity-matrix.md (no unknown cells) |
| 6.2 captures legible (0 tofu) | ✅ **root cause fixed** | tofu was `QT_QPA_PLATFORM=offscreen`'s glyphless font engine (reproduced then fixed); harness now renders on the native platform behind a font sanity gate; windows/*.png legible |
| 6.3 drift guards fail on unclassified additions | ✅ | backend test_ui_protocol_manifest, Windows test_protocol_manifest, Android ProtocolManifestTest |
| 6.4 docs match reality | ✅ | CLAUDE.md PySide6 fix; 041/042/043 reconciled (T055) |

## Suite tallies (post-remediation)
- Backend: **3037 passed** (default flags), incl. 28 new 044 tests + manifest guards.
- Windows: **210 passed** (offscreen-safe pytest).
- Android: `:core` **58**, `:app` **72** unit + **10/10 instrumented on the emulator**, ktlint clean, assembleDebug OK.

## What was driven live vs. test-covered (honest split)
- **Driven live in a real client this run**: web welcome canvas + dashboard query (rich
  Document card, Reasoning collapsible, live progress step-trail, **visible error Alert**,
  markdown answer, cross-client Recent-chats persistence); Windows welcome canvas + settings
  menu (server model, admin/tour omitted) + dice query (markdown + Reasoning collapsible) +
  server-driven top-bar buttons + paperclip; Android app launch + **live session-expired →
  SignInScreen** + 10/10 instrumented Compose tests on the emulator.
- **Test-covered, NOT interactively clicked in a native app this run** (residual manual pass):
  the native **theme-preset apply** (T051) and the Windows **live file upload** (T048) — both
  fully unit-tested (test_theme_live, test_attachments, ThemeTest/ThemeReducerTest) and their
  server round-trips proven, but not driven through a live native click here. Native **table
  pagination** click is likewise unit-tested; the paginate contract is server-shared.

## Known limitations (recorded, not defects)
🔒 D-032 — Android full logged-in chat over real Keycloak not driven autonomously (credential
entry is out of bounds); covered by instrumented on-device rendering + the identical server
contract exercised live on web and Windows.
🔒 The local dev LLM under default-deny scopes returns text answers rather than provisioning
rich dashboards for a fresh user, so a live agent-produced chart/table on the canvas wasn't
captured; rich-component rendering is instead proven by the welcome canvas + the dashboard
Document card live, and by the renderer unit/instrumented suites.
