# Defect Register — 044 Cross-Client Native Parity

**Schema**: per [data-model.md §4](data-model.md). Severity P1 = correctness/security in the
core loop; P2 = feature-parity hole; P3 = polish/evidence/docs. Disposition `fixed` requires
linked evidence; `deferred` requires rationale. Sources: [baseline-findings.md](baseline-findings.md)
(§2.5 Windows, §3.5 Android, §1/§4 backend) + plan-phase re-verification.

| ID | Sev | Client(s) | Summary | Disposition | Evidence / Rationale |
|---|---|---|---|---|---|
| D-001 | P1 | Windows | No reconnect/backoff on socket drop; only `auth_required` triggers a rebuild (app.py:1136-1162); outbound frames silently dropped while disconnected (protocol.py:115) | open → T007/T013 | pending |
| D-002 | P1 | Windows, Android | `error` frames invisible (no handler on either native; 3 incompatible server shapes) | open → T011/T012 | pending |
| D-003 | P1 | Windows, Android | Unknown inbound frames dropped unlogged (Windows: no else branch app.py:1178-1235; Android: reducer `else -> s`) | open → T005/T006/T011/T012 | pending |
| D-004 | P1 | Windows, Android | Sign-out never revokes the server-side session (Windows local quit app.py:1090-1100; Android store.clear MainActivity.kt:186-190); no backend endpoint exists for token-holding clients (/auth/logout is cookie-bound) | open → T017–T019 | pending |
| D-005 | P1 | Windows | Dead session on failed/absent refresh: frozen "Re-authenticating…" caption, no path back (app.py:1142-1144) | open → T015 | pending |
| D-006 | P1 | Android | Cold-start/AuthRequired refresh failure only logs — no sign-in routing (MainActivity.kt:122-131) | open → T016 | pending |
| D-007 | P1 | Windows, Android | Progress contract gaps: `chat_step`, `tool_progress`, `task_started/task_completed` unhandled on both; `user_message_acked` missing on Windows | open → T020/T021 | pending |
| D-008 | P1 | Android (+Windows same class) | Canvas clobber: out-of-turn full `ui_render` wholesale-replaces keyed components (AppViewModel.kt:446); Windows `Canvas.set_components` unconditional rebuild (app.py:232) | open → T023–T025 | pending |
| D-009 | P1 | backend | Generic ui_event failure emits nothing to the client (orchestrator.py:2296-2298 log-only) | open → T009 | pending |
| D-010 | P1 | backend | Chrome error/close paths web-only: unknown-action, admin-denied, uncaught-handler, chrome_close push `ChromeRender` HTML natives can't render (chrome_events.py:227-278) | open → T008 | pending |
| D-011 | P2 | Windows | No attachment UI at all (rest.py GET-only; composer chip-less; send_chat attachments param dead) | open → T043–T046 | pending |
| D-012 | P2 | Windows, Android | No table pagination (Windows fixed-height renderer.py:733-753; Android all-rows Data.kt:57-78) despite server contract | open → T026/T027 | pending |
| D-013 | P2 | Android | 042 top-bar model decoded but never rendered (zero call sites for topbar/topbarActions/settingsControl); client-invented New/Recent; dead connectionLabel() | open → T037 | pending |
| D-014 | P2 | Windows | Parsed `topbar_actions` never rendered by TopBar (rest.py:100-108) | open → T038 | pending |
| D-015 | P2 | Android | Infinite skeleton when chrome_surface never arrives (Screens.kt:255-258); no action error/in-flight state | open → T039 | pending |
| D-016 | P2 | Windows | Surface host lacks bounded wait/retry (unverified timeout) | open → T040 | pending |
| D-017 | P2 | backend | workspace_timeline/pulse/attachments surfaces have no components() → native placeholder; timeline is IN the native topbar model | open → T034–T036 | pending |
| D-018 | P2 | Windows | `ui_render target=history` silently dropped (app.py:1187-1188) | open → T032 | pending |
| D-019 | P2 | Windows | Renderer vocabulary 31 vs Android 33: `image`, `plotly_chart` degraded despite FR-026 build-to-parity | open → T028 | pending |
| D-020 | P2 | Android | Markdown links render as raw text (Markdown.kt inline fallthrough) | open → T029 | pending |
| D-021 | P3 | Windows, Android | theme_apply is a no-op on both (renderer.py:919-925; Input.kt:48); color_picker read-only; user_preferences frame unhandled → preset doesn't survive restart | open → T049/T050 | pending |
| D-022 | P3 | Windows | Desktop verification screenshots render all text as tofu | **fixed** | Root cause confirmed LIVE: `QT_QPA_PLATFORM=offscreen`'s stub font engine resolves no glyphs (reproduced on this Windows host under offscreen, then rendered legibly on the native platform). Fix: `tests/screenshot.py` runs on the native Qt backend + a font sanity gate (`assert_fonts_legible`) that fails loudly rather than emit tofu. Evidence: verification/windows/*.png legible (Segoe UI). |
| D-023 | P3 | repo | No protocol-coverage guard / machine-readable frame registry; per-client vocab guards anchored on hand-copied snapshots | open → T003–T006 | pending |
| D-024 | P3 | repo | Windows client pytest suite never runs in CI (ci.yml has no windows job; release-windows.yml builds only) | open → T010 | pending |
| D-025 | P3 | Android | Dead code: DevAuth (debug+release, unreferenced), Screen.SurfacePlaceholder/SurfacePlaceholderScreen/pendingSurfaceLabel unreachable, navigation-compose unused, proguard-rules.pro reference dangling | open → T039/T056 | pending |
| D-026 | P3 | docs | CLAUDE.md said tkinter (is PySide6) — fixed during planning; 041 status stale; 042 tasks all unchecked despite shipping; 043 verification/US2/US3 tasks open; README/KNOWN-ISSUES stale | open → T055 (CLAUDE.md portion done in c76054a) | pending |
| D-027 | P3 | Windows | Launch-AstralBody.bat overwrites env config unconditionally (hardcoded WS URL/authority) | open → T055 | pending |
| D-028 | P1 | backend | `notification` frame (scheduler → notify_user) absent from every protocol inventory — silently dropped by both natives | open → T003/T020/T021 | pending |
| D-029 | P2 | Android | Outbound queue overflow silently drops oldest frame (OrchestratorClient.kt:147) — vanishing sends | open → T014 | pending |
| D-030 | P3 | backend tests | `test_rest_body_equals_ws_frame_model` (042) went stale when 043 made the REST menu `include_tour=False` — failing on main before 044 touched anything; exactly the drift class the 044 manifest guards target | **fixed** (test now mirrors the WS emission's flags) | commit pending — found during T008 |

| D-031 | P3 | local env | Local `.env` enables ~58 experimental `FF_*` research flags (033-era) → 35 backend tests fail in the local container while CI (no .env, default flags) is green; plus a stale bind-mounted `backend/agents/etf_tracker_1/__pycache__` leftover broke `test_etf_removal` | **fixed** (stale dir removed; canonical local invocation = unset `FF_*` before pytest, documented in quickstart) | 2999 passed / 0 failed under default flags, 2026-07-01 |

| D-032 | P3 | Android | Full logged-in chat over real Keycloak not driven in the autonomous verification run (credential entry is out of bounds for the assistant) | **deferred (limitation)** | Android UI/rendering verified live via app launch (session-expired routing screenshot) + 10/10 instrumented Compose tests on the emulator; the identical server contract runs the full loop live on web + Windows. A human runs the on-device Keycloak login once for the final bundle. |
| D-033 | P3 | Android tests | `SurfacesTest.agents_screen_lists_agent` asserted exact `onNodeWithText("Weather")` against the 043 caret-prefixed `"▶ Weather"` — silently broken since 043 because instrumented tests are nightly-only (never PR-gated) | **fixed** | Found by running the nightly-only suite live during 044 verification; test now matches `substring = true`. 10/10 instrumented pass. |

## Standing deferrals (entered with rationale, not "open")

| ID | Sev | Summary | Disposition | Rationale |
|---|---|---|---|---|
| D-100 | P3 | `agents`/`audit` menu items open client-implemented native screens rather than server `components()` surfaces | **deferred** | Deliberate 042/043 disposition; functional and information-equivalent today; convergence is a separate feature-sized port. Matrix records `native-equivalent`. |
| D-101 | P3 | Android `:app` changed-code coverage not gated in CI (only `:core` Kover) | **deferred** | Pre-existing project posture; Principle III's mechanical gate is Python diff-cover. New 044 `:app` code still lands with unit tests. |
| D-102 | P3 | Android has no in-app endpoint override (BuildConfig-only) | **deferred** | Not a web-parity gap (web has no override either); Windows first-run prompt is its own idiom. DataStore seam documented in baseline for a future feature. |
| D-103 | P3 | `drafts` surface has no components() | **deferred** | Reachable from no client's menu (web included); draft decisions arrive as in-chat cards that round-trip on all clients — equal reachability, no user-visible gap. |
