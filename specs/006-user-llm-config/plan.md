# Implementation Plan: User-Configurable LLM Subscription

**Branch**: `006-user-llm-config` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-user-llm-config/spec.md`

## Summary

Lift the three OpenAI-compatible LLM env vars (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`) from being the sole source of LLM credentials to being a **deployment-level default** that any user can override on a per-device basis. A user opens an "LLM Settings" panel in the frontend, enters their own credentials, runs a "Test Connection" probe (a real `chat.completions.create` with `max_tokens: 1`), and saves. Their credentials live only in their browser's localStorage; they are sent to the server transiently with every request that needs LLM access and held in per-WebSocket session memory until the socket closes. Calls served with user credentials never fall back to the operator's defaults — even on runtime failure — and emit an `llm.call` audit event tagged `credential_source = user`. Calls for users with no personal config use the operator default and emit `credential_source = operator_default`. Server-initiated background jobs (notably the daily feedback quality / proposals job) keep using the operator default, since they have no caller. A new client-only "Token usage" dialog accumulates `usage.total_tokens` from each user-credentialed response into per-session / per-day / lifetime counters.

## Technical Context

**Language/Version**: Python 3.11 (backend, per `backend/.venv` + Constitution Principle I); TypeScript 5+ on Vite + React (frontend, per Constitution Principle II)
**Primary Dependencies**: FastAPI + WebSocket (existing); `openai` Python SDK (already a dependency, used via `OpenAI(...).chat.completions.create`); raw `psycopg2` for the existing audit table; React + Vite + Vitest + `@testing-library/react` (existing); existing Keycloak JWT middleware. **No new third-party libraries** — Constitution Principle V (lead-developer approval) is satisfied by reuse.
**Storage**:
- **Browser localStorage** for the user's `apiKey`, `baseUrl`, `modelName`, `connectedAt`, plus the three integer token counters and per-model breakdown. Server has no per-user credential store.
- **PostgreSQL** — *no new tables*. Three new audit `event_class` identifiers (`llm.config_change`, `llm.unconfigured`, `llm.call`) are added by extending the existing `audit_events` schema's enum check. The existing per-user isolation, hash-chain, and retention guarantees from feature 003 apply unchanged.
- **Per-WebSocket in-memory map** `_session_llm_creds: Dict[id(websocket), {api_key, base_url, model}]` on the orchestrator. Cleared on disconnect; never written to disk; never logged.
**Testing**: pytest (backend, `backend/llm_config/tests/`); Vitest + Testing Library (frontend, alongside existing component tests). 90% coverage on changed code per Constitution Principle III.
**Target Platform**: Existing AstralBody runtime — orchestrator container on port 8001, browser frontend over `ws://localhost:8001/ws`, PostgreSQL co-located.
**Project Type**: Web application (existing `backend/` + `frontend/` split).
**Performance Goals**: Per-call overhead introduced by the credential-resolution path MUST be ≤ 1 ms (cred lookup + audit-event prep are pure in-memory operations). Test Connection probe MUST complete within the existing orchestrator LLM timeout (no new timeout). Token-usage counter updates MUST be O(1) on the browser side.
**Constraints**:
- API key MUST NEVER touch disk on the server side (no log line, no DB row, no audit field).
- API key in WebSocket frames MUST be redacted from any orchestrator request/response logging (extend the existing log-scrubber pattern).
- No new third-party dependencies (Constitution V).
- Knowledge-synthesis module (`backend/orchestrator/knowledge_synthesis.py`) is **not** in scope — it uses `KNOWLEDGE_LLM_*` env vars, which the user's request did not mention.
**Scale/Scope**:
- ~6 LLM call sites change behavior: 3 in `orchestrator.py` (`_call_llm`, `_generate_tool_summary`, the synthesis-trigger call at ~line 3929), 2 in `agent_generator.py`, 1 in `agents/general/mcp_tools.py` (already takes a `_credentials` kwarg).
- 3 new WS message types: `llm_config_set`, `llm_config_clear`, `llm_usage_report` (server→client).
- 1 new REST endpoint: `POST /api/llm/test`.
- ~2 frontend components, 2 hooks.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python) | ✅ Pass | All backend changes are Python. |
| II. Frontend Framework (Vite + React + TS) | ✅ Pass | All frontend changes are TSX/TS in the existing Vite project. |
| III. Testing Standards (90% coverage) | ✅ Pass | New `backend/llm_config/tests/` for credential resolution, audit emission, factory; Vitest tests for the settings panel and the two hooks. CI coverage gate enforced as today. |
| IV. Code Quality (PEP 8 / ESLint) | ✅ Pass | No new style exceptions. |
| V. Dependency Management (lead approval) | ✅ Pass | **Zero new third-party libraries** — `openai`, `psycopg2`, FastAPI, React, Vitest are all already approved and in use. |
| VI. Documentation | ✅ Pass | Python additions get Google-style docstrings; TS exports get JSDoc; the new `POST /api/llm/test` endpoint surfaces in FastAPI's `/docs`. |
| VII. Security | ✅ Pass | Auth: Keycloak JWT validation continues to gate every LLM-dependent path. Authorization: per-user isolation is enforced by sourcing credentials exclusively from the caller's own session, never from a stored per-user record. Secrets: API keys never persisted server-side; localStorage is acknowledged as device-local with an explicit in-UI privacy notice. RFC 8693 token exchange for agents is unaffected (the agent's `_credentials` kwarg path already supports per-call key passthrough). |
| VIII. User Experience | ✅ Pass | Settings panel uses existing primitive components (Modal/Card/Input/Button/Alert). No new UI primitive proposed. |

**Result: PASS, no violations.** Complexity Tracking section is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-user-llm-config/
├── plan.md              # this file
├── spec.md              # feature specification (already exists, with Clarifications)
├── research.md          # Phase 0 output — generated below
├── data-model.md        # Phase 1 output — generated below
├── quickstart.md        # Phase 1 output — generated below
├── contracts/           # Phase 1 output — generated below
│   ├── ws-messages.md           # llm_config_set / llm_config_clear / llm_usage_report
│   ├── rest-llm-test.md         # POST /api/llm/test
│   └── audit-events.md          # llm.config_change / llm.unconfigured / llm.call
├── checklists/
│   └── requirements.md  # already exists
└── tasks.md             # NOT created here — produced by /speckit.tasks
```

### Source Code (repository root)

```text
backend/
├── llm_config/                     # NEW module (sibling of audit/, feedback/)
│   ├── __init__.py
│   ├── protocol.py                 # WS message dataclasses + Pydantic schemas
│   ├── session_creds.py            # SessionCredentialStore — per-WebSocket in-memory map
│   ├── client_factory.py           # build_llm_client(session_creds, default_env) → (OpenAI, source)
│   ├── audit_events.py             # event-class identifiers + helper recorders
│   ├── api.py                      # POST /api/llm/test — Test Connection probe
│   ├── ws_handlers.py              # handle_llm_config_set / handle_llm_config_clear
│   ├── log_scrub.py                # redact api_key in logs (extend existing scrubber)
│   └── tests/
│       ├── test_session_creds.py
│       ├── test_client_factory.py
│       ├── test_audit_emission.py
│       ├── test_test_connection_endpoint.py
│       └── test_ws_handlers.py
├── audit/                          # MODIFIED — extend event-class enum check
│   └── schemas.py                  # add 'llm.config_change', 'llm.unconfigured', 'llm.call'
├── orchestrator/
│   ├── orchestrator.py             # MODIFIED — replace `self.llm_client` with factory call
│   │                               #   in _call_llm, _generate_tool_summary, synthesis path
│   ├── agent_generator.py          # MODIFIED — accept (websocket, default_env) → factory
│   └── knowledge_synthesis.py      # UNCHANGED — uses KNOWLEDGE_LLM_*, out of scope
├── agents/
│   └── general/
│       └── mcp_tools.py            # MODIFIED — _credentials kwarg now carries resolved
│                                   #   user-or-default credentials from orchestrator
└── shared/
    └── protocol.py                 # MODIFIED — add LLMConfigSet, LLMConfigClear,
                                    #   LLMUsageReport message types

frontend/
├── src/
│   ├── components/
│   │   ├── llm/
│   │   │   ├── LlmSettingsPanel.tsx          # NEW — overlay, mirrors AuditLogPanel pattern
│   │   │   ├── LlmConfigForm.tsx             # NEW — apiKey/baseUrl/model + Test Connection
│   │   │   └── TokenUsageDialog.tsx          # NEW — session/today/lifetime + per-model
│   │   ├── layout/
│   │   │   └── DashboardLayout.tsx           # MODIFIED — add sidebar entry "LLM Settings"
│   │   └── primitives/                       # UNCHANGED
│   ├── hooks/
│   │   ├── useLlmConfig.ts                   # NEW — localStorage-backed config + dispatcher
│   │   ├── useTokenUsage.ts                  # NEW — listens for llm_usage_report → counters
│   │   └── useWebSocket.ts                   # MODIFIED — send llm_config in register_ui;
│   │                                         #   forward llm_usage_report → window event
│   └── catalog.ts                            # UNCHANGED
└── tests/
    └── components/llm/
        ├── LlmSettingsPanel.test.tsx
        ├── LlmConfigForm.test.tsx
        └── TokenUsageDialog.test.tsx
```

**Structure Decision**: AstralBody is a web application with the existing `backend/` + `frontend/` split. The new backend module is `backend/llm_config/`, sibling of `backend/audit/` and `backend/feedback/`, mirroring the convention established by features 003 and 004 (a self-contained module with `schemas.py`, `repository.py`-equivalent, `api.py`, `ws_handlers.py`, and a `tests/` subdir). On the frontend, settings UI lives under `src/components/llm/` and hooks under `src/hooks/`, matching how feature 003's audit panel was organized.

## Complexity Tracking

> No Constitution violations. Section intentionally empty.
