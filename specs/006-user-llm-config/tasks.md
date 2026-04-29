# Tasks: User-Configurable LLM Subscription

**Input**: Design documents from `/specs/006-user-llm-config/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Tests are **mandatory** for this codebase per Constitution Principle III (90% coverage on changed code). Test tasks below are not optional.

**Organization**: Tasks are grouped by user story. The four user stories from spec.md are:

| Story | Priority | Title |
|-------|----------|-------|
| US1   | P1 (MVP) | User opts in to their own LLM provider |
| US2   | P2       | User rotates, switches, or clears their LLM credentials |
| US3   | P2       | User reviews their cumulative token usage |
| US4   | P3       | Operator verifies that user-configured calls never fall back to operator credentials |

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Setup, Foundational, and Polish phases have no story label.

## Path Conventions

Web app split: `backend/`, `frontend/src/` per [plan.md](plan.md) Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create empty module skeletons so subsequent phases can land code without bikeshedding directory layout.

- [ ] T001 Create backend module skeleton at [backend/llm_config/__init__.py](backend/llm_config/__init__.py) with module docstring
- [ ] T002 [P] Create backend test package at [backend/llm_config/tests/__init__.py](backend/llm_config/tests/__init__.py)
- [ ] T003 [P] Create frontend component directory marker at [frontend/src/components/llm/.gitkeep](frontend/src/components/llm/.gitkeep) (will be populated in US1)
- [ ] T004 [P] Confirm `openai` Python SDK is already pinned in `backend/requirements.txt` (or equivalent) — no new dependency added; just verify version supports `OpenAI(...).chat.completions.create` with `usage` field

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core scaffolding that every user story depends on — credential plumbing, audit-event identifiers, WS message types, and the credential-resolution factory. **No story-level work may begin until this phase completes.**

- [ ] T005 Add three new `event_class` identifiers (`llm.config_change`, `llm.unconfigured`, `llm.call`) to the existing CHECK constraint in [backend/audit/schemas.py](backend/audit/schemas.py); update the matching `EventClass` enum/literal definition in the same file
- [ ] T006 Update `Database._init_db()` in [backend/database.py](backend/database.py) (or wherever the audit-events DDL lives) so the new identifiers are accepted by the CHECK constraint on fresh-init AND on existing databases (use idempotent `ALTER TABLE … DROP CONSTRAINT … ADD CONSTRAINT …` pattern, matching how features 003/004 handled in-place schema additions)
- [ ] T007 [P] Add `LLMConfigSet`, `LLMConfigClear`, `LLMUsageReport` Pydantic message models to [backend/shared/protocol.py](backend/shared/protocol.py) with the field shapes from [contracts/ws-messages.md](contracts/ws-messages.md); extend the `RegisterUI` model with an optional `llm_config: Optional[LLMConfigPayload]` field
- [ ] T008 [P] Add `SessionCreds` dataclass with custom `__repr__` (key elided) at [backend/llm_config/session_creds.py](backend/llm_config/session_creds.py); add `SessionCredentialStore` thin wrapper exposing `get(ws_id)`, `set(ws_id, creds)`, `clear(ws_id)`, `__contains__(ws_id)` over `Dict[int, SessionCreds]`
- [ ] T009 [P] Add `OperatorDefaultCreds` frozen dataclass at [backend/llm_config/operator_creds.py](backend/llm_config/operator_creds.py) with `from_env()` classmethod that reads `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`LLM_MODEL` and an `is_complete` property
- [ ] T010 [P] Add `CredentialSource` enum (`USER`, `OPERATOR_DEFAULT`) and `LLMUnavailable` exception at [backend/llm_config/types.py](backend/llm_config/types.py)
- [ ] T011 Implement `build_llm_client(session_creds, default_creds) -> (OpenAI, CredentialSource, ResolvedConfig)` in [backend/llm_config/client_factory.py](backend/llm_config/client_factory.py); raise `LLMUnavailable` when neither side is complete; depends on T008/T009/T010
- [ ] T012 [P] Add audit-event helpers `record_llm_config_change()`, `record_llm_unconfigured()`, `record_llm_call()` at [backend/llm_config/audit_events.py](backend/llm_config/audit_events.py); each helper validates that `api_key` is NOT in any payload field and asserts so via a runtime guard
- [ ] T013 [P] Add log scrubber `redact_llm_config(record_or_dict)` at [backend/llm_config/log_scrub.py](backend/llm_config/log_scrub.py) that replaces any `api_key` field with the literal `"<redacted>"`; wire it into the existing FastAPI/uvicorn logging filter chain
- [ ] T014 [P] [Test] Unit test `SessionCreds.__repr__` does not contain the key — at [backend/llm_config/tests/test_session_creds.py](backend/llm_config/tests/test_session_creds.py)
- [ ] T015 [P] [Test] Unit test `build_llm_client` covers all 5 cases (user-only, default-only, both → user wins, neither → raises, partial-user → falls through to default if default complete else raises) — at [backend/llm_config/tests/test_client_factory.py](backend/llm_config/tests/test_client_factory.py)
- [ ] T016 [P] [Test] Unit test audit-event helpers reject any payload containing `api_key` — at [backend/llm_config/tests/test_audit_events.py](backend/llm_config/tests/test_audit_events.py)
- [ ] T017 [P] [Test] Unit test `redact_llm_config` strips `api_key` from nested dicts and JSON strings — at [backend/llm_config/tests/test_log_scrub.py](backend/llm_config/tests/test_log_scrub.py)
- [ ] T018 [P] [Test] Integration test verifying the new event-class identifiers persist through `_init_db` on a fresh database AND on a pre-existing one (no constraint violation) — at [backend/audit/tests/test_event_class_extension.py](backend/audit/tests/test_event_class_extension.py)

**Checkpoint**: `build_llm_client` resolves credentials correctly in isolation; audit log accepts `llm.*` event classes; logs no longer expose API keys. User-story phases can now begin.

---

## Phase 3: User Story 1 — User opts in to their own LLM provider (Priority: P1) 🎯 MVP

**Goal**: A user can open the LLM Settings panel, enter `apiKey` / `baseUrl` / `model`, run Test Connection (which exercises a real `chat.completions.create` with `max_tokens: 1`), save, and from that point every LLM-dependent call on their behalf uses *their* credentials and emits an `llm.call` audit event with `credential_source = "user"`. Users with no personal config keep working against the operator default.

**Independent Test**: Quickstart sections 1, 2, 3, 6 — verify default path (US1:1), save+probe (US1:2), override (US1:3), and fail-closed when both are missing (FR-004a, US4:3 partial).

### Backend implementation — wire credential resolution into existing call sites

- [ ] T019 [US1] In [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): add `self._session_llm_creds: SessionCredentialStore` to `Orchestrator.__init__`; rename existing `self.llm_client` to `self.default_llm_client`; build `OperatorDefaultCreds` from env there too; clear `_session_llm_creds[id(ws)]` in the existing socket-cleanup block (search for `_chat_locks.pop` to find it)
- [ ] T020 [US1] In `Orchestrator._call_llm` ([backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) ~line 2274): replace `self.llm_client` reference with a `build_llm_client(self._session_llm_creds.get(id(websocket)), self._operator_creds)` call; on `LLMUnavailable`, emit `llm.unconfigured` audit and return the existing `Alert(message="LLM unavailable — set your own provider in settings", variant="error")` UI render (replacing the line 1627 message)
- [ ] T021 [US1] In `Orchestrator._call_llm` (same file, same function): after the `chat.completions.create` returns or raises, call `record_llm_call()` with `feature='tool_dispatch'`, the resolved `credential_source`, `base_url`, `model`, `total_tokens` (from `usage.total_tokens` or `None`), and `outcome`
- [ ] T022 [US1] In `Orchestrator._generate_tool_summary` ([backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) ~line 2324): apply the same factory replacement and audit emission as T020/T021, with `feature='tool_summary'`
- [ ] T023 [US1] In the third `chat.completions.create` call site ([backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) ~line 3929): apply the same factory replacement and audit emission, with the appropriate `feature` identifier (read the surrounding function name to label correctly)
- [ ] T024 [P] [US1] In [backend/orchestrator/agent_generator.py](backend/orchestrator/agent_generator.py): change `_get_llm_client()` (~line 216) to accept `session_creds` and `default_creds`, replace its env-reading body with `build_llm_client(...)`; update both call sites (~lines 376, 458) to thread the websocket through
- [ ] T025 [P] [US1] In [backend/agents/general/mcp_tools.py](backend/agents/general/mcp_tools.py) (~line 871): the existing `_credentials` kwarg already passes `OPENAI_API_KEY`/`OPENAI_BASE_URL`. Extend `Orchestrator.execute_single_tool` in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) (the function that today builds the kwargs passed to MCP tool dispatch — locate by searching for `_credentials`) to populate the `_credentials` dict from `self._session_llm_creds.get(id(websocket))` when present, falling back to env (existing behavior). The `mcp_tools.py` side stays close to its current shape; only `execute_single_tool` changes.

### Backend implementation — new WS handlers and REST endpoint

- [ ] T026 [US1] In [backend/llm_config/ws_handlers.py](backend/llm_config/ws_handlers.py): implement `async def handle_llm_config_set(orchestrator, websocket, msg, user_id)` per [contracts/ws-messages.md](contracts/ws-messages.md) §2 — validates the trio, swaps `_session_llm_creds[id(ws)]`, emits `llm.config_change(action=created|updated)`, sends `llm_config_ack` reply
- [ ] T027 [US1] In [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): in the existing WS message dispatch switch, add a case for `llm_config_set` that calls `handle_llm_config_set(...)`. (T032 will add the `_clear` case in US2.)
- [ ] T028 [US1] In [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): in the `register_ui` handler, after JWT validation, if the parsed `RegisterUI` carries an `llm_config` field, call the same code path as `handle_llm_config_set` so initial-load creds populate the session in one round-trip
- [ ] T029 [US1] Implement `POST /api/llm/test` at [backend/llm_config/api.py](backend/llm_config/api.py) per [contracts/rest-llm-test.md](contracts/rest-llm-test.md): JWT-required, validates body, builds a one-shot `OpenAI` client with a 15 s timeout, issues `chat.completions.create(model=…, messages=[{"role":"user","content":"ping"}], max_tokens=1)`, classifies the outcome, emits `llm.config_change(action=tested, …)`, returns the response shape from the contract
- [ ] T030 [US1] Register the `POST /api/llm/test` router in [backend/orchestrator/api.py](backend/orchestrator/api.py) (or wherever feature-003's `GET /api/audit` is registered)

### Backend tests — US1

- [ ] T031 [P] [US1] Pytest: `register_ui` with valid `llm_config` populates `_session_llm_creds`, emits one `llm.config_change(action=created)`, key never appears in stored audit payload — at [backend/llm_config/tests/test_register_ui_extension.py](backend/llm_config/tests/test_register_ui_extension.py)
- [ ] T032 [P] [US1] Pytest: `llm_config_set` mid-session (1) updates store, (2) emits `action=updated` when prior creds existed, `action=created` otherwise, (3) rejects malformed payloads with `llm_config_invalid` error, (4) does NOT mutate state on rejection — at [backend/llm_config/tests/test_ws_handlers.py](backend/llm_config/tests/test_ws_handlers.py)
- [ ] T033 [P] [US1] Pytest: `POST /api/llm/test` returns `{ok:true}` on a stub `OpenAI` client that returns a synthetic message; returns the right `error_class` for each of `auth_failed`/`model_not_found`/`transport_error`/`contract_violation`/`other`; emits one `llm.config_change(action=tested)` per call regardless of outcome; api_key never written to logs — at [backend/llm_config/tests/test_test_connection_endpoint.py](backend/llm_config/tests/test_test_connection_endpoint.py)
- [ ] T034 [US1] Pytest: end-to-end `_call_llm` smoke — with `_session_llm_creds` populated, the call uses the user-credential client; with it absent and `OperatorDefaultCreds.is_complete`, uses the default client; with both absent, raises and emits `llm.unconfigured`; in all three cases emits exactly one `llm.call` event (or `llm.unconfigured` in the third) with the correct `credential_source` — at [backend/orchestrator/tests/test_call_llm_credential_resolution.py](backend/orchestrator/tests/test_call_llm_credential_resolution.py)

### Frontend implementation — settings panel and hook

- [ ] T035 [P] [US1] Implement `useLlmConfig` hook at [frontend/src/hooks/useLlmConfig.ts](frontend/src/hooks/useLlmConfig.ts): reads/writes localStorage key `astralbody.llm.config.v1`; exposes `{ config, save(c), clear(), testConnection(c) }` where `testConnection` posts to `/api/llm/test`; never logs the key; emits a custom `window` event `llm-config-changed` on save/clear so `useWebSocket` can dispatch the WS message. Sets `connectedAt = new Date().toISOString()` after a successful `testConnection()` response; clears `connectedAt` whenever `save()` is called without an immediately-prior successful probe (so the panel header can distinguish "configured AND probe-validated" from "configured but probe failed/skipped"). The hook does NOT subscribe to auth-state changes — sign-out, token refresh, and session expiry leave the localStorage key untouched (FR-013).
- [ ] T036 [P] [US1] Implement `LlmConfigForm.tsx` at [frontend/src/components/llm/LlmConfigForm.tsx](frontend/src/components/llm/LlmConfigForm.tsx): three input fields (`apiKey` is `<input type="password" autoComplete="off">`), a "Test Connection" button (disabled until all three fields non-empty), latency-and-error display from the probe response, a "Save" button (disabled unless probe passed since last edit). **Constitution Principle VIII compliance**: this component must use ONLY the existing primitives (`Card`, `Input`, `Button`, `Alert` from `frontend/src/catalog.ts`). Do NOT introduce new primitives, third-party UI libraries, or raw styled HTML beyond the password input.
- [ ] T037 [P] [US1] Implement `LlmSettingsPanel.tsx` at [frontend/src/components/llm/LlmSettingsPanel.tsx](frontend/src/components/llm/LlmSettingsPanel.tsx): overlay component mirroring the `AuditLogPanel` pattern from feature 003; header shows "Connected — using your own provider" / "Using operator default" / "LLM unavailable" depending on `useLlmConfig` and a server-supplied default-availability flag (from `system_config` WS message — check existing field; if absent, the panel assumes operator default may be available). **Constitution Principle VIII compliance**: use ONLY existing primitives (`Modal`/overlay container, `Card`, `Button`) from `frontend/src/catalog.ts`. No new primitives.
- [ ] T038 [US1] Modify [frontend/src/components/layout/DashboardLayout.tsx](frontend/src/components/layout/DashboardLayout.tsx): add a sidebar entry "LLM Settings" that toggles the panel via URL state (`?llm=open`), matching the existing `?audit=open` pattern from feature 003
- [ ] T039 [US1] Modify [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts): on initial `register_ui` send, include the current `useLlmConfig` value as an `llm_config` field; subscribe to the `llm-config-changed` window event to dispatch `llm_config_set` mid-session
- [ ] T040 [US1] In [frontend/src/components/DynamicRenderer.tsx](frontend/src/components/DynamicRenderer.tsx) or the relevant alert-handling path: when an `Alert` with the new `LLM unavailable — set your own provider in settings` message renders, render a clickable link that toggles the LLM Settings panel via the URL-state mechanism (T038)

### Frontend tests — US1

- [ ] T041 [P] [US1] Vitest: `useLlmConfig` round-trips through localStorage, emits the window event on save/clear, redacts the key in any debug-render — at [frontend/tests/hooks/useLlmConfig.test.ts](frontend/tests/hooks/useLlmConfig.test.ts)
- [ ] T042 [P] [US1] Vitest: `LlmConfigForm` — inputting partial fields keeps the Test Connection button disabled; a successful probe enables Save; an edit after a successful probe re-disables Save until next probe — at [frontend/tests/components/llm/LlmConfigForm.test.tsx](frontend/tests/components/llm/LlmConfigForm.test.tsx)
- [ ] T043 [P] [US1] Vitest: `LlmSettingsPanel` shows the correct header text in the three states; the Clear button is wired (no-op test for click → mock hook call) — at [frontend/tests/components/llm/LlmSettingsPanel.test.tsx](frontend/tests/components/llm/LlmSettingsPanel.test.tsx)

**Checkpoint**: A user can save personal credentials, run Test Connection, see calls routed through their endpoint with `credential_source='user'` audit events. Operator default still serves unconfigured users. Quickstart §§1–3 and §6 pass.

---

## Phase 4: User Story 2 — User rotates, switches, or clears their LLM credentials (Priority: P2)

**Goal**: A configured user can edit their saved fields and save again (rotate/switch — already covered by the Save flow from US1), OR click "Clear configuration" to remove their personal config and revert to the operator default for subsequent calls. Sign-out and session expiry never auto-clear.

**Independent Test**: Quickstart §4 (no runtime fallback when key fails → user clears → operator default takes over) and §5 (sign-out/sign-in preserves config).

### Backend — Clear handler

- [ ] T044 [P] [US2] In [backend/llm_config/ws_handlers.py](backend/llm_config/ws_handlers.py): implement `async def handle_llm_config_clear(orchestrator, websocket, user_id)` per [contracts/ws-messages.md](contracts/ws-messages.md) §3 — pops `_session_llm_creds[id(ws)]`, emits `llm.config_change(action=cleared)` ONLY if a prior entry existed, sends `llm_config_ack` reply
- [ ] T045 [US2] In [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): in the WS message dispatch switch, add a case for `llm_config_clear` that calls `handle_llm_config_clear(...)`

### Frontend — Clear button + sign-out preservation

- [ ] T046 [US2] In [frontend/src/components/llm/LlmSettingsPanel.tsx](frontend/src/components/llm/LlmSettingsPanel.tsx): add a "Clear configuration" button with a confirmation dialog ("Remove your saved LLM configuration on this device? Your subscription is unaffected.") that calls `useLlmConfig().clear()` on confirm
- [ ] T047 [US2] (Removed — T035 already specifies "does NOT subscribe to auth-state changes" as part of the hook contract, and T050 supplies the regression test. Renumber-free placeholder retained to keep downstream task IDs stable.)

### Tests — US2

- [ ] T048 [P] [US2] Pytest: `llm_config_clear` removes the entry, emits `action=cleared` audit only if a prior entry existed, sends `llm_config_ack`; clearing an already-empty slot is a no-op (no audit event) — at [backend/llm_config/tests/test_ws_handlers.py](backend/llm_config/tests/test_ws_handlers.py) (extend the existing file from T032)
- [ ] T049 [P] [US2] Vitest: clicking "Clear configuration" calls `clear()` after confirmation; cancelling the dialog does not; subsequent localStorage read returns null — at [frontend/tests/components/llm/LlmSettingsPanel.test.tsx](frontend/tests/components/llm/LlmSettingsPanel.test.tsx) (extend file from T043)
- [ ] T050 [P] [US2] Vitest: simulating a sign-out (clearing the auth token in the test harness) does NOT remove `astralbody.llm.config.v1` from localStorage — at [frontend/tests/hooks/useLlmConfig.test.ts](frontend/tests/hooks/useLlmConfig.test.ts) (extend file from T041)
- [ ] T051 [US2] Pytest: integration — save creds, simulate runtime failure on the user's endpoint, assert `_call_llm` raises and emits `llm.call(credential_source=user, outcome=failure)` with NO additional `llm.call(credential_source=operator_default)` event for the same call — at [backend/orchestrator/tests/test_no_runtime_fallback.py](backend/orchestrator/tests/test_no_runtime_fallback.py)

**Checkpoint**: Clear flow works; sign-out preserves config; runtime failure on user creds never silently bills the operator. Quickstart §4 and §5 pass.

---

## Phase 5: User Story 3 — User reviews their cumulative token usage (Priority: P2)

**Goal**: After every LLM-dependent call served with the user's personal credentials, the server pushes a `llm_usage_report` to the client; the client accumulates this into session/today/lifetime/per-model counters in localStorage; a Token Usage dialog inside the settings panel renders the totals. Calls served with the operator default are NOT reported.

**Independent Test**: Quickstart §7.

### Backend — usage emission

- [ ] T052 [US3] In [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) `_call_llm` (and the other two re-wired call sites from T022/T023): after recording the `llm.call` audit event, if `credential_source == USER`, send an `llm_usage_report` WS message to the originating websocket with the shape from [contracts/ws-messages.md](contracts/ws-messages.md) §4 (best-effort fire-and-forget)
- [ ] T053 [US3] Same edit but explicitly suppress the message when `credential_source == OPERATOR_DEFAULT` — verify by code review and a regression test (T058)

### Frontend — counter hook + dialog

- [ ] T054 [P] [US3] Implement `useTokenUsage` hook at [frontend/src/hooks/useTokenUsage.ts](frontend/src/hooks/useTokenUsage.ts): subscribes to `llm_usage_report` (forwarded by `useWebSocket` as a window event); maintains `{session, today, todayDate, lifetime, unknownCalls, perModel}` in the same localStorage key as `LlmConfig` (sub-object `usage`); handles local-day rollover by comparing `todayDate`; exposes `reset()`
- [ ] T055 [P] [US3] In [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts): add a handler that dispatches incoming `llm_usage_report` messages as a `llm-usage-report` window event (matching the existing `audit:append` pattern from feature 003)
- [ ] T056 [P] [US3] Implement `TokenUsageDialog.tsx` at [frontend/src/components/llm/TokenUsageDialog.tsx](frontend/src/components/llm/TokenUsageDialog.tsx): renders session/today/lifetime/unknownCalls and a per-model table; "Reset usage stats" button calls `useTokenUsage().reset()`; if no personal config is set, renders "Not tracked while using operator default" placeholder instead of zeros (FR-016, US3:4 — this fixes the "hidden OR placeholder" ambiguity by canonicalizing the placeholder choice). **Constitution Principle VIII compliance**: use ONLY existing primitives (`Card`, `Button`, simple table primitive if available; otherwise stack `Card` instances). No new primitives.
- [ ] T057 [US3] In [frontend/src/components/llm/LlmSettingsPanel.tsx](frontend/src/components/llm/LlmSettingsPanel.tsx): mount `<TokenUsageDialog />` below the config form

### Tests — US3

- [ ] T058 [P] [US3] Pytest: `_call_llm` with user creds emits exactly one `llm_usage_report` WS message per call; with operator-default creds emits zero; on upstream failure, emits `outcome=failure` and the client's counter increment logic must not increment numeric totals (assert by inspecting the emitted message's `outcome`) — at [backend/orchestrator/tests/test_usage_report_emission.py](backend/orchestrator/tests/test_usage_report_emission.py)
- [ ] T059 [P] [US3] Vitest: `useTokenUsage` — three synthetic `llm-usage-report` events with `total_tokens=100, 200, 300, outcome="success"` produce session=600, today=600, lifetime=600, perModel[model]=600; a fourth event with `total_tokens=null, outcome="success"` does NOT change numerics but increments `unknownCalls` to 1; a fifth event with `outcome="failure"` (any `total_tokens`) does NOT change `session/today/lifetime/perModel/unknownCalls`; a date rollover (mock `todayDate=yesterday`) resets `today` to 0 before adding the new value — at [frontend/tests/hooks/useTokenUsage.test.ts](frontend/tests/hooks/useTokenUsage.test.ts)
- [ ] T060 [P] [US3] Vitest: `TokenUsageDialog` renders the counters correctly; "Reset usage stats" zeroes them; with no personal config, shows the "Not tracked" placeholder — at [frontend/tests/components/llm/TokenUsageDialog.test.tsx](frontend/tests/components/llm/TokenUsageDialog.test.tsx)

**Checkpoint**: Token counters accumulate correctly per user, only for personal-credential calls. Quickstart §7 passes.

---

## Phase 6: User Story 4 — Operator verifies that user-configured calls never fall back (Priority: P3)

**Goal**: This story is verification-scaffolding rather than user-visible features. It is delivered as a set of tests + the SC-006 audit query + a documented operator runbook, demonstrating that the FR-003 / FR-009 / FR-010 invariants hold.

**Independent Test**: Quickstart §8 (the SC-006 audit-log query) returns zero rows; the api-key-leak grep test in T061 finds zero matches.

### Verification tests — US4

- [ ] T061 [P] [US4] Pytest: scan all rows of `audit_events.payload` produced by the full backend test suite for any string matching `\bsk-[A-Za-z0-9]{20,}\b` plus prefixes `gsk_`, `xai-`, `or-`; expected match count = 0 — at [backend/llm_config/tests/test_no_api_key_leak.py](backend/llm_config/tests/test_no_api_key_leak.py)
- [ ] T062 [P] [US4] Pytest: SC-006 query as a SQL-test fixture — set up two users (Alice with personal config, Bob without), generate calls for each, run the query from [contracts/audit-events.md](contracts/audit-events.md) §"Operator queries enabled by these events" row 1; expected zero rows — at [backend/llm_config/tests/test_sc006_query.py](backend/llm_config/tests/test_sc006_query.py)
- [ ] T063 [P] [US4] Pytest: with `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`LLM_MODEL` unset and no user creds, `_call_llm` raises `LLMUnavailable`, emits `llm.unconfigured` once, and the orchestrator surfaces the FR-004a alert UI render — at [backend/orchestrator/tests/test_fail_closed.py](backend/orchestrator/tests/test_fail_closed.py)
- [ ] T064 [P] [US4] Pytest: with env set but user creds absent, calls succeed against the default and emit `llm.call(credential_source=operator_default)`; with user creds set AND env set, calls succeed against the user endpoint and emit `llm.call(credential_source=user)` — at [backend/orchestrator/tests/test_credential_source_audit_field.py](backend/orchestrator/tests/test_credential_source_audit_field.py)
- [ ] T064a [P] [US4] Pytest: regression test for **FR-011 (background jobs)** — invoke `Orchestrator._call_llm(websocket=None, …)` (the shape used by the daily feedback quality / proposals job from feature 004 when no user is the caller) with `OperatorDefaultCreds.is_complete == True` and assert (a) the call succeeds, (b) exactly one `llm.call` audit event fires with `credential_source='operator_default'` and `actor_user_id='system'`, (c) no `llm_usage_report` WS message is emitted (no socket to send it to anyway, but verify the emission code path is gated). Also assert that User A's `_session_llm_creds` entry is NOT consulted when `websocket=None` even if A is connected — at [backend/orchestrator/tests/test_background_jobs_use_operator_default.py](backend/orchestrator/tests/test_background_jobs_use_operator_default.py)

### Operator runbook — US4

- [ ] T065 [US4] Add a short operator runbook section to [docs/operations.md](docs/operations.md) (or wherever ops docs live; create the file if it doesn't exist) titled "Verifying per-user LLM billing isolation" linking to the SC-006 query in [contracts/audit-events.md](contracts/audit-events.md)

**Checkpoint**: All four user stories ship. The SC-006 invariant is provable via a single SQL query. Quickstart §8 passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T066 [P] Update [README.md](README.md) (if it documents env vars) to mention that `OPENAI_*` / `LLM_MODEL` are now the operator-default credentials and that users may override them per-device
- [ ] T067 [P] Update [.env.example](.env.example) with a comment above the `OPENAI_*` block explaining that these are the operator default and users may override them via the LLM Settings panel
- [ ] T068 [P] Add a JSDoc block to each new TypeScript export per Constitution Principle VI (Documentation): `useLlmConfig`, `useTokenUsage`, `LlmSettingsPanel`, `LlmConfigForm`, `TokenUsageDialog`
- [ ] T069 [P] Add Google-style docstrings to each new Python function/class per Constitution Principle VI: `SessionCreds`, `SessionCredentialStore`, `OperatorDefaultCreds`, `build_llm_client`, the audit-event helpers, the WS handlers, and the `POST /api/llm/test` endpoint
- [ ] T070 Run the full coverage report and confirm ≥90% on changed files: `docker exec astralbody bash -c "cd /app/backend && python -m pytest llm_config/tests/ audit/tests/ --cov=llm_config --cov=audit --cov-fail-under=90"` and `cd frontend && npx vitest run --coverage src/components/llm/ src/hooks/useLlmConfig.ts src/hooks/useTokenUsage.ts`
- [ ] T071 Execute [quickstart.md](quickstart.md) §§1–8 manually against a freshly-rebuilt local environment; confirm each acceptance scenario from the spec resolves

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 must complete before T002. T003 and T004 are independent and can run in parallel with T001/T002.
- **Foundational (Phase 2)**: depends on Setup. T005 must complete before T006. T007/T008/T009/T010 are parallelizable. T011 depends on T008/T009/T010. T012/T013 are parallelizable with each other and with T011. Tests T014–T018 each depend on their respective implementation tasks.
- **User stories (Phase 3+)**: all depend on Foundational completion.
  - US1 (Phase 3) is the MVP and should ship first.
  - US2 (Phase 4) depends on US1 (US2 reuses the WS dispatch switch and the settings panel).
  - US3 (Phase 5) depends on US1 (it adds emission inside `_call_llm` which US1 just rewired, and it mounts a dialog inside the settings panel US1 created).
  - US4 (Phase 6) depends on US1 + US2 + US3 outcomes existing in the audit log to verify against, but US4's individual tasks can be drafted in parallel with US1/US2/US3 if the verifying author has access to fixtures.
- **Polish (Phase 7)**: depends on all stories complete.

### User Story Dependencies (graph)

```
Phase 1 ──> Phase 2 ──> Phase 3 (US1, MVP)
                             │
                             ├──> Phase 4 (US2)
                             ├──> Phase 5 (US3)
                             └──> Phase 6 (US4)  ──> Phase 7
```

### Parallel Opportunities

- **Within Foundational**: T007, T008, T009, T010, T012, T013 are all in different files → all `[P]`. Tests T014–T018 are `[P]` once their implementation lands.
- **Within US1**: backend rewiring (T019–T025) is mostly sequential within `orchestrator.py` (T019→T020→T021→T022→T023 share a file); but T024 (agent_generator) and T025 (mcp_tools) are `[P]` against the orchestrator chain. WS handler T026 is `[P]` with the orchestrator chain. All US1 tests T031–T034 and T041–T043 are `[P]` with each other.
- **Within US2**: T044 and T046 are `[P]` (different files); their tests T048–T050 are `[P]`.
- **Within US3**: T054, T055, T056 are all `[P]`; T058–T060 are `[P]`.
- **Within US4**: T061, T062, T063, T064 are all `[P]` (different test files).

---

## Parallel Example: Foundational

```bash
# Once T005/T006 land, kick these in parallel:
Task: "T007 Add LLM* Pydantic message models to backend/shared/protocol.py"
Task: "T008 Add SessionCreds dataclass and SessionCredentialStore to backend/llm_config/session_creds.py"
Task: "T009 Add OperatorDefaultCreds frozen dataclass to backend/llm_config/operator_creds.py"
Task: "T010 Add CredentialSource enum and LLMUnavailable exception to backend/llm_config/types.py"

# After T008/T009/T010 land, T011 (factory) is unblocked.
# In parallel with T011:
Task: "T012 Add audit-event helpers to backend/llm_config/audit_events.py"
Task: "T013 Add log scrubber to backend/llm_config/log_scrub.py"
```

## Parallel Example: User Story 1 — frontend

```bash
# All independent, different files:
Task: "T035 Implement useLlmConfig hook at frontend/src/hooks/useLlmConfig.ts"
Task: "T036 Implement LlmConfigForm.tsx at frontend/src/components/llm/LlmConfigForm.tsx"
Task: "T037 Implement LlmSettingsPanel.tsx at frontend/src/components/llm/LlmSettingsPanel.tsx"

# Tests in parallel after their targets land:
Task: "T041 Vitest useLlmConfig at frontend/tests/hooks/useLlmConfig.test.ts"
Task: "T042 Vitest LlmConfigForm at frontend/tests/components/llm/LlmConfigForm.test.tsx"
Task: "T043 Vitest LlmSettingsPanel at frontend/tests/components/llm/LlmSettingsPanel.test.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (Setup): T001–T004 — module skeletons.
2. Phase 2 (Foundational): T005–T018 — credential plumbing, audit identifiers, log scrubbing, factory; **all gated tests green**.
3. Phase 3 (US1): T019–T043 — wire the factory into existing call sites, add WS handlers, REST endpoint, settings panel, hook, all tests.
4. **STOP and VALIDATE**: run quickstart §§1–3 + §6. If green, the MVP is shippable. Operators can already see per-user credential isolation via the new `llm.call` audit events.

### Incremental Delivery

After MVP:
- **+ US2** (T044–T051): rotate/clear flow + sign-out preservation tests. Quickstart §§4–5 unlock.
- **+ US3** (T052–T060): token usage dialog. Quickstart §7 unlocks.
- **+ US4** (T061–T065): verification tests + operator runbook. Quickstart §8 unlocks.
- **+ Polish** (T066–T071): docs, coverage, manual quickstart pass.

### Parallel Team Strategy

Once Foundational is done:
- Dev A: US1 backend chain (T019–T030, T031–T034)
- Dev B: US1 frontend chain (T035–T043)
- Dev C (after US1 merges): US2 + US3 in parallel (different files, mostly independent)
- Dev D: US4 verification tests (can start as soon as US1 audit emission is in `main`)

---

## Notes

- **Tests are mandatory**, not optional — Constitution Principle III requires 90% coverage on changed code. T070 enforces this in CI.
- Every backend Python file added/changed gets a Google-style docstring (T069); every TypeScript export gets a JSDoc block (T068) — Principle VI.
- **No new third-party dependencies** anywhere in this task list — Principle V satisfied by reuse of existing `openai` SDK, `psycopg2`, FastAPI, React, Vitest. T004 verifies the `openai` SDK pin is sufficient.
- **API key MUST never appear** in logs, DB rows, or audit payloads. T013 (scrubber), T012 (audit-helper guard), T016 (audit-helper test), T017 (scrubber test), and T061 (regex sweep over emitted audit payloads) collectively enforce this.
- **No runtime fallback** when a user's saved key fails — T020 (factory call once at the start of `_call_llm`) plus T051 (no-fallback regression test) plus T064 (credential-source audit field test) collectively enforce FR-009.
- **Knowledge synthesis is out of scope** — `backend/orchestrator/knowledge_synthesis.py` uses `KNOWLEDGE_LLM_*` env vars and is not touched by any task.
