# Tasks: Bring-Your-Own-LLM — Mandatory Provider Setup & Shipped-Credential Removal

**Input**: Design documents from `/specs/054-byo-llm-setup/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/first-run-gate.md, quickstart.md

**Tests**: REQUIRED — Constitution III mandates ≥90% changed-code coverage; every phase carries its test tasks.

**Organization**: Grouped by user story (US1 first-run dialog, US2 credential removal, US3 persistence-everywhere, US4 admin system credential, US5 watch) so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1..US5 for story phases; setup/foundational/polish have no label

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Schema, catalog, and hygiene plumbing every story builds on.

- [ ] T001 Add idempotent `_init_db` deltas creating `user_llm_config` and `system_llm_config` per [data-model.md](data-model.md) in `backend/shared/database.py` (CREATE TABLE IF NOT EXISTS guards; no FKs; rollback note in migration comment)
- [ ] T002 [P] Create server-owned provider preset catalog `backend/llm_config/providers.py` — ordered `ProviderPreset(key, label, base_url, key_required, key_prefix_hint)` entries for openai/anthropic/gemini/xai/openrouter/groq/together/mistral/ollama/lmstudio/custom (base URLs per research.md R7, re-verified against provider docs), plus `get_preset(key)` and `all_presets()`; module docstring documents the catalog contract
- [ ] T003 [P] Extend key-shape redaction patterns (`sk-ant-`, `sk-proj-`, `AIza`) in `backend/llm_config/audit_events.py::_KEY_PREFIX_PATTERNS` and `backend/llm_config/log_scrub.py::_KEY_TOKEN_PATTERNS`
- [ ] T004 Wire `install_redaction_filter()` into orchestrator boot (call during `Orchestrator` init or `orchestrator.py` startup path) — the filter exists in `backend/llm_config/log_scrub.py` but was never installed (research.md R8)
- [ ] T005 [P] Unit tests for T001–T004: table creation idempotency in `backend/tests/test_database_migrations.py` (or the existing migration-test home), catalog integrity (unique keys, valid URLs, custom last) in `backend/llm_config/tests/test_providers.py`, new-pattern redaction in `backend/llm_config/tests/test_log_scrub.py`, filter-installed-at-boot assertion in `backend/llm_config/tests/test_log_scrub.py`

**Checkpoint**: Schema + catalog exist; keys of all cataloged providers redact.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The persisted credential store and per-user/system resolution — every story depends on this. ⚠️ MUST complete before any user story phase.

- [ ] T006 Create `backend/llm_config/user_store.py` — `PersistedLLMConfig` dataclass (repr elides key; `has_key` client shape) and `UserLLMConfigStore` with `get/set/clear(user_id)`, `get_system/set_system/clear_system()`, Fernet encrypt/decrypt of `api_key` under `CREDENTIAL_ENCRYPTION_KEY` (reuse `credential_manager`'s key-resolution incl. dev key-file fallback), TTL read-through cache with synchronous invalidation on set/clear, undecryptable-row audited discard (`llm_config_change{action:"discarded_undecryptable"}`) returning None
- [ ] T007 Update `backend/llm_config/types.py` + `backend/llm_config/client_factory.py`: add `CredentialSource.SYSTEM`; `build_llm_client` keeps its shape but callers pass the system record (system context) or an empty sentinel (user context) as `default_creds`, preserving no-cross-fallback mechanically; update docstrings
- [ ] T008 Re-key credential resolution in `backend/orchestrator/orchestrator.py`: `_resolve_llm_client_for` (≈4457) resolves user sockets via `ui_sessions[websocket]["sub"]` → `user_store.get(user_id)`, and `None`/`VirtualWebSocket` → `user_store.get_system()`; instantiate the store at init (replacing `_session_llm_creds` per-socket store with the user-keyed cache); delete the disconnect-time `clear` calls (≈8484, ≈8517); re-key the `_session_llm_credentials` agent-tool-arg injection (≈5795-5804) to the resolved per-turn record
- [ ] T009 Re-key `backend/llm_config/ws_handlers.py`: `handle_llm_config_set` persists via the store keyed by `actor_user_id` and re-runs the connection probe server-side before accepting (probe fail ⇒ `error{code:"llm_config_invalid"}`, nothing stored); `handle_llm_config_clear` deletes + audits; `populate_from_register_ui` becomes accept-and-ignore (vestigial field, wire-compatible); optional additive `provider` field defaulting to `"custom"`
- [ ] T010 Foundational tests: store round-trip/encryption-at-rest/undecryptable-discard/cache-invalidation in `backend/llm_config/tests/test_user_store.py` [P with T011]; resolution matrix (user socket→user record, None/VWS→system, no cross-fallback, `LLMUnavailable` when absent, `credential_source` audit values) rewritten in `backend/llm_config/tests/test_call_llm_credential_resolution.py`
- [ ] T011 [P] Rewrite `backend/llm_config/tests/test_session_creds.py`, `test_per_user_isolation.py` (cross-user isolation now via distinct `user_id` rows), and `test_ws_handlers.py` (persistence semantics + probe-on-save) against the store model
- [ ] T012 Update `backend/verification/drivers/in_process.py` (≈110-117): replace the `OPENAI_*` env fake with seeding a harness-namespaced `user_llm_config`/`system_llm_config` row (or `client_factory` injection), so 032 verification runs under the new model

**Checkpoint**: Creds persist per-user; resolution is user/system-split; suite green.

---

## Phase 3: User Story 1 — First login triggers mandatory provider setup (P1) 🎯 MVP

**Goal**: Unconfigured user on any client sees the non-dismissible provider dialog first; completing it (probe-gated save) unlocks the normal experience; tutorial untouched.

**Independent Test**: Fresh user on each client family → dialog first, undismissable, server refuses everything AI-adjacent, save unlocks welcome + tour reachable (quickstart §1).

- [ ] T013 [US1] Extend the `llm` chrome surface `backend/webrender/chrome/surfaces/llm.py`: provider dropdown from `providers.all_presets()` (web `render()` `<select>` + native `components()` SDUI picker), preset selection prefills/locks `base_url` (editable only for `custom`), key field marked optional for keyless presets, first-run title/copy variant ("Set up your AI provider", server-reachability note for local runtimes), `has_key` saved-indicator (never echo key); `chrome_llm_save` validates preset key-requirements server-side
- [ ] T014 [P] [US1] Add mandatory modal variant to `backend/webrender/chrome/__init__.py::render_modal_shell` — `mandatory=True` omits the ✕ button and stamps `data-mandatory="1"` on `.astral-modal-card`
- [ ] T015 [US1] Implement the register-time gate in `backend/orchestrator/orchestrator.py` (register_ui branch ≈1228-1317): when `FF_LLM_FIRST_RUN` (new flag, default on) and user unconfigured — push the mandatory dialog (web: `chrome_render` modal via T014; natives: `chrome_surface{mode:"mandatory"}` with the T013 components) between `user_preferences` and the welcome render, and suppress the welcome `ui_render`; configured users get today's flow byte-for-byte
- [ ] T016 [US1] Enforce the server-authoritative gate: in `backend/orchestrator/chrome_events.py` force `chrome_open`≠`llm` back to `llm` and refuse `chrome_close` while unconfigured (audited `llm_unconfigured{feature:"chrome_open"}`); in `backend/orchestrator/orchestrator.py` refuse `component_action` and workspace combine/condense verbs while the acting user is unconfigured (existing `llm_unconfigured` audit; chat pre-flight ≈3159-3181 already refuses via resolver)
- [ ] T017 [US1] Implement save-success unlock in `backend/orchestrator/orchestrator.py`: after a persisted save, fan out to ALL of the user's sockets — close instruction (web modal-close `chrome_render` / native empty `chrome_surface{mode:"replace"}`) followed by the welcome `ui_render` for sockets that were gated (fan-out precedent: workspace `ui_upsert`)
- [ ] T018 [P] [US1] Web client `backend/webrender/static/client.js`: `closeModal()` refuses while `[data-mandatory]` present (single choke point for ✕/backdrop/Escape paths at ≈895/930-939); ES5 only
- [ ] T019 [P] [US1] Windows client `windows-client/astral_client/app.py`: honor `mode=="mandatory"` on `chrome_surface` — `SurfaceDialog` becomes application-modal, close/Esc/reject suppressed while mandatory (≈498-570, `_on_chrome_surface` ≈1537); clear modality on replace/close
- [ ] T020 [P] [US1] Android client: parse `mode` into `Inbound.ChromeSurface` (`android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/Wire.kt` ≈89-94, `Messages.kt` ≈114-118); mandatory branch in the reduce (`android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AppViewModel.kt` ≈681-713: accept unsolicited surface, navigate to `Screen.Surface`, pin); suppress top-bar navigation + add `BackHandler` swallow while mandatory (`RootScaffold.kt` ≈66-108)
- [ ] T021 [P] [US1] Apple clients: parse `mode` and add the mandatory branch in `reduceChromeSurface` (`apple-clients/AstralApp/AstralApp/AppModel.swift` ≈585-607); suppress top-bar/menu navigation while mandatory (`AppModel.swift` `goTo`/`newChat` ≈820-866, `Views/RootView.swift` ≈75-97)
- [ ] T022 [US1] Fix stale tour copy in `backend/orchestrator/guide_content.py` (≈454) claiming the tour auto-launches on first sign-in (it is user-initiated; first-run ordering now = gate → welcome → tour-on-demand)
- [ ] T023 [US1] Backend gate tests in `backend/tests/test_llm_first_run_gate.py`: register_ui ordering (gate frame precedes/suppresses welcome; configured user unchanged), chrome_open/chrome_close refusal + audit, chat/component_action/combine refusal while gated, save-probe-enforced persistence, multi-socket unlock fan-out, `FF_LLM_FIRST_RUN=0` kill switch (gate refusals remain, push disabled)
- [ ] T024 [P] [US1] Chrome-surface tests: provider dropdown composition (web HTML + SDUI components, preset prefill, keyless flag, no key echo) extending `backend/tests/chrome/test_surface_llm.py`
- [ ] T025 [P] [US1] Client drift/unit tests: Android `mode` parse + mandatory reduce test (`android-client/core/src/test/.../WireTest.kt`, `app/src/test/.../AppViewModelTest.kt`); Apple mandatory-branch XCTest (`apple-clients/AstralApp/AstralAppTests/`); Windows mandatory-dialog unit test (`windows-client/tests/`); verify all four drift guards stay green (no manifest change)

**Checkpoint**: US1 fully demoable — fresh user gated on every client, setup unlocks, tour intact (MVP).

---

## Phase 4: User Story 2 — The product ships with no working AI credential (P1)

**Goal**: The operator-default code path is deleted; legacy env vars are inert; repo/artifacts/docs scrubbed.

**Independent Test**: Boot with legacy vars set → nothing changes (SC-007); grep sweeps clean (quickstart §0/§5).

- [ ] T026 [US2] Delete operator-default remnants in `backend/orchestrator/orchestrator.py`: `self._operator_creds` (≈543), `self.llm_model` env/hardcoded fallback (≈557-559; derive per-call from the resolved record; update the ≈4417 error message), prebuilt `self.llm_client` (≈588-604); re-point the `_combine_components_llm` fast-fail (≈2454) at the system record (full re-wire lands in US4/T036)
- [ ] T027 [US2] Delete `backend/llm_config/operator_creds.py` and every import; `client_factory` empty-sentinel path (T007) covers absence
- [ ] T028 [P] [US2] Replace direct env reads with system-store reads: `backend/orchestrator/agent_generator.py` (≈213-224) and `backend/orchestrator/knowledge_synthesis.py` (≈107-144, drop `KNOWLEDGE_LLM_MODEL`; per-cycle availability re-check instead of init-once `_available=False`)
- [ ] T029 [P] [US2] Remove the `OPENAI_API_KEY` env fallback from agent LLM tools: `backend/agents/general/mcp_tools.py`, `backend/agents/summarizer/mcp_tools.py`, `backend/agents/web_research/mcp_tools.py` (per-turn `_session_llm_credentials` injection becomes the only source; its absence returns the tools' existing "LLM not configured" error)
- [ ] T030 [P] [US2] Scrub `.env.example` (lines 11-23 operator-default block → note pointing at in-app user/system configuration) and the local `.env`; keep `backend/orchestrator/sandbox.py` env denylist as harmless defense-in-depth
- [ ] T031 [P] [US2] Add the migration note to `docs/production-deployment.md` (operator default removed; users self-configure; admin sets the system credential in-app; legacy vars inert)
- [ ] T032 [US2] Retarget/rewrite affected suites: `backend/llm_config/tests/test_background_jobs_use_operator_default.py` → system-credential semantics; `backend/tests/test_sandbox.py` env expectations; sweep `backend/tests/` for `OPENAI_*` env setup (`test_backend.py`, `test_chat_text_only.py`, designer/turn-seam/wave0 suites, agent conftests) replacing with store seeding or factory injection
- [ ] T033 [US2] Inertness + hygiene tests in `backend/tests/test_llm_env_inert.py`: boot/init with legacy vars set produces zero credential resolution (SC-007); repo-tree grep guard asserting no live `os.getenv("OPENAI_API_KEY"|"OPENAI_BASE_URL"|"LLM_MODEL"|"KNOWLEDGE_LLM_MODEL")` outside sandbox denylist/tests (SC-004 automation)

**Checkpoint**: No operator-default path exists; suite green with zero LLM env anywhere.

---

## Phase 5: User Story 3 — Configure once, works everywhere, survives sessions (P2)

**Goal**: One configuration serves all clients/sessions; clear re-gates everywhere immediately.

**Independent Test**: Configure on web → Android/Windows work without dialog; sign-out/in no dialog; Clear re-gates all sockets (quickstart §2).

- [ ] T034 [US3] Implement clear→immediate-re-gate in `backend/orchestrator/orchestrator.py` + `backend/llm_config/ws_handlers.py`: on `llm_config_clear`/`chrome_llm_clear`, delete + invalidate cache, push the mandatory dialog to ALL of the user's connected sockets (reuse T017 fan-out; web + natives; watch excluded), audit `llm_config_change{action:"cleared"}`
- [ ] T035 [US3] Cross-session/cross-socket tests in `backend/tests/test_llm_config_persistence.py`: config survives socket disconnect + new register_ui (no dialog frame emitted), second simultaneous socket is unblocked at connect, clear re-gates every socket, cross-user isolation (user B gated while A configured; B's resolution never returns A's record), undecryptable row → audited discard → re-gate (FR-010), settings-surface update flow (`has_key` indicator, blank key keeps saved key)

**Checkpoint**: Persistence + re-gate semantics proven end-to-end in-process.

---

## Phase 6: User Story 4 — Admin system credential for background work (P2)

**Goal**: Admin-only surface manages the deployment-wide credential; background features use it exclusively and degrade honestly without it.

**Independent Test**: quickstart §3 — scheduled job honestly fails without it, runs with it; non-admin refused; unconfigured users still gated.

- [ ] T036 [US4] Create admin surface `backend/webrender/chrome/surfaces/llm_system.py` (`SURFACE_KEY="llm_system"`, `TITLE="System LLM"`, `admin_only=True`): same field set + provider dropdown + Load models/Test/Save/Clear via new `HANDLERS` `chrome_llm_sys_models/_test/_save/_clear` delegating to the store's `*_system` accessors; every handler enforces the `admin` role server-side (JWT roles per handler, existing pattern); audit `llm_config_change{scope:"system"}`; register the surface + add the admin-gated menu item in `backend/webrender/chrome/menu_model.py`
- [ ] T037 [US4] Honest scheduled-run failure in `backend/scheduler/runner.py` + `backend/orchestrator/orchestrator.py::run_scheduled_turn` (≈2877-2943): when the system credential is absent/failing, record `job_run.outcome="failed"` with `error="llm_unavailable"` and send the owner a notification stating the AI was unavailable — never the "finished" summary (fixes today's silent-success: the VWS alert is swallowed and success recorded)
- [ ] T038 [P] [US4] Re-wire in-session helpers to the system record (explicit owner decision): `backend/orchestrator/compaction.py` call path (websocket=None now ⇒ system via T008 — verify + honest fallback note retained) and `_combine_components_llm` (`orchestrator.py` ≈2438-2455) building its client from `get_system()` with the existing `combine_error` on absence
- [ ] T039 [P] [US4] Verify/adjust remaining system-context consumers for honest degradation: knowledge synthesis per-cycle skip log (T028), attachment autoparse "couldn't prepare a reader" path (`backend/orchestrator/attachment_autoparse.py` ≈228-285 — codegen now raises via system-store absence), job narration deterministic fallback (`orchestrator.py` ≈7825-7902) — each with a structured log line naming `system_llm_unconfigured`
- [ ] T040 [US4] US4 tests in `backend/tests/test_system_llm_credential.py`: admin surface role-gating (non-admin `chrome_open`/handlers refused server-side), save/test/clear round-trip with `scope:"system"` audit, scheduled-run honest failure (outcome=failed + notification text) and success-after-configure, compaction/combine system-source resolution (`credential_source:"system"` in `llm_call` audit), user-gate unaffected by system credential presence (FR-019 both directions)

**Checkpoint**: Background features admin-powered with honest degradation; user/system isolation proven.

---

## Phase 7: User Story 5 — Watch guidance when unconfigured (P3)

**Goal**: Watch users get spoken/displayed "configure on phone/web" guidance; watch works once configured elsewhere.

**Independent Test**: quickstart §4 on the watch simulator.

- [ ] T041 [US5] Device-aware unconfigured guidance in `backend/orchestrator/orchestrator.py` chat pre-flight (≈3159-3181): watch sockets get Alert text "Set up your AI provider on your phone or the web first." (other clients keep the settings-pointing copy); confirm alert-only render auto-routes to chat and is spoken (`webrender/voice.py`; no watch client change, no `speech`-frame change)
- [ ] T042 [US5] Watch-path tests in `backend/tests/test_watch_llm_guidance.py`: unconfigured watch chat turn → alert with watch copy + voice rendition present + `llm_unconfigured` audit; after seeding the user's store row, the same watch socket completes a turn (server-persisted creds resolve without watch-side action)

**Checkpoint**: Watch posture complete without touching watch client code.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T043 [P] Add the "Amended by 054" conformance note to `specs/006-user-llm-config/spec.md` enumerating superseded FRs (FR-022 list: storage clause of FR-002; FR-004/FR-004a; FR-010; FR-011; FR-012/US2 revert-to-default; Clarifications Q1–Q3; "no provider catalog" out-of-scope) and the surviving invariants
- [ ] T044 [P] Sweep user-facing copy: `.env.example` note (T030 follow-through), `backend/orchestrator/welcome.py` (no operator-default mention), LLM settings surface docstrings (`llm.py` storage-model text), README/docs references to operator credentials
- [ ] T045 Run the full quickstart verification (quickstart.md §0–§6): container suite (`docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"`), `ruff check .` from repo root, hygiene greps (SC-004), legacy-var inertness (SC-007)
- [ ] T046 Live client verification per Constitution X/XII: web in a real browser, Windows client launched, Android emulator, iOS + macOS simulators, watch simulator — fresh-user gate, save-unlock, clear-re-gate, admin surface (web), watch guidance; record evidence in `specs/054-byo-llm-setup/evidence/`
- [ ] T047 Changed-code coverage gate ≥90% (diff-cover vs origin/main) and all four client drift-guard suites green; fix any shortfall

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → (Phases 3–7) → Phase 8**
- User stories after Phase 2 are independent of each other, EXCEPT:
  - T026/T027 (US2 deletion) must land after T008 (resolver no longer reads operator creds) — satisfied by phase order
  - T038 (US4) touches `_combine_components_llm` which T026 (US2) fast-fail re-points; if US4 is implemented before US2, T038 subsumes the re-point
  - T034 (US3) reuses the T017 (US1) fan-out helper
- Recommended order: 1 → 2 → US1 → US2 → US3 → US4 → US5 → Polish (priority order; also the lowest-conflict path)

## Parallel Opportunities

- Phase 1: T002/T003/T005 in parallel after T001
- Phase 2: T010/T011 in parallel; T012 parallel with T011
- US1: T014, T018, T019, T20, T021, T024, T025 all parallel once T013/T015–T017 define the server contract; the four client edits (T018–T021) are fully independent files
- US2: T028/T029/T030/T031 parallel after T026/T027
- US4: T038/T039 parallel after T036/T037
- Polish: T043/T044 parallel

## Implementation Strategy

**MVP** = Phases 1–3 (US1): the mandatory dialog with persisted per-user creds delivers the app-store-compliant experience even before the env path is deleted (unconfigured users are already fail-closed today). US2 then makes removal irreversible; US3/US4/US5 complete the cross-client and operational story. Each checkpoint is a demoable, testable increment; commit per phase.
