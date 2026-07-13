# Tasks: Uniform Cross-Device Artifacts & First-Turn Loading Contract

**Input**: Design documents from `/specs/055-uniform-artifacts/`

**Prerequisites**: plan.md, spec.md, research.md (12 decisions + verification amendments), data-model.md, contracts/wire-contract.md, contracts/rest-endpoints.md, quickstart.md

**Tests**: REQUIRED — Constitution III (≥90% changed-code coverage) and X (every affected client exercised live). Test tasks accompany every code path; quickstart.md is the live-verification script.

**Organization**: grouped by user story; US1–US5 are independently shippable increments. MVP = Phase 3 (US1).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (shared vocabulary + flags)

**Purpose**: the wire-vocabulary and flag scaffolding every story hangs off. The manifest and all three client disposition tables MUST land together (drift guards fail otherwise).

- [x] T001 Register the six 055 feature flags (`FF_FIRST_TURN_CONTRACT` on, `FF_STREAM_ARTIFACTS` on, `FF_DESIGNER_ALL_DEVICES` on, `FF_COMPONENT_REFINE` on, `FF_ARTIFACT_EXPORT` on, `FF_ARTIFACT_SHARING` off) in `backend/shared/feature_flags.py` + document each in `.env.example`
- [ ] T002 Edit `backend/shared/ui_protocol.json`: add `additive_fields` entry for `component_id` on `ui_stream_data`+`stream_subscribed` (per contracts/wire-contract.md §2) and add `component_refine`, `component_restore` to `accept_actions` (sorted)
- [ ] T003 [P] Update Windows dispositions in `windows-client/astral_client/protocol_manifest.py`: the 8 `component_verbs` frames ignored→handled, new accept actions classified; keep `tests/test_protocol_manifest.py` green
- [ ] T004 [P] Update Android dispositions in `android-client/core/src/main/kotlin/**/ProtocolManifest.kt` (same deltas); keep `ProtocolManifestTest`/`VocabularyParityTest` green
- [ ] T005 [P] Update Apple dispositions in `apple-clients/AstralCore/Sources/AstralCore/Protocol/Dispositions.swift` (same deltas; watch keeps verbs/refine ignored-with-reason); keep `ManifestDriftTests` green
- [ ] T006 Update `specs/044-native-client-parity/parity-matrix.md`: rows for the 8 verb promotions, the 2 new actions, the `component_id` additive field, the provenance-field render note, and the declared watch carve-outs

**Checkpoint**: backend + all three client drift-guard suites pass with the new vocabulary.

---

## Phase 2: Foundational (blocking prerequisites)

- [x] T007 Add idempotent `_init_db` migrations for `component_version` and `share_grant` per data-model.md (guarded CREATE TABLE/INDEX IF NOT EXISTS), bump `SCHEMA_REVISION` 054.001→055.001 in `backend/shared/database.py`; test in `backend/tests/test_migrations_055.py` (fresh boot, re-boot no-op, representative-dataset boot)
- [x] T008 [P] Add the `wel_` namespace guard to `backend/orchestrator/workspace.py` (resolve/upsert refuses `wel_`-prefixed identities with a structured warning); unit tests in `backend/tests/test_workspace_wel_guard.py`
- [x] T009 [P] Preserve `id`/`component_id` through ROTE degrade rebuilds in `backend/rote/adapter.py` (fallback-ladder rebuild ≈62-76, grid→container collapse ≈408-410); unit tests in `backend/tests/test_rote_identity_preservation.py` (watch-profile hero→text and grid-collapse keep identities)

**Checkpoint**: migrations green on representative data; identity plumbing ready for US1/US2.

---

## Phase 3: User Story 1 — Reliable first-turn loading on every device (P1) 🎯 MVP

**Goal**: loading feedback from send to first content on all six targets; welcome cleanly retired everywhere; no blank-canvas window; no history leaks.

**Independent test**: quickstart.md §US1 — fresh chat per target, typed + example-card sends, text-only first turn, second-query parity.

- [x] T010 [US1] Stamp `wel_` identities (`id` AND `component_id`) on every welcome component in `backend/orchestrator/welcome.py` (`wel_hero`, `wel_enable`, `wel_ex_<slug>`, `wel_hint`); unit tests in `backend/tests/test_welcome_identity.py` (both fields present, slugs stable, never workspace-persistable via T008 guard)
- [x] T011 [US1] Behind `FF_FIRST_TURN_CONTRACT`: remove ONLY the blanking `send_ui_render(websocket, [])` at `backend/orchestrator/orchestrator.py` ≈1497-1499 (keep `_ws_welcome` bookkeeping — enable_recommended_agents re-render must still work); integration test in `backend/tests/test_first_turn_contract.py` (VirtualWebSocket: first chat_message emits NO empty canvas render, flag off restores it byte-identically, welcome re-render paths still fire)
- [x] T012 [US1] Fix the all-tools-denied `break` path so it sends `chat_status done` (orchestrator.py ≈4120-4125); regression test in `backend/tests/test_first_turn_contract.py::test_denied_break_sends_done`
- [x] T013 [P] [US1] Web `backend/webrender/static/client.js`: selective purge of `[data-component-id^="wel_"]` (+ legacy `[id^="wel_"]`) nodes in `sendChat` (never blanket clear); canvas `ui_render` empty-state decision keyed on the structured `components` array (not `data.html` truthiness)
- [x] T014 [P] [US1] Windows `windows-client/astral_client/app.py`: arm `Canvas.show_skeleton()` in `_send` (typed path, ≈1905-1924) matching `_emit`; suppress the idle empty-state hint while turn-active; purge `wel_` entries from `_last_components` + canvas at both send sites; tests in `windows-client/tests/test_first_turn.py` (offscreen)
- [x] T015 [P] [US1] Android `android-client/app/**/AppViewModel.kt`: filter `wel_` components from `canvas` at `sendChat` (≈254-267) and `sendEvent` chat_message (≈303-314) arming; exclude `wel_` from `commitTurn` history push (≈879-888); text-only-turn resurrection covered by the arming purge; tests added to `CanvasClobberTest.kt` (welcome never in history; text-only first turn ends welcome-free)
- [x] T016 [P] [US1] Apple `apple-clients/AstralApp/AstralApp/AppModel.swift`: same purge at `sendChat` (≈782-784) / `sendEvent` (≈816-824) + `commitTurn` history filter (≈668-671); tests in AstralApp test target mirroring Android
- [x] T017 [P] [US1] watchOS `apple-clients/AstralWatch/WatchModel.swift`: unconditional `wel_` filter applied when `ui_upsert` ops are applied (≈339-342); test in AstralWatch tests (first-turn upserts never land under welcome)
- [ ] T018 [US1] Live verification per quickstart.md §US1 on ALL six targets — WEB verified 2026-07-13 (skeleton survives first send, welcome purged, no blank window); Windows/Android/Apple/watch pending (Constitution X) — record evidence (screenshots + notes) under `specs/055-uniform-artifacts/evidence/us1/`

**Checkpoint**: US1 shippable — SC-001/SC-002 measurable; flags-off run byte-identical.

---

## Phase 4: User Story 2 — Progressive artifacts (P1)

**Goal**: streams fill durable identity-bearing components; what streamed is what persists; mid-stream text always clean; leaked syntax never rendered.

**Independent test**: quickstart.md §US2 — streaming tool + slow tool + reload + kill-mid-stream + leak fixture.

- [ ] T019 [US2] `backend/orchestrator/stream_manager.py`: assign workspace rule-2 fingerprint to `StreamSubscription.component_id` at subscribe (≈168, 467); retain last content-bearing chunk per subscription; carry `component_id` on both `ui_stream_data` builders (≈676-686, 1193-1203) AND on `stream_subscribed`; unit tests in `backend/tests/test_stream_bridge.py` (identity assignment, retention, field presence, narrative/legacy streams never carry it)
- [ ] T020 [US2] `backend/orchestrator/orchestrator.py`: auto-subscribe the originating socket (+ co-viewing sockets of the chat) at streaming-tool dispatch (`_dispatch_stream_request` adjacency ≈6878-6930); persist-on-terminal in the `handle_agent_end` wrapper (≈1106-1111): `_tag_source`-stamp retained components → `workspace.upsert` → snapshot → audit → `ui_upsert` fan; abandoned-stream error path resolves to an honest failed-state alert under the same identity; integration tests in `backend/tests/test_stream_persist.py` (stream → persist → reload-visible; abandoned stream; `FF_STREAM_ARTIFACTS` off = today's behavior)
- [ ] T021 [P] [US2] Boundary-buffered incremental markdown for the narrative stream (hold-back tail at last safe boundary outside unclosed `**`/`*`/backtick/`[` spans; terminal flushes) in `backend/orchestrator/stream_manager.py` narrative path + `_emit_narrative_frame`; unit tests in `backend/tests/test_narrative_markdown_boundary.py` (no frame ever ships dangling tokens; property test over random split points)
- [ ] T022 [P] [US2] Extract shared `_strip_toolcall_leakage()` and apply on chat narrative (≈4152-4165), doc-card promotion (≈4334-4385), and `_generate_tool_summary`; extend patterns for XML-ish pseudo-calls (`<arg_key>`, `<arg_value>`, `NAME@true` trains); honest fallback when stripped-empty + diagnostic log; tests in `backend/tests/test_toolcall_leak_stripping.py` including the recorded `update_component<arg_key>…` fixture
- [ ] T023 [P] [US2] Web `backend/webrender/static/client.js`: `mergeStream` keys by `component_id` from the FIRST frame when present (no `stream-<id>` node), reusing `applyUpsert` morph mechanics (CSS.escape, fragment unwrap/replaceWith, side-effect re-init) + `Plotly.purge` before chart replacement + ≤1/s interim chart re-plot throttle; `stream_subscribed` placeholder keyed the same way
- [ ] T024 [P] [US2] Android: add `componentId` to `Inbound.UiStreamData`/`StreamSubscribed` in `android-client/core/**/Wire.kt` + `Messages.kt`; `Streaming.kt` keys node by `componentId ?: "stream-<id>"` from first frame; tests in core test target (keying rule, seq dedup still on stream_id, no double-render on terminal upsert)
- [ ] T025 [P] [US2] Apple `apple-clients/AstralCore/Sources/AstralCore/Transport/Streaming.swift`: same keying rule (payload read is dynamic); tests in AstralCoreTests (keying + no-double-render)
- [ ] T026 [P] [US2] Windows `windows-client/astral_client/streaming.py`: same keying rule; tests in `windows-client/tests/test_streaming_bridge.py`
- [ ] T027 [US2] Live verification per quickstart.md §US2 (web + one native simultaneously; kill-mid-stream; reload) — evidence under `evidence/us2/`

**Checkpoint**: US2 shippable — SC-003/SC-004 measurable.

---

## Phase 5: User Story 3 — One designed canvas on every device (P2)

**Goal**: arrangement decided by content, never by originating device; live cross-device edit reconcile.

**Independent test**: quickstart.md §US3 — same prompt from web vs Android → equivalent persisted canvases; two-device live edits.

- [ ] T028 [US3] `backend/orchestrator/orchestrator.py` behind `FF_DESIGNER_ALL_DEVICES`: remove the native skip tuple (≈7450-7461); add the ONE coalesced post-done designer pass for native-origin turns (inline after the done send ≈4410-4414, before return; designer progress `chat_status` frames suppressed on this pass; turn-marker stale guard; async-mode turns sequence before `task_completed`); materialized native canvas excludes `doc_` cards + Reasoning collapsibles; thread `speak=False` through the designed push AND `_push_canvas` (≈7430-7431); integration tests in `backend/tests/test_designer_all_devices.py` (native-origin turn persists `workspace_layout`; post-done frame ordering on a VirtualWebSocket with a native profile; stale guard drops late push; flag off restores skip; no chat_status after done; watch frame carries no speech)
- [ ] T029 [P] [US3] Windows `windows-client/astral_client/app.py` + surfaces: handle the 8 verb-ack frames (identity-keyed remove/replace for `component_deleted`/`components_combined`/`components_condensed`; status surface for save/combine acks; `saved_components_list` refresh); tests in `windows-client/tests/test_workspace_verbs.py`
- [ ] T030 [P] [US3] Android `AppViewModel.kt` + reducers: same verb-ack handling; tests in app test target
- [ ] T031 [P] [US3] Apple `AppModel.swift`: same verb-ack handling (watch stays ignored); tests in AstralApp target
- [ ] T032 [US3] Cross-device equivalence integration test in `backend/tests/test_canvas_origin_independence.py`: identical multi-component turn driven via browser-profile and android-profile VirtualWebSockets → both persist layout rows; materialized canvases equivalent per profile capability
- [ ] T033 [US3] Live verification per quickstart.md §US3 (two live devices, edits both directions, designer-failure injection) — evidence under `evidence/us3/`

**Checkpoint**: US3 shippable — SC-005 measurable; Constitution XII(b) violation retired.

---

## Phase 6: User Story 4 — Iterate on an artifact + provenance (P2)

**Goal**: component-scoped refine with restorable history; trust marks on every target.

**Independent test**: quickstart.md §US4.

- [ ] T034 [US4] Provenance stamp in `_tag_source` (`backend/orchestrator/orchestrator.py` ≈4009-4054): derive grounded/estimated/generated from the `_source_*` subtree (same logic as the web footer), stamp AFTER designer output is final, ALWAYS overwrite agent-supplied values; ROTE preserved-field rule in `backend/rote/adapter.py`; property + unit tests in `backend/tests/test_provenance_stamp.py`
- [ ] T035 [P] [US4] Web `backend/webrender/renderer.py`: provenance footer reads the stamped field (keep visual parity with today's footer); golden-test updates
- [ ] T036 [P] [US4] Native provenance badges: Windows `windows-client/astral_client/renderer.py`, Android `android-client/app/**/renderers/` shared chrome, Apple `apple-clients/AstralApp/**/ComponentView.swift` (compact badge from the field; watch inherits via text degradation); per-client renderer tests; screenshot set for SC-006
- [ ] T037 [US4] `backend/orchestrator/artifact_versions.py` (NEW): archive/list/get/prune (retain 5) per data-model.md, `(chat_id, user_id)`-scoped, cascade on component/chat delete; unit tests in `backend/tests/test_artifact_versions.py`
- [ ] T038 [US4] `component_refine` + `component_restore` handlers in `backend/orchestrator/orchestrator.py` beside `component_action` (≈7599): full gate sequence (timeline guard, security flags, per-user permission on source agent/tool, 054 LLM gate, audit), bounded same-type-validated LLM edit, version archive before overwrite, force-upsert onto the same id, `ui_upsert` fan; behind `FF_COMPONENT_REFINE`; integration tests in `backend/tests/test_component_refine.py` (gates, refusal paths, version cycle, restore audit)
- [ ] T039 [P] [US4] Web refine/restore affordance in `backend/webrender/renderer.py` component chrome + `client.js` (instruction prompt → `component_refine` ui_event; history list → restore); stripped on non-interactive hosts by existing ROTE rule
- [ ] T040 [P] [US4] Native refine affordances: Windows context menu, Android overflow, Apple context menu → same ui_events; per-client tests (watch: none — declared carve-out)
- [ ] T041 [US4] Live verification per quickstart.md §US4 (refine + restore on web and one native; provenance distinct on all six targets; timeline + unconfigured-LLM refusals) — evidence under `evidence/us4/`

**Checkpoint**: US4 shippable — SC-006/SC-007 measurable.

---

## Phase 7: User Story 5 — Take an artifact with you (P3)

**Goal**: CSV/HTML export; revocable snapshot share links; PHI fail-closed.

**Independent test**: quickstart.md §US5.

- [ ] T042 [US5] `backend/orchestrator/artifact_share.py` (NEW): share_grant store (mint with PHI gate fail-closed, hashed token, snapshot html+json; list; revoke; open-count) per data-model.md; unit tests in `backend/tests/test_artifact_share.py` (incl. PHI refusal + audit events)
- [ ] T043 [US5] Export endpoints in `backend/orchestrator/api.py` behind `FF_ARTIFACT_EXPORT`: `GET /api/export/component/{id}.csv` (ownership check; full-data re-invoke via the component_action pipeline when paginated; formula-injection guard; `?stored_only=1` fallback) and `GET /api/export/canvas/{chat_id}.html` (materialized layouts via `_canvas_components`, standalone document wrapper added in `backend/webrender/renderer.py`, charts degraded, provenance + date stamped); tests in `backend/tests/test_artifact_export.py`
- [ ] T044 [US5] Share endpoints in `backend/orchestrator/api.py` behind `FF_ARTIFACT_SHARING`: `POST /api/share`, `GET /api/share`, `DELETE /api/share/{id}`, public `GET /share/{token}` with noindex/no-store/no-referrer/CSP headers per contracts/rest-endpoints.md; tests in `backend/tests/test_share_routes.py` (unauth serve, revoke-immediate, flag-off 404, header assertions)
- [ ] T045 [P] [US5] Client affordances: web component-footer/canvas-toolbar export+share entries (`client.js` + `renderer.py`); Windows/Android/Apple menu entries opening the export URLs via system browser; parity-matrix rows (watch: none — carve-out)
- [ ] T046 [US5] Live verification per quickstart.md §US5 (incognito open, revoke, PHI fixture refusal, offline HTML open) — evidence under `evidence/us5/`

**Checkpoint**: US5 shippable — SC-008 measurable.

---

## Phase 8: Polish & cross-cutting

- [ ] T047 Flags-off byte-equivalence job: CI variant running the backend suite + all drift guards with the six 055 flags forced off in `.github/workflows/ci.yml`; prove SC-009
- [ ] T048 [P] Observability sweep: structured logs for stripper hits, stream-bridge fallbacks, designer post-done skips (stale guard), share mint/refusals — verify each has agent/chat/correlation context
- [ ] T049 [P] Documentation: renderer docstrings for the new behaviors (Constitution VI), `.env.example` flag notes, contracts kept in sync with any implementation drift
- [ ] T050 Full gate run: container pytest suite, host `ruff check .`, `./gradlew test`, `swift test --package-path apple-clients/AstralCore`, `python -m pytest windows-client/tests -q`, changed-code coverage ≥90% (diff-cover), representative-dataset migration evidence attached to the PR

---

## Dependencies & execution order

- **Phase 1 → Phase 2 → user stories**: T002–T005 must land atomically (drift guards); T007–T009 block their dependents (T008→T010, T009→T017).
- **US1 (Phase 3)**: independent MVP. T010→T011; T013–T017 parallel after T010; T018 last.
- **US2 (Phase 4)**: independent of US1 (shares only T009). T019→T020; T021/T022 parallel anytime; T023–T026 parallel after T019.
- **US3 (Phase 5)**: independent; T028 before T032/T033; T029–T031 parallel (need Phase 1 dispositions).
- **US4 (Phase 6)**: T034 independent; T037→T038; T039/T040 after T038; provenance (T034–T036) has no dependency on refine.
- **US5 (Phase 7)**: T042→T044; T043 independent after T007.
- **Phase 8** after all shipped stories (T047 runnable once any story lands).

## Parallel opportunities

- Within Phase 1: T003/T004/T005 (three client repos).
- US1: T013+T014+T015+T016+T017 concurrently (five client codebases, disjoint files).
- US2: T021+T022 (backend, disjoint) and T023–T026 (four clients) concurrently.
- US3: T029+T030+T031. US4: T035+T036, then T039+T040.
- Cross-story: US1 and US2 backend work touches orchestrator.py in different regions — coordinate merges, otherwise US1..US5 phases can proceed as separate PRs in priority order.

## Implementation strategy

MVP = Phase 1 + Phase 2 + Phase 3 (US1) — ships the headline fix alone. Then
US2 (progressive artifacts) as the second P1 increment. US3–US5 follow in
priority order, each independently PR-able. Every phase ends at its checkpoint
with drift guards green and its quickstart section executed live.
