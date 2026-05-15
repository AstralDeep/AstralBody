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
- 016-persistent-login: Added 365-day persistent login on web + Flutter wrapper. Frontend `oidc-client-ts` `userStore` swapped to localStorage via `SafeWebStorageStateStore`; new `frontend/src/auth/` module enforces 365-day hard cap (client-side anchor `astralbody.persistentLogin.v1`), user-switch revocation, offline-tolerant sign-out queue (`astralbody.revocationQueue.v1` in sessionStorage). Three new audit `action_type` values (`auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed`) under existing `event_class="auth"`; new `POST /api/audit/session-resume-failed` REST endpoint for the offline-fallback audit path. `RegisterUI` dataclass gained optional `resumed: bool = False`. **No new dependencies**, no DB schema change, no Flutter code change. Operator setting: Keycloak realm Offline Session Idle/Max ≥ 365 days — see [docs/keycloak-persistent-login-realm-settings.md](docs/keycloak-persistent-login-realm-settings.md).
- 013-agent-visibility-tool-picker: Added per-tool permissions (extending `tool_overrides` with `permission_kind`), in-chat tool picker (per-user pref under `user_preferences.tool_selection`), `chats.agent_id` for active-agent tracking, and frontend filter fix for owned-and-public agents. **No new dependencies** (Constitution V).
- 012-fix-agent-flows: Added Python 3.11+ (backend), TypeScript 5.x (frontend, Vite + React 18) + FastAPI, websockets, the existing OpenAI-compatible LLM client (`_call_llm`); React 18, Tailwind, framer-motion, sonner, the existing `fetchJson` helper. **No new dependencies** (Constitution V).
- 011-nsf-grant-agent: Added Python 3.11+ (backend; per Constitution Principle I and existing `grants` agent module). + Existing — `shared.base_agent.BaseA2AAgent`, `shared.protocol.MCPRequest/MCPResponse`, `shared.primitives` (Text, Card, Alert, Table, List_, Tabs, MetricCard), `agents.grants.mcp_server.MCPServer`, `agents.grants.mcp_tools.TOOL_REGISTRY`, `agents.grants.caai_knowledge`, the project's existing OpenAI-compatible LLM client (used by `_call_llm`). **No new third-party libraries** (Constitution Principle V).
- 010-fix-page-flash: Added TypeScript 5.x (frontend), Python 3.11+ (backend — no backend code change expected for this feature) + Vite + React 18, framer-motion, sonner, existing `fetchJson` helper in `frontend/src/api/feedback.ts`. No new dependencies.


<!-- MANUAL ADDITIONS START -->
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
<!-- SPECKIT END -->
