---

description: "Task list for feature 008-llm-text-only-chat"
---

# Tasks: LLM Text-Only Chat When No Agents Enabled

**Input**: Design documents from `/specs/008-llm-text-only-chat/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included. Constitution Principle III mandates 90% coverage on changed code, and the contracts in [contracts/ws-agent-list.md](./contracts/ws-agent-list.md) and [contracts/audit-event-text-only.md](./contracts/audit-event-text-only.md) define explicit acceptance signals that require tests.

**Organization**: Tasks are grouped by user story (US1, US2, US3) so each story can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to user story from [spec.md](./spec.md) (US1 = P1 plain LLM reply; US2 = P2 banner; US3 = P2 tutorial step)
- All file paths below are repository-relative

## Path Conventions

This is a web-app repo with split `backend/` and `frontend/` trees. Tests live in `backend/tests/` (pytest) and `frontend/src/**/__tests__/` (Vitest). Tutorial seed lives in `backend/seeds/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm baseline before changes.

- [x] T001 Run baseline test suites from a clean checkout to confirm green state before any feature changes: `cd backend; pytest`, `cd frontend; npm test`. Record any pre-existing failures as out-of-scope so they aren't attributed to this feature.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish prerequisites that BOTH the dispatch path (US1) and the broadcast path (US2) depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Add `compute_tools_available_for_user(user_id, include_draft_agent_id=None) -> bool` helper method on `Orchestrator` in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py). Mirrors the existing filter loop at [orchestrator.py:1799-1829](../../backend/orchestrator/orchestrator.py#L1799-L1829): returns `True` iff at least one tool survives the agent connectivity, security_flag, and `tool_permissions.is_tool_allowed` filters. Used by US1 (decide whether to enter the text-only branch) and US2 (compute the broadcast flag).
- [x] T003 [P] Add a module-level constant `TEXT_ONLY_SYSTEM_PROMPT_ADDENDUM` in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py) carrying the FR-006a addendum text: tells the LLM (a) it has no tools, (b) MUST NOT fabricate tool output, (c) when the user requests an action requiring an agent, briefly state that no agents are enabled and suggest enabling one. Add a Google-style docstring referencing FR-006a.

**Checkpoint**: Foundation ready — US1, US2, US3 can proceed in parallel.

---

## Phase 3: User Story 1 - Plain LLM conversation when no agents are available (Priority: P1) 🎯 MVP

**Goal**: Replace the early-return "No agents connected" warning with a real LLM dispatch using an empty tools list and the FR-006a system-prompt addendum, so users with a working LLM can chat even when no agents are available.

**Independent Test**: With LLM configured and zero connected agents, send "What is the capital of France?" and confirm the assistant replies with normal text saved to chat history. No warning alert appears. (Quickstart Path 1.)

### Tests for User Story 1

> Write these tests FIRST and confirm they FAIL before implementing T008–T010.

- [x] T004 [P] [US1] Create [backend/tests/test_chat_text_only.py](../../backend/tests/test_chat_text_only.py) with a pytest test `test_handle_chat_message_dispatches_text_only_when_no_tools` that boots the orchestrator with zero agents, calls `handle_chat_message`, mocks `_call_llm` to return a stub assistant message, and asserts: (a) `_call_llm` was called with empty/None `tools_desc`, (b) the messages array passed to `_call_llm` includes the FR-006a addendum in its system prompt, (c) NO `Alert(message="No agents connected...")` was sent via `send_ui_render`, (d) the assistant reply was added to chat history via `self.history.add_message(... "assistant" ...)`.
- [x] T005 [P] [US1] In [backend/tests/test_chat_text_only.py](../../backend/tests/test_chat_text_only.py), add `test_text_only_dispatch_passes_full_history_with_prior_tool_calls` (FR-012, Edge Case "Tool-call attempts from history"): pre-seed chat history with a prior assistant message containing tool_call entries, dispatch a text-only turn, and assert `_call_llm` was called with the messages array containing those prior tool_call/tool_result entries unchanged (not stripped, not summarized).
- [x] T006 [P] [US1] In [backend/tests/test_chat_text_only.py](../../backend/tests/test_chat_text_only.py), add `test_draft_agent_test_chat_does_not_fall_through_to_text_only` (FR-010): set `draft_agent_id` and have the draft agent expose zero usable tools; assert the existing draft-test diagnostic path runs (NOT the new text-only branch) and `_call_llm` is NOT invoked with the FR-006a addendum.
- [x] T007 [P] [US1] In [backend/tests/test_chat_text_only.py](../../backend/tests/test_chat_text_only.py), add `test_text_only_dispatch_emits_audit_event_with_correct_feature_tag` (FR-009, [contracts/audit-event-text-only.md](./contracts/audit-event-text-only.md)): mock the audit recorder, run a successful no-tools dispatch, assert exactly one `_record_llm_call` invocation with `feature="chat_dispatch_text_only"` and `inputs_meta.tools_count == 0`. Also run a tool-augmented dispatch in the same test session and assert NO `chat_dispatch_text_only` event leaks for that turn.

### Implementation for User Story 1

- [x] T008 [US1] Modify `handle_chat_message` in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py) at lines 1831–1835: replace the `if not tools_desc: send Alert + return` block with the text-only branch. New behavior: if `tools_desc` is empty AND `not draft_agent_id`, set a local `is_text_only = True`, append `TEXT_ONLY_SYSTEM_PROMPT_ADDENDUM` (T003) to the system prompt being assembled below (after the canvas-context block ~line 1885), then continue into the existing dispatch loop with `tools_desc=[]`. If `tools_desc` is empty AND `draft_agent_id` is set, retain existing draft-test behavior (FR-010). Preserve all surrounding code (history append, file_mappings, title summarization).
- [x] T009 [US1] In [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py), update the `_call_llm` invocation inside `handle_chat_message` so that when `is_text_only` is True the call passes `feature="chat_dispatch_text_only"` (rather than the default `feature="tool_dispatch"`). This propagates to `_record_llm_call` in [backend/llm_config/audit_events.py:195](../../backend/llm_config/audit_events.py#L195) without changes to the recorder itself.
- [x] T010 [US1] In [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py), add a structured `logger.info` line at the entry of the text-only branch tagging `chat_id`, `user_id`, and `tools_attempted=0` so operators can filter logs alongside the audit event (Constitution Principle X observability).

**Checkpoint**: US1 fully functional — a user with a configured LLM and no agents receives normal text replies, history persists, audit events tag the fallback. Quickstart Paths 1, 2, and 7 all pass.

---

## Phase 4: User Story 2 - Persistent text-only banner with path to enable agents (Priority: P2)

**Goal**: Render a persistent banner at the top of the chat surface whenever the current turn would dispatch in text-only mode, with an inline button that opens the existing agent management modal. Disappears on the next turn that has tools (FR-005, FR-007a).

**Independent Test**: With no agents enabled, open a chat — banner appears at the top and links to the agents modal. Enable an agent — banner disappears on the next render without reload. (Quickstart Paths 4 and 5.)

### Tests for User Story 2

> Write these tests FIRST and confirm they FAIL before implementing T016–T021.

- [x] T011 [P] [US2] In [backend/tests/test_chat_text_only.py](../../backend/tests/test_chat_text_only.py) (or a dedicated `test_agent_list_tools_flag.py` if test isolation matters), add `test_agent_list_payload_includes_tools_available_for_user_false_when_no_agents`: drive `send_agent_list` with zero connected agents and assert the broadcast JSON has top-level `tools_available_for_user: false`. Reference [contracts/ws-agent-list.md](./contracts/ws-agent-list.md).
- [x] T012 [P] [US2] In the same backend test module, add `test_agent_list_payload_includes_tools_available_for_user_true_when_user_has_at_least_one_allowed_tool`: register one agent with one tool that survives `tool_permissions.is_tool_allowed`, call `send_agent_list`, assert top-level `tools_available_for_user: true`.
- [x] T013 [P] [US2] Create [frontend/src/components/__tests__/TextOnlyBanner.test.tsx](../../frontend/src/components/__tests__/TextOnlyBanner.test.tsx) with `it('mounts the banner when toolsAvailableForUser is false')`: render `<TextOnlyBanner toolsAvailableForUser={false} onOpenAgentSettings={vi.fn()} />` and assert visible text mentions text-only mode and a "Enable agents" CTA exists in the DOM.
- [x] T014 [P] [US2] In [frontend/src/components/__tests__/TextOnlyBanner.test.tsx](../../frontend/src/components/__tests__/TextOnlyBanner.test.tsx), add `it('unmounts when toolsAvailableForUser flips to true')`: render with `false`, then re-render with `true`, assert the banner is no longer in the DOM.
- [x] T015 [P] [US2] In [frontend/src/components/__tests__/TextOnlyBanner.test.tsx](../../frontend/src/components/__tests__/TextOnlyBanner.test.tsx), add `it('fires onOpenAgentSettings when the CTA is clicked')`: render with `false` and a `vi.fn()` handler, simulate a click on the CTA button, assert the handler was called once.

### Implementation for User Story 2

- [x] T016 [US2] Update `send_agent_list` (around [orchestrator.py:4003-4037](../../backend/orchestrator/orchestrator.py#L4003-L4037)) in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py) to compute `tools_available_for_user = self.compute_tools_available_for_user(user_id)` (T002 helper) and include it as a top-level field in the JSON payload alongside `agents`. Per [contracts/ws-agent-list.md](./contracts/ws-agent-list.md), the field MUST be present unconditionally. The user_id MUST come from the receiving WebSocket (`self._get_user_id(websocket)`).
- [x] T017 [P] [US2] Create [frontend/src/components/TextOnlyBanner.tsx](../../frontend/src/components/TextOnlyBanner.tsx) — a new functional component with props `{ toolsAvailableForUser: boolean, onOpenAgentSettings: () => void }`. When `toolsAvailableForUser === false`, render a top-of-chat banner using Tailwind classes consistent with the rest of `ChatInterface.tsx` (matching dark theme, rounded corners) and Framer Motion `<AnimatePresence>` for mount/unmount fade. Banner copy: state that no agents are currently enabled and the assistant is in text-only mode; include a primary button labeled "Enable agents" that calls `onOpenAgentSettings`. Add JSDoc on the props interface (Constitution Principle VI).
- [x] T018 [US2] Update the `case "agent_list":` handler in [frontend/src/hooks/useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts) at lines 319–321: in addition to setting `agents`, set a new state `toolsAvailableForUser` from `data.tools_available_for_user`. Defensive default: if the field is absent (older backend), fall back to `(data.agents?.length ?? 0) > 0` per [contracts/ws-agent-list.md](./contracts/ws-agent-list.md). Export the new state from the hook.
- [x] T019 [US2] In [frontend/src/App.tsx](../../frontend/src/App.tsx), thread the new `toolsAvailableForUser` value from `useWebSocket` into the existing `<DashboardLayout>` props.
- [x] T020 [US2] In [frontend/src/components/DashboardLayout.tsx](../../frontend/src/components/DashboardLayout.tsx), accept `toolsAvailableForUser` and pass it plus a new callback `onOpenAgentSettings={() => setAgentsModalOpen(true)}` down to the `<ChatInterface>` props.
- [x] T021 [US2] In [frontend/src/components/ChatInterface.tsx](../../frontend/src/components/ChatInterface.tsx), accept the two new props (`toolsAvailableForUser`, `onOpenAgentSettings`) and mount `<TextOnlyBanner toolsAvailableForUser={...} onOpenAgentSettings={...} />` at the top of the messages region (immediately inside the `<div className="flex-1 overflow-y-auto ...">` block, before the `{messages.length === 0 ...}` empty-state block).

**Checkpoint**: US2 fully functional — banner appears whenever the current user has zero usable tools and disappears the moment that changes. Clicking the CTA opens the existing agents modal. Quickstart Paths 4 and 5 pass.

---

## Phase 5: User Story 3 - Onboarding tutorial step pointing users to agents (Priority: P2)

**Goal**: Add a dedicated onboarding step that explicitly tells the user to turn on at least one agent, so users discover agent enablement during their first session (FR-007b).

**Independent Test**: A new user steps through onboarding and sees a step (between "Browse available agents" and "Review the audit log") that says "Turn an agent on" and points to the agents panel. (Quickstart Path 6.)

### Tests for User Story 3

> Write this test FIRST and confirm it FAILS before implementing T023.

- [x] T022 [P] [US3] In [backend/onboarding/tests/test_seed.py](../../backend/onboarding/tests/test_seed.py) (the existing seed test module), add `test_seed_creates_enable_agents_step`: run the seed against a fresh test database, query the `tutorial_step` table, assert a row exists with `slug='enable-agents'`, `audience='user'`, `display_order=35`, `target_kind='static'`, `target_key='sidebar.agents'`, and a body containing the literal phrase `turn` and `agent` (case-insensitive). If the file does not yet exist, create it following the convention used by other tests in [backend/onboarding/tests/](../../backend/onboarding/tests/).

### Implementation for User Story 3

- [x] T023 [US3] Append a new INSERT row to the user-flow block in [backend/seeds/tutorial_steps_seed.sql](../../backend/seeds/tutorial_steps_seed.sql) immediately after the `open-agents-panel` row: `('enable-agents', 'user', 35, 'static', 'sidebar.agents', 'Turn an agent on', 'Open the Agents panel and switch on at least one agent. Until you do, AstralBody talks to the language model in text-only mode — it can chat, but it can''t take actions on your behalf.')`. The trailing `ON CONFLICT (slug) DO NOTHING` clause already on the multi-row INSERT covers idempotency (Constitution Principle IX).

**Checkpoint**: US3 fully functional — the new step appears in the user tutorial flow at display_order 35, sandwiched between "Browse available agents" (30) and "Review the audit log" (40).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final gates before merge.

- [x] T024 [P] Run `ruff check backend/` and fix any new lint errors introduced by this feature (Constitution Principle IV).
- [x] T025 [P] Run `npm run lint` (or equivalent ESLint command) in `frontend/` and fix any new lint errors (Constitution Principle IV).
- [x] T026 Verify code coverage on changed files meets the Constitution Principle III ≥90% threshold: `cd backend; pytest --cov=orchestrator --cov-report=term-missing tests/test_chat_text_only.py backend/tests/test_agent_flow.py backend/onboarding/tests/test_seed.py`. For frontend, run `cd frontend; npm test -- --coverage TextOnlyBanner`.
- [ ] T027 Walk all 7 paths in [quickstart.md](./quickstart.md) manually against a running backend + frontend (Constitution Principle X — UI changes MUST be exercised in a real browser before declaring complete).
- [x] T028 [P] Update [README.md](../../README.md) (or feature index) only if the existing README references chat behavior — note the new text-only fallback. If README does not currently document chat behavior, skip.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup, T001)**: No dependencies — start immediately.
- **Phase 2 (Foundational, T002–T003)**: Depends on Phase 1. BLOCKS US1, US2.
  - T002 (helper) → required by T008 (US1) and T016 (US2).
  - T003 (constant) → required by T008 (US1).
  - US3 does NOT need Phase 2.
- **Phase 3 (US1)**: Depends on T002 and T003.
- **Phase 4 (US2)**: Depends on T002.
- **Phase 5 (US3)**: Depends only on Phase 1.
- **Phase 6 (Polish, T024–T028)**: Depends on whichever stories are being shipped.

### User Story Dependencies

- **US1 (P1)**: Independent of US2 and US3. Delivers the core feature value alone.
- **US2 (P2)**: Independent of US1 in build order — both share T002 only. The banner reads tool-availability state regardless of whether the dispatch path has been switched. (In practice ship US1 first to avoid a banner that nudges users toward a non-functional path.)
- **US3 (P2)**: Fully independent of US1 and US2. Pure data change.

### Within Each User Story

- Tests MUST be written first and FAIL before implementation tasks land.
- US1: T004–T007 (tests) → T008 → T009 → T010.
- US2 backend: T011–T012 (tests) → T016. US2 frontend: T013–T015 (tests) → T017 → T018 → T019 → T020 → T021. Note T017 can run in parallel with the backend half.
- US3: T022 → T023.

### Parallel Opportunities

- All `[P]`-marked tasks within a phase touch different files and have no inter-dependency.
- **Within Phase 2**: T003 (constant) is parallel to T002 (helper) — different concerns, same file but different region; in practice safe to do back-to-back.
- **Within US1 tests**: T004, T005, T006, T007 can be authored in parallel (all in the same new test file but each is an independent function — split or pair-program if needed).
- **Within US2 tests**: T011 + T012 (backend) parallel to T013 + T014 + T015 (frontend) — different files entirely.
- **Across stories**: With multiple developers, US1, US2, and US3 can proceed simultaneously after Phase 2 completes.

---

## Parallel Example: User Story 1 Tests

```bash
# Author all four US1 tests concurrently (different functions in the same new file):
Task: "test_handle_chat_message_dispatches_text_only_when_no_tools in backend/tests/test_chat_text_only.py"
Task: "test_text_only_dispatch_passes_full_history_with_prior_tool_calls in backend/tests/test_chat_text_only.py"
Task: "test_draft_agent_test_chat_does_not_fall_through_to_text_only in backend/tests/test_chat_text_only.py"
Task: "test_text_only_dispatch_emits_audit_event_with_correct_feature_tag in backend/tests/test_chat_text_only.py"
```

## Parallel Example: User Story 2 (cross-stack)

```bash
# Backend and frontend test work fan out simultaneously:
Task: "Backend: test_agent_list_payload_includes_tools_available_for_user_false_when_no_agents"
Task: "Backend: test_agent_list_payload_includes_tools_available_for_user_true_when_user_has_at_least_one_allowed_tool"
Task: "Frontend: TextOnlyBanner mounts when toolsAvailableForUser is false"
Task: "Frontend: TextOnlyBanner unmounts when toolsAvailableForUser flips to true"
Task: "Frontend: TextOnlyBanner CTA fires onOpenAgentSettings"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 — Setup (T001).
2. Phase 2 — Foundational (T002, T003).
3. Phase 3 — US1 (T004–T010).
4. **STOP and VALIDATE**: walk Quickstart Paths 1, 2, and 7. Confirm a user with no agents gets an LLM reply.
5. Ship MVP.

### Incremental Delivery

After MVP:

- Add US2 → ship banner + agent_list flag (Quickstart Paths 4 and 5).
- Add US3 → ship tutorial step (Quickstart Path 6).
- Run full Quickstart at end (T027).

### Parallel Team Strategy

After Phase 2 completes:

- Developer A: US1 (backend dispatch path).
- Developer B: US2 (banner UI + agent_list extension) — can split: B-backend on T011, T012, T016; B-frontend on T013–T015, T017–T021.
- Developer C: US3 (seed addition + test).

All three streams converge in Phase 6 polish.

---

## Notes

- All file paths are repository-relative; tests are co-located per the conventions surfaced in [research.md](./research.md).
- No new third-party dependencies are introduced (Constitution Principle V passes without exception).
- Schema is unchanged; the only data-side touch is one idempotent SQL row in an existing seed (Constitution Principle IX).
- Verify each test fails before its implementation lands (TDD discipline).
- Commit at each task or logical group; pause at any checkpoint to re-test the prior story for regressions.
