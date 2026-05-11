# Implementation Plan: External AI Service Agents (CLASSify, Timeseries Forecaster, LLM-Factory)

**Branch**: `015-external-ai-agents` | **Date**: 2026-05-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/015-external-ai-agents/spec.md`

## Summary

Add three new MCP agents to AstralBody — **CLASSify**, **Timeseries Forecaster**, and **LLM-Factory** — each wrapping an external HTTP service and gated behind a per-user Service URL + API Key the user enters in the existing agent-permissions modal. Each agent exposes ~4–6 curated tools (curated set per [Clarification Q1, 2026-05-07](spec.md#clarifications)). Long-running operations on CLASSify and Timeseries Forecaster (ClearML-backed training/forecast jobs) are handled by the agent: the tool returns immediately with a job handle, then a background poller pushes progress and the final result into the originating chat using the existing `ToolProgress` mechanism delivered in feature 014 ([Clarification Q2](spec.md#clarifications)). A small in-memory registry caps each `(user, agent)` pair to 3 concurrent in-flight jobs, rejecting further attempts with an actionable message ([Clarification Q3](spec.md#clarifications)).

The implementation follows the existing canonical agent layout (one directory under [backend/agents/](backend/agents/) per agent, with `*_agent.py` / `mcp_server.py` / `mcp_tools.py` / `__init__.py`) and reuses every supporting subsystem already in place — auto-discovery in [backend/start.py](backend/start.py), E2E-encrypted credential storage in [backend/orchestrator/credential_manager.py](backend/orchestrator/credential_manager.py), the credential-form rendering in [frontend/src/components/AgentPermissionsModal.tsx](frontend/src/components/AgentPermissionsModal.tsx), and the audit-log subsystem under [backend/audit/](backend/audit/). **No new database tables, no new third-party libraries, and no constitutional waivers** are required.

## Technical Context

**Language/Version**: Python 3.11 (backend, per `backend/.venv` + Constitution Principle I); TypeScript 5+ on Vite + React for any UI placeholder text changes (per Constitution Principle II).

**Primary Dependencies**: FastAPI + WebSocket (existing); `requests` (already used by other agents — `weather`, `nocodb`, `grants`); `cryptography` (already used by `credential_manager.py` for ECIES + Fernet). **No new third-party libraries** — Constitution Principle V is satisfied by reuse. The only new code modules introduced are first-party (under `backend/agents/{classify,forecaster,llm_factory}/` and one tiny orchestrator helper for concurrency capping).

**Storage**: PostgreSQL — credentials reuse the existing [`user_credentials` table](backend/shared/database.py) (columns: `user_id`, `agent_id`, `credential_key`, `encrypted_value`, with unique constraint on the triple). **No schema changes**, so Constitution Principle IX (Database Migrations) does not gate this feature. The FR-026 concurrency cap is held in process memory on the orchestrator (3 ints per user-agent pair) — durability is not required because in-flight jobs are themselves ephemeral and survive only until the WebSocket session.

**Testing**: pytest (existing, see [backend/audit/tests/](backend/audit/tests/), [backend/feedback/tests/](backend/feedback/tests/), [backend/llm_config/tests/](backend/llm_config/tests/) for analogous test layouts) with `pytest-asyncio` and `responses` / `httpretty`-style HTTP mocks already in use. Frontend changes are minimal (no new components — only placeholder strings on the existing modal); covered by `vitest` + `@testing-library/react` if any change touches React. Coverage target ≥ 90% on changed files (Constitution Principle III).

**Target Platform**: Linux server inside the existing `astralbody` Docker container; agents run as in-cluster subprocesses spawned by [backend/start.py](backend/start.py:37-101). External services reached over HTTPS; user supplies the URL.

**Project Type**: Web application (existing FastAPI + WebSocket backend with Vite/React frontend).

**Performance Goals**: Per [Success Criteria](spec.md#measurable-outcomes) — credential save → user-visible verdict in ≤ 5 s; long-running job result visible in chat ≤ 30 s after the underlying service marks it done; admin-disable propagation ≤ 10 s.

**Constraints**:
- API keys MUST never be logged, never echoed back to the frontend, and never leave the agent's process in plaintext (per FR-006 / FR-007). The existing E2E ECIES flow already enforces this.
- The user-supplied URL is an SSRF surface — request validation must reject `file://`, `localhost`, and RFC1918 ranges unless explicitly enabled via an admin allow-list (default deny). This is a security-hardening constraint for this feature, not a constitutional gate.
- Backwards-compatibility shims are not introduced; no agent-toggle config knobs beyond the existing admin-disable.

**Scale/Scope**: ≤ 3 concurrent jobs per `(user, agent)` pair (FR-026); the existing platform comfortably handles dozens of agents and hundreds of users; this feature does not change those bounds.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-evaluated after Phase 1 design — see [Constitution re-check (post-design)](#constitution-re-check-post-design).*

| Principle | Verdict | Notes |
|----------|---------|-------|
| I. Primary Language (Python backend) | ✅ Pass | Three agents implemented in Python 3.11 under `backend/agents/`. |
| II. Frontend Framework (Vite + React + TypeScript) | ✅ Pass | No new components; only string-level changes (placeholder URLs) to the existing TypeScript [AgentPermissionsModal](frontend/src/components/AgentPermissionsModal.tsx). |
| III. Testing (≥ 90% coverage on changed code) | ✅ Pass (planned) | Each new agent ships unit + integration tests in `backend/agents/{name}/tests/` covering happy path, auth failure, unreachable host, async-job lifecycle, and the FR-026 cap. Coverage measured in CI. |
| IV. Code Quality (PEP 8 / ESLint) | ✅ Pass | Existing project linters apply. |
| V. Dependency Management (no new third-party deps without lead approval) | ✅ Pass | `requests`, `cryptography`, `pydantic`, `fastapi`, `websockets` are already in `backend/requirements.txt`. **Zero new third-party libraries.** |
| VI. Documentation (docstrings + `/docs`) | ✅ Pass | Each tool function carries a Google-style docstring; the agent's MCP `tools/list` reply already feeds Swagger-style metadata to the frontend. |
| VII. Security (Keycloak + RFC 8693 + secret hygiene) | ✅ Pass | Per-user credentials encrypted via existing ECIES pipeline; URLs validated against an SSRF block-list before HTTP egress (see [research.md §SSRF](research.md)); audit events emitted via existing [backend/audit/](backend/audit/) hooks (FR-019, FR-020). |
| VIII. UI Consistency (primitive components) | ✅ Pass | Tool results rendered via existing primitives (`Text`, `Card`, `Table`, `Alert`); no new primitive introduced. |
| IX. Database Migrations | ✅ Pass | **No schema changes** — credentials reuse `user_credentials`; concurrency cap is in-process state. |
| X. Production Readiness | ✅ Pass (planned) | Tests exercise golden path, auth failure, unreachable, async-cancellation, and rate-limit edge cases. Structured logs on every HTTP egress. No stubs or hard-coded URLs (production URLs are placeholder text only; user-supplied URL always wins). |

**Initial gate verdict**: Pass. No violations to justify; **Complexity Tracking section is intentionally empty.**

## Project Structure

### Documentation (this feature)

```text
specs/015-external-ai-agents/
├── plan.md                     # This file (/speckit-plan command output)
├── spec.md                     # Feature specification (already complete)
├── research.md                 # Phase 0 output — design decisions resolved here
├── data-model.md               # Phase 1 output — entities, schemas, state machines
├── quickstart.md               # Phase 1 output — local dev walkthrough
├── contracts/
│   ├── rest-credentials.md     # PUT /api/agents/{agent_id}/credentials (existing — referenced)
│   ├── ws-tool-progress.md     # ToolProgress protocol message (existing — referenced)
│   ├── classify-tools.md       # MCP tool schemas exposed by classify agent
│   ├── forecaster-tools.md     # MCP tool schemas exposed by forecaster agent
│   └── llm-factory-tools.md    # MCP tool schemas exposed by llm-factory agent
├── checklists/
│   └── requirements.md         # Spec-quality checklist (already complete)
└── tasks.md                    # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── agents/
│   ├── classify/                          # NEW — wraps classify.ai.uky.edu
│   │   ├── __init__.py
│   │   ├── classify_agent.py              # BaseA2AAgent subclass + card_metadata
│   │   ├── mcp_server.py                  # tools/list + tools/call dispatcher
│   │   ├── mcp_tools.py                   # ~5 tools + TOOL_REGISTRY
│   │   ├── http_client.py                 # Bearer-auth, URL normalization, SSRF guard, error mapping
│   │   ├── job_poller.py                  # async ClearML-job poller pushing ToolProgress
│   │   └── tests/
│   │       ├── test_classify_tools.py
│   │       ├── test_http_client.py
│   │       └── test_job_poller.py
│   ├── forecaster/                        # NEW — wraps forecaster.ai.uky.edu
│   │   ├── __init__.py
│   │   ├── forecaster_agent.py
│   │   ├── mcp_server.py
│   │   ├── mcp_tools.py                   # ~4 tools + TOOL_REGISTRY
│   │   ├── http_client.py                 # (same shape as classify; imports shared helper if useful)
│   │   ├── job_poller.py
│   │   └── tests/
│   │       ├── test_forecaster_tools.py
│   │       └── test_job_poller.py
│   └── llm_factory/                       # NEW — wraps llm-factory.ai.uky.edu
│       ├── __init__.py
│       ├── llm_factory_agent.py
│       ├── mcp_server.py
│       ├── mcp_tools.py                   # ~4 tools + TOOL_REGISTRY (chat is sync; no poller needed)
│       ├── http_client.py
│       └── tests/
│           └── test_llm_factory_tools.py
├── shared/
│   └── external_http.py                   # NEW — small shared helper: URL normalization,
│                                          # SSRF guard, ping-test, retry/timeout policy.
│                                          # Used by all three agents' http_client.py.
└── orchestrator/
    └── concurrency_cap.py                 # NEW — tiny in-memory registry: per (user_id, agent_id)
                                            # → set of in-flight job_ids; cap = 3 (FR-026).
                                            # Hooks into orchestrator's tool-dispatch path.

frontend/
└── src/
    └── components/
        └── AgentPermissionsModal.tsx       # MODIFIED only if placeholder text needs updating
                                            # for the three new agents' URL hints. No new component.
```

**Structure Decision**: AstralBody's existing per-agent-directory convention is followed verbatim — three new directories, each implementing the canonical four-file layout used by every other agent. Two genuinely shared pieces of code are added at higher scopes:
- [backend/shared/external_http.py](backend/shared/external_http.py) — because URL normalization, SSRF blocking, the cheap-ping-test for credential save, and the retry/timeout policy are identical across all three agents and have no agent-specific knowledge. Putting this in `backend/shared/` (alongside `base_agent.py` and `protocol.py`) keeps each agent thin.
- [backend/orchestrator/concurrency_cap.py](backend/orchestrator/concurrency_cap.py) — because the FR-026 cap must be enforced before tool dispatch, which is orchestrator-layer code; a per-agent implementation would either duplicate logic or fail to coordinate across multiple agents started by the same user. One file, one class, no public API beyond `acquire(user_id, agent_id, job_id) → bool` and `release(user_id, agent_id, job_id)`.

## Complexity Tracking

> Constitution Check passed without violations. **No entries.**

## Constitution re-check (post-design)

After Phase 1 (data-model + contracts) the design surfaces no additional constitutional concerns:

- No new third-party dependency was introduced by the contracts (Principle V holds).
- No schema changes appeared (Principle IX holds — `user_credentials` is sufficient).
- All three agents' tool surfaces stay within the curated ~4–6 set (Principle X — no half-finished tools merged).
- Production-readiness gates remain achievable: each tool has explicit failure-mode tests in [research.md](research.md).

**Final verdict**: Pass. Proceed to `/speckit-tasks`.
