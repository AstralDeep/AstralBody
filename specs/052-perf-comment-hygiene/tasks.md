# Tasks: System-Wide Performance Optimization + Repo-Wide Comment Hygiene

**Input**: Design documents from `/specs/052-perf-comment-hygiene/`

**Prerequisites**: plan.md, spec.md (clarified 2026-07-08), research.md (R1–R18), data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED — the spec mandates automated guards (FR-017/FR-031, SC-002/SC-005) and Constitution III requires ≥90% changed-line coverage; every implementation task bundles its tests.

**Organization**: Two delivery phases per decision D1 (plan.md): **PR 1 = Phases 1–8** (performance, this branch), **PR 2 = Phase 9** (comment hygiene, follow-up branch after PR 1 merges). User stories US1–US5 are the perf stories; US6 is hygiene.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1–US6 from spec.md (story phases only)

---

## Phase 1: Setup — Instrumentation & Baselines

**Purpose**: Measurement capability first; baselines captured BEFORE any optimization lands (FR-030/FR-032).

- [ ] T001 Create `backend/shared/perf.py` with `perf_span(name, **ctx)` context manager emitting `perf <name> duration_ms=<int> <ctx>` log lines (stdlib only, no PHI/PII), plus unit tests in `backend/tests/test_perf_span.py`
- [ ] T002 Instrument spans from data-model.md §5 — `surface.render.<key>` in `backend/orchestrator/chrome_events.py`; `register_ui.*`/`welcome.render`, `turn.route/tools/designer/narrative`, `boot.init_db/jwks_warm/phi_warm`, `static.version_map` in `backend/orchestrator/orchestrator.py` (depends on T001)
- [ ] T003 [P] Create `backend/scripts/perf_report.py` summarizing perf lines to P50/P95 per span (consumed by quickstart.md protocol)
- [ ] T004 Capture pre-change baselines per quickstart.md protocol into `specs/052-perf-comment-hygiene/baselines.md` — per-surface open, first-login warm/cold, turn non-model overhead, Windows launch-to-window, container boot-to-ready, repeat-visit static transfer (depends on T002, T003; BLOCKS all optimization phases)

---

## Phase 2: Foundational — Pool, Async Facade, Detector (Blocking Prerequisites)

**Purpose**: The systemic fixes every perf story depends on (research R1–R3). **⚠️ No user story work until this phase completes.**

- [ ] T005 [P] Create event-loop guard: `backend/tests/plugins/event_loop_guard.py` fixture wrapping `Database.fetch_one/fetch_all/execute` to raise `BlockingDBOnEventLoop` when called on the loop thread, with transitional allowlist module `backend/tests/loop_guard_allowlist.py`; wire into `backend/tests/conftest.py` in REPORT-ONLY mode (contracts/db-async-and-detector.md)
- [ ] T006 [P] Create query-count test helper `backend/tests/helpers/query_count.py` (`count_queries()` fixture wrapping Database methods)
- [ ] T007 Add `ThreadedConnectionPool` to `backend/shared/database.py` — `_get_connection()` borrows, `putconn` in `finally`, `DB_POOL_MIN`(2)/`DB_POOL_MAX`(10) env, stale-recovery (discard + one retry on OperationalError/InterfaceError), `DB_POOL_DISABLE=1` kill switch, pool close on shutdown; tests in `backend/tests/test_db_pool.py` (leak count zero after suite, restart recovery, kill switch) (research R1)
- [ ] T008 Add async facade `afetch_one/afetch_all/aexecute` (= `asyncio.to_thread` twins) to `backend/shared/database.py` with tests proving identical results/exceptions (same file as T007 — sequential) (research R2)
- [ ] T009 Migrate `backend/orchestrator/orchestrator.py` async hot paths to the facade — `register_ui` handshake reads, `handle_chat_message` reads (e.g. current `:2996`, `:3169`), `load_chat` hydration, WS handlers, `send_dashboard` (depends on T008)
- [ ] T010 [P] Migrate all `backend/webrender/chrome/surfaces/*.py` `render()`/HANDLERS DB access and `backend/orchestrator/chrome_events.py` dispatch to the facade (depends on T008)
- [ ] T011 [P] Migrate remaining loop-reachable call sites — `backend/orchestrator/api.py`, `session_store.py`, `workspace.py`, `history.py` callers, attachment repos (depends on T008)
- [ ] T012 Flip the event-loop guard to ENFORCING with an empty allowlist; full backend suite green under it (SC-005) (depends on T009–T011)

**Checkpoint**: Event loop never blocks on DB; pooled connections; user stories can start (in parallel if staffed).

---

## Phase 3: User Story 1 — Pages and settings surfaces open near-instantly (Priority: P1) 🎯 MVP

**Goal**: Indicator ≤100ms + content ≤400ms P95 on every settings surface, all three clients; hard query budgets; 20-concurrent de-serialization proof.

**Independent Test**: quickstart SC-001 measurements per surface + `test_query_budgets.py` + `concurrent_surfaces.py --n 20`.

- [ ] T013 [P] [US1] Rewrite `get_recent_chats` in `backend/orchestrator/history.py` as a single query (correlated subquery for last-message preview, `_translate_query`-portable); add `backend/tests/test_query_budgets.py::test_recent_chats_single_query` == 1 (research R4)
- [ ] T014 [P] [US1] Merge the two `fetch_all`s in `get_effective_tool_permissions` (`backend/orchestrator/tool_permissions.py:390-404`) into one (split per-kind vs legacy in Python); tests prove identical resolution
- [ ] T015 [US1] Promote `backfill_per_tool_rows` to a one-time guarded `_init_db` migration `_migrate_backfill_tool_kinds_052` in `backend/shared/database.py`; delete the per-render call from `backend/webrender/chrome/surfaces/agents.py:476` and any API callers; idempotency test (data-model.md §2)
- [ ] T016 [US1] Consolidate agent-detail render in `backend/webrender/chrome/surfaces/agents.py` to ≤3 DB round trips (combine ownership + disabled + safe + credential-keys reads); `test_query_budgets.py::test_agent_detail_max_3` (depends on T014, T015)
- [ ] T017 [P] [US1] Agents-list render ≤2 queries (combine `get_all_agent_ownership` + `get_user_disabled_agents` paths) in `backend/webrender/chrome/surfaces/agents.py`; `test_query_budgets.py::test_agents_list_max_2`
- [ ] T018 [US1] Per-turn permission memo keyed `(user_id, agent_id, tool, kind)` created in `handle_chat_message` and threaded into `is_tool_allowed` (`backend/orchestrator/tool_permissions.py`); tests: repeated tool in one turn = one lookup set, revocation visible next turn (research R5, FR-019)
- [ ] T019 [P] [US1] Web modal skeleton: on `chrome_open` click render skeleton into `#astral-modal` immediately (reuse `astral-skeleton` pattern) with ~6s timeout → retry state, in `backend/webrender/static/client.js` (+ any `astral.css` additions); `chrome_render` replaces it (FR-002, research R6)
- [ ] T020 [P] [US1] Create `backend/tests/perf/concurrent_surfaces.py` — 20 parallel surface opens via in-process `VirtualWebSocket` harness asserting P95 ≤ 2× single-user P95 (SC-011)
- [ ] T021 [US1] Measure SC-001/SC-002 per quickstart in the reference environment; record results in `specs/052-perf-comment-hygiene/verification.md` (depends on T013–T020)

**Checkpoint**: US1 independently demonstrable — surfaces near-instant with budgets enforced by CI.

---

## Phase 4: User Story 2 — First login reaches the welcome cards fast (Priority: P2)

**Goal**: Post-redirect → visible example cards ≤1.5s warm / ≤3.0s cold; zero external-origin pre-paint; repeat transfer <100KB.

**Independent Test**: quickstart SC-003/SC-004 browser measurements + `test_shell_assets.py` + JWKS warm tests.

- [ ] T022 [P] [US2] Self-host fonts: audit actually-used weights, vendor Inter + JetBrains Mono woff2 into `backend/webrender/static/fonts/`, replace the googleapis `@import` (`astral.css:11`) with `@font-face` + `font-display: swap`, add `<link rel="preload">` to `backend/webrender/templates/shell.html` (FR-007, research R7; same families per Constitution XII)
- [ ] T023 [US2] Per-file asset version map + version-aware caching in `backend/orchestrator/orchestrator.py` (`_static_asset_version` → map; `_NoCacheStaticFiles` → `public, max-age=31536000, immutable` on matching `?v=`, `no-cache` otherwise); per-file `?v=` for every asset in `shell.html`; header-matrix + hash-change tests (contracts/static-asset-caching.md)
- [ ] T024 [US2] Plotly lazy-load: remove the `<head>` tag from `shell.html`; loader in `backend/webrender/static/client.js` injecting on first chart render with `initCharts` re-scan on script `load` (fixes the verified no-re-init gap) + `requestIdleCallback` prefetch; add `backend/tests/test_shell_assets.py` asserting no external origins, no plotly tag in shell, versioned URLs on all assets (FR-008, CI asset-budget check) (depends on T023)
- [ ] T025 [P] [US2] Remove `setTimeout(connect, 200)` (`client.js:1026`) — connect immediately (FR-010)
- [ ] T026 [P] [US2] JWKS warm-at-boot + ~500s background refresh task in orchestrator startup using `backend/shared/jwks_cache.py`; IdP-down at boot = log + backoff retry, boot/`/readyz` unblocked, validation stays fail-closed; tests (FR-011, research R8)
- [ ] T027 [US2] `register_ui` pipeline: `asyncio.gather` the independent reads (prefs, `compute_tools_available_for_user`, dashboard data), send welcome `ui_render` as early as possible, move profile-save/audit emission off the critical path via `create_task` with audit completeness preserved; ordering tests (FR-012) (depends on T009)
- [ ] T028 [US2] Measure SC-003 (warm + cold profile) and SC-004 per quickstart; record in `verification.md` (depends on T022–T027)

**Checkpoint**: First login demonstrably fast; asset contract CI-guarded.

---

## Phase 5: User Story 3 — Chat turns feel responsive despite LLM latency (Priority: P3)

**Goal**: Components visible the moment they exist; designer = later refinement (1 pass default); narrative streams on all three clients.

**Independent Test**: frame-order tests (upsert precedes design), streaming discrimination/fallback tests, drift guards green, SC-006/SC-007 measurements.

- [ ] T029 [US3] Upsert-first web delivery in `_deliver_round_components` (`backend/orchestrator/orchestrator.py:6892-6988`): send `ui_upsert(ops)` immediately (as the native branch does), then run design passes; push designed `ui_render` as in-place refinement; drop the push if the socket's active chat changed; tests assert frame order, identity preservation (morph anchors), and unchanged failure fallback (FR-013, research R9)
- [ ] T030 [P] [US3] `DEFAULT_MAX_ROUNDS` 3 → 1 in `backend/orchestrator/ui_designer.py:51`; `UI_DESIGNER_MAX_ROUNDS` override unchanged; update tests + default-budget test (FR-014, clarification)
- [ ] T031 [US3] Streaming mode in `_call_llm` (`backend/orchestrator/orchestrator.py:4343-4594`): `stream=True` iterated in the worker thread, deltas marshaled via `loop.call_soon_threadsafe`, buffer-until-discriminate (`delta.tool_calls` → abort to non-streamed path; `delta.content` → stream), per-call fallback on provider error, `FF_LLM_STREAMING` (default on); unit tests via a fake streaming client through `llm_config/client_factory.py` (contracts/narrative-streaming.md)
- [ ] T032 [US3] Emit the streamed narrative through the existing `ui_stream_data` path with the final `ui_render` superseding; transcript persistence unchanged (full final text); tests incl. mixed-client tolerance (depends on T031)
- [ ] T033 [US3] Verify zero protocol drift: `backend/shared/ui_protocol.json` diff empty; run all three stacks' drift-guard/parity suites; measure SC-006/SC-007 per quickstart into `verification.md` (depends on T029–T032)

**Checkpoint**: Rich turns paint progressively; designer latency invisible; streaming live with clean fallback.

---

## Phase 6: User Story 4 — Native clients start instantly and render efficiently (Priority: P4)

**Goal**: Windows window ≤1s with in-window auth; Android skips recomposition of unchanged components.

**Independent Test**: `test_launch_timing.py` (offscreen) + auth-flow tests; Android reference-identity test + Compose stability report.

- [ ] T034 [US4] Window-first launch in `windows-client/astral_client/app.py` `main()` (`:2635-2652`): construct+show `MainWindow` with "Signing in…" status immediately; run `resolve_auth` in a `QThread` worker; on token reuse the existing rebuild-with-new-token flow (`app.py:1936-1953`); cancel aborts the loopback wait with retry/quit; defer the first-run config prompt until after first paint; update `windows-client/tests/test_auth.py` (FR-023, research R14)
- [ ] T035 [US4] Defer `_init_workspace` (`app.py:2336-2362`) from `MainWindow.__init__` to first win_agent/file-tool use; update `windows-client/tests/test_workspace_override.py` (depends on T034)
- [ ] T036 [P] [US4] Cheap early-exit in `Canvas.set_components` (`app.py:357-425`): skip reconciliation when the incoming list is reference/`==`-identical to `_last_components`; extend `windows-client/tests/test_canvas_convergence.py`; document theme-restyle full rebuild as intentional (FR-024 disposition per research R14)
- [ ] T037 [US4] Add `windows-client/tests/test_launch_timing.py` on the offscreen harness (stub pattern from `test_message_routing.py:49-54` + stubbed `resolve_auth`) asserting window-visible ≤1s (SC-008) (depends on T034)
- [ ] T038 [P] [US4] Add `@Immutable` to Android state/wire types — `core/.../sdui/Component.kt`, UiState-held types in `core/.../protocol/Messages.kt`, `core/.../chrome/ChromeMenu.kt`, `app/.../ui/AppViewModel.kt` (`UiState`, `ChatTurn`, `StagedAttachment`, `CanvasSnapshot`), `app/.../ui/theme/Theme.kt` (`ThemePalette`) (FR-025, research R15)
- [ ] T039 [P] [US4] Enable Compose compiler metrics/reports for debug builds in `android-client/app/build.gradle.kts`
- [ ] T040 [US4] Add `android-client/app/src/test/.../ui/CanvasIdentityTest.kt` asserting untouched components keep reference identity across `Canvas.apply` (the skipping precondition); verify the stability report shows the annotated types stable (SC-009) (depends on T038, T039)
- [ ] T041 [US4] Run full windows-client + android-client suites and drift guards; measure SC-008/SC-009 into `verification.md` (depends on T034–T040)

**Checkpoint**: Both native clients verified; parity suites green.

---

## Phase 7: User Story 5 — The stack boots fast (Priority: P5)

**Goal**: `_init_db` ≤250ms when schema current; PHI pre-warmed; no fixed startup sleeps; boot ≥40% faster than baseline.

**Independent Test**: fast-path unit tests + source-hash guard; timed `docker compose up` → `/readyz` vs baselines.md.

- [ ] T042 [US5] `schema_meta` table + `SCHEMA_REVISION` constant + fast path in `backend/shared/database.py::_init_db` (marker match → skip; mismatch/absent → full idempotent run then upsert marker); rollback = delete marker row (data-model.md §1); tests: fast-path skip, mismatch full-run, ≤250ms budget (FR-027, research R11)
- [ ] T043 [US5] Source-hash guard test: hash the `_init_db`(+helpers) source region and fail when it changes without a `SCHEMA_REVISION` bump, in `backend/tests/test_schema_revision_guard.py` (depends on T042)
- [ ] T044 [P] [US5] PHI analyzer pre-warm daemon thread at orchestrator startup (calls `get_phi_gate()`; flag-respecting; `/readyz` untouched); test that readiness never waits on it (FR-028, research R12)
- [ ] T045 [P] [US5] `backend/start.py`: replace `time.sleep(2)` (`:85`) with a bounded `/healthz` poll; drop the 1s-per-custom-agent sleep (`:119`); preserve supervisor exit-code propagation (production-posture smoke unchanged) (FR-029, research R13)
- [ ] T046 [US5] Measure `boot.init_db` fast path + container boot-to-ready vs `baselines.md` (SC-010) into `verification.md` (depends on T042–T045)

**Checkpoint**: Boot measurably faster; migration safety net (revision guard) in place.

---

## Phase 8: PR 1 Verification & Polish (Cross-Cutting)

**Purpose**: Prove every perf SC, ship PR 1.

- [ ] T047 Complete `specs/052-perf-comment-hygiene/verification.md`: full SC-001..SC-011 + SC-013 sweep in the reference environment per quickstart.md (depends on T021, T028, T033, T041, T046)
- [ ] T048 [P] Live three-client verification against the dev backend (browser + Windows client + Android emulator): surfaces, first login, one rich chat turn (streamed narrative + designed refinement), theme switch (Constitution X / XII)
- [ ] T049 [P] Production evidence report (SC-001/003/004 metrics, one-time capture against the deployed instance) → `specs/052-perf-comment-hygiene/production-report.md` (SC-014; evidence, not a gate)
- [ ] T050 [P] Document new operator knobs in `docs/production-deployment.md` (`DB_POOL_MIN/MAX`, `DB_POOL_DISABLE`, `FF_LLM_STREAMING`, `UI_DESIGNER_MAX_ROUNDS` default change, `ASTRAL_DEBUG_SLOW_CALLBACKS`) and quickstart kill-switch table cross-check
- [ ] T051 Open **PR 1** from `052-perf-comment-hygiene`: all Constitution XI gates green (ruff repo-root, both in-image pytest runs incl. detector + query budgets + asset check, diff-cover ≥90%, image build, smoke exit-78, gitleaks); PR documents the psycopg2.pool usage + vendored fonts under Constitution V (depends on T047–T050)

---

## Phase 9: User Story 6 — Comment hygiene, repo-wide minus apple-clients (Priority: P6) — **PR 2**

**Goal**: Every in-scope file has a purpose header; comments limited to docstrings + rationale lines + directives; mechanical rules CI-gated (decision D2).

**Independent Test**: `comment_policy.py --check` clean repo-wide; 588 directives intact; full suites green; diff is comment/docstring-only.

- [ ] T052 [US6] Cut follow-up branch `052-perf-comment-hygiene-b` from main after PR 1 merges (decision D1)
- [ ] T053 [US6] Implement `scripts/comment_policy.py` per contracts/comment-policy-check.md (`tokenize`+`ast` for Python; string-aware lexers for JS/CSS/Kotlin; `--report`/`--check`/`--check --diff BASE`; exit codes 0/1/2; scope + exclusions incl. `apple-clients/` and vendor/fonts); unit tests in `backend/tests/test_comment_policy.py` (string-literal safety, directive protection, each mechanical rule, diff mode)
- [ ] T054 [US6] Generate per-area `--report` worklists; inventory TODO/FIXME and convert the ones marking real outstanding work into tracked items (recorded in the PR description) before removal (spec Assumption) (depends on T053)
- [ ] T055 [P] [US6] Sweep `backend/shared/` + `backend/orchestrator/`: add missing purpose headers, remove banners/narration/dead code/spec markers, keep rationale lines + directives verbatim, move kept rationale into docstrings where natural; backend suite green (depends on T054)
- [ ] T056 [P] [US6] Sweep remaining backend Python — `backend/agents/`, `personalization/`, `audit/`, `feedback/`, `attachments/`, `llm_config/`, `security_benchmark/`, `qual_audit/`, misc modules; backend suite green (depends on T054)
- [ ] T057 [P] [US6] Sweep `backend/webrender/` (Python + `static/client.js` + `static/astral.css`, vendor dir excluded) and `backend/tests/` (traceability moves into test docstrings); suites green (depends on T054)
- [ ] T058 [P] [US6] Sweep `windows-client/astral_client/` + `windows-client/tests/`; windows suite green (depends on T054)
- [ ] T059 [P] [US6] Sweep `android-client/` Kotlin (`core/`, `app/`, KDoc file headers); android unit tests green (depends on T054)
- [ ] T060 [P] [US6] Sweep repo scripts (`scripts/`, `backend/scripts/`, `backend/start.py` if remaining) (depends on T054)
- [ ] T061 [US6] Repo-wide verification: `comment_policy.py --check` clean; directive count unchanged (588 across 234 files); scripted diff audit proves comment/docstring-only changes (no executable-line deltas); `python -m compileall`; full backend + windows + android suites green (SC-012) (depends on T055–T060)
- [ ] T062 [US6] Wire `python scripts/comment_policy.py --check --diff origin/main` into `.github/workflows/ci.yml` as a lint-job step; document the CI-side tool in the PR per Constitution XI (decision D2) (depends on T061)
- [ ] T063 [US6] Open **PR 2** from `052-perf-comment-hygiene-b`: all CI gates green (coverage gate trivially satisfied — no executable lines added); reviewers pointed at the rationale-comment judgment calls (depends on T062)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)** → nothing; T004 baselines BLOCK all optimization phases (2–7)
- **Phase 2 (Foundational)** → Phase 1; BLOCKS US1–US5 phases
- **Phases 3–7 (US1–US5)** → Phase 2; mutually independent after that (parallelizable if staffed); recommended order = priority order (US1 → US5)
- **Phase 8 (PR 1 verification)** → Phases 3–7
- **Phase 9 (US6, PR 2)** → Phase 8 (PR 1 merged); T053 checker is independent code and MAY be developed any time after Phase 1, but sweeps wait for the branch cut

### Key intra-phase dependencies

- T007 → T008 (same file) → T009/T010/T011 → T012 (detector enforcing)
- T014, T015 → T016 (agent detail) | T031 → T032 (streaming emission) | T034 → T035/T037 | T038+T039 → T040 | T042 → T043
- T023 → T024 (shell URL scheme before asset test)

### Parallel Opportunities

- Phase 2: T005 ∥ T006 while T007–T008 proceed; then T010 ∥ T011 (T009 same-file-heavy, keep solo)
- US1: T013 ∥ T014 ∥ T017 ∥ T019 ∥ T020
- US2: T022 ∥ T025 ∥ T026 while T023→T024 proceed
- US4: Windows track (T034→T035/T036/T037) ∥ Android track (T038/T039→T040)
- US6: all six sweeps T055–T060 in parallel (disjoint trees)
- Cross-story: after Phase 2, US1–US5 phases can run concurrently by different developers

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + US1** — the "abysmally slow pages" complaint is resolved and CI-guarded; demo at the T021 checkpoint.
- **Incremental delivery**: each US phase ends in a measurable checkpoint recorded in `verification.md`; stop/ship at any checkpoint.
- **Two-PR delivery (D1)**: PR 1 after Phase 8; PR 2 after Phase 9. Flip D1/D2 by saying so — the phasing isolates the change to T051/T052 and T062.
- Kill switches ship with the code (quickstart table): `DB_POOL_DISABLE`, `FF_LLM_STREAMING=0`, `UI_DESIGNER_MAX_ROUNDS=3`, schema-marker delete.

## Notes

- Total: **63 tasks** (Setup 4, Foundational 8, US1 9, US2 7, US3 5, US4 8, US5 5, PR1-polish 5, US6 12)
- Every task bundles its tests; coverage gate (Constitution III) applies to PR 1's changed lines; PR 2 adds no executable lines
- `apple-clients/` is touched by NO task (clarification 2026-07-08)
- `backend/shared/ui_protocol.json` is modified by NO task — T033 asserts it
