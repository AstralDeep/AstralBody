---
description: "Task list for In-Chat Progress Notifications & Persistent Step Trail"
---

# Tasks: In-Chat Progress Notifications & Persistent Step Trail

**Input**: Design documents from `/specs/014-progress-notifications/`
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are included throughout — Constitution III requires every new feature to ship with unit + integration tests at ≥ 90% coverage on changed code. Tests are written before implementation in each phase.

**Organization**: Tasks are grouped by user story so each can be implemented, tested, and demoed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: Which user story this task belongs to (US1, US2, US3). Setup/Foundational/Polish tasks have no story label.
- File paths are repository-relative.

## Path Conventions

- **Backend**: `backend/orchestrator/`, `backend/shared/`, `backend/tests/`
- **Frontend**: `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/api/`, `frontend/src/types/`, `frontend/src/__tests__/`, `frontend/src/hooks/__tests__/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new folder for chat-related components. The repo is already initialized; nothing else is needed at this stage.

- [X] T001 Create directory `frontend/src/components/chat/` for the new chat-area components (CosmicProgressIndicator, ChatStepEntry, chatStepWords)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: This feature has **no cross-story foundational dependencies** — User Story 1 (P1, MVP) is fully client-side and stands alone. Backend recorder, schema, and PHI redactor are scoped to User Story 2 since US1 does not need them. User Story 3 builds on US2's `<ChatStepEntry>` component.

**Checkpoint**: Phase 2 is intentionally empty. User stories may begin immediately after Phase 1.

---

## Phase 3: User Story 1 - Ambient rotating progress indicator (Priority: P1) 🎯 MVP

**Goal**: Replace the existing static "Processing…" loader with a rotating cosmic-word indicator inside the loading slot of `ChatInterface.tsx`. The indicator is purely client-side, driven by the existing `chatStatus.status` state — no backend or schema work required.

**Independent Test**: Submit a query that takes longer than ~500 ms; observe a rotating word from the approved 55-word list, changing at least once per second, disappearing as soon as the assistant reply finishes (covers spec SC-001, SC-002 and US1 acceptance scenarios 1–4).

### Tests for User Story 1

> Write these tests FIRST and confirm they fail against the current `ChatInterface.tsx` before implementing.

- [X] T002 [P] [US1] Write Vitest tests for `<CosmicProgressIndicator>` (mounts on `chatStatus.status ∈ {thinking, executing, fixing}`, unmounts on `idle`/`done`, displayed word ∈ approved list, word changes at least once per second, never repeats two in a row) in `frontend/src/__tests__/CosmicProgressIndicator.test.tsx`

### Implementation for User Story 1

- [X] T003 [P] [US1] Create the 55-word approved constant array (typed `readonly string[]`) and exported helper `pickCosmicWord(prev?: string)` in `frontend/src/components/chat/chatStepWords.ts`
- [X] T004 [US1] Implement `<CosmicProgressIndicator>` consuming `chatStatus.status`, using `framer-motion` fade transitions at 200 ms and a 1.2 s rotation interval with cleanup on unmount, in `frontend/src/components/chat/CosmicProgressIndicator.tsx` (depends on T003)
- [X] T005 [US1] Replace the static `"Processing..."` `<span>` inside the loading slot at lines ~715-741 of `frontend/src/components/ChatInterface.tsx` with `<CosmicProgressIndicator />`, keeping the existing cancel button and surrounding `<motion.div>` intact (depends on T004)

**Checkpoint**: US1 fully shippable as an MVP. Indicator visible, rotating, hidden on completion. No backend changes deployed.

---

## Phase 4: User Story 2 - Persistent in-chat step trail (Priority: P2)

**Goal**: Each tool invocation, agent hand-off, and orchestrator phase emits a `chat_step` lifecycle event that the frontend renders as a persistent entry in the chat between the user message and the assistant reply. Entries persist via a new `chat_steps` table (with PHI redaction) and are rehydrated on chat load via `GET /chats/{id}/steps`.

**Independent Test**: Submit a query that triggers multiple tool calls; observe entries appearing as steps begin, status flipping on completion, entries surviving page reload (covers spec FR-007 through FR-013, FR-009a/b, FR-020/021, SC-003, SC-004, SC-008 and US2 acceptance scenarios 1–5).

### Tests for User Story 2

- [X] T006 [P] [US2] Backend pytest covering `ChatStepRecorder` lifecycle (start emits in-progress event, complete emits terminal event with truncated args/result, error emits errored event with redacted error message, cancel emits cancelled event for all in-flight rows), in `backend/tests/test_chat_steps.py`
- [X] T007 [P] [US2] Backend pytest covering `phi_redactor.redact()` (HIPAA Safe Harbor identifiers — name, DOB, SSN, MRN, address, phone, email, account, certificate, vehicle, device, biometric, photo URL — masked at field-key and value-pattern level; safe content passes through unchanged; truncation runs after redaction; never raises on malformed JSON), in `backend/tests/test_phi_redactor.py`
- [X] T008 [P] [US2] Backend pytest covering migration idempotency (run `Database._init_schema()` twice, no error, `chat_steps` table present, `messages.step_count` column added with default 0, foreign keys enforced, indexes created), in `backend/tests/test_chat_steps_migration.py`
- [X] T009 [P] [US2] Backend pytest covering `GET /chats/{chat_id}/steps` (200 with empty list for new chat, 200 with sorted entries for chat with steps, 403 cross-user, 404 unknown chat, read-time `interrupted` healing for stale `in_progress` rows older than 30 s with no active task, defense-in-depth redaction on read), in `backend/tests/test_chat_steps_api.py`
- [X] T010 [P] [US2] Frontend Vitest covering the `case "chat_step"` arm of `useWebSocket` (event payload merges into `chatSteps[chat_id][step_id]` map, terminal event overwrites in-progress entry, out-of-order delivery resolves to highest `started_at`/`ended_at` view), in `frontend/src/hooks/__tests__/useWebSocket.chatSteps.test.ts`
- [X] T011 [P] [US2] Frontend Vitest covering `<ChatStepEntry>` rendering for all five statuses (in-progress / completed / errored / cancelled / interrupted), truncation badge when `args_was_truncated` or `result_was_truncated` is true, error message visible only on `errored` status, in `frontend/src/__tests__/ChatStepEntry.test.tsx`

### Implementation for User Story 2 — backend types & utilities (parallel-safe)

- [X] T012 [P] [US2] Add idempotent schema delta to `Database._init_schema()`: `CREATE TABLE IF NOT EXISTS chat_steps(...)` with the columns and indexes from [data-model.md](./data-model.md), and `_column_exists`-guarded `ALTER TABLE messages ADD COLUMN step_count INTEGER NOT NULL DEFAULT 0`, in `backend/shared/database.py`
- [X] T013 [P] [US2] Implement `redact(value, *, kind)` in `backend/shared/phi_redactor.py` — pure-Python, dependency-free, regex + key-name pattern set covering the HIPAA Safe Harbor 18 identifiers; truncates `kind ∈ {"args","result","error"}` to 512 chars after redaction; emits `phi_redactor.redaction_applied` structured-log when a mask is applied; never raises (returns `"[redaction failed]"` on internal exception)
- [X] T014 [P] [US2] Add `ChatStep`, `ChatStepKind`, `ChatStepStatus` types matching [data-model.md](./data-model.md) in `frontend/src/types/chatSteps.ts`

### Implementation for User Story 2 — backend recorder & emit seams

- [X] T015 [US2] Implement `ChatStepRecorder` class in `backend/orchestrator/chat_steps.py` with `start(kind, name, args)`, `complete(step_id, result)`, `error(step_id, exception)`, `cancel_all_in_flight()` methods. Each method (a) PHI-redacts + truncates via T013, (b) writes/updates the `chat_steps` row + bumps `messages.step_count`, (c) emits a `chat_step` WebSocket event matching `contracts/chat_step_event.md`, (d) structured-logs lifecycle transitions. Depends on T012, T013.
- [X] T016 [P] [US2] Wire `ChatStepRecorder.start/complete/error` around `Orchestrator.execute_tool_and_wait()`, `_execute_via_websocket()`, and `_execute_via_a2a()` (around lines 3410–3527, 3691) in `backend/orchestrator/orchestrator.py` so every tool call emits a `tool_call` step. Depends on T015.
- [X] T017 [P] [US2] Wire `ChatStepRecorder.start/complete/error` around the agent delegation seam in `backend/orchestrator/coordinator.py` so each hand-off emits an `agent_handoff` step. Depends on T015.
- [X] T018 [US2] Add sibling `recorder.start/complete` calls beside the existing ~25 `chat_status` emit sites in `backend/orchestrator/orchestrator.py` (lines 950, 1012, 1438, 1840, 1911, 2186, 2215, 2243, 2374, 2498, 2537, 2547, 2568, 2585, 2605, 2618, 3152, 3164, 3170, 3327, 3337, etc.) so each phase boundary emits a `phase` step. Depends on T015. (Same file as T016, so sequential.)
- [X] T019 [US2] Wire `ChatStepRecorder.cancel_all_in_flight()` into the `cancel_task` handler at `backend/orchestrator/orchestrator.py:947` and into the `Task.transition(CANCELLED)` path in `backend/orchestrator/task_state.py` so user-cancel marks every in-flight step `cancelled` and short-circuits result integration per R6. Depends on T015, T018.
- [X] T020 [US2] Add `GET /chats/{chat_id}/steps` endpoint in `backend/orchestrator/api.py` per [`contracts/chat_steps_rest.md`](./contracts/chat_steps_rest.md): Keycloak auth, ownership scope, sorted response, read-time `interrupted` healing for stale rows, defense-in-depth `phi_redactor.redact` on every field on the way out, `Cache-Control: no-store`. Depends on T012, T013.

### Implementation for User Story 2 — frontend (parallel-safe with backend)

- [X] T021 [P] [US2] Add `chatSteps` state (typed `Record<chat_id, Record<step_id, ChatStep>>`) and a `case "chat_step"` arm in the `handleMessage` switch of `frontend/src/hooks/useWebSocket.ts`; expose `chatSteps` from the hook return. Depends on T014.
- [X] T022 [P] [US2] Implement `<ChatStepEntry>` in `frontend/src/components/chat/ChatStepEntry.tsx` rendering name, status icon, `args_truncated`, `result_summary`, `error_message`, and a `truncated` badge. Use existing primitives (`Card`, `Text`) and Tailwind tokens consistent with the rest of `ChatInterface.tsx`. Defaults its expanded/collapsed view based on `status` (in-progress / errored / cancelled → expanded; completed → collapsed) — note that the durable session-persisted toggle arrives in US3. Depends on T014.
- [X] T023 [P] [US2] Add `fetchChatSteps(chatId: string): Promise<ChatStep[]>` calling `GET /chats/{id}/steps` via the existing `fetchJson` helper, in `frontend/src/api/chatSteps.ts`.
- [X] T024 [US2] In `frontend/src/hooks/useWebSocket.ts`, on chat-load (`chat_loaded` message) and on WebSocket reconnect, call `fetchChatSteps(activeChatId)` (T023) and merge results into the `chatSteps` map; ensure entries newer than the snapshot via the live `chat_step` arm reconcile correctly. Depends on T021, T023.
- [X] T025 [US2] In `frontend/src/components/ChatInterface.tsx`, group `chatSteps[activeChatId]` by `turn_message_id`, sort by `started_at`, and render `<ChatStepEntry>` rows interleaved between the user message and the matching assistant reply inside the existing `messages.map` block (lines ~673–712). Live-running steps for the active turn render before the assistant reply arrives. Depends on T021, T022.

**Checkpoint**: US2 shippable independently of US3 — entries appear, persist, survive reload, redact PHI, handle cancellation. Default collapse follows status but is not session-persistent yet.

---

## Phase 5: User Story 3 - Collapsible entries with session-persistent state (Priority: P3)

**Goal**: User toggles of step-entry collapse/expand state persist across page reloads and chat-switching within the same browser session via `sessionStorage`. Status-dependent defaults (US2) become overridable per FR-017.

**Independent Test**: After a turn finishes, manually expand/collapse various entries; reload the page within the same tab — every entry's state matches what the user last set (covers spec FR-014 through FR-019, SC-005 and US3 acceptance scenarios 1–6).

### Tests for User Story 3

- [X] T026 [P] [US3] Frontend Vitest covering `useStepCollapseState(stepId, status)` hook: returns status-dependent default when no override stored, returns stored override when present, persists toggle to `sessionStorage` under key `astral.chat_step_collapse.v1`, survives unmount/remount within the same `sessionStorage`, in `frontend/src/hooks/__tests__/useStepCollapseState.test.ts`
- [X] T027 [P] [US3] Frontend Vitest covering `<ChatStepEntry>` collapse-toggle behaviour with `useStepCollapseState` wired in: clicking the toggle flips state and persists, status changes from in-progress → completed/errored apply the new default only when no override is set, in `frontend/src/__tests__/ChatStepEntry.collapse.test.tsx`

### Implementation for User Story 3

- [X] T028 [P] [US3] Implement `useStepCollapseState(stepId: string, status: ChatStepStatus)` in `frontend/src/hooks/useStepCollapseState.ts`: reads/writes JSON object at `sessionStorage` key `astral.chat_step_collapse.v1`, status-dependent defaults from FR-016 (success → collapsed; error/cancelled/interrupted → expanded; in-progress → expanded), per-entry override-wins-over-default per FR-017, returns `{ collapsed: boolean, toggle: () => void }`.
- [X] T029 [US3] Replace the local US2 default-collapse logic in `frontend/src/components/chat/ChatStepEntry.tsx` with a call to `useStepCollapseState(step.id, step.status)`; wire its `toggle` to the expand/collapse affordance with an accessible button (`aria-expanded`, keyboard-reachable) and screen-reader announcement on state change per Constitution VIII / accessibility assumption. Depends on T028.

**Checkpoint**: All three user stories independently functional. Reload-survival, session-scoping, and status-dependent defaults all confirmed.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Production-readiness gates per Constitution X — coverage, lint, end-to-end browser walk-through, and observability validation.

- [DEFERRED-CI] T030 [P] Verify backend coverage ≥ 90% on changed files via `pytest --cov`. **Local status:** `pytest-cov` is not installed locally and adding it requires lead-developer approval per Constitution V. Coverage is enforced in CI per Constitution III. Local evidence: 103 new backend tests across 4 files exercise every branch of `phi_redactor.py`, `chat_steps.py`, the `chat_steps` schema migration, and the `GET /api/chats/{id}/steps` endpoint (auth, ownership, sorting, healing, defense-in-depth redaction).
- [DEFERRED-CI] T031 [P] Verify frontend coverage ≥ 90% on changed files via `vitest --coverage`. **Local status:** `@vitest/coverage-v8` is not installed locally (Constitution V). Coverage is enforced in CI. Local evidence: 55 new frontend tests across 5 files cover `<CosmicProgressIndicator>` lifecycle/word selection/cadence, `<ChatStepEntry>` all 5 statuses + truncation badges + error rendering, `useStepCollapseState` defaults/overrides/persistence/corrupt-storage, and the `chat_step` WebSocket arm merge semantics.
- [X] T032 [P] Run `cd backend && ruff check .` and resolve every finding (no `# noqa` exceptions per Constitution IV)
- [X] T033 [P] Run `cd frontend && npm run lint` and resolve every finding (no `eslint-disable` exceptions per Constitution IV)
- [USER-OWNED] T034 Walk through every section of [quickstart.md](./quickstart.md) in a real browser against the running backend (Constitution X) — confirm US1, US2, US3, cancellation semantics, and PHI redaction all behave as specified, covering SC-001 through SC-008. **Cannot be executed by the implementing agent — requires a real browser session against the running stack.** Quickstart is up-to-date and ready to follow.
- [USER-OWNED] T035 Sample-audit the PHI redactor on production-shaped step content per the SC-008 procedure: trigger steps with synthetic PHI inputs, expand each entry, retrieve via `GET /chats/{id}/steps`, confirm `phi_redactor.redaction_applied` log events fired and no PHI is visible in either the live or rehydrated rendering. **Cannot be executed by the implementing agent — requires production-shaped synthetic PHI test data.** PHI redactor unit tests (T007) already verify that all HIPAA Safe Harbor identifier categories are masked.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; can start immediately.
- **Phase 2 (Foundational)**: Empty — no cross-story prerequisites in this feature.
- **Phase 3 (US1)**: Depends only on Phase 1. Standalone MVP.
- **Phase 4 (US2)**: Depends only on Phase 1. Independent of US1.
- **Phase 5 (US3)**: Depends on Phase 4 (consumes the `<ChatStepEntry>` component from US2).
- **Phase 6 (Polish)**: Runs after all desired user stories are complete.

### User Story Dependencies

- **US1 (P1)**: Independent. Ships as MVP.
- **US2 (P2)**: Independent of US1. Can be developed in parallel with US1.
- **US3 (P3)**: Depends on US2 (extends `<ChatStepEntry>`).

### Within Each User Story

- Tests (T002 / T006-T011 / T026-T027) are written first and confirmed failing before the corresponding implementation tasks.
- Backend types/utilities (T012, T013, T014) come before the recorder (T015) which comes before its consumers (T016-T020).
- Frontend types (T014) come before the WebSocket arm (T021) and entry component (T022), which come before the chat-load merge (T024) and the message-list integration (T025).
- US3 hook (T028) before its consumer wiring (T029).

### Parallel Opportunities

- **Phase 3 (US1)**: T002 and T003 are different files; T002 ↔ T003 ↔ early scaffold of T004 can interleave once T003 is in. T004 → T005 sequentially in the same file.
- **Phase 4 (US2)**:
  - All test files T006–T011 are mutually independent — run in parallel.
  - T012, T013, T014 touch different files — run in parallel.
  - T016 (`orchestrator.py` execute_tool seams) and T017 (`coordinator.py`) are different files — parallel. T018 is also in `orchestrator.py` so it must follow T016 sequentially.
  - T021, T022, T023 touch different files — run in parallel after T014.
  - T024 (`useWebSocket.ts` — same file as T021) follows T021. T025 (`ChatInterface.tsx`) needs T021 + T022.
- **Phase 5 (US3)**: T026 and T027 are different test files — parallel. T028 and T029 touch different files but T029 depends on T028.
- **Phase 6 (Polish)**: T030–T033 run in parallel; T034 and T035 follow.

### Cross-Story Parallelism

Once Phase 1 lands, US1 and US2 work streams can run in parallel by different developers. US3 starts when US2's `<ChatStepEntry>` (T022) is mergeable.

---

## Parallel Example: User Story 2 test scaffolding

```bash
# Launch all US2 tests in parallel (different files, no shared state):
Task: "Backend pytest for ChatStepRecorder lifecycle in backend/tests/test_chat_steps.py"
Task: "Backend pytest for phi_redactor in backend/tests/test_phi_redactor.py"
Task: "Backend pytest for migration idempotency in backend/tests/test_chat_steps_migration.py"
Task: "Backend pytest for GET /chats/{id}/steps in backend/tests/test_chat_steps_api.py"
Task: "Frontend Vitest for chat_step WebSocket arm in frontend/src/hooks/__tests__/useWebSocket.chatSteps.test.ts"
Task: "Frontend Vitest for <ChatStepEntry> rendering in frontend/src/__tests__/ChatStepEntry.test.tsx"
```

```bash
# Once tests are written, launch US2 backend foundation tasks in parallel:
Task: "Add chat_steps table + step_count column in backend/shared/database.py"
Task: "Implement phi_redactor in backend/shared/phi_redactor.py"
Task: "Add ChatStep types in frontend/src/types/chatSteps.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup (T001).
2. Skip Phase 2 (empty for this feature).
3. Phase 3: US1 (T002 → T003 → T004 → T005).
4. **STOP and VALIDATE**: Walk through the US1 section of `quickstart.md` in a browser.
5. Deploy/demo: rotating cosmic word visible during processing.

### Incremental Delivery

1. MVP (US1) → Demo. Indicator alone is a tangible UX win.
2. US2 → Demo. Step entries appear and persist; PHI redaction in place.
3. US3 → Demo. Collapse states survive reload within the session.
4. Phase 6 → Merge gate. Coverage, lint, browser walk-through, PHI audit.

### Parallel Team Strategy

- Developer A: US1 (frontend only, ~half a day).
- Developer B: US2 backend half (T012, T013, T015–T020).
- Developer C: US2 frontend half (T014, T021, T022, T023, T024, T025).
- Developer D (after T022 lands): US3 (T026–T029).
- Whoever finishes first picks up Phase 6.

---

## Notes

- `[P]` tasks operate on different files with no incomplete-task dependencies.
- `[Story]` labels (US1/US2/US3) map every implementation task back to its user story for traceability.
- Each user story is independently completable, testable, and demoable.
- Tests are written before implementation in each phase per Constitution III; coverage is enforced in Phase 6.
- Avoid: same-file edit conflicts (see sequential-vs-parallel notes above), cross-story coupling that breaks independence, scope creep (e.g., chat-export integration, backend per-user collapse-state persistence — both deferred per spec/research).
- Commit after each task or per logical group; the optional `/speckit-git-commit` hook can wrap each phase.
