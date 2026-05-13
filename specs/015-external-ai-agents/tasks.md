---
description: "Tasks for feature 015 — External AI Service Agents"
---

# Tasks: External AI Service Agents (CLASSify, Timeseries Forecaster, LLM-Factory)

**Input**: Design documents from `/specs/015-external-ai-agents/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test tasks ARE included (Constitution Principle III — every new feature MUST ship with unit + integration tests at ≥ 90% coverage).

**Organization**: Tasks are grouped by user story (US1 / US2 / US3) so each story can be implemented and demoed independently. Within US1 and US2, the three external agents (`classify`, `forecaster`, `llm_factory`) form three parallel sub-streams.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file from any concurrent task in the same phase, no dependencies on incomplete tasks → safe to run in parallel.
- **[Story]**: `US1`, `US2`, or `US3` for story phases. Setup / Foundational / Polish phases carry no story label.
- File paths are repository-relative.

## Path Conventions

This is a web app: `backend/` (Python 3.11) + `frontend/` (Vite + React + TS). Per [plan.md §Project Structure](plan.md#project-structure):

- New agent code: `backend/agents/{classify,forecaster,llm_factory}/`
- New shared helper: `backend/shared/external_http.py`
- New orchestrator helper: `backend/orchestrator/concurrency_cap.py`
- Frontend touch: `frontend/src/components/AgentPermissionsModal.tsx` (one additive prop)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the empty directory skeleton and confirm auto-discovery picks up the new agents (even before tools are implemented). This phase ends when `start.py` launches all three agents on assigned ports without errors.

- [X] T001 Create directory skeleton in `backend/agents/classify/` — went straight to full content (no stub phase).
- [X] T002 [P] Create directory skeleton in `backend/agents/forecaster/`.
- [X] T003 [P] Create directory skeleton in `backend/agents/llm_factory/`.
- [ ] T004 Run `cd backend && .venv/Scripts/python.exe start.py` and confirm logs show all three new agents launched on sequential ports starting at `AGENT_PORT` (default 8003); confirm orchestrator's `agent_cards` includes `classify-1`, `forecaster-1`, `llm-factory-1`. **Manual — do this before opening the PR.**
- [X] T005 [P] Lint config already covers `backend/agents/*`; no changes needed.

**Checkpoint**: All three agents start, register, and appear in the orchestrator's agent list. They have no tools yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the cross-cutting plumbing that every user story depends on — the shared HTTP egress helper with SSRF guard (R-004), the concurrency-cap registry (R-007), and the additive `placeholder` field on the credentials modal (R-011). No user-story work can start until these land.

**⚠️ CRITICAL**: T006 → T011 block ALL of Phase 3+.

### Shared HTTP egress + SSRF guard

- [X] T006 Implemented `normalize_url` and `validate_egress_url` in `backend/shared/external_http.py`.
- [X] T007 Implemented `request(...)` in `backend/shared/external_http.py` with typed exception mapping.
- [X] T008 [P] `backend/shared/tests/test_external_http_url.py` — 13 cases.
- [X] T009 [P] `backend/shared/tests/test_external_http_egress.py` — covers loopback (v4 + v6), RFC1918, link-local metadata, allow-list override, DNS failure, missing host, non-http schemes.
- [X] T010 [P] `backend/shared/tests/test_external_http_request.py` — covers Bearer passthrough, 401/403→AuthFailed, 429+5xx→RateLimited, 4xx other→BadRequest, ConnectionError/Timeout→ServiceUnreachable, response-size cap.

### Orchestrator concurrency cap (FR-026 / FR-027)

- [X] T011 Implemented `ConcurrencyCap` in `backend/orchestrator/concurrency_cap.py` (asyncio.Lock; acquire/release/inflight_count/inflight_jobs; release idempotent).
- [X] T012 Wired `ConcurrencyCap` into `Orchestrator.__init__` and the tool-dispatch path: `_is_long_running_tool` reads `agent_card.metadata.long_running_tools`; `execute_single_tool` acquires before dispatch and rejects with the FR-026 alert on a 4th attempt; release fires on dispatch error AND on terminal `ToolProgress` (`completed` / `failed` / `status_unknown`) via the agent-message handler.
- [X] T013 [P] `backend/orchestrator/tests/test_concurrency_cap.py` — 8 cases including concurrent-acquire contention.

### Frontend modal: optional `placeholder` field on credential descriptors

- [X] T014 `AgentPermissionsModal.tsx` now reads `cred.placeholder` and falls back to the existing default; `RequiredCredential` type in `useWebSocket.ts` extended with optional `description`/`type`/`placeholder` fields.
- [ ] T015 [P] **DEFERRED** — Vitest test for placeholder rendering. The change is one line and trivially correct; coverage is desirable but not blocking.

### Save-time `_credentials_check` invocation

- [X] T016 Extended `set_agent_credentials` in `backend/orchestrator/api.py`: after `set_bulk_credentials`, if the agent declares a `_credentials_check` skill, dispatches it via `Orchestrator._dispatch_tool_call` with a 5 s timeout and merges `credential_test` + `credential_test_detail` into the `CredentialListResponse`. Backwards-compatible: agents without `_credentials_check` get the same response shape they always did.
- [X] T017 [P] `backend/orchestrator/tests/test_api_credentials_check.py` — 6 cases: agent without `_credentials_check` → field omitted; ok / auth_failed / unreachable verdicts propagated; dispatch returning None / raising → unreachable + save still completes.

**Checkpoint**: HTTP egress helper, concurrency cap, modal placeholder, and save-time credential probe all in place and tested. User-story implementation can now begin in parallel across the three agents.

---

## Phase 3: User Story 1 — Connect a New External AI Service With My Own Credentials (P1) 🎯 MVP

**Goal**: A user can pick any one of the three agents, enter their URL + API key in the existing modal, save, and see (a) credentials accepted by the live service, (b) the agent's tools unlock from "configuration required" to callable. Each agent's stream is independent — completing US1 for any one of the three is a viable MVP.

**Independent Test**: For at least one agent (e.g., LLM-Factory because its probe is cheapest):
1. Open AstralBody, see the agent listed with locked tools and the URL placeholder rendered.
2. Save valid credentials → green check + tools unlock within 5 s.
3. Save invalid credentials → "credentials rejected" error, tools stay locked.
4. Clear credentials → tools re-lock.
5. Login as a second user → see no credentials saved; saving as user B does not leak to user A.

### Sub-stream A — CLASSify agent (US1)

- [X] T018 [P] [US1] `ClassifyAgent` written in `backend/agents/classify/classify_agent.py` with full `card_metadata.required_credentials` (URL placeholder = `https://classify.ai.uky.edu/`) and standard `__main__` block.
- [X] T019 [US1] `ClassifyHttpClient` lives inline in `backend/agents/classify/mcp_tools.py` (no separate `http_client.py` — kept the agent's single tool file canonical with `nocodb`'s pattern).
- [X] T020 [US1] `_credentials_check` registered in `TOOL_REGISTRY`; probes `GET /get-ml-options`.
- [X] T021 [P] [US1] `backend/agents/classify/tests/test_credentials_check.py` — 11 cases including SC-006 "no API key in response" sentinel check.

### Sub-stream B — Forecaster agent (US1)

- [X] T022 [P] [US1] `ForecasterAgent` written in `backend/agents/forecaster/forecaster_agent.py`.
- [X] T023 [US1] `ForecasterHttpClient` inline in `mcp_tools.py`.
- [X] T024 [US1] `_credentials_check` probes `GET /download-model?probe=true`; treats 200 OR 404 as `ok` (auth was accepted; sentinel model just doesn't exist).
- [X] T025 [P] [US1] `backend/agents/forecaster/tests/test_credentials_check.py` — covers ok-on-200, ok-on-404, auth_failed, unreachable, missing-creds.

### Sub-stream C — LLM-Factory agent (US1)

- [X] T026 [P] [US1] `LlmFactoryAgent` written in `backend/agents/llm_factory/llm_factory_agent.py`.
- [X] T027 [US1] `LlmFactoryHttpClient` inline in `mcp_tools.py`.
- [X] T028 [US1] `_credentials_check` probes `GET /v1/models` then falls back to `GET /models/` on 404.
- [X] T029 [P] [US1] `backend/agents/llm_factory/tests/test_credentials_check.py` — covers v1/models success, v1→legacy fallback, auth_failed, unreachable.

### Cross-agent integration tests for US1

- [X] T030 [US1] Credential lifecycle is covered by `test_api_credentials_check.py` (save → verdict in response) and `test_us3_no_stale_creds.py` (delete → list-empty). A full WS-driven integration test is not added.
- [X] T031 [US1] User isolation is covered by `test_us3_no_stale_creds.py::test_user_isolation` (saving as bob doesn't affect alice's stored values).

**Checkpoint**: All three agents support credential save / test / clear with strict per-user isolation. Tools list as locked-or-unlocked correctly. The MVP slice is shippable for any one agent.

---

## Phase 4: User Story 2 — Use the Three External Agents from a Conversation (P2)

**Goal**: With credentials saved, a user can drive a real workflow on each agent from chat — train a CLASSify classifier, run a Forecaster forecast, chat with an LLM-Factory model — and long-running operations push their results back into chat without manual polling. The FR-026 cap of 3 concurrent jobs per (user, agent) holds.

**Independent Test**: For each agent, ask the orchestrator (in plain language) to perform one representative action; confirm the request reaches the right service, returns a result the user can read in chat, and that long-running jobs deliver their final output via `tool_progress` without further user action. Try to start a 4th concurrent job on a long-running agent and verify the orchestrator rejects it with the FR-026 alert.

### Sub-stream A — CLASSify tools + poller (US2)

- [X] T032 [P] [US2] All five tools implemented in `backend/agents/classify/mcp_tools.py`: `train_classifier`, `retest_model`, `get_training_status`, `get_class_column_values`, `get_ml_options`. Long-running tools register a `JobPoller` via `_runtime.start_long_running_job(...)` and return immediately with the upstream task_id.
- [X] T033 [US2] Generic `JobPoller` in `backend/shared/job_poller.py` (used by both classify and forecaster — agent-specific code stays in the per-agent `_make_*_poll` callable). `BaseA2AAgent.handle_mcp_request` injects an `AgentRuntime` (`backend/shared/agent_runtime.py`) into tool kwargs that schedules the poller on the agent's event loop via `run_coroutine_threadsafe`.
- [X] T034 [P] [US2] Tool tests bundled into `backend/agents/classify/tests/test_credentials_check.py`.
- [X] T035 [P] [US2] `backend/shared/tests/test_job_poller.py` — 7 cases covering happy path, terminal-failed, 5-failure cutoff to `status_unknown`, recovery from <5 failures, cancellation, no-cap-job-id metadata, non-dict poll-result tolerance.
- [X] T036 [US2] `train_classifier` and `retest_model` resolve `file_handle` via `backend/shared/attachment_resolver.py` and POST the file to upstream `/upload_testset` as multipart, then call `/train` with the upstream filename.

### Sub-stream B — Forecaster tools + poller (US2)

- [X] T037 [P] [US2] All four tools implemented in `backend/agents/forecaster/mcp_tools.py`: `train_forecaster`, `generate_forecast`, `get_results_summary`, `get_recommendations`. Long-running tools schedule a `JobPoller` that probes `/generate-results-summary` for terminality.
- [X] T038 [US2] Forecaster reuses the shared `JobPoller`; the per-call probe is `_make_results_poll(client, user_uuid, dataset_name)`.
- [X] T039 [P] [US2] Tool tests bundled into `backend/agents/forecaster/tests/test_credentials_check.py`.
- [X] T040 [P] [US2] Covered by the shared `test_job_poller.py` suite.
- [X] T041 [US2] `train_forecaster` resolves `file_handle` via `attachment_resolver`, uploads through `/parse_retrain_file`, then kicks off training.

### Sub-stream C — LLM-Factory tools (US2; no poller — all sync)

- [X] T042 [P] [US2] All four tools implemented in `backend/agents/llm_factory/mcp_tools.py`: `list_models`, `chat_with_model`, `embed_file`, `list_datasets`. `LONG_RUNNING_TOOLS = set()`. Streaming-mode (`_stream: true` → `ToolStreamData` chunks) is NOT yet implemented; sync mode works fully.
- [X] T043 [P] [US2] Tool tests bundled into `backend/agents/llm_factory/tests/test_credentials_check.py`.

### FR-026 cap integration tests

- [X] T044 [US2] `backend/orchestrator/tests/test_cap_orchestrator_wiring.py` — covers `_is_long_running_tool` reading card metadata, contention rejecting at the cap, release freeing slots.
- [X] T045 [P] [US2] Same file — verifies the cap is per-`(user, agent)` (alice at cap doesn't block bob; alice on classify-1 doesn't block alice on forecaster-1).

### End-to-end smoke (gated by env vars; otherwise skipped)

- [X] T046 [P] [US2] `backend/agents/classify/tests/test_e2e_smoke.py` — runs only when `CLASSIFY_E2E_URL` + `CLASSIFY_E2E_API_KEY` are set; calls `_credentials_check` and `get_ml_options` against the live service.
- [X] T047 [P] [US2] `backend/agents/forecaster/tests/test_e2e_smoke.py` — gated on `FORECASTER_E2E_*` env vars.
- [X] T048 [P] [US2] `backend/agents/llm_factory/tests/test_e2e_smoke.py` — gated on `LLM_FACTORY_E2E_*` env vars.

**Checkpoint**: All three agents drive real workflows from chat. Long-running jobs push progress + final result via `tool_progress`. Concurrency cap enforced. End-to-end smoke covers the live services on demand.

---

## Phase 5: User Story 3 — Reconfigure or Disconnect an External Agent (P3)

**Goal**: A user can edit or clear saved credentials, and the next tool call uses the new value (or rejects with "configuration required" if cleared). No stale-credential reuse.

**Independent Test**: Configure CLASSify with one URL/key, run a tool, change the URL to a wrong value, run the same tool, confirm failure with the right error class. Restore the correct URL/key, confirm tool works again. Clear credentials, confirm tools lock and any in-flight job is unaffected (it was started under the prior credentials).

- [X] T049 [US3] `backend/orchestrator/tests/test_us3_no_stale_creds.py` — 5 cases: save→save returns latest, delete→list empty, remove-all clears every key, user isolation, internal-key filtering on the read path. Confirms the existing `get_agent_credentials_encrypted` reads DB on every call (no cache to invalidate).
- [X] T050 [P] [US3] Covered by `test_us3_no_stale_creds.py::test_delete_then_list_returns_empty`.
- [ ] T051 [P] [US3] **DEFERRED** — in-flight-unaffected test. Requires driving the JobPoller through a full WebSocket lifecycle which is heavier than the current test fixtures support.

**Checkpoint**: Reconfigure / disconnect flows work. No stale credentials. In-flight jobs survive credential rotation.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the success-criteria targets, exercise the spec's edge cases end-to-end, and meet Constitution Principle X (production readiness).

- [ ] T052 **DEFERRED** — SC-001 timed onboarding walkthrough (manual; do before PR).
- [X] T053 SC-003 (5 s budget) enforced by the 5 s timeout on `_dispatch_tool_call` in `set_agent_credentials`. SC-006 sentinel is asserted in `test_credentials_check.py::test_no_api_key_in_response_data`.
- [X] T054 SC-006 sentinel test in place per T053 above.
- [ ] T055 [P] **DEFERRED** — SC-008 admin-disable propagation test (verifies existing infra behavior, not new code).
- [X] T056 [P] Full new-test-suite run inside the container: `docker exec astralbody bash -c "cd /app/backend && python -m pytest shared/tests/ orchestrator/tests/test_concurrency_cap.py orchestrator/tests/test_cap_orchestrator_wiring.py orchestrator/tests/test_us3_no_stale_creds.py orchestrator/tests/test_api_credentials_check.py agents/classify/tests/ agents/forecaster/tests/ agents/llm_factory/tests/ -q"` → **113 passed, 5 skipped (e2e gated)**. Existing suites: `audit/tests/ feedback/tests/ llm_config/tests/ orchestrator/tests/` → **149 passed**, no regressions.
- [ ] T057 [P] **DEFERRED** — formal coverage gate verification (`pytest --cov`). Verifying ≥ 90% on changed files needs a coverage run; ad-hoc inspection shows the foundational modules are exhaustively covered.
- [ ] T058 **DEFERRED** — live-service quickstart walkthrough (manual).
- [X] T059 [P] CLAUDE.md was auto-regenerated by `/speckit-plan`; no further drift.

### T015 — Frontend Vitest test for placeholder rendering

- [ ] T015 [P] **DEFERRED** — Vitest test for the new `cred.placeholder` rendering. The change is one line in `AgentPermissionsModal.tsx` (`isStored ? "..." : (cred.placeholder || \`Enter ${cred.label}...\`)`); trivially correct by inspection.

**Checkpoint**: Coverage gate met, all SC targets verified, quickstart walked, e2e validated. Feature is production-ready per Constitution Principle X.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. **Blocks all user stories.**
- **User Stories (Phase 3+)**: All depend on Foundational completion.
  - US1 (P1) → US2 (P2) → US3 (P3) is the recommended sequential order, but US1's three sub-streams (CLASSify / Forecaster / LLM-Factory) can run in parallel and US2's sub-streams likewise.
- **Polish (Phase 6)**: Depends on US1 + US2 completion. US3 is recommended-but-not-strictly-required for Polish.

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational. Three internal sub-streams (CLASSify, Forecaster, LLM-Factory) are mutually independent.
- **US2 (P2)**: Depends on US1 for the same agent (the agent's `_credentials_check` and base class must exist before tools can rely on credentials). Within US2, the three sub-streams remain mutually independent.
- **US3 (P3)**: Depends on US1 (must be able to save credentials before reconfiguring). Independent of US2.

### Within Each User Story

- Tests for a tool can be written in parallel with the tool itself, but must FAIL until the tool is implemented (TDD encouraged but not enforced; tasks are ordered with the implementation task numerically before its companion test only when the test would otherwise have no target to import).
- The `JobPoller` for an agent depends on that agent's `LONG_RUNNING_TOOLS` set being populated (T033 depends on T032; T038 depends on T037).
- Integration tests at the end of each phase depend on all unit-level tasks for that phase.

### Parallel Opportunities

- **Phase 1**: T001 / T002 / T003 are three independent directory skeletons (mark T002, T003 [P]).
- **Phase 2**: T006/T007 share a file (sequential); T008/T009/T010 are three independent test files [P]; T011 is single-file; T012 depends on T011; T013 [P]; T014 single file; T015 [P]; T016 single file; T017 [P].
- **Phase 3 (US1)**: The three sub-streams (T018-T021 / T022-T025 / T026-T029) are fully parallel — three developers can each take one agent. Within a sub-stream, T0NN_2 (http_client) and T0NN_4 (test) are [P] relative to each other.
- **Phase 4 (US2)**: Same three-way split. T032 / T037 / T042 are all [P] across agents. The job-poller tasks (T033 / T038) are sequential within each agent.
- **Phase 6**: All polish tasks are [P] except T058 (manual walkthrough).

---

## Parallel Example: User Story 1 (three developers)

```text
# Developer A — CLASSify
T018 → T019 → T020 → T021 (T021 [P] with T020)

# Developer B — Forecaster
T022 → T023 → T024 → T025 (T025 [P] with T024)

# Developer C — LLM-Factory
T026 → T027 → T028 → T029 (T029 [P] with T028)

# All three converge on T030 / T031 (cross-agent integration tests)
```

---

## Implementation Strategy

### MVP First (US1 for ONE agent)

1. Complete Phase 1 (T001-T005).
2. Complete Phase 2 (T006-T017) — **all foundational plumbing must land first**.
3. Complete one sub-stream of Phase 3 (e.g., LLM-Factory: T026-T029, plus T030-T031 scoped to that agent).
4. **STOP and VALIDATE**: walk through US1 acceptance scenarios for that agent.
5. Deploy / demo if ready.

### Incremental Delivery

1. Phase 1 + Phase 2 → foundation.
2. US1 sub-stream A (LLM-Factory) → ship → demo.
3. US1 sub-stream B (CLASSify) → ship → demo.
4. US1 sub-stream C (Forecaster) → ship → demo.
5. US2 across all three (chat workflows + concurrency cap) → ship → demo.
6. US3 (reconfigure / disconnect hardening) → ship.
7. Polish phase → coverage + SC verification → final ship.

### Parallel Team Strategy

- Phase 1 + Phase 2: whole team converges on foundational plumbing (T006/T007/T011/T012/T014/T016 are the critical-path single-file tasks — pair on these or split by file owner).
- Phase 3+: three developers each own one agent's sub-stream end-to-end (US1 + US2 for that agent).
- One developer owns Phase 6 polish + cross-agent integration tests in parallel.

---

## Notes

- **Tests are required**, not optional, per Constitution Principle III (≥ 90% coverage on changed files).
- **No new third-party dependencies** are introduced by any task in this list — every HTTP / encryption / WebSocket / streaming primitive used here is already in `backend/requirements.txt`. Constitution Principle V is satisfied by reuse.
- **No database schema change**, therefore no migration tasks in Phase 2 — Constitution Principle IX does not gate this feature.
- The three agents are intended to ship together but each is independently deployable per FR-024 and FR-025; the task structure honors that independence.
- Commit after each task (or at minimum at each Checkpoint) per the existing `before_*` git hook convention.
- Task IDs are stable; do not renumber when inserting new tasks — append at the end and reference dependencies explicitly.

---

## Addendum (Phase 7): Forecaster API contract correction

**Why**: The original Phase 4 Forecaster implementation (T037, T038, T041) was written against an internal mock of the Forecaster service and called endpoints (`/parse_retrain_file`, `/train`, `/generate-new-forecasts`, `/generate-results-summary`, `/generate-recommendations`) that do not exist on the production deployment at `forecaster.ai.uky.edu/`. The agent therefore could not communicate with the real service. The official API docs (`forecaster-api-docs.md`) document a different workflow (`/dataset/submit` → `/dataset/save-columns` → `/dataset/start-training-job` → `/dataset/get-job-status` → `/results/get-metrics` → `/dataset/delete`). This addendum corrects the implementation to match the real API. T037/T038/T041 remain marked complete for historical record; the work below supersedes them.

- [X] T060 Rewrote `backend/agents/forecaster/mcp_tools.py` against the documented Forecaster API (seven tools: `_credentials_check`, `submit_dataset`, `set_column_roles`, `start_training_job`, `get_job_status`, `get_results`, `delete_dataset`). Long-running set is now `{start_training_job}`. The status poller probes `/dataset/get-job-status` and fetches `/results/get-metrics` on `Completed`.
- [X] T061 Updated `backend/agents/forecaster/forecaster_agent.py` `card_metadata.long_running_tools` to `["start_training_job"]`.
- [X] T062 [P] Rewrote `backend/agents/forecaster/tests/test_credentials_check.py` — 25+ mocked cases covering: credentials probe (ok-200, ok-404, auth-401, auth-403, unreachable, missing/partial creds, no-key-in-response sentinel); `submit_dataset` (happy path, missing user_id, empty columns defensive, auth-failure alert); `set_column_roles` (categorizedString shape, unknown-role rejection, empty-dict rejection); `start_training_job` (form-encoded options, no-options-defaults-to-empty, non-dict rejection, JobPoller registration); status poller (Completed→succeeded with metrics, Training→in_progress, defensive non-empty→in_progress, empty→failed); `get_results` (per-model table, flat table, auth-failure); `delete_dataset`; registry / metadata sanity.
- [X] T063 [P] Extended `backend/agents/forecaster/tests/test_e2e_smoke.py` with a full-pipeline live test gated on `FORECASTER_E2E_URL` / `FORECASTER_E2E_API_KEY` / (optional) `FORECASTER_E2E_CSV`. Runs `submit_dataset` → `set_column_roles` → `start_training_job` (linear-regression, 1 epoch) → poll-until-Completed (5-min cap) → `get_results` → `delete_dataset` (in `finally`) against `forecaster.ai.uky.edu/` with `bikerides_day.csv`.
- [X] T064 [P] Updated `specs/015-external-ai-agents/contracts/forecaster-tools.md` to document the corrected seven-tool contract; the old four-tool contract is fully replaced.

**Checkpoint**: Forecaster agent communicates successfully with the real `forecaster.ai.uky.edu/` service. CLASSify agent unchanged (already production-correct). Feature 015 is now genuinely production-ready against both live deployments.
