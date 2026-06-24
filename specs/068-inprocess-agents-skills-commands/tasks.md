---
description: "Task list for 068-inprocess-agents-skills-commands"
---

# Tasks: In-Process Built-In Agents, Owner-Safe Marking, and Skills + Slash Commands

**Input**: Design documents from `specs/068-inprocess-agents-skills-commands/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution III mandates ≥90% changed-code coverage and the spec defines acceptance scenarios per story. Write each story's tests before/alongside its implementation and ensure they fail first.

**Organization**: Tasks are grouped by user story (US1–US5) so each story can be implemented, tested, and demoed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US5 (Setup/Foundational/Polish carry no story label)
- Paths are repository-relative.

## Path Conventions

Single server-driven backend under `backend/`. Tests under `backend/tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization shared by all stories.

- [X] T001 [P] Register feature flags `FF_INPROCESS_AGENTS`, `FF_SAFE_AGENTS`, `FF_SKILL_PACKS`, `FF_SLASH_COMMANDS` (defaults per research.md D10: all default-on, exact legacy behavior when off) in `backend/shared/feature_flags.py`.
- [X] T002 [P] Add a canonical `BUILT_IN_AGENT_IDS` constant (the nine first-party agent ids; `etf-tracker-1-1` excluded) in `backend/orchestrator/local_agents.py`, re-exported for reuse by the safe seed (US2) and removal checks (US3).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infra prerequisites the agent-execution stories build on.

**⚠️ CRITICAL**: T003–T004 gate US2; T005–T006 gate US1. Complete the relevant pair before starting that story.

- [X] T003 Add the `agent_trust` table to `shared/database.py::_init_db()` as an idempotent guarded delta (`CREATE TABLE IF NOT EXISTS agent_trust(...)`) per data-model.md, in `backend/shared/database.py`.
- [X] T004 Add `agent_trust` CRUD helpers (`get_agent_is_safe`, `upsert_agent_safe`, `reset_agent_safe`) in `backend/shared/database.py`.
- [X] T005 Implement `LoopbackSocket` (`send_text`/`send_json` decode frames → orchestrator handlers; captures the running loop for cross-thread emits) in `backend/shared/local_transport.py` per contracts/inprocess-dispatch.md.
- [X] T006 Refactor `backend/shared/base_agent.py` to extract the per-request pre-steps (credential decrypt + `_runtime` build + per-server kwarg filtering) into a method callable in-process without a live WS server, preserving `_credentials_stale` and predecessor-key fallback.

**Checkpoint**: Foundation ready — US1 and US2 can begin (in parallel if staffed); US3/US4/US5 are independent of the foundation.

---

## Phase 3: User Story 1 — Built-in agents run in-process (Priority: P1) 🎯 MVP

**Goal**: The nine bundled agents run inside the orchestrator with no per-agent port; chat tool calls behave identically (results, UI, streaming, progress, jobs) and faster.

**Independent Test**: Full agent suite + manual chat against each bundled agent (unary/stream/job/credentialed) with `FF_INPROCESS_AGENTS` on; confirm parity, no `:8003+` ports listening, no event-loop stalls, external A2A still networked, and the flag-off path falls back to WS identically.

### Tests for User Story 1 ⚠️ (write first, ensure they fail)

- [X] T007 [P] [US1] Parity tests (unary result/UI shape, streaming chunk order + cancel, long-running "started"+terminal) in `backend/tests/test_inprocess_dispatch.py`.
- [X] T008 [P] [US1] Credential-confidentiality test (ECIES decrypt happens inside the agent; orchestrator never holds plaintext) in `backend/tests/test_inprocess_credentials.py`.
- [X] T009 [P] [US1] Audit-attribution test (in-process turn emits start/end with correct actor/agent/correlation, chain verifies) in `backend/tests/test_inprocess_audit.py`.

### Implementation for User Story 1

- [X] T010 [US1] Implement `LocalAgentRegistry` (`discover`, `instantiate` without uvicorn, `register_into`, `is_local`) in `backend/orchestrator/local_agents.py` per contracts/inprocess-dispatch.md.
- [X] T011 [US1] At orchestrator boot, instantiate + register the built-ins in-process (cards, tool→scope map, `tool_security.analyze_agent` flags, ownership) gated by `FF_INPROCESS_AGENTS`, in `backend/orchestrator/orchestrator.py`.
- [X] T012 [US1] Branch `_execute_via_websocket` → `_execute_in_process(agent_id, request, timeout)` on `is_local` (pre-steps via `LoopbackSocket`, `await asyncio.to_thread(agent.mcp_server.process_request, request)`, return `MCPResponse`) in `backend/orchestrator/orchestrator.py`.
- [X] T013 [US1] Wire streaming for local agents: launch the agent's streaming generator emitting `ToolStreamData` into the `LoopbackSocket` and honor `ToolStreamCancel` → generator cancel, in `backend/orchestrator/orchestrator.py` / `stream_manager.py`.
- [X] T014 [US1] Wire long-running jobs: `JobPoller` progress flows through `LoopbackSocket` → `_handle_tool_progress` (fan-out, terminal workspace-persist, concurrency-cap release); unary call still returns "started" promptly.
- [X] T015 [US1] Update `backend/start.py` to NOT spawn bundled agents as subprocesses when in-process is on (drafts on-demand + external A2A discovery unchanged).
- [X] T016 [US1] Preserve error classification (retryable vs not) + `TOOL_TIMEOUT_OVERRIDES` wall-clock timeout in the in-process executor, matching the WS path.

**Checkpoint**: US1 fully functional and independently testable (the MVP).

---

## Phase 4: User Story 2 — Trusted built-ins work out of the box (Priority: P1)

**Goal**: The bundled fleet is owner-approved "safe"; a new user can use a safe agent's tools without manual enabling; explicit opt-out and hard blocks still win; every transition is audited.

**Independent Test**: Fresh user invokes a safe agent's tool (works, no setup); disable a scope/tool → opt-out wins; hard-blocked tool stays blocked; non-admin cannot mark safe; revising a safe agent resets it; `marked_safe` events present and chain verifies.

### Tests for User Story 2 ⚠️ (write first, ensure they fail)

- [X] T017 [P] [US2] `backend/tests/test_agent_trust.py`: safe baseline allow, explicit opt-out wins, hard-block stays, admin-gating, reset-on-revision, audited transitions, and `FF_SAFE_AGENTS`-off legacy behavior.

### Implementation for User Story 2

- [X] T018 [US2] Implement `backend/orchestrator/agent_trust.py` (`is_safe`, admin/owner-gated `mark_safe`/`unmark_safe`, `reset_on_revision`) emitting `agent_lifecycle` audit events with actor + prior_state, per contracts/safe-marking.md.
- [X] T019 [US2] Update `is_tool_allowed` in `backend/orchestrator/tool_permissions.py` to apply the safe baseline (allow unless explicit per-(tool,kind)/scope negative record or hard security-flag block), gated by `FF_SAFE_AGENTS`, writing no per-user rows.
- [X] T020 [US2] Boot-seed the nine built-ins as safe idempotently (`marked_by='system'`, one audit event per newly-seeded agent, none on re-run) in `backend/orchestrator/orchestrator.py`.
- [X] T021 [US2] Add the admin/owner-gated mark-safe action + a chrome control on the agents surface in `backend/orchestrator/chrome_events.py` and `backend/webrender/chrome/surfaces/` (server-side role check).
- [X] T022 [US2] In `backend/orchestrator/agentic_creation.py::apply_revision`, call `agent_trust.reset_on_revision` for a revised previously-safe agent (re-approval required), audited.

**Checkpoint**: US1 + US2 both independently functional.

---

## Phase 5: User Story 3 — Retire etf_tracker_1 (Priority: P2)

**Goal**: `etf_tracker_1` removed everywhere; orphaned data cleaned up idempotently; old transcripts degrade gracefully; suite green.

**Independent Test**: Agent absent from catalog/surface/tool-list/glyphs; seeded orphan rows purged after one boot, no-op on re-boot; old transcript shows retirement notice; updated catalog tests pass.

### Tests for User Story 3 ⚠️ (write first, ensure they fail)

- [X] T023 [P] [US3] `backend/tests/test_etf_removal.py`: agent absent everywhere, idempotent orphan cleanup, retired-agent transcript handling.

### Implementation for User Story 3

- [X] T024 [US3] Delete the entire `backend/agents/etf_tracker_1/` directory.
- [X] T025 [US3] Remove `'etf-tracker-1-1'` from `_FIRST_PARTY_PUBLIC_AGENT_IDS` in `backend/shared/database.py`.
- [X] T026 [US3] Remove the `etf_tracker_1` entry from `_AGENT_ICONS` in `backend/orchestrator/history_surface.py` and fix the stale `_is_draft_agent` doc comment in `backend/orchestrator/orchestrator.py`.
- [X] T027 [US3] Add `'etf-tracker-1-1'` to `RETIRED_AGENT_IDS` in `backend/orchestrator/orchestrator.py` for graceful old-transcript handling.
- [X] T028 [US3] Add the one-time guarded `_init_db` cleanup (purge orphaned `agent_scopes`/`tool_overrides`/credentials/`agent_ownership`/`agent_trust` rows + retire/reassign `chats` for `etf-tracker-1-1`) per data-model.md, in `backend/shared/database.py`.
- [X] T029 [P] [US3] Update `backend/tests/test_agent_retirement.py` (drop from expected set), `backend/tests/test_no_behavior_change.py` (drop `agents.etf_tracker_1.mcp_tools`), `backend/tests/test_wiring_030.py` (re-point the public-agent assertion to a surviving id).

**Checkpoint**: etf_tracker_1 cleanly gone; suite green.

---

## Phase 6: User Story 4 — On-demand skill packs (Priority: P2)

**Goal**: Authored, version-controlled capability/technique packs load by relevance into the turn (wiring the dormant `get_techniques_for_agent`), protected from the auto-synthesizer.

**Independent Test**: A capability-specific request loads only that pack; an unrelated request loads none (no baseline growth); the synthesizer never overwrites authored packs; load failure fails open.

### Tests for User Story 4 ⚠️ (write first, ensure they fail)

- [X] T030 [P] [US4] `backend/tests/test_skill_packs.py`: relevance-only loading, no baseline context growth on unrelated turns, authored-not-clobbered, fail-open.

### Implementation for User Story 4

- [X] T031 [P] [US4] Create `backend/knowledge_packs/techniques/` with a README (authored/protected format per contracts/skill-packs.md) and initial authored packs for the built-in capabilities.
- [X] T032 [US4] Extend `KnowledgeIndex` to read `backend/knowledge_packs/` with `authored` provenance (authored precedence) and ensure the synthesizer never writes there, in `backend/orchestrator/knowledge_synthesis.py`.
- [X] T033 [US4] Implement `backend/orchestrator/skill_packs.py` and wire `get_techniques_for_agent` into per-turn system-prompt assembly (relevance selection + bounded digest), gated by `FF_SKILL_PACKS`, fail-open, in `backend/orchestrator/orchestrator.py`.

**Checkpoint**: Relevant technique knowledge reaches the model on demand.

---

## Phase 7: User Story 5 — User-typed slash commands (Priority: P3)

**Goal**: A `/command` surface in chat that expands into a prompt or triggers a flow, routed through permission/audit/PHI rails with discovery; unknown commands are friendly, not errors.

**Independent Test**: Known command expands/triggers; a flow calling a gated tool still respects scopes; `/` shows typeahead/help; unknown→friendly; command menu renders via SDUI and ROTE-adapts; invocations are audited; args are untrusted.

### Tests for User Story 5 ⚠️ (write first, ensure they fail)

- [X] T034 [P] [US5] `backend/tests/test_slash_commands.py`: known expand/flow, permission gate not bypassed, unknown/malformed→friendly, untrusted-arg handling, `FF_SLASH_COMMANDS`-off legacy behavior.

### Implementation for User Story 5

- [X] T035 [US5] Implement `backend/orchestrator/slash_commands.py` registry + parser for the curated set (`/help`, `/agents`, `/summarize`, `/research`, `/weather`) per contracts/slash-commands.md.
- [X] T036 [US5] Detect a leading `/command` at chat ingress and route (`prompt_expand` → prefilled turn; `flow` → defined sequence) always through `is_tool_allowed` + audit + PHI/taint, in `backend/orchestrator/api.py` / `backend/orchestrator/chat_steps.py`; gated by `FF_SLASH_COMMANDS`, fail-open.
- [X] T037 [US5] Add discovery UI: `/` typeahead menu + a commands/help chrome surface in `backend/webrender/templates/shell.html`, `backend/webrender/static/client.js`, `backend/webrender/static/astral.css`, and `backend/webrender/chrome/surfaces/` (server-rendered, ROTE-safe).
- [X] T038 [US5] Unknown/malformed commands return a friendly chrome message; ensure command text/args are treated as untrusted input.

**Checkpoint**: All five stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T039 [P] FR-032: bring `execute_parallel_tools` under `ToolDispatchAudit` so parallel batches emit tool audit events, with a test, in `backend/orchestrator/orchestrator.py` + `backend/tests/test_inprocess_audit.py`.
- [X] T040 [P] Observability: structured fail-open markers on each soft path (`skill_packs.fallback{reason}`, in-process→WS fallback, slash-parse fallback).
- [X] T041 [P] Add Google/NumPy docstrings to all new modules/functions (`local_agents.py`, `local_transport.py`, `agent_trust.py`, `skill_packs.py`, `slash_commands.py`).
- [X] T042 Run `ruff check .` (repo-root clean) and the full `pytest` suite inside the `astralbody` container; fix to green.
- [X] T043 Run quickstart.md validation against the running container (no-port check, audit verify, credential confidentiality, real-browser command menu, flag on/off parity).
- [X] T044 [P] Add a feature-068 summary paragraph to CLAUDE.md's manual notes section (mirroring prior features).

---

## Dependencies & Execution Order

### Phase dependencies

- Setup (P1) → no deps.
- Foundational (P2): T003–T004 gate US2; T005–T006 gate US1.
- US1 (P3): after T005–T006. US2 (P4): after T003–T004. US3/US4/US5: independent (only need Setup).
- Polish (P8): after the desired stories.

### Story independence

- US1, US2, US3, US4, US5 are mutually independent and each independently testable. US2's safe seed references `BUILT_IN_AGENT_IDS` (T002) but does not depend on US1 being in-process (safe marking works on either transport).

### Within each story

- Tests first (must fail), then models/helpers, then services, then wiring/UI.

### Parallel opportunities

- T001/T002 in parallel. Within a story, all `[P]` test tasks in parallel. US3 (removal), US4 (skills), US5 (commands) can be staffed in parallel with US1/US2.

## Parallel Example: User Story 1

```text
# Tests together:
Task: "Parity tests in backend/tests/test_inprocess_dispatch.py"
Task: "Credential-confidentiality test in backend/tests/test_inprocess_credentials.py"
Task: "Audit-attribution test in backend/tests/test_inprocess_audit.py"
```

## Implementation Strategy

### MVP first

1. Setup (T001–T002) → Foundational T005–T006 → US1 (T007–T016). STOP & VALIDATE in the running container. This alone delivers the owner's core ask (no per-agent ports, faster).

### Incremental delivery

2. Foundational T003–T004 → US2 (safe out-of-box). 3. US3 (etf removal). 4. US4 (skills). 5. US5 (slash commands). 6. Polish (audit-coverage, observability, docs, quickstart).

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Each story ships its tests; verify they fail before implementing.
- Every new behavior is flag-gated; off-path must equal today's behavior (fail-open for UI, fail-closed for security).
- Zero new third-party runtime dependencies (Constitution V); schema via idempotent guarded `_init_db` (Constitution IX).
- Validate the in-process transport change end-to-end against the running container before declaring done (Constitution X).
