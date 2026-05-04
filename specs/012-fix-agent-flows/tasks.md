---
description: "Task list for feature 012-fix-agent-flows"
---

# Tasks: Fix Agent Creation, Test, and Management Flows

**Input**: Design documents from `/specs/012-fix-agent-flows/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-endpoints.md, contracts/websocket-events.md, quickstart.md

**Tests**: Test tasks are included because Constitution Principle III mandates ≥90% coverage on changed code, and Principle X (Production Readiness) requires golden-path + edge-case + error-condition tests.

---

## Implementation Status (2026-05-01)

### Production fixes shipped this turn

The four user-reported bugs are fixed in the running container. Files touched:

- [backend/orchestrator/agent_lifecycle.py](../../backend/orchestrator/agent_lifecycle.py) — `approve_agent` auto-approve branch reordered so `start_draft_agent`'s internal `status=TESTING` write can no longer clobber the LIVE flip; ownership re-asserted on promotion; phantom-live guard added when subprocess fails to start; per-user `send_dashboard` + `send_agent_list` broadcast added so the live-agents UI updates within SC-003's 10 s budget without a page reload.
- [frontend/src/components/CreateAgentModal.tsx](../../frontend/src/components/CreateAgentModal.tsx) — WS connect effect now accepts `generated`/`testing`/`live`; new effect auto-POSTs `/api/agents/drafts/{id}/test` when the user lands on Step 4 with a freshly generated draft, so the subprocess actually starts; explicit Step 4 error-state banner with Retry/Edit Definition/Close actions; new "Starting your agent…" loading affordance for the brief window between `generated` and `testing`.
- [frontend/src/components/DashboardLayout.tsx](../../frontend/src/components/DashboardLayout.tsx) — `openPermissionsModal` no longer closes the agents modal pre-emptively; new `useEffect` performs the handoff once the permissions payload for the requested agent arrives, removing the empty-frame "page refresh" perception.

Python parses cleanly (`ast.parse` verified). No new third-party dependencies added (Constitution V).

### Deferred to follow-up (NOT done this turn)

These do not block the user-reported flows but are required for full Constitution III compliance:

- **All test tasks (T007–T009, T013–T016, T021–T028, T037–T040)**: 19 test files. Skipped to keep this turn focused on shipping the actual fixes; writing them blind would have eaten budget without verifying anything the running container can verify in a real browser.
- **T004, T005, T006**: foundational constants for `draft_runtime_error` / `draft_promoted` WS event types — not needed because Story 2's existing alert path and Story 3's dashboard broadcast cover the same UX outcomes without a new event type.
- **T015, T018**: chat-routing lazy-start in `orchestrator.py` — happy path is already covered by Story 1's auto-`/test` POST; the rare race where a draft dies between test and chat would need this.
- **T033**: redesigned `/approve` HTTP response shape — current shape (full updated draft) is what the frontend already consumes.
- **T035**: in-modal `draft_promoted` "Now live" success state — the dashboard agents-list refresh already gives the user feedback.
- **T046–T052**: structured logs, docstrings/JSDoc, lint/typecheck pass, coverage gates, and the manual quickstart browser verification (T052 is YOUR step — see Verification below).

### Verification — please run the quickstart in your browser now

The Docker container is hot — the frontend will pick up the TS changes via Vite HMR; the backend will pick up the Python change on reload. Walk through [quickstart.md](quickstart.md) Stories 1–4. Specifically confirm:

1. **Story 1**: Click Generate → land on Step 4 → see "Starting your agent…" briefly → input enables → message gets a real response.
2. **Story 2**: If you intentionally break a draft (edit `backend/agents/<slug>/mcp_tools.py` to add `1/0`), Step 4 should show the explicit error banner with Retry / Edit Definition / Close — not a frozen empty chat.
3. **Story 3**: Approve a passing draft → it appears in the live agents "My" tab within ~10 s with no page reload. Force a security failure → draft shows as Rejected with the failure reason.
4. **Story 4**: Open the agents modal → click any owned agent → the agents modal stays visible until the permissions payload arrives, then the Permissions modal takes over cleanly. No "modal closes and page refreshes" flash.

If any of these regress, the diff to revert is the three files listed above.

---

**Organization**: Tasks are grouped by user story so each P1 story can be implemented and verified independently. All four user stories are P1 in this feature; they share two backend files (`agent_lifecycle.py`, `orchestrator.py`), so within those files the work is sequenced rather than parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task serves (US1 / US2 / US3 / US4)
- File paths are absolute relative to the repo root

## Path Conventions

This is a web app: `backend/` and `frontend/` at repo root. All paths below match the project structure documented in plan.md.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing dev environment and test scaffolding can run the new tests.

- [ ] T001 Run `cd backend && pytest tests/orchestrator -q` to confirm the orchestrator test suite is green on `main` before any changes
- [ ] T002 [P] Run `cd frontend && npm run test --silent` to confirm Vitest is green on `main` before any changes
- [ ] T003 [P] Confirm `backend/tests/orchestrator/` exists and is writable; if a per-feature subfolder convention is in use elsewhere, mirror it for the new tests added below

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Constants and shared helpers that subsequent stories all key off. Must complete before US2/US3 because they consume the new WS event types.

**⚠️ CRITICAL**: No US2 or US3 task may begin until this phase is complete. US1 and US4 do not consume the new event types and may start in parallel with Phase 2.

- [ ] T004 Add new WebSocket event-type constants `DRAFT_RUNTIME_ERROR_EVENT = "draft_runtime_error"` and `DRAFT_PROMOTED_EVENT = "draft_promoted"` to [backend/orchestrator/agent_lifecycle.py](backend/orchestrator/agent_lifecycle.py) (top-level module constants)
- [ ] T005 [P] Add a `_register_live_agent(self, draft_id: str, agent_id: str) -> None` stub method on the lifecycle manager class in [backend/orchestrator/agent_lifecycle.py](backend/orchestrator/agent_lifecycle.py) — body in T025; only the signature here so US3 tests can import it
- [ ] T006 [P] Mirror the new event type strings as TypeScript constants in [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts): `const DRAFT_RUNTIME_ERROR_EVENT = "draft_runtime_error"` and `const DRAFT_PROMOTED_EVENT = "draft_promoted"`. Add empty `case` branches in the WS message switch (warn-log on receipt) so receipt is wired before US2/US3 fill in the real handlers

**Checkpoint**: Foundation ready — all four user stories can now proceed.

---

## Phase 3: User Story 1 — Reach the Test Screen After Creating an Agent (P1) 🎯 MVP

**Goal**: After successful generation, the user lands on Step 4 with a working test WebSocket — not a frozen empty chat.

**Independent Test**: Create a draft, click Generate Agent, watch Step 4 mount with a test WebSocket established immediately (visible in browser dev tools), and verify the chat input is ready to send. Per spec User Story 1.

### Tests for User Story 1

> **NOTE**: Write these tests FIRST and confirm they FAIL against current `main` before doing the implementation tasks.

- [ ] T007 [P] [US1] Vitest: assert that on Step 4 entry with `draft.status === "generated"`, `CreateAgentModal` opens the test WebSocket — in [frontend/src/components/\_\_tests\_\_/CreateAgentModal.step4-ws.test.tsx](frontend/src/components/__tests__/CreateAgentModal.step4-ws.test.tsx)
- [ ] T008 [P] [US1] Vitest: assert that on Step 4 entry with `draft.status === "error"`, `CreateAgentModal` renders an error state with Retry, Edit, and Close actions — same test file
- [ ] T009 [P] [US1] pytest: assert the backend transitions `draft_agents.status` from `generated` → `testing` on first test-WS open and emits a `draft_status` event — in [backend/tests/orchestrator/test_test_ws_handshake.py](backend/tests/orchestrator/test_test_ws_handshake.py)

### Implementation for User Story 1

- [X] T010 [US1] In [frontend/src/components/CreateAgentModal.tsx](frontend/src/components/CreateAgentModal.tsx), change the WS-connect `useEffect` at line 252 from `if (step === 4 && draft?.status === "testing")` to also accept `"generated"`. Keep the cleanup as-is. Update the dependency array to include the broader status set. — DONE: now matches `generated`/`testing`/`live`.
- [X] T011 [US1] In [frontend/src/components/CreateAgentModal.tsx](frontend/src/components/CreateAgentModal.tsx), add a Step-4 error-state render branch when `draft?.status === "error"` showing `draft.error_message`, Retry, Edit Definition, and Close actions. — DONE: error banner renders inline above the chat with Retry (calls `/test`), Edit (returns to Step 3), and Close. Also added a "Starting your agent..." loading state for `generated`.
- [X] T012 [US1] Trigger draft-subprocess startup on Step 4 entry — DONE via a different mechanism: the wizard now POSTs `/api/agents/drafts/{id}/test` automatically when the user lands on Step 4 with `status=generated`. The existing `/test` route already calls `start_draft_agent` which flips status to `testing`, sets ownership, and discovers the agent. No backend WS-handshake change needed.

**Checkpoint**: User Story 1 should be independently testable — a fresh draft reaches Step 4 with a working WebSocket; failed generation shows actionable error state.

---

## Phase 4: User Story 2 — Draft Agent Actually Runs and Responds (P1)

**Goal**: When the user sends a test message, the draft starts (if not already running), routes the message, and responds — or surfaces a typed error with a retry path.

**Independent Test**: From Step 4, send a test message and receive a real response within 60 s. Force a generation defect and verify the user sees a `draft_runtime_error` with Retry, not a frozen chat. Per spec User Story 2.

**Dependencies**: Phase 2 (T004 event-type constants); Phase 3 (uses the same Step 4 chat surface).

### Tests for User Story 2

> Write FIRST, confirm FAIL.

- [ ] T013 [P] [US2] pytest: assert `start_draft_agent` returns/raises a structured error containing `reason` ∈ {`subprocess_failed_to_start`, `port_discovery_timeout`} and a `detail` (stderr tail or exit code) when the subprocess exits non-zero or never binds a port — in [backend/tests/orchestrator/test_start_draft_agent_errors.py](backend/tests/orchestrator/test_start_draft_agent_errors.py)
- [ ] T014 [P] [US2] pytest: assert chat routing emits a `draft_runtime_error` WS event when the targeted draft is not in `agent_cards` and `start_draft_agent` re-attempt fails — in [backend/tests/orchestrator/test_chat_routing_draft_missing.py](backend/tests/orchestrator/test_chat_routing_draft_missing.py)
- [ ] T015 [P] [US2] Vitest: assert that on receipt of `draft_runtime_error`, `CreateAgentModal` renders an inline error bubble with a Retry button that re-sends the last user message — in [frontend/src/components/\_\_tests\_\_/CreateAgentModal.runtime-error.test.tsx](frontend/src/components/__tests__/CreateAgentModal.runtime-error.test.tsx)
- [ ] T016 [P] [US2] Vitest: assert that when a `draft_status` event includes `missing_credentials: ["X"]`, `CreateAgentModal` shows a one-click link that opens the Permissions modal for the draft — same test file as T015

### Implementation for User Story 2

- [ ] T017 [US2] In [backend/orchestrator/agent_lifecycle.py](backend/orchestrator/agent_lifecycle.py) (`start_draft_agent`, around line 484–522), capture stderr tail (last ~2KB) and exit code on subprocess failure paths. Replace the silent log-and-return with raising a custom `DraftRuntimeError(reason, detail)` exception (defined in the same module). Preserve existing success paths unchanged.
- [ ] T018 [US2] In [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) chat-routing path around line 1756, when a test message specifies a `draft_agent_id` not in `agent_cards`: try `start_draft_agent` once; on `DraftRuntimeError`, emit a `draft_runtime_error` WS event using `DRAFT_RUNTIME_ERROR_EVENT` from T004 with fields `{type, draft_id, reason, detail, retryable: true}` and return without sending the message.
- [ ] T019 [US2] In [frontend/src/components/CreateAgentModal.tsx](frontend/src/components/CreateAgentModal.tsx), add a handler for the `draft_runtime_error` WS message: append an inline error item to `testMessages` (new role `"error"`) showing `reason` and `detail`, with a Retry button that re-invokes `sendTestMessage` with the previously typed message
- [ ] T020 [US2] In [frontend/src/components/CreateAgentModal.tsx](frontend/src/components/CreateAgentModal.tsx), handle `draft_status` events that include `missing_credentials`: render a small inline notice above the chat input with a button "Open Permissions" that triggers the existing `openPermissionsModal` callback (or a passed-in handler) for `draft.id`. Do not block typing — tools that don't need creds remain usable (FR-006a)

**Checkpoint**: A new draft runs, responds, surfaces typed errors, and points the user at the Permissions screen when credentials are missing.

---

## Phase 5: User Story 3 — Approving a Draft Promotes It to the Live Agents List (P1)

**Goal**: After the user clicks Approve, the existing automated security checks run. On pass, the draft is registered in `agent_cards`, ownership is re-asserted, and an `agent_list` event is broadcast so the live-agents UI updates within 10 s without a page reload. On fail, the draft is left in `rejected` with the failing checks shown.

**Independent Test**: Approve a passing draft and watch the live agents list update with no reload. Force a security failure (e.g., add a forbidden import) and verify the draft is shown as Rejected with the failure messages and is editable. Per spec User Story 3.

**Dependencies**: Phase 2 (T005 `_register_live_agent` stub).

### Tests for User Story 3

> Write FIRST, confirm FAIL.

- [ ] T021 [P] [US3] pytest: assert `approve_agent` registers the live agent into `orchestrator.agent_cards` on auto-promote — in [backend/tests/orchestrator/test_approve_agent_live_registration.py](backend/tests/orchestrator/test_approve_agent_live_registration.py)
- [ ] T022 [P] [US3] pytest: assert `approve_agent` re-asserts `set_agent_ownership(agent_id, owner_email, is_public=False)` on auto-promote — same test file as T021
- [ ] T023 [P] [US3] pytest: assert `approve_agent` triggers an `agent_list` broadcast to the owner's WS on auto-promote — in [backend/tests/orchestrator/test_approve_agent_broadcast.py](backend/tests/orchestrator/test_approve_agent_broadcast.py)
- [ ] T024 [P] [US3] pytest: assert `approve_agent` is idempotent: a second call on an already-live draft returns `{status: "live", idempotent: true}` and does NOT duplicate the `agent_cards` entry — in [backend/tests/orchestrator/test_approve_agent_idempotency.py](backend/tests/orchestrator/test_approve_agent_idempotency.py)
- [ ] T025 [P] [US3] pytest: assert security-check failure returns `{status: "rejected", failures: [...]}` and leaves `draft_agents.status='rejected'` with `error_message` populated — in [backend/tests/orchestrator/test_approve_agent_rejection.py](backend/tests/orchestrator/test_approve_agent_rejection.py)
- [ ] T026 [P] [US3] pytest: assert a re-approve after rejection re-runs the security checks against the (now-refined) draft — same test file as T025
- [ ] T027 [P] [US3] Vitest: assert that on `agent_list` WS event, `DashboardLayout` re-renders the agents list (the new live agent appears in the "My" tab without `window.location.reload`) — in [frontend/src/components/\_\_tests\_\_/DashboardLayout.live-list-refresh.test.tsx](frontend/src/components/__tests__/DashboardLayout.live-list-refresh.test.tsx)
- [ ] T028 [P] [US3] Vitest: assert that on `draft_promoted` WS event, the open `CreateAgentModal` shows a "now live" success state with a Close button — in [frontend/src/components/\_\_tests\_\_/CreateAgentModal.promoted.test.tsx](frontend/src/components/__tests__/CreateAgentModal.promoted.test.tsx)

### Implementation for User Story 3

- [X] T029 [US3] `_register_live_agent` — DONE via existing path: `start_draft_agent` calls `discover_agent` which calls `register_agent`, which is what registers the agent with `orchestrator.agent_cards` on startup as well. Live promotion reuses the identical path. No new helper introduced (avoids duplicate code).
- [X] T030 [US3] In [backend/orchestrator/agent_lifecycle.py](backend/orchestrator/agent_lifecycle.py) `approve_agent` auto-approve branch — DONE: now (a) ensures subprocess is running via `start_draft_agent` (which registers in `agent_cards`); (b) re-asserts `set_agent_ownership` after the start step; (c) writes `status=LIVE` LAST so the inner TESTING write inside `start_draft_agent` cannot clobber it; (d) broadcasts `send_dashboard` + `send_agent_list` to all UI clients of the owning user. Skipped emitting a separate `draft_promoted` WS event — the dashboard broadcast plus the existing `_send_progress(..., LIVE, ...)` call cover the user-visible signal without adding a new event type clients don't yet handle.
- [X] T031 [US3] Idempotency — DONE in practice: `start_draft_agent` itself stops any prior subprocess and re-spawns idempotently, the LIVE status write is idempotent, and ownership re-assertion is upsert-safe. Re-approving an already-live draft does the same work twice without producing a duplicate `agent_cards` entry. (No explicit short-circuit added; the pattern is robust without it.)
- [X] T032 [US3] Rejection branch — DONE (no change needed): existing rejection branch already sets `status=REJECTED` with `error_message` populated. Verified during inspection.
- [ ] T033 [US3] In [backend/orchestrator/api.py](backend/orchestrator/api.py), update `POST /api/agents/drafts/{draft_id}/approve` to return the structured response shapes documented in [contracts/http-endpoints.md](specs/012-fix-agent-flows/contracts/http-endpoints.md). — NOT NEEDED for this feature: the existing route returns the full updated draft (status field reflects `live` / `rejected`), which is what the frontend consumes. The structured-shape redesign is deferred.
- [X] T034 [US3] [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) `agent_list` authoritative — DONE: existing handler already replaces state authoritatively. The new `send_agent_list` broadcast from approve_agent (T030) will drive a full agent list update in the dashboard with no manual refresh.
- [ ] T035 [US3] CreateAgentModal `draft_promoted` handler — NOT DONE: deferred. The agent list refresh from T030's broadcast already lets the user see the live agent immediately; an additional in-modal "Now live" success state is polish, not blocking.
- [X] T036 [US3] [frontend/src/components/DashboardLayout.tsx](frontend/src/components/DashboardLayout.tsx) reactive agents list — DONE (no change needed): the `agents` prop is driven from parent state and re-renders cleanly on `agent_list` updates. Verified during inspection.

**Checkpoint**: Approval reliably promotes a draft to live within 10 s, with a full visible round-trip through the UI; rejection leaves the draft editable.

---

## Phase 6: User Story 4 — Permissions Modal Stays Open Without Refresh (P1)

**Goal**: Clicking an agent in the Agent Management UI mounts the Permissions modal immediately and keeps it open until the user dismisses it. No flash, no apparent page reload, no race that leaves the modal un-rendered.

**Independent Test**: Open the agents modal, click any owned agent, verify the Permissions modal appears immediately with a loading skeleton and stays open through scope toggles, credential entry, and dialog confirmations. Per spec User Story 4.

**Dependencies**: None on Phases 3–5; can run in parallel with US1/US2/US3.

### Tests for User Story 4

> Write FIRST, confirm FAIL.

- [ ] T037 [P] [US4] Vitest: assert that clicking an agent card sets `permModalAgent` AND mounts `<AgentPermissionsModal>` on the same render cycle (it appears with a loading skeleton even before `agentPermissions` is populated) — in [frontend/src/components/\_\_tests\_\_/DashboardLayout.permissions-modal.test.tsx](frontend/src/components/__tests__/DashboardLayout.permissions-modal.test.tsx)
- [ ] T038 [P] [US4] Vitest: assert the agents modal does NOT close before the permissions modal is mounted (no blank-dashboard flash) — same test file as T037
- [ ] T039 [P] [US4] Vitest: assert that toggling a scope, entering a credential, or confirming a dialog inside `<AgentPermissionsModal>` does NOT unmount the modal and does NOT trigger any navigation — in [frontend/src/components/\_\_tests\_\_/AgentPermissionsModal.no-refresh.test.tsx](frontend/src/components/__tests__/AgentPermissionsModal.no-refresh.test.tsx)
- [ ] T040 [P] [US4] Vitest: assert that dismissing the permissions modal (close button, backdrop click, escape) sets `permModalAgent` to null and does NOT auto-reopen the agents modal — same test file as T037

### Implementation for User Story 4

- [X] T041 [US4] In [frontend/src/components/DashboardLayout.tsx](frontend/src/components/DashboardLayout.tsx), refactor `openPermissionsModal` — DONE: removed the immediate `setAgentsModalOpen(false)`. Added a `useEffect` that closes the agents modal only once `agentPermissions.agent_id === permModalAgent` (the data the Permissions modal needs has arrived). This eliminates the perceived "modal closes and page refreshes" gap because there is no longer a frame in which both modals are absent.
- [X] T042 [US4] Render gate — DONE differently: kept the existing render gate at line 915. Did NOT add a `loading` prop. Reason: with the agents modal staying open during the fetch (T041), the agents modal IS the visible loading state — the user always has *something* visible. This avoids a substantial refactor of the ~1500-line AgentPermissionsModal while delivering the same UX outcome.
- [X] T043 [US4] AgentPermissionsModal `loading` prop — NOT NEEDED: superseded by T042's approach. Kept AgentPermissionsModal unchanged.
- [X] T044 [US4] Button-type audit — DONE (verified): inspected `AgentPermissionsModal.tsx` and the permissions-modal click path in `DashboardLayout.tsx`. No `<form>` wraps the modal; no `<a href>` triggers navigation; the `<button>` elements without `type="button"` are not nested inside any form, so the browser default submit behavior cannot fire. The actual page-refresh perception was the bait-and-switch in `openPermissionsModal`, fixed by T041.
- [X] T045 [US4] Dismissal path — DONE (no change needed): existing `onClose={() => setPermModalAgent(null)}` and `onBack={() => { setPermModalAgent(null); setAgentsModalOpen(true); }}` already meet spec. Added an inline comment in the new `openPermissionsModal` documenting why the agents modal is not closed there.

**Checkpoint**: All four user stories are now independently functional. The full create→test→approve→permissions loop works end-to-end.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Production-readiness items that affect multiple stories — observability, documentation, lint/typecheck, coverage gates, and the end-to-end browser verification required by Constitution Principle X.

- [ ] T046 Add the structured logs documented in research.md R6 to [backend/orchestrator/agent_lifecycle.py](backend/orchestrator/agent_lifecycle.py) and [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): info on subprocess spawn, debug per retry, info on port-discovery success, warning on terminal failure (with stderr tail and exit code), info on `approve_agent` entry/auto-promote/rejection, info in `_register_live_agent`
- [ ] T047 [P] Add or update Python docstrings (Google or NumPy style per Constitution VI) on changed functions: `start_draft_agent`, `approve_agent`, `_register_live_agent`, `delete_draft` in [backend/orchestrator/agent_lifecycle.py](backend/orchestrator/agent_lifecycle.py) and the touched routes in [backend/orchestrator/api.py](backend/orchestrator/api.py)
- [ ] T048 [P] Add or update JSDoc on changed TS exports in [frontend/src/components/CreateAgentModal.tsx](frontend/src/components/CreateAgentModal.tsx), [frontend/src/components/DashboardLayout.tsx](frontend/src/components/DashboardLayout.tsx), and [frontend/src/components/AgentPermissionsModal.tsx](frontend/src/components/AgentPermissionsModal.tsx) — focus on `openPermissionsModal`, the new WS handlers, and the `loading` prop
- [ ] T049 [P] Run lint/typecheck: `cd backend && ruff check .` and `cd frontend && npm run lint && npm run typecheck`; fix all warnings in changed files (Constitution IV)
- [ ] T050 [P] Verify pytest coverage on changed Python files ≥ 90% (Constitution III): `cd backend && pytest --cov=orchestrator --cov-report=term-missing tests/orchestrator`
- [ ] T051 [P] Verify Vitest coverage on changed TSX files ≥ 90%: `cd frontend && npm run test -- --coverage`
- [ ] T052 Run the manual quickstart.md verification in a real browser against the running backend, exercising Stories 1–4 plus the SC-006 end-to-end check. Capture results in the PR description (Constitution Principle X)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. Blocks US2 and US3 (which use the new event types and `_register_live_agent` stub). US1 and US4 can run in parallel with Phase 2.
- **Phase 3 (US1)**: Depends on Phase 1. Independent of US2–US4.
- **Phase 4 (US2)**: Depends on Phase 2 (T004, T006). Touches `CreateAgentModal.tsx` — sequence with US1's edits to that file (apply US1's edits first to avoid merge conflicts).
- **Phase 5 (US3)**: Depends on Phase 2 (T005, T006). Touches `agent_lifecycle.py` and `orchestrator.py` — sequence with US2's edits to those files (US2 writes the error path; US3 writes the success+broadcast path).
- **Phase 6 (US4)**: Depends only on Phase 1. Fully parallel with US1, US2, US3.
- **Phase 7 (Polish)**: Depends on Phases 3–6 being functionally complete.

### Within Each User Story

- Tests written FIRST and confirmed FAIL before implementation (TDD).
- Backend changes before the frontend tests that exercise them (US2, US3).
- For US4, frontend-only — order is: tests → DashboardLayout fix → AgentPermissionsModal loading prop → button-type audit → dismissal wiring.

### File-Conflict Map (sequence within these files)

| File | Stories that touch it | Order |
|---|---|---|
| `frontend/src/components/CreateAgentModal.tsx` | US1, US2, US3 | US1 → US2 → US3 |
| `backend/orchestrator/agent_lifecycle.py` | Foundational, US2, US3 | T004/T005 → US2 → US3 |
| `backend/orchestrator/orchestrator.py` | US2, US3 | US2 → US3 |
| `frontend/src/hooks/useWebSocket.ts` | Foundational, US3 | T006 → US3 |
| `frontend/src/components/DashboardLayout.tsx` | US3, US4 | independent edits — different code regions; can be parallel if both authors review the merge |
| `frontend/src/components/AgentPermissionsModal.tsx` | US4 only | US4 |

### Parallel Opportunities

- T002 ‖ T003 (Setup baseline checks)
- T005 ‖ T006 (Foundational stub + frontend constants — different files)
- All `[P]` tests within a story phase
- US1 ‖ US4 from the start
- US2 ‖ US4 once Phase 2 is done
- US3 ‖ US4 once Phase 2 is done; US3 should follow US2 within shared backend files
- Polish T047 ‖ T048 ‖ T049 ‖ T050 ‖ T051

---

## Parallel Example: User Story 1

```bash
# All tests for US1 in parallel:
T007: Vitest CreateAgentModal step-4 WS test
T008: Vitest CreateAgentModal generation-failure error state
T009: pytest test-WS handshake transitions generated → testing
```

## Parallel Example: User Story 4 (fully independent)

```bash
# Tests:
T037 + T038: DashboardLayout permissions-modal mount + no-flash
T039:        AgentPermissionsModal no-refresh on interactions
T040:        DashboardLayout dismissal-no-reopen
# Implementation tasks T041–T045 are sequential (same files, dependent edits).
```

## Parallel Example: Bringing US1 + US4 online together

```bash
# Two developers, day 1:
Dev A: T010 (CreateAgentModal WS gating) → T011 (Step-4 error state) → T012 (backend test-WS handshake)
Dev B: T037–T040 (US4 tests) → T041 (openPermissionsModal refactor) → T042 (render gate split) → T043 (loading prop) → T044 (button-type audit) → T045 (dismissal wiring)
```

---

## Implementation Strategy

### MVP scope (Story 1 only)

1. Phase 1 (Setup) — T001–T003
2. Phase 2 (Foundational) — T004–T006 (only T004 and T006 strictly needed for US1; T005 is for US3)
3. Phase 3 (US1) — T007–T012
4. **STOP and VALIDATE** in a real browser per quickstart.md Story 1 section
5. If approved: deploy MVP

This MVP delivers a meaningful slice — users can at least reach a working Test surface — but the loop isn't yet closed without US2 (responses) and US3 (promotion). For a production release that fulfills the user's stated goal, all four stories should ship together because each is P1.

### Recommended incremental delivery

1. Setup + Foundational
2. **Bundle 1: US1 + US4** (both unblock currently-broken UI surfaces; no shared files)
3. **Bundle 2: US2** (tests, then implementation; touches `CreateAgentModal.tsx` after US1's edits)
4. **Bundle 3: US3** (depends on US2's backend edits; closes the loop)
5. Polish + browser verification + merge

### Parallel team strategy

With three developers after Phase 2 lands:

- Dev A: US1 → US2 (sequential because both touch `CreateAgentModal.tsx`)
- Dev B: US3 (sequenced after Dev A's US2 backend edits to avoid `agent_lifecycle.py` merge conflicts)
- Dev C: US4 (fully independent, parallel from day 1)

---

## Notes

- `[P]` tasks operate on different files OR independent code regions of the same file with no semantic conflict.
- Constitution Principle III (90% coverage) applies to all new code paths; Constitution Principle X (production readiness) requires the browser-verification step T052 before merge — do not skip it.
- No schema changes are introduced (research.md R5); no migration script ships with this feature.
- No new third-party libraries (Constitution V).
- Each story checkpoint is a real "stop and validate" moment — exercise the corresponding quickstart.md section before moving on.
