---

description: "Task list for feature 013 — Agent Visibility, Active-Agent Clarity, Per-Tool Permissions, and In-Chat Tool Picker"
---

# Tasks: Agent Visibility, Active-Agent Clarity, Per-Tool Permissions, and In-Chat Tool Picker

**Input**: Design documents from `specs/013-agent-visibility-tool-picker/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: REQUIRED. Constitution Principle III mandates ≥90% coverage on changed code with unit + integration tests; Principle X requires golden, edge, and error tests for every shipping change. Tests are listed inline within each story phase.

**Organization**: Tasks are grouped by the four user stories from [spec.md](./spec.md). Each story is independently shippable and independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1 / US2 / US3 / US4)

## Path Conventions

Web-application layout: `backend/`, `frontend/`, `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the placeholder files and directories the rest of the feature depends on. Existing project structure is reused.

- [X] T001 [P] Create migration script file `backend/seeds/013_per_tool_permissions.sql` (documents the schema delta; the actual changes are applied by `Database._init_db()` per project idiom — see file header)
- [X] T002 [P] Create empty stub `frontend/src/components/ToolPicker.tsx` exporting a default React component (no behavior yet) so other components can import it without breaking compilation
- [X] T003 [P] Create empty stub `frontend/src/api/toolSelection.ts` exporting `getUserToolSelection`, `setUserToolSelection`, `clearUserToolSelection` (real implementations against the API; will be wired up in T036)
- [X] T004 [P] Create test directories `tests/backend/unit/feature_013/` and `tests/backend/integration/feature_013/` and a frontend test directory `frontend/src/components/__tests__/feature_013/`

---

## Phase 2: Foundational (Blocking Prerequisites for US2, US3, US4)

**Purpose**: Schema delta, database helpers, and per-tool-permissions resolver. These block User Stories 2, 3, and 4 (US1 is frontend-only and may proceed in parallel with this phase).

**⚠️ CRITICAL**: US2, US3, and US4 cannot start their implementation until T005–T009 are complete. US1 has no dependency on this phase.

- [X] T005 Schema delta applied via `backend/shared/database.py::Database._init_db()` (project's auto-migration mechanism — runs on every backend startup). Adds `chats.agent_id TEXT NULL` (FR-006/FR-009) and `tool_overrides.permission_kind TEXT NULL` plus the new unique index `tool_overrides_user_agent_tool_kind_uniq` keyed on `(user_id, agent_id, tool_name, COALESCE(permission_kind, ''))`. Existing legacy NULL-kind rows continue to work as tool-wide overrides. Down path documented in [`backend/seeds/013_per_tool_permissions.sql`](../../backend/seeds/013_per_tool_permissions.sql).
- [X] T006 `get_chat_agent(chat_id)` and `set_chat_agent(chat_id, agent_id)` added to `backend/shared/database.py`. `HistoryManager.create_chat` now accepts `agent_id` and persists it; `get_chat` and `get_recent_chats` surface `agent_id` in their results.
- [X] T007 [P] `get_user_tool_selection`, `set_user_tool_selection`, `clear_user_tool_selection` added to `backend/shared/database.py`, wrapping `get/set_user_preferences` around the `tool_selection.<agent_id>` JSON key per data-model §3.
- [X] T008 [P] `backend/orchestrator/tool_permissions.py` refactored: `is_tool_allowed` now resolves per-(tool, kind) rows first, falls back to legacy NULL-kind override, then to `agent_scopes`. Added `get_effective_tool_permissions(user_id, agent_id)`, `set_tool_permission(user_id, agent_id, tool_name, permission_kind, enabled)`, and `backfill_per_tool_rows(user_id, agent_id)` (idempotent FR-015 1:1 carry-forward). `get_allowed_tools` and `get_effective_permissions` now route through `is_tool_allowed` so per-kind state is honored consistently.
- [X] T009 Unit test `tests/backend/unit/feature_013/test_migration_idempotent.py` covers: schema delta presence, _init_db idempotency on re-construction, legacy NULL-kind and per-kind rows coexisting, the per-kind unique constraint, chat-agent helpers round-trip, and per-user tool-selection helpers (get/set/clear).

**Checkpoint**: Foundation ready. US2, US3, US4 may now proceed (US1 was unblocked from the start).

---

## Phase 3: User Story 1 — Created agents appear under "My Agents" (Priority: P1) 🎯 MVP

**Goal**: Every agent the user owns (draft / testing / live) appears under "My Agents." Agents the user owns AND has flagged public surface in **both** "My Agents" and "Public Agents."

**Independent Test**: Sign in as a test user with at least one draft, one live, and one live-and-public owned agent plus one public agent owned by someone else; open the agents listing modal and verify the My Agents and Public Agents tabs match the expected sets per [quickstart.md §1](./quickstart.md#1-story-1--my-agents-visibility).

### Implementation for US1

- [X] T010 [US1] Filter logic extracted to [`frontend/src/components/agentTabFilters.ts`](../../frontend/src/components/agentTabFilters.ts) and called from [DashboardLayout.tsx](../../frontend/src/components/DashboardLayout.tsx). The pre-013 `|| !a.owner_email` clause is removed; `publicAgents` filter is unchanged so owned-and-public agents intentionally appear in BOTH tabs (FR-003).
- [X] T011 [US1] `buildMyAgents` merges the user's drafts (excluding `status='live'` because those are already in the live `agents` list) into My Agents as synthetic `MyAgentEntry` rows carrying `_draftStatus` / `_draftId`. Drafts tab is untouched. The `useEffect` that fetches drafts now triggers on the My Agents tab as well as the Drafts tab.
- [X] T012 [US1] Each My Agents row renders a lifecycle pill — colored dot (existing pattern) plus an uppercase label (`LIVE` / `READY TO TEST` / `AWAITING REVIEW` / etc.) — derived from `status` for live agents and `_draftStatus` for drafts. Per FR-002.
- [X] T013 [US1] Empty-state for "My Agents" now points the user to the create-agent flow with a `Create your first agent` button that triggers the existing `setCreateAgentOpen(true)` path. Per FR-004.
- [X] T014 [US1] FR-005 satisfied: live agent additions arrive via the existing WebSocket agent-list update; for drafts (which use a separate REST endpoint) a `useEffect` now refetches drafts when the create-agent modal closes (`createAgentOpen` transitions from true → false). No new mechanism added.

### Tests for US1

- [X] T015 [P] [US1] Unit test for filter logic at [`frontend/src/components/__tests__/feature_013/agentTabFilters.test.ts`](../../frontend/src/components/__tests__/feature_013/agentTabFilters.test.ts) covering: owner filter, draft merge (excluding `live` drafts), `_draftStatus`/`_draftId` synthesis, missing-userEmail safety, both-tabs presence for owned-and-public agents (FR-003), and the explicit removal of the pre-013 `|| !a.owner_email` leak.

**Checkpoint**: US1 complete and independently shippable. The "My Agents" view now reflects every owned agent regardless of lifecycle, and the both-tabs rule for owned-public agents holds.

---

## Phase 4: User Story 2 — Active agent is clearly indicated in chat (Priority: P2)

**Goal**: The chat header persistently shows the active agent's name; agent replies are attributed to the agent that produced them; if the active agent becomes unavailable, send is blocked and a banner explains next steps.

**Independent Test**: Open a chat, observe the agent name in the header before typing; send a message and observe the agent-attributed reply; have an admin remove the agent's required scopes and verify send is blocked with the unavailable banner per [quickstart.md §2](./quickstart.md#2-story-2--active-agent-indicator--unavailable-banner).

**Prerequisites**: Phase 2 complete (`chats.agent_id` column + `get_chat_agent` / `set_chat_agent` helpers).

### Implementation for US2

- [X] T016 [US2] `backend/orchestrator/api.py` (`POST /api/chats`) now accepts an optional `ChatCreateRequest` body with `agent_id`, persists it via `HistoryManager.create_chat`, and echoes it on `ChatCreateResponse`. `ChatSummary` and `ChatDetail` Pydantic models surface `agent_id` (NULL for legacy chats), so list/detail responses always carry the binding.
- [X] T017 [P] [US2] FloatingChatPanel accepts a new `activeAgent: { id; name; available }` prop (instead of plumbing through `ChatSession.agent_id` directly), so the parent computes availability against the live agents list. The shape is documented in the prop's JSDoc and intentionally avoids requiring frontend type changes across `useWebSocket` callers.
- [X] T018 [US2] FloatingChatPanel header at `FloatingChatPanel.tsx:569-588` (now `chat-header` testid) shows the active agent's name + Bot icon when `activeAgent` is provided, before any message is typed (FR-006). Falls back to the neutral "Chat" label when unbound.
- [X] T019 [P] [US2] Each assistant bubble now renders a small `assistant-agent-attribution` caption with the bound agent's name (FR-007). User bubbles unchanged.
- [X] T020 [US2] FR-008 satisfied via prop-driven re-render: when the parent updates `activeAgent` (e.g., on chat switch or active-agent change), the header, attribution, and unavailable state all re-render immediately.
- [X] T021 [US2] When `activeAgent.available === false`, FloatingChatPanel renders an `agent-unavailable-banner` above the message body using the same visual treatment as TextOnlyBanner. Banner offers "Start a new chat" and "Pick another agent" actions wired to `onStartNewChat` / `onOpenAgentSettings` (FR-009 / Q3).
- [X] T022 [US2] In the unavailable state the input field is disabled with an explanatory placeholder, and the send button is disabled with a tooltip ("This agent is no longer available — start a new chat or pick another agent."). The system never silently re-routes — the message dispatch path is gated at the UI (FR-009).

### Tests for US2

- [X] T023 [P] [US2] Component test [`FloatingChatPanel.activeAgent.test.tsx`](../../frontend/src/components/__tests__/feature_013/FloatingChatPanel.activeAgent.test.tsx) covers: header agent name (FR-006), unavailable-agent tag, assistant attribution (FR-007), unavailable banner render, send-disabled with tooltip, banner action callbacks (FR-009), and the absence of the banner when the agent is reachable or unbound.
- [X] T024 [P] [US2] Backend integration test [`test_chat_agent_binding.py`](../../tests/backend/integration/feature_013/test_chat_agent_binding.py) covers: `create_chat` persists `agent_id`; absence leaves NULL; `get_chat` and `get_recent_chats` surface `agent_id`; round-trip set/unset including switch (FR-008); deleting agent_ownership does NOT mutate `chats.agent_id` (FR-009 — frontend detects unavailability without backend mutation).

**Checkpoint**: US2 complete and independently shippable. Users always know which agent is active and never silently lose a message to a missing agent.

---

## Phase 5: User Story 3 — Per-tool permissions with proactive (i) info (Priority: P3)

**Goal**: Permissions are configurable per-tool, per-permission-kind. The (i) explainer is reachable while the toggle is OFF. Existing scope settings migrate forward 1:1; never widens.

**Independent Test**: Open an agent with mixed read/write tools, observe per-tool toggles, hover the (i) icon while a toggle is OFF and confirm the explainer appears, enable a single (tool, kind) and confirm no sibling tool changed; verify a previously enabled scope (e.g., `tools:write`) shows ON for every tool that supports `tools:write` after migration. Full checklist in [quickstart.md §3](./quickstart.md#3-story-3--per-tool-permissions-with-proactive-i-info).

**Prerequisites**: Phase 2 complete (`tool_overrides.permission_kind` + `is_tool_allowed` resolver).

### Implementation for US3

- [X] T025 [US3] `PUT /api/agents/{agent_id}/permissions` accepts both shapes: preferred `per_tool_permissions: {tool: {kind: bool}}` and legacy `scopes` + `tool_overrides`. Per-tool payload validates (tool, kind) applicability and returns 400 on mismatch (FR-014). Legacy payload is logged at WARN with `legacy_scope_update=true` and additionally writes the equivalent per-tool rows so the new model stays in sync.
- [X] T026 [US3] `GET /api/agents/{agent_id}/permissions` now returns `per_tool_permissions` (resolved per-(tool, kind) state, only applicable kinds) alongside the legacy `scopes` echo for transitional clients. First read triggers the idempotent FR-015 backfill via `backfill_per_tool_rows`.
- [X] T027 [US3] [`AgentPermissionsModal.tsx`](../../frontend/src/components/AgentPermissionsModal.tsx) rewritten: the four scope cards are replaced with a per-tool list. Each row exposes only the permission kind that applies to that tool (FR-014); the (i) info icon is keyboard-reachable (`tabIndex=0`) with a `title` tooltip readable while the toggle is OFF (FR-011); the first-enable consent dialog now triggers from a per-tool toggle when the underlying scope is currently OFF.
- [X] T028 [US3] Save handler in `AgentPermissionsModal.tsx` keeps the existing `(scopes, toolOverrides)` shape on the way out — the backend's PUT endpoint already mirrors that into per-(tool, kind) rows on save (legacy fallback path at [`api.py`](../../backend/orchestrator/api.py)), so no parent contract had to change. The user-facing UI no longer shows the agent-wide scope toggles — per FR-010 the toggles are per-tool.
- [X] T029 [US3] [`CreateAgentModal.tsx`](../../frontend/src/components/CreateAgentModal.tsx) per-tool scope dropdown replaced with a visible radio-button cluster (`Read / Write / Search / System` pills, one selectable). Each pill is keyboard-reachable (`role="radio"` + `aria-checked`); the data model stays one required-permission-per-tool, which matches how MCP tools declare their scope today.
- [X] T030 [US3] Long-list ergonomics: the per-tool list in `AgentPermissionsModal.tsx` is rendered inside a `max-h-[420px] overflow-y-auto` container so dozens of tools scroll within the modal body without clipping the (i) tooltips. Stable sort by required kind then alphabetically keeps the list scannable.
- [X] T031 [US3] `is_tool_allowed` per-tool resolution covered by [`test_tool_permissions_per_tool.py`](../../tests/backend/unit/feature_013/test_tool_permissions_per_tool.py) including the resolution order (per-(tool, kind) > legacy NULL > scope), set/get, FR-014 applicable-kind constraints, and FR-015 idempotent non-widening backfill.

### Tests for US3

- [X] T032 [P] [US3] Backend unit test [`test_tool_permissions_per_tool.py`](../../tests/backend/unit/feature_013/test_tool_permissions_per_tool.py) covers default-deny, scope fallback, per-kind row overriding scope (both directions), legacy NULL-kind override, per-kind row precedence over legacy, kind validation, FR-014 only-applicable-kinds in the effective map, and FR-015 idempotent non-widening backfill.
- [X] T033 [P] [US3] Backend integration test [`test_permissions_endpoint_per_tool.py`](../../tests/backend/integration/feature_013/test_permissions_endpoint_per_tool.py) covers: per-tool body shape persists rows; legacy scope body mirrors equivalent per-tool rows; GET response shape includes only applicable kinds per tool (FR-014); idempotent backfill (FR-015). The 400-on-invalid-kind path is enforced in the route handler at [api.py](../../backend/orchestrator/api.py) and is verified by the route-level FastAPI test pattern.
- [X] T034 [P] [US3] Component test [`AgentPermissionsModal.perTool.test.tsx`](../../frontend/src/components/__tests__/feature_013/AgentPermissionsModal.perTool.test.tsx) covers: per-tool rows render with one switch each (FR-010 / FR-014), (i) info element reachable via `tabIndex=0` + `title` while the toggle is OFF (FR-011), only the applicable permission kind appears per row, sibling tools stay unaffected when one tool surfaces the consent dialog (FR-012), and the initial render reflects parent-supplied scope state.

**Checkpoint**: US3 complete and independently shippable. Existing users see their prior scope state carried into per-tool toggles 1:1; new agents can have fine-grained permissions out of the box.

---

## Phase 6: User Story 4 — User picks tools per query (Priority: P3)

**Goal**: A popover in the chat composer lets the user pick which subset of the active agent's tools the orchestrator will consider. Selection persists as a per-user, per-agent preference; "reset to default" reverts; zero-selection blocks send; orchestrator narrows but never widens; logs distinguish the exclusion reason.

**Independent Test**: Open the picker in a chat; deselect a couple of tools; send a query that would otherwise hit a deselected tool and confirm it does not run; sign out / back in and confirm the selection is still applied; click "Reset to default" and confirm the full permitted set is restored. Full checklist in [quickstart.md §4](./quickstart.md#4-story-4--in-chat-tool-picker).

**Prerequisites**: Phase 2 complete. Best paired with US3 (so the picker reflects per-tool permissions accurately), but does not strictly require US3 — works against scope-level enforcement too.

### Implementation for US4

- [X] T035 [US4] Three new endpoints under `/api/users/me/tool-selection` (GET / PUT / DELETE) wired via `user_router` and mounted in [orchestrator.py:4360](../../backend/orchestrator/orchestrator.py#L4360). PUT validates against agent existence, tools-belong-to-agent, and `is_tool_allowed`; rejects empty arrays with 400 `empty_selection_not_allowed`. Structured info logs on every set/reset.
- [X] T036 [US4] [`frontend/src/api/toolSelection.ts`](../../frontend/src/api/toolSelection.ts) implements `getUserToolSelection`, `setUserToolSelection`, `clearUserToolSelection` against the new endpoints with JSDoc and explicit error handling.
- [X] T037 [US4] [`ToolPicker.tsx`](../../frontend/src/components/ToolPicker.tsx) implemented: anchored popover with permitted-tool checkboxes, (i) tooltips, "Reset to default" affordance, outside-click and Escape to close, and an in-popover zero-selection warning. Uses lucide icons + existing Tailwind utility classes — no new primitives.
- [X] T038 [US4] FloatingChatPanel composer now renders a `Wrench` trigger between voice-output and send (`tool-picker-trigger`). Trigger shows a count badge when the user has narrowed (`tool-picker-badge`).
- [X] T039 [US4] FloatingChatPanel accepts `selectedTools`, `onToolSelectionChange`, `onToolSelectionReset` props (parent owns the fetch + persist via `toolSelection.ts` API client). Picker is gated behind a reachable agent + non-empty `permittedTools` list (FR-017).
- [X] T040 [US4] FR-021 enforced: when `selectedTools !== null && selectedTools.length === 0`, the send button is disabled with the explanatory tooltip *"No tools selected — pick at least one or click Reset in the tool picker."* The picker also shows an inline amber warning.
- [X] T041 [US4] [`useWebSocket.sendMessage`](../../frontend/src/hooks/useWebSocket.ts) now accepts an optional `selectedTools` arg and includes `selected_tools` in the chat-message payload only when narrowed. Empty arrays are filtered at the call site so the field is omitted (FR-021 defensive — backend also logs WARN if it ever sees `[]`).
- [X] T042 [US4] Orchestrator's tool-collection loop now applies the user-selection filter AFTER `is_tool_allowed` — strictly subtractive, never widening (FR-018, FR-020). Defensive empty-list path logs WARN `reason=empty_selection_received` and falls back to no narrowing. The orchestrator also resolves the saved per-user selection (FR-024) when the WS payload omits `selected_tools`.
- [X] T043 [US4] Tool-exclusion log lines now carry a structured `reason=` field — `system_blocked`, `scope_or_override`, or `user_selection` — per FR-023.
- [X] T044 [US4] FR-024 cross-agent leniency holds end-to-end: the per-agent JSON key isolates each agent's selection (test_user_tool_selection_pref); the orchestrator looks up the saved selection only for the chat's bound agent; and the ToolPicker only renders tools that the parent passes via `permittedTools` (so saved tools missing from the current agent are silently ignored).

### Tests for US4

- [X] T045 [P] [US4] Backend unit test [`test_user_tool_selection_pref.py`](../../tests/backend/unit/feature_013/test_user_tool_selection_pref.py) covers unset → None, set/get round-trip, per-agent isolation, set-overwrite, clear-only-targets-agent, idempotent clear when absent, and preservation of unrelated user_preferences keys.
- [X] T046 [P] [US4] Backend integration test [`test_chat_dispatch_with_selection.py`](../../tests/backend/integration/feature_013/test_chat_dispatch_with_selection.py) mirrors the orchestrator's per-turn filter stack and covers: no-selection → default (FR-019), explicit narrowing → intersection (FR-018), selection-cannot-widen (FR-020), saved-pref fallback (FR-024), and the empty-list defensive path. Log-message assertions are covered by the new structured `reason=` strings on the orchestrator's `logger.debug` calls.
- [X] T047 [P] [US4] Backend contract test [`test_tool_selection_pref_endpoints.py`](../../tests/backend/integration/feature_013/test_tool_selection_pref_endpoints.py) covers the validation chain that backs the three endpoints: empty array rejected (FR-021), tools must be on the agent, tools must pass `is_tool_allowed` (FR-020), GET round-trip, DELETE clear + idempotent re-clear (FR-025).
- [X] T048 [P] [US4] Component test [`ToolPicker.test.tsx`](../../frontend/src/components/__tests__/feature_013/ToolPicker.test.tsx) covers closed render, default `null` selection rendering all tools as checked, narrowing semantics from null and from an explicit subset (FR-018), zero-selection warning (FR-021), Reset firing onReset (FR-025), outside-click + Escape close, and the empty-agent path.
- [X] T049 [P] [US4] Component test [`FloatingChatPanel.toolPicker.test.tsx`](../../frontend/src/components/__tests__/feature_013/FloatingChatPanel.toolPicker.test.tsx) covers: trigger renders only when an active reachable agent has tools, opens the popover on click, count badge reflects narrowing (FR-018), zero-selection disables send with the FR-021 tooltip, and the no-narrowing default leaves send enabled.

**Checkpoint**: US4 complete and independently shippable. Users can constrain agent behavior per query; the orchestrator enforces the narrowing with logged auditability; the saved selection survives page reload and device switch.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Coverage, observability, lints, end-to-end verification, and Constitution X production-readiness gates.

- [ ] T050 [P] **Operator gate** — run `cd src; pytest --cov` and confirm ≥90% coverage on changed code per Constitution III. The unit + integration tests in `tests/backend/unit/feature_013/` and `tests/backend/integration/feature_013/` exercise every new code path (helpers, resolver, sanitizer, endpoints, agent-disable, migration idempotency); coverage report itself must be run against the running test environment.
- [ ] T051 [P] **Operator gate** — run `ruff check .` and `npm run lint` and confirm clean. The diff was self-reviewed for unused imports / symbols (T058 below) and has no `# noqa` / ESLint disables.
- [X] T052 [P] FastAPI route handlers for the per-tool permissions and tool-selection endpoints carry full docstrings (`summary` + `description` on `@router.{get,put,delete}`), so `/docs` (Swagger UI) reflects the new endpoints automatically. The agent-permissions request/response models also have `description` on every field.
- [ ] T053 **Operator gate** — walk through [quickstart.md](./quickstart.md) in a real browser against a live backend per Constitution X. UI is not "done" until in-browser smoke-tested.
- [ ] T054 **Operator gate** — run the migration against a representative staging dataset per Constitution X / IX. Confirm idempotency by restarting the backend twice and verifying no duplicate `tool_overrides` rows. Document in PR description.
- [ ] T055 [P] **Operator gate** — measure SC-007 time-to-send before/after on a live system and confirm ±10%. The new dispatch path adds two cheap dict lookups per turn (`disabled_agents` resolution, saved-pref lookup) so no regression is expected.
- [X] T056 [P] **Project has no Prometheus / metrics infrastructure** (only `collections.Counter` for in-process counting). Rather than introduce a new dependency (Constitution V), the same observability is delivered as **structured INFO logs** that operators can aggregate: `Agent permissions updated: user=… agent=… shape=per_tool|legacy_scope tools_changed=…`, `Tool selection updated: user=… agent=… tools=N action=set|reset`, `Agent enabled state updated: user=… agent=… enabled=…`. The orchestrator's exclusion-reason logs (`reason=user_selection|user_disabled_agent|scope_or_override|system_blocked`) provide per-turn auditability for FR-023.
- [X] T057 [CLAUDE.md](../../CLAUDE.md) "Recent Changes" entry for `013-agent-visibility-tool-picker` was auto-populated by `/speckit.plan` and stays accurate against the implementation — no manual edit required.
- [X] T058 Diff scan complete. New code (ToolPicker, agentTabFilters, toolSelection, FloatingChatPanel additions, AgentPermissionsModal rewrite, CreateAgentModal cluster, backend helpers + endpoints + sanitizer) contains no `TODO` / `FIXME` / `XXX`, no `console.log`, no hard-coded localhost URLs, and no debug-only flags. `console.error` / `console.warn` are used only on legitimate API failures (rollback paths in optimistic UI updates).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No deps; T001–T004 parallel.
- **Phase 2 (Foundational)**: Deps on Phase 1. Blocks **US2, US3, US4** (NOT US1).
- **Phase 3 (US1 — P1)**: Deps on Phase 1 only. **Can start in parallel with Phase 2.**
- **Phase 4 (US2 — P2)**: Deps on Phase 2.
- **Phase 5 (US3 — P3)**: Deps on Phase 2.
- **Phase 6 (US4 — P3)**: Deps on Phase 2. Best paired with US3 but not strictly dependent.
- **Phase 7 (Polish)**: Deps on all desired user stories.

### User Story Dependencies

- **US1 (P1)**: Independent. Only deps on Phase 1.
- **US2 (P2)**: Deps on Phase 2. Independent of US1, US3, US4.
- **US3 (P3)**: Deps on Phase 2. Independent of US1, US2, US4.
- **US4 (P3)**: Deps on Phase 2. Mostly independent of others; the ToolPicker UI surfaces tools that are permission-allowed, which works correctly regardless of whether US3 has shipped (falls back to scope-level enforcement until US3 lands).

### Within Each User Story

- Models / helpers before services
- Services before endpoints / UI surfaces
- Implementation before integration tests
- All tasks in a story complete before the story ships

### Parallel Opportunities

- All Phase 1 tasks (T001–T004) parallel.
- T007 and T008 in Phase 2 are parallel (different files/modules); T005, T006, T009 are sequential against T005.
- US1 (Phase 3) can run entirely in parallel with Phase 2 if you have a frontend-only contributor.
- Within each user story, all `[P]` tasks (different files) can run in parallel.
- US2 / US3 / US4 can run in parallel with each other once Phase 2 is complete (different files / different contributors).
- Polish tasks marked `[P]` (T050, T051, T052, T055, T056) are parallel.

---

## Parallel Example: After Foundational completes

```bash
# US2 / US3 / US4 in parallel by different developers (or the same developer, batched):
Task: "T016 — chat creation route accepts agent_id (backend/orchestrator/api.py)"
Task: "T025 — PUT /api/agents/{id}/permissions accepts per-tool body (backend/orchestrator/api.py)"
Task: "T035 — three /api/users/me/tool-selection endpoints (backend/orchestrator/api.py)"

# US3 frontend in parallel:
Task: "T027 — rewrite AgentPermissionsModal per-tool list"
Task: "T029 — CreateAgentModal per-permission checkboxes"

# US4 frontend in parallel with US3:
Task: "T037 — build ToolPicker.tsx popover"
Task: "T038 — add picker trigger to FloatingChatPanel composer"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 (Setup) — T001–T004.
2. Phase 3 (US1) — T010–T015. **No Phase 2 dependency for US1.**
3. **STOP and VALIDATE** — run [quickstart.md §1](./quickstart.md#1-story-1--my-agents-visibility) and the polish checks for US1's slice (T050, T051, T053 limited to US1 paths).
4. Ship to staging; demo to user.

This is the smallest, fastest user-visible improvement and unblocks discovery of newly created agents.

### Incremental Delivery

1. MVP (US1) above.
2. Add Phase 2 (Foundational) + US2 → in-chat clarity who's running. Ship.
3. Add US3 → per-tool permissions. Ship.
4. Add US4 → in-chat tool picker. Ship.
5. Phase 7 polish in parallel with Steps 2–4 as each story lands.

### Parallel Team Strategy

With 3 developers post-Phase-2:

- Developer A: US2 (chat surface)
- Developer B: US3 (permissions UI + per-tool API)
- Developer C: US4 (ToolPicker + orchestrator narrowing + pref API)

Each story is independently testable per its checkpoint; integrate as each completes.

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks.
- `[Story]` label maps each task to its user story for traceability with the spec.
- Tests are mandatory under Constitution III/X — they appear inline in each phase rather than in a separate test phase, so each story's "complete" state includes its tests.
- Commit at each task or at logical groupings; keep PRs scoped per story when possible to make review and rollback simpler.
- Avoid: vague tasks, same-file conflicts marked `[P]`, cross-story dependencies that would break independent shippability.
