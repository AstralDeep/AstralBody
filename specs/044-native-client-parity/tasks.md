# Tasks: Cross-Client Native Parity Review & Remediation

**Input**: Design documents from `specs/044-native-client-parity/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R18), data-model.md, contracts/ (6), parity-matrix.md, quickstart.md

**Tests**: REQUIRED — the drift guards ARE deliverables (FR-023), and Constitution III/X demand
per-change tests + live verification on every affected client. Every implementation task lands
with its tests; live-verification checkpoints close each story.

**Organization**: Foundational manifest/transport/chrome plumbing first (blocks everything),
then user stories in spec priority order (US1, US2 = P1; US3, US4 = P2; US5, US6 = P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 from spec.md

## Phase 1: Setup

- [X] T001 Seed the Defect Register from baseline-findings §2.5/§3.5 + the four cross-cutting backend flags (chrome HTML error paths, cookie-bound logout, uncatalogued `notification`, no manifest), with severity/client/disposition columns per data-model §4, in specs/044-native-client-parity/defect-register.md
- [X] T002 [P] Scaffold the verification bundle (README.md regeneration procedure per quickstart §6, results.md scenario table for US1–US6 acceptance scenarios, empty web/ windows/ android/ dirs with .gitkeep) in specs/044-native-client-parity/verification/

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ Blocks all user stories** — the manifest anchors every guard; transport + chrome device-awareness underpin US1/US3.

- [X] T003 Author the UI-protocol manifest (47 push_types with category+shapes incl. `notification` and `error`'s 3 shapes; accept_actions from orchestrator.py:1364-2294 + chrome_events.py; 35 component_types) per contracts/ui-protocol.md §1 in backend/shared/ui_protocol.json
- [X] T004 [P] Backend manifest guards: component-vocabulary equality vs `webrender.allowed_primitive_types()` + send-site regex sweep over UI-socket send modules (inbound/voice allowlist) in backend/tests/test_ui_protocol_manifest.py
- [X] T005 [P] Windows frame classification `CLASSIFICATION: dict[str, "handled"|"ignored"]` covering all 47 types in windows-client/astral_client/protocol_manifest.py, coverage guard in windows-client/tests/test_protocol_manifest.py, and re-anchor `BACKEND_TYPES` on the manifest JSON in windows-client/tests/test_renderer.py
- [X] T006 [P] Android frame classification (object ProtocolManifest, all 47 types) in android-client/core/src/main/kotlin/com/kyopenscience/astral/core/protocol/ProtocolManifest.kt, JSON-coverage guard in android-client/core/src/test/kotlin/.../protocol/ProtocolManifestTest.kt, and re-anchor VocabularyParityTest on the manifest in android-client/app/src/test/kotlin/.../render/VocabularyParityTest.kt
- [X] T007 [P] Windows transport: reconnect loop with 1s→30s exponential backoff (reset on open), bounded 64-frame outbound queue flushed on open, widened status vocabulary (`reconnecting:<n>`, queue-overflow signal) in windows-client/astral_client/protocol.py + unit tests (backoff math, queue drop-visibility, resume re-register) in windows-client/tests/test_transport.py
- [X] T008 [P] Device-aware chrome error/close: unknown-action, admin-denied, uncaught-handler paths + `chrome_close` emit `chrome_surface` (error Alert / empty components) for windows/android targets, HTML unchanged for web, in backend/orchestrator/chrome_events.py + tests in backend/tests/chrome/test_chrome_surface.py
- [X] T009 [P] Generic ui_event failure emits `{"type":"error","code":"internal","message"}` in backend/orchestrator/orchestrator.py (handle_ui_message outer catch) + web toast for error frames in backend/webrender/static/client.js + test in backend/orchestrator/tests/
- [X] T010 Add windows-client CI job (ubuntu, `pip install -r windows-client/requirements.txt`, `QT_QPA_PLATFORM=offscreen python -m pytest windows-client/tests -q`) to .github/workflows/ci.yml; confirm backend guards ride the existing test job and Android guards ride android-ci.yml unit jobs

**Checkpoint**: manifest + guards green on all three stacks; Windows reconnects; chrome errors visible everywhere.

## Phase 3: User Story 1 — Dependable daily chat loop (P1) 🎯 MVP

**Goal**: errors visible, reconnect+resume automatic, expiry never dead-ends, sign-out revokes server-side, progress signals reflected, every turn terminal.

**Independent Test**: scripted conversation per client with injected failures (server error, socket drop, expired token, sign-out) — expected states + recovery on all three.

- [X] T011 [P] [US1] Windows routing rework: classified dispatch + `unhandled frame type` warning default branch, 3-shape error normalizer → banner + rail notice + turn-fail, in windows-client/astral_client/app.py (_on_message) + tests in windows-client/tests/test_message_routing.py
- [ ] T012 [P] [US1] Android: log Unknown frames in reducer, decode `error` (3 shapes) in android-client/core/.../protocol/Wire.kt + surface banner/turn-fail in android-client/app/.../ui/AppViewModel.kt + tests in core WireTest + app unit
- [X] T013 [US1] Windows connection UX: top-bar status chip + reconnect banner + queue-overflow visible notice wired to T007 status vocabulary in windows-client/astral_client/app.py
- [ ] T014 [P] [US1] Android: disconnected banner + queue-overflow visible notice (replace silent drop-oldest) in android-client/app/.../transport/OrchestratorClient.kt + ui/RootScaffold.kt
- [X] T015 [P] [US1] Windows explicit sign-in affordance on dead auth (no session / refresh failed / tries exhausted → dialog running oidc_login off-thread → _reconnect) in windows-client/astral_client/app.py + test
- [ ] T016 [P] [US1] Android: cold-start/AuthRequired refresh failure routes to SignInScreen (not log-only) in android-client/app/.../MainActivity.kt + test
- [X] T017 [US1] Backend native logout: `POST /api/auth/logout` (bearer + KEYCLOAK_ALLOWED_AZP client_id validation) in backend/orchestrator/api.py; `client_id` param through `_revoke_refresh_token`/`_revoke_or_queue`/retrier in backend/orchestrator/web_auth.py; idempotent `auth_revocation_queue.client_id TEXT` migration in backend/shared/database.py; offline-grant revocation + `auth.logout` audit; tests (endpoint, queue retry with client_id, allowlist reject) in backend/tests/
- [X] T018 [US1] Windows sign-out ladder (POST /api/auth/logout → direct Keycloak logout fallback → always local clear + quit; outcome logged) in windows-client/astral_client/app.py + rest.py + tests in windows-client/tests/test_rest.py
- [ ] T019 [US1] Android sign-out ladder (AstralRest.logout → OidcAuth direct revoke fallback → store.clear + SignInScreen) in android-client/app/.../rest/AstralRest.kt + auth/OidcAuth.kt + MainActivity.kt + tests
- [X] T020 [P] [US1] Windows progress signals: user_message_acked, chat_step trail, tool_progress line, task_started/task_completed notices, notification toast, full chat_status vocab (incl. processing_async) in windows-client/astral_client/app.py + tests
- [ ] T021 [P] [US1] Android progress signals: chat_step, tool_progress, task_started/task_completed, notification decode (Wire.kt) + reduce/UI (AppViewModel.kt, Screens.kt) + tests
- [ ] T022 [US1] US1 live checkpoint on all three clients (error reply, socket drop → ≤30 s resume, expired token, sign-out then SC-004 refresh-rejection check) — record interim evidence in specs/044-native-client-parity/verification/results.md

**Checkpoint**: US1 independently shippable — the daily loop is dependable everywhere.

## Phase 4: User Story 2 — Every component renders right (P1)

**Goal**: canvas converges identically; tables page; vocabulary gaps closed (Windows image/plotly, Android links); gallery proves fidelity.

**Independent Test**: canonical 35-type gallery + convergence/pagination scripts per client vs parity matrix.

- [X] T023 [US2] Backend canvas guarantee: regression test asserting canvas-target `ui_render`s deliver the full materialized canvas (029 designer contract; fix server-side if violated) in backend/tests/test_canvas_full_render.py
- [ ] T024 [P] [US2] Windows identity-reconciled canvas (Canvas.set_components morphs matching ids, appends new, removes absent — no blind rebuild) in windows-client/astral_client/app.py + stream sequence guard (drop out-of-order/duplicate frames) in windows-client/astral_client/streaming.py + tests incl. the known clobber sequence in windows-client/tests/test_canvas_convergence.py
- [ ] T025 [P] [US2] Android out-of-turn full-render identity reconcile (AppViewModel reduce ui_render else-branch → Canvas.apply-based reconcile per contracts/canvas-and-interaction.md §1) in android-client/app/.../ui/AppViewModel.kt + clobber-sequence unit test
- [ ] T026 [P] [US2] Windows table pager (`‹ Prev · rows X–Y of Z · Next ›` when total_rows+page_size+component_id; emits table_paginate per contract §2) in windows-client/astral_client/renderer.py + tests
- [ ] T027 [P] [US2] Android table pager (same contract) in android-client/app/.../render/renderers/Data.kt + tests
- [ ] T028 [P] [US2] Windows `image` (QPixmap via rest.fetch_bytes/base64) + `plotly_chart` (QtCharts approximation; undisplayable trace kinds → table with disclosure) renderers; registry 31→33; shrink KNOWN_DEGRADED to {audio, generative} in windows-client/astral_client/renderer.py + windows-client/tests/test_renderer.py
- [ ] T029 [P] [US2] Android markdown links (inlineMarkdown → LinkAnnotation.Url via withLink) in android-client/app/.../render/Markdown.kt + test
- [ ] T030 [P] [US2] Shared markdown construct fixture (headings/bold/italic/inline+fenced code/lists/links) asserted in windows-client/tests/test_renderer.py and android-client :app unit test (same fixture text)
- [X] T031 [US2] Canonical gallery driver: push all 35 types + interactive variants (button, input, multi-action param_picker, file_upload/download, paginated table, empty/long/malformed cases) through the real WS path to connected clients in backend/verification/gallery_driver.py
- [ ] T032 [US2] Windows `ui_render target=history` routing into the history view (replace silent pass, app.py:1187-1188) in windows-client/astral_client/app.py + test
- [ ] T033 [US2] US2 live checkpoint: gallery + convergence + pagination clicks on all three clients; interim captures into specs/044-native-client-parity/verification/

**Checkpoint**: rendering fidelity proven; both P1 stories complete.

## Phase 5: User Story 3 — Settings usable from any client (P2)

**Goal**: server model top bar rendered natively; every native menu/topbar entry opens something functional; surfaces resilient with visible action feedback.

**Independent Test**: walk the entire menu + topbar per client, exercise every surface action incl. one forced failure.

- [X] T034 [P] [US3] `components()` for workspace_timeline (snapshot rows + Newer/Older/Back-to-live buttons) + device-aware `_view`/`_live` handlers in backend/webrender/chrome/surfaces/workspace_timeline.py + tests
- [X] T035 [P] [US3] `components()` for pulse (digest cards via build_digest; flag-off notice) in backend/webrender/chrome/surfaces/pulse.py + tests
- [X] T036 [P] [US3] `components()` for attachments (rows + `attach_existing` Attach buttons + `chrome_attachment_delete` + empty state) in backend/webrender/chrome/surfaces/attachments.py + tests
- [ ] T037 [P] [US3] Android server-driven top bar: render model.topbar (status ← ConnectionState reviving connectionLabel, pulse/timeline action IconButtons with sparkle/history/gear icon map, settings anchor) in android-client/app/.../ui/RootScaffold.kt + ui/Screens.kt + tests
- [ ] T038 [P] [US3] Windows top bar: render parsed topbar_actions + bind status chip to the `status` control in windows-client/astral_client/app.py (TopBar) + tests
- [ ] T039 [P] [US3] Android surface resilience: 10 s bounded skeleton → error+Retry (re-emit chrome_open), in-flight state on action submit, remove unreachable Screen.SurfacePlaceholder/SurfacePlaceholderScreen/pendingSurfaceLabel in android-client/app/.../ui/{AppViewModel,Screens,RootScaffold}.kt + tests
- [ ] T040 [P] [US3] Windows surface resilience: same 10 s timeout/retry + in-flight submit state in windows-client/astral_client/chrome.py + app.py + tests
- [ ] T041 [US3] `workspace_timeline_mode` read-only enforcement (disable send/component mutations while viewing history) on both natives: windows-client/astral_client/app.py + android-client/app/.../ui/AppViewModel.kt + tests
- [ ] T042 [US3] US3 live checkpoint: full menu+topbar walk, 8/8 surface round-trips incl. forced failure (e.g. invalid LLM base URL), timeline/pulse/attachments surfaces open natively on both clients; interim evidence

**Checkpoint**: settings parity complete.

## Phase 6: User Story 4 — Attachments from the desktop (P2)

**Goal**: full attachment lifecycle on Windows at parity with Android/web.

**Independent Test**: attach supported + unsupported types on Windows; compare chips/status/agent-read/reload against Android and web.

- [ ] T043 [US4] Windows multipart upload helper `upload_attachment(http_base, token, filename, mime, data)` (stdlib urllib; POST /api/upload; parses attachment_id/filename/category/parser_status; 4xx surfaced) in windows-client/astral_client/rest.py + tests in windows-client/tests/test_rest.py
- [ ] T044 [US4] Windows composer: paperclip menu (Upload files… ≤10 multi-select / Choose from your files), chip strip above input (filename + parser-status glyph/tooltip + remove; worker-thread uploads; failed state), send maps ready chips to send_chat(attachments=…), strip clears on send, in windows-client/astral_client/app.py + tests in windows-client/tests/test_attachments.py
- [ ] T045 [US4] Windows transcript rehydration: per-turn attachment chips in the rail from load_chat data in windows-client/astral_client/app.py + test
- [ ] T046 [P] [US4] Windows `attach_existing` interception (stage chip from attachments-surface button payload, never forwarded) in windows-client/astral_client/app.py (_emit) + test
- [ ] T047 [P] [US4] Android paperclip parity: "Choose from your files" entry → chrome_open attachments + `attach_existing` interception staging a chip in android-client/app/.../ui/{AppViewModel,Screens}.kt + tests
- [ ] T048 [US4] US4 live checkpoint: full lifecycle on Windows (covered + no-parser file), cross-client reload comparison; interim evidence

**Checkpoint**: the last big feature hole closed.

## Phase 7: User Story 5 — Theme follows me (P3)

**Goal**: preset apply visibly restyles both natives immediately and persists via the server preference.

**Independent Test**: each preset on each client → immediate restyle; restart → preset persists; fine-tune a channel.

- [ ] T049 [P] [US5] Windows live theme: mutable Palette + build_stylesheet(palette) in windows-client/astral_client/theme.py; apply path (user_preferences boot + theme_apply live + save_theme echo) re-sets app stylesheet, repolishes chrome, re-renders canvas; interactive color_picker (QColorDialog → save_theme); disclosure line on the Theme surface behavior; in windows-client/astral_client/{theme,app,renderer}.py + tests in windows-client/tests/test_theme_live.py
- [ ] T050 [P] [US5] Android live theme: UiState.themePalette → dynamic ColorScheme in android-client/app/.../ui/theme/Theme.kt; user_preferences decode (Wire.kt) + theme_apply handling + interactive color_picker (color dialog → save_theme) in android-client/app/.../{ui/AppViewModel.kt,render/renderers/Input.kt} + tests
- [ ] T051 [US5] US5 live checkpoint: all 5 presets × both natives restyle immediately; restart persistence; fine-tune channel; interim captures

**Checkpoint**: no more broken promise on the Theme surface.

## Phase 8: User Story 6 — Evidence & docs truth (P3)

**Goal**: legible committed evidence, finalized matrix/register, truthful docs, dead code gone.

**Independent Test**: regenerate the bundle from a clean checkout per verification/README; every artifact legible + matched by a passing guard.

- [ ] T052 [US6] Screenshot pipeline: real-platform capture mode (`--live`, default Windows platform, window shown) + font sanity gate (fail loudly when no requested family resolves) in windows-client/tests/screenshot.py; diagnose tofu by running offscreen-vs-windowed and record root cause + evidence in specs/044-native-client-parity/defect-register.md
- [ ] T053 [US6] Full live verification (quickstart §6): gallery + all US1–US5 acceptance scenarios on web (browser), Windows app (dev machine), Android emulator (adb screencap); legible captures into verification/{web,windows,android}/; complete specs/044-native-client-parity/verification/results.md
- [ ] T054 [US6] Finalize specs/044-native-client-parity/parity-matrix.md (evidence links, zero pending) + defect-register.md dispositions (fixed / deferred-with-rationale: agents/audit convergence, :app Kover gate, Android endpoint override)
- [ ] T055 [P] [US6] Docs reconciliation: 041 spec status header; 042 tasks.md checked to shipped reality (+ commit or regenerate its untracked captures); 043 open tasks closed/re-homed with 044 cross-refs; windows-client/README.md + android-client/README.md + specs/041-android-sdui-client/KNOWN-ISSUES.md updated; Launch-AstralBody.bat `if not defined` env guards
- [ ] T056 [P] [US6] Android dead code: remove debug+release DevAuth.kt, drop unused navigation-compose from android-client/gradle/libs.versions.toml + app/build.gradle.kts, resolve dangling proguard-rules.pro reference (add file or drop reference)

**Checkpoint**: the parity claim is durable.

## Phase 9: Polish & Final Gates

- [ ] T057 Full suites: backend in-container (default + module + agent suites), windows-client pytest, android :core/:app unit + ktlint/lint, ruff repo-root, workflows valid — all green (SC-009)
- [ ] T058 Open PR to main (spec/task IDs referenced, dependency note "zero new third-party runtime deps; one removal", migration evidence for the queue column) and drive the Principle XI gate set green

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → stories**: T003 blocks T004–T006; T007 blocks T013; T008/T009 block US3 feedback + US1 error UX polish; T010 needs T004–T006 test files to exist (can land with placeholders running existing suites).
- **US1**: T017 blocks T018/T019. T022 needs T011–T021.
- **US2**: independent of US1 except shared files (app.py sequencing); T031 blocks T033; T023 first (server truth) then T024/T025.
- **US3**: T034–T036 (server) unblock native surface content; T037–T040 parallel per client; T042 needs all.
- **US4**: T043 → T044 → T045; T046 needs T036+T044; T047 parallel (Android files).
- **US5/US6**: independent after Phase 2; T053 needs every story's implementation + T031 + T052; T054 needs T053.
- **Same-file sequencing**: tasks touching `windows-client/astral_client/app.py` (T011, T013, T015, T018, T020, T024, T032, T038, T040, T041, T044–T046, T049) and `android-client/.../AppViewModel.kt` (T012, T021, T025, T039, T041, T047, T050) are [P]-marked only when they touch different files — respect file overlap when parallelizing.

## Parallel Example (post-Foundational, per-client tracks)

```text
Track A (backend):  T017 → T023 → T034, T035, T036 → T031
Track B (Windows):  T011 → T013/T015 → T020 → T024/T026/T028 → T032 → T038/T040 → T044…
Track C (Android):  T012 → T014/T016 → T021 → T025/T027/T029 → T037/T039 → T047 → T050
```

## Implementation Strategy

**MVP = US1** (the dependable loop). Then US2 (fidelity), US3 (settings), US4 (attachments),
US5 (theme), US6 (evidence) — each story independently testable and shippable, each closed by
its live checkpoint so Constitution X/XII stay satisfied continuously rather than at the end.
