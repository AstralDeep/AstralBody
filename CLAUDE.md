# AstralBody Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-13

## Active Technologies
- Python 3.11+ (backend), TypeScript 5.x (frontend, Vite + React 18) + FastAPI, websockets, existing OpenAI-compatible LLM client (`_call_llm`); React 18, Tailwind, framer-motion, lucide-react, existing `fetchJson` helper. **No new third-party libraries** (Constitution V). (013-agent-visibility-tool-picker)
- PostgreSQL — existing tables (`agent_ownership`, `agent_scopes`, `tool_overrides`, `chats`, `user_preferences`); schema delta: `chats.agent_id`, `tool_overrides.permission_kind`. Idempotent auto-migration per Constitution IX. (013-agent-visibility-tool-picker)
- Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend) + Backend — FastAPI, websockets, the existing OpenAI-compatible client used in `_call_llm`. Frontend — React 18, Tailwind, Framer Motion, sonner (already present). (008-llm-text-only-chat)
- Postgres (existing). Tutorial steps live in the `tutorial_step` table seeded by [backend/seeds/tutorial_steps_seed.sql](../../backend/seeds/tutorial_steps_seed.sql); no new tables. (008-llm-text-only-chat)
- TypeScript 5.x (frontend), Python 3.11+ (backend — no backend code change expected for this feature) + Vite + React 18, framer-motion, sonner, existing `fetchJson` helper in `frontend/src/api/feedback.ts`. No new dependencies. (010-fix-page-flash)
- N/A — feature is pure frontend behavior; no schema changes. (010-fix-page-flash)
- Python 3.11+ (backend; per Constitution Principle I and existing `grants` agent module). + Existing — `shared.base_agent.BaseA2AAgent`, `shared.protocol.MCPRequest/MCPResponse`, `shared.primitives` (Text, Card, Alert, Table, List_, Tabs, MetricCard), `agents.grants.mcp_server.MCPServer`, `agents.grants.mcp_tools.TOOL_REGISTRY`, `agents.grants.caai_knowledge`, the project's existing OpenAI-compatible LLM client (used by `_call_llm`). **No new third-party libraries** (Constitution Principle V). (011-nsf-grant-agent)
- N/A. No new tables, no schema changes. Cross-session memory inherits the existing `grants` agent's posture per Clarifications Q3. (011-nsf-grant-agent)
- Python 3.11+ (backend), TypeScript 5.x (frontend, Vite + React 18) + FastAPI, websockets, the existing OpenAI-compatible LLM client (`_call_llm`); React 18, Tailwind, framer-motion, sonner, the existing `fetchJson` helper. **No new dependencies** (Constitution V). (012-fix-agent-flows)
- PostgreSQL — existing `draft_agents` and `agent_ownership` tables. **No schema change required**; FR-016/FR-017 are satisfied by existing columns plus the existing `delete_draft` endpoint at [`api.py:1014`](../../backend/orchestrator/api.py#L1014). (012-fix-agent-flows)
- Python 3.11+ (backend); vanilla ES5-compatible JavaScript maintained by the orchestrator render layer (`backend/webrender/static/client.js`, no build step) + Existing only — FastAPI, websockets, `python-jose` (JWT), `cryptography` (Fernet, already used by `offline_grant.py`), httpx/requests (existing Keycloak calls), astralprims (first-party, consumed unchanged per spec A9). **No new third-party libraries** (Constitution V). (028-workspace-auth-revival)
- PostgreSQL via existing `shared/database.py` `_init_db()` idempotent migrations. Deltas: new `web_session` table; new `workspace_snapshot` table; new columns on `saved_components` (`component_id`, `position`, `updated_at`); new `auth_revocation_queue` table for offline-tolerant revocation. Rollback documented in [data-model.md](data-model.md). (028-workspace-auth-revival)

- Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend) (002-file-uploads)

## Project Structure

```text
backend/
frontend/
tests/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend): Follow standard conventions

## Recent Changes
- 028-workspace-auth-revival: Added Python 3.11+ (backend); vanilla ES5-compatible JavaScript maintained by the orchestrator render layer (`backend/webrender/static/client.js`, no build step) + Existing only — FastAPI, websockets, `python-jose` (JWT), `cryptography` (Fernet, already used by `offline_grant.py`), httpx/requests (existing Keycloak calls), astralprims (first-party, consumed unchanged per spec A9). **No new third-party libraries** (Constitution V).
- 025-agentic-soul-integration: Porting openclaw's agentic experience (personalized onboarding, enableable skills, personality/"soul", cross-session memory, scheduled "cron" jobs, background "dreaming" consolidation) into AstralBody, HIPAA-safe. Skill = an agent tool gated by existing `agent_scopes`/`tool_overrides` (no new artifact). New backend modules `personalization/`, `scheduler/`, `dreaming/` + `orchestrator/offline_grant.py`; new per-user tables (`user_personalization`, `memory_item`, `short_term_signal`, `scheduled_job`, `job_run`, `consolidation_sweep`, `user_offline_grant`) via the existing idempotent `_init_db()`. Scheduling/cron are **pure-Python** (no new deps); the memory PHI gate uses **Presidio** (lead-dev-approved local PHI detector, the one sanctioned new dependency); jobs run on the existing `BackgroundTaskManager`+`VirtualWebSocket`. **Key finding**: persistent login (016) is client-side only, so unattended jobs need a new server-side encrypted `offline_access` refresh-token store that re-derives a fresh access token → RFC 8693 delegation per run, bounded by live scopes + 365-day cap. Memory holds **structured non-PHI personalization only**; all surfaces server-generated via existing primitives (no new types). In-app delivery only; everything audited.
- 016-persistent-login: Added 365-day persistent login on web + Flutter wrapper. Frontend `oidc-client-ts` `userStore` swapped to localStorage via `SafeWebStorageStateStore`; new `frontend/src/auth/` module enforces 365-day hard cap (client-side anchor `astralbody.persistentLogin.v1`), user-switch revocation, offline-tolerant sign-out queue (`astralbody.revocationQueue.v1` in sessionStorage). Three new audit `action_type` values (`auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed`) under existing `event_class="auth"`; new `POST /api/audit/session-resume-failed` REST endpoint for the offline-fallback audit path. `RegisterUI` dataclass gained optional `resumed: bool = False`. **No new dependencies**, no DB schema change, no Flutter code change. Operator setting: Keycloak realm Offline Session Idle/Max ≥ 365 days — see [docs/keycloak-persistent-login-realm-settings.md](docs/keycloak-persistent-login-realm-settings.md).


<!-- MANUAL ADDITIONS START -->
## UI delivery (feature 026)

The UI is **server-driven from the backend** — there is no separate React/Vite frontend.
- **Primitives** are defined by the first-party pip package **`astralprims`** (`pip install astralprims`). Build UI with its classes (`Text`, `Card`, `Table`, …) and serialize with **`.to_dict()`** (NOT `.to_json()`, which returns a string) or `create_ui_response([...])`. The base styling field is **`css`** (not `style`).
- The **orchestrator renders** those primitive dicts to web HTML in `backend/webrender/` (pure-Python render functions, escape-by-default via `esc()`); **ROTE** (`backend/rote/`) adapts per device. New client targets register a renderer via `webrender.register_target(...)` — no change to astralprims or agent code.
- The orchestrator serves the shell + static assets on **`:8001`** (`GET /`, `/static/*`); server-side OIDC at `/auth/{login,callback,session,logout}` (`backend/orchestrator/web_auth.py`). No `:5173` static server.
- Per Constitution II (v2.0.1): **astralprims defines → orchestrator renders → ROTE adapts.**

## Chrome + agentic creation (feature 027)

- **App chrome** (top bar, static settings menu, modal surfaces) is server-rendered HTML in `backend/webrender/chrome/` — NOT astralprims primitives, and it never enters ROTE. The shell injects the role-gated top bar at `GET /` (`%%ASTRAL_TOPBAR%%`); surfaces are pushed over WS as `chrome_render {region, html}`. Surface modules in `webrender/chrome/surfaces/` export `TITLE`, `async render(orch, user_id, roles, params)` and a `HANDLERS` dict; `backend/orchestrator/chrome_events.py` dispatches all `chrome_*`/draft-decision `ui_event` actions (unmatched legacy actions still log a warning).
- **Agentic creation**: orchestrator meta-tools `create_capability`/`extend_agent` (pseudo-agent `__orchestrator__`, defined in `backend/orchestrator/agentic_creation.py`) are injected into chat tool lists when `FF_AGENTIC_CREATION` is on (default). Gap → auto-create draft (012 lifecycle) → VirtualWebSocket self-test → approve/refine/discard cards; live-agent revisions re-pass the security gate with backup/rollback. Provenance columns on `draft_agents`: `origin`, `source_chat_id`, `gap_fingerprint`, `revises_agent_id`, `self_test`.
- Audit event class `agent_lifecycle` covers the creation lifecycle; admin gating is server-side (`web_auth.session_roles` for shell render, JWT roles per handler).
<!-- MANUAL ADDITIONS END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
- [specs/001-tool-stream-ui/plan.md](specs/001-tool-stream-ui/plan.md)
- [specs/002-file-uploads/plan.md](specs/002-file-uploads/plan.md)
- [specs/003-agent-audit-log/plan.md](specs/003-agent-audit-log/plan.md)
- [specs/004-component-feedback-loop/plan.md](specs/004-component-feedback-loop/plan.md)
- [specs/005-tooltips-tutorial/plan.md](specs/005-tooltips-tutorial/plan.md)
- [specs/006-user-llm-config/plan.md](specs/006-user-llm-config/plan.md)
- [specs/007-sidebar-settings-menu/plan.md](specs/007-sidebar-settings-menu/plan.md)
- [specs/008-llm-text-only-chat/plan.md](specs/008-llm-text-only-chat/plan.md)
- [specs/010-fix-page-flash/plan.md](specs/010-fix-page-flash/plan.md)
- [specs/011-nsf-grant-agent/plan.md](specs/011-nsf-grant-agent/plan.md)
- [specs/012-fix-agent-flows/plan.md](specs/012-fix-agent-flows/plan.md)
- [specs/013-agent-visibility-tool-picker/plan.md](specs/013-agent-visibility-tool-picker/plan.md)
- [specs/014-progress-notifications/plan.md](specs/014-progress-notifications/plan.md)
- [specs/016-persistent-login/plan.md](specs/016-persistent-login/plan.md)
- [specs/025-agentic-soul-integration/plan.md](specs/025-agentic-soul-integration/plan.md)
- [specs/026-frontend-removal-astralprims/plan.md](specs/026-frontend-removal-astralprims/plan.md)
- [specs/027-agentic-creation-settings/plan.md](specs/027-agentic-creation-settings/plan.md)
<!-- SPECKIT END -->
