---
description: "Task list for Agentic Agent/Tool Creation & Top-Bar Settings Menu"
---

# Tasks: Agentic Agent/Tool Creation & Top-Bar Settings Menu

**Input**: Design documents from `specs/027-agentic-creation-settings/`
**Prerequisites**: plan.md, spec.md (Clarifications 2026-06-10), research.md (D1–D10), data-model.md, contracts/

**Tests**: INCLUDED — Constitution III (≥90% changed code) + X (real-browser gate before done).

**Architecture**: chrome = pure-Python render fns in `backend/webrender/chrome/` (orchestrator
renders; astralprims untouched); each surface module exports `render(...)` AND a `HANDLERS`
dict `{action: async handler}`; `chrome_events.py` aggregates handler registries so surface
tasks stay file-disjoint and parallelizable.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (shared plumbing)

- [x] T001 Add `agentic_creation` flag (env `FF_AGENTIC_CREATION`, default **enabled**) to [backend/shared/feature_flags.py](../../backend/shared/feature_flags.py).
- [x] T002 [P] Append `agent_lifecycle` to `EVENT_CLASSES` in [backend/audit/schemas.py](../../backend/audit/schemas.py) (action_types per data-model.md).
- [x] T003 [P] Schema delta in [backend/shared/database.py](../../backend/shared/database.py) `_init_db()`: idempotent `ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS` for `origin` (TEXT NOT NULL DEFAULT 'manual'), `source_chat_id`, `gap_fingerprint`, `revises_agent_id`, `self_test`; partial index `idx_draft_gap (user_id, source_chat_id, gap_fingerprint)`; extend `create_draft_agent`/row mappers to carry the new columns.
- [x] T004 [P] Add `ChromeRender` message (`{type:"chrome_render", region, html, mode}`) to [backend/shared/protocol.py](../../backend/shared/protocol.py) per [contracts/chrome-ws-protocol.md](contracts/chrome-ws-protocol.md).

---

## Phase 2: Foundational (blocks all stories)

- [x] T005 Create chrome package skeleton [backend/webrender/chrome/\_\_init\_\_.py](../../backend/webrender/chrome/__init__.py): `render_topbar(roles, availability)`, `render_modal_shell(title, body_html, surface)`, `chrome_error_block(message, retry_surface?)`, helpers re-exporting `esc`/`render_one`; and [backend/webrender/chrome/topbar.py](../../backend/webrender/chrome/topbar.py): top bar (brand, `#astral-status` slot, `data-tour-target` attrs) + **static grouped settings menu** (Account/Help/Admin tools/Session per contracts/settings-surfaces.md; admin group only when `"admin" in roles`; omission rules FR-019; WAI-ARIA menu markup FR-017; Sign out = plain `GET /auth/logout` link).
- [x] T006 Create surfaces registry [backend/webrender/chrome/surfaces/\_\_init\_\_.py](../../backend/webrender/chrome/surfaces/__init__.py): `SURFACE_RENDERERS: {key -> module}`, `collect_handlers() -> {action: handler}` aggregation, common form helpers (notice blocks, field rows — all `esc()`d).
- [x] T007 Create dispatcher [backend/orchestrator/chrome_events.py](../../backend/orchestrator/chrome_events.py): `async handle_chrome_event(orch, websocket, action, payload, user_id, roles) -> bool` — routes `chrome_open`/`chrome_close` + aggregated surface/creation handlers; pushes `chrome_render`; admin re-check per handler; exception → `chrome_error_block` + `logger.exception`; **unknown chrome action → explicit error notice** (never silent).
- [x] T008 Hook lines in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py): (a) `serve_shell` renders `%%ASTRAL_TOPBAR%%` from session roles (mock-auth admin path preserved); (b) `handle_ui_message` delegates unmatched actions to `chrome_events.handle_chrome_event` before the silent fall-through.
- [x] T009 Update [backend/webrender/templates/shell.html](../../backend/webrender/templates/shell.html): replace static header with `<header id="astral-topbar">%%ASTRAL_TOPBAR%%</header>`, add `<div id="astral-modal"></div>` root (keep canvas/chat/form ids unchanged).
- [x] T010 Extend [backend/webrender/static/client.js](../../backend/webrender/static/client.js) chrome runtime: `chrome_render` region swap (modal/topbar) + `processSideEffects` on inserted subtree; settings-menu open/close + full keyboard semantics (Enter/Space/arrows/Home/End/Escape/outside-click, focus restore — FR-017); modal Escape/backdrop close (sends `chrome_close`); generic `[data-ui-action]` + `[data-ui-form]`/`data-ui-collect` field collection per contract; keep all existing handlers.
- [x] T011 [P] Foundational tests: [backend/tests/chrome/test_topbar.py](../../backend/tests/chrome/test_topbar.py) (admin group present/absent in rendered HTML — SC-005; menu groups + entries; escaping) and [backend/tests/test_ws_chrome_protocol.py](../../backend/tests/test_ws_chrome_protocol.py) (ChromeRender shape; FR-018 untouched: ui_render still carries components+html).

**Checkpoint**: shell shows the top bar + menu; dispatcher routes; modal opens/closes.

---

## Phase 3: User Story 2 — Static top-bar settings menu (P1) 🎯 co-MVP

**Goal**: every menu entry opens a working server-rendered surface over existing backends.

**Independent Test**: non-admin sees Account/Help/Sign out only; each entry opens its surface;
permissions/theme/profile mutations explicit-save with notices; sign-out works.

- [x] T012 [P] [US2] Agents & permissions surface [backend/webrender/chrome/surfaces/agents.py](../../backend/webrender/chrome/surfaces/agents.py): list (mine/public tabs, health/status, enable toggle), detail (per-tool permission matrix `{tool:{permission_kind:bool}}`, visibility, credentials status/set/delete) + `HANDLERS` (`chrome_perms_save`, `chrome_visibility_set`, `chrome_credentials_save`, `chrome_credential_delete`, `chrome_agent_enabled`) calling the api.py internals; tests in [backend/tests/chrome/test_surface_agents.py](../../backend/tests/chrome/test_surface_agents.py).
- [x] T013 [P] [US2] LLM settings surface [backend/webrender/chrome/surfaces/llm.py](../../backend/webrender/chrome/surfaces/llm.py): form + `HANDLERS` (`chrome_llm_models`, `chrome_llm_test`, `chrome_llm_save`, `chrome_llm_clear`) over llm_config internals + session-creds semantics; tests in [backend/tests/chrome/test_surface_llm.py](../../backend/tests/chrome/test_surface_llm.py).
- [x] T014 [P] [US2] Personalization surface [backend/webrender/chrome/surfaces/personalization.py](../../backend/webrender/chrome/surfaces/personalization.py): soul/memory/skills/schedule/dreaming tabs + `HANDLERS` (`chrome_profile_save`, `chrome_memory_update`, `chrome_memory_delete`, `chrome_skill_toggle`, `chrome_job_pause|resume|delete|run_now`, `chrome_dreaming_toggle`, `chrome_dreaming_trigger`) over personalization/scheduler/dreaming service internals (PHI gates preserved); tests in [backend/tests/chrome/test_surface_personalization.py](../../backend/tests/chrome/test_surface_personalization.py).
- [x] T015 [P] [US2] Audit surface [backend/webrender/chrome/surfaces/audit.py](../../backend/webrender/chrome/surfaces/audit.py): filterable cursor-paginated list + detail (`chrome_audit_page`, detail via `chrome_open params.event_id`) over audit repository internals; tests in [backend/tests/chrome/test_surface_audit.py](../../backend/tests/chrome/test_surface_audit.py).
- [x] T016 [P] [US2] Theme surface [backend/webrender/chrome/surfaces/theme.py](../../backend/webrender/chrome/surfaces/theme.py): preset cards + embedded `color_picker` primitives (via `render_one`) + `chrome_theme_preset` (persist via save_theme semantics + instant `theme_apply` block); tests in [backend/tests/chrome/test_surface_theme.py](../../backend/tests/chrome/test_surface_theme.py).
- [x] T017 [P] [US2] Tour surface [backend/webrender/chrome/surfaces/tour.py](../../backend/webrender/chrome/surfaces/tour.py): step payload from `tutorial_step` (audience-filtered) embedded as `data-tour-steps`; `chrome_tour_event` → onboarding-state internals; client step-runner in client.js (highlight resolvable `[data-tour-target]`, centered card otherwise, skip unresolvable static targets with note — A10); tests in [backend/tests/chrome/test_surface_tour.py](../../backend/tests/chrome/test_surface_tour.py).
- [x] T018 [P] [US2] User guide surface [backend/webrender/chrome/surfaces/guide.py](../../backend/webrender/chrome/surfaces/guide.py) + [backend/webrender/chrome/guide_content.py](../../backend/webrender/chrome/guide_content.py) (content ported from `git show 29de624:frontend/src/components/guide/UserGuidePanel.tsx`); tests in [backend/tests/chrome/test_surface_guide.py](../../backend/tests/chrome/test_surface_guide.py).
- [x] T019 [US2] Dispatcher integration tests [backend/tests/test_chrome_events.py](../../backend/tests/test_chrome_events.py): every US2 action routes + re-renders with notice; failure path renders error block; `chrome_open` unknown surface → non-silent error; mutations persist via the same internals as REST (spot-check one per surface).

**Checkpoint**: full management plane reachable; SC-003/SC-004 verifiable.

---

## Phase 4: User Story 1 — Agentic creation from chat (P1) 🎯 co-MVP

**Goal**: capability gap → auto-create draft → self-test → approve/refine/discard in chat.

**Independent Test**: ask for an unserved capability; assistant auto-creates + self-tests; card
shows outcome; approve → gate → live → original request succeeds same-session.

- [x] T020 [US1] Create [backend/orchestrator/agentic_creation.py](../../backend/orchestrator/agentic_creation.py): meta-tool schemas (`create_capability`, `extend_agent` per [contracts/agentic-creation.md](contracts/agentic-creation.md)), `gap_fingerprint()`, dedup lookup, `handle_meta_tool()` returning MCPResponse cards, system-prompt addendum (+ disabled-tools FR-008 pointer), audit events (one correlation_id per gap).
- [x] T021 [US1] Auto-create + self-test pipeline in agentic_creation.py: `db.create_draft_agent(origin='auto_chat', ...)` → `lifecycle.generate_code` → `start_draft_agent` → self-test via `BackgroundTaskManager`+`VirtualWebSocket` draft-test turn (120 s timeout, ≤1 auto-refine — A11) → persist `draft_agents.self_test` → creation card (name/what-it-does/self-test outcome + `draft_approve`/`draft_refine`/`draft_discard` buttons).
- [x] T022 [US1] Hook meta-tools into [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py): inject into tools_desc when flag on AND not draft-test (D1; text-only addendum coexistence); map to `__orchestrator__`; intercept in `execute_single_tool` AND `execute_parallel_tools` before the agent-existence gate.
- [x] T023 [US1] Decision handlers in agentic_creation.py `HANDLERS` (registered through chrome_events): `draft_approve` (existing `approve_agent`; success → immediate-usability card; reject → failures card), `draft_refine` (existing `refine_agent`; renders refine-input card when no message), `draft_discard` (existing `delete_draft`); all owner-verified + audited.
- [x] T024 [US1] Live-agent revision in [backend/orchestrator/agent_lifecycle.py](../../backend/orchestrator/agent_lifecycle.py): `revise_live_agent(agent_id, instruction, user_id)` (ownership check, clone dir → `agents/{slug}__rev{n}/`, draft row origin='revision', refine, start, self-test) and `apply_revision(draft_id)` (stop live → backup → install → security+compile+validator gates → restart; rollback restores backup on any failure — FR-006); `revision_apply`/`revision_discard` handlers.
- [x] T025 [US1] Tests [backend/tests/test_agentic_creation.py](../../backend/tests/test_agentic_creation.py): fingerprint/dedup (FR-007); meta-tool injection on/off (flag, draft-test exclusion); handle_meta_tool with monkeypatched lifecycle (cards carry buttons + self-test outcome; failure card has retry/abandon); decision handlers owner-check + audit emission; revision apply success/rollback (filesystem-level with fake agent dir); disabled-tool pointer path (FR-008).

**Checkpoint**: self-extending assistant working end-to-end against the live LLM.

---

## Phase 5: User Story 3 — Manual creation & fleet management (P2)

- [x] T026 [P] [US3] Drafts surface [backend/webrender/chrome/surfaces/drafts.py](../../backend/webrender/chrome/surfaces/drafts.py): unified drafts list (origin badges — SC-007), draft detail (status, self-test, failures), create-agent form → `chrome_draft_create {fields}` (create+generate+start+self-test via the same agentic_creation pipeline), resume/test links, decision buttons shared with chat; wire as the Agents surface "Drafts" tab; tests in [backend/tests/chrome/test_surface_drafts.py](../../backend/tests/chrome/test_surface_drafts.py).
- [x] T027 [US3] Convergence test in [backend/tests/test_chrome_events.py](../../backend/tests/test_chrome_events.py): a chat-created draft appears in the drafts surface and is approvable/discardable from there (single lifecycle, zero divergence — SC-007); unhealthy live agents remain listed with status (012 FR-015 carried).

---

## Phase 6: User Story 4 — Admin tools stay admin-only (P3)

- [x] T028 [P] [US4] Admin tools surface [backend/webrender/chrome/surfaces/admin_tools.py](../../backend/webrender/chrome/surfaces/admin_tools.py): Tool quality tab (feedback-admin internals: quality signals/proposals/quarantine) + Tutorial admin tab (steps CRUD incl. archived: `chrome_admin_step_save|archive|restore`); every handler re-checks admin role server-side (rejection audited); tests in [backend/tests/chrome/test_surface_admin.py](../../backend/tests/chrome/test_surface_admin.py).
- [x] T029 [US4] Gating tests: non-admin rendered menu contains zero admin references (SC-005); non-admin invoking `chrome_open {surface:"admin_tools"}` or any `chrome_admin_*` action gets error notice + server-side rejection + audit (US4 scenario 3).

---

## Phase 7: Polish & Real-Browser Gate (Constitution X)

- [ ] T030 [P] Docstrings + structured logs sweep over all new modules (Constitution VI/X); `ruff check backend/` clean (py311 target).
- [ ] T031 [P] Update [CLAUDE.md](../../CLAUDE.md) manual section + [docs/](../../docs/) for the chrome layer (`webrender/chrome/`, `chrome_render`, meta-tools, FF_AGENTIC_CREATION).
- [ ] T032 Full suite in container: 026 suites stay green + all 027 suites; coverage ≥90% changed code.
- [ ] T033 **GATE** Rebuild image, restart containers, real-browser E2E (Playwright vs :8001): menu keyboard nav + role gating; every surface opens; permissions save round-trip; theme preset applies + persists across reload; audit paging; tour run (skips deferred-chrome targets); guide; sign-out → signed-out screen; **agentic flow**: unserved request → auto-create+self-test card → approve → original request succeeds same-session (SC-001/SC-002); drafts surface shows the chat-created draft (SC-007). Record evidence under `specs/027-agentic-creation-settings/evidence/`.

---

## Dependencies & Execution Order

- Setup (T001–T004) → Foundational (T005–T011, sequential except T011) → US2 surfaces T012–T018 all [P] (file-disjoint via per-surface HANDLERS) → T019.
- US1 (T020–T025) independent of US2 surfaces but needs T007/T008 (dispatcher) + Setup; T022 after T020; T024 after T021.
- US3 (T026–T027) needs US1 pipeline (shared creation path) + chrome foundation.
- US4 (T028–T029) needs foundation only. Polish/Gate last; T033 is the completion gate.

## Implementation Strategy

MVP = Phases 1–4 (menu + surfaces + agentic creation). Surfaces fan out in parallel;
orchestrator.py is touched only by T008 and T022 (keep those single-writer). The feature is done
only when T033's browser gate passes (Constitution X; "make sure the UI works correctly").
