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
- Python 3.11+ (backend); ES5-compatible vanilla JavaScript + CSS maintained by the orchestrator render layer (`backend/webrender/static/`, no build step) + Existing only — FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client used by `_call_llm` (resolved through the feature-006 `llm_config.client_factory`), `shared.external_http` (egress-gated HTTP), astralprims v0.1.0 (consumed unchanged). **Zero new runtime dependencies** (Constitution V). CI-only tooling: ruff, pytest-cov, diff-cover, gitleaks action (Constitution XI carve-out, documented in PR). (029-agents-adaptive-ui-ci)
- PostgreSQL via `shared/database.py::_init_db()` idempotent startup migrations. Deltas: new `workspace_layout` table; additive `workspace_snapshot.layouts` column; one-time guarded agent-id/tool-name remap (classify/forecaster/llm_factory → ml_services); cleanup of permission rows for the six removed agent ids. Rollback documented in [data-model.md](data-model.md). (029-agents-adaptive-ui-ci)
- Python 3.11+ (production image) / 3.13 (local `.venv`) + FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client (`_call_llm` via `llm_config.client_factory`), `cryptography` (Fernet, offline grants), `python-jose` (JWT), astralprims ≥0.2.0 (defines primitives), `shared.external_http`. PHI gate uses already-approved presidio/spacy/tzdata. **No new third-party runtime libraries.** (030-finish-soul-integration)
- PostgreSQL via `shared/database.py::_init_db()` idempotent, guarded startup migrations. Existing tables reused: `scheduled_job`, `job_run`, `user_offline_grant`, `memory_item`, `short_term_signal`, `user_personalization`, `consolidation_sweep`. No new tables anticipated; any column addition (if needed for notification persistence) ships as an idempotent `_init_db` delta. (030-finish-soul-integration)

- Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend) (002-file-uploads)

## Project Structure

```text
backend/
frontend/
tests/
```

## Commands

Everything runs in the `astralbody` container (no host venv; backend needs py3.11):

```bash
docker compose up -d                                   # postgres + astralbody
docker cp <file> astralbody:/app/<repo-rel-path>       # sync one edit (source is baked)
docker exec astralbody bash -c "cd /app/backend && python -m pytest -q"   # full suite
docker exec astralbody bash -c "cd /app/backend && python -m ruff check ."  # lint (repo-wide clean)
```

Dev posture: `.env` must have `ASTRAL_ENV=development` (unset == production fail-closed). Production: see [docs/production-deployment.md](docs/production-deployment.md) — runtime-only secrets (never baked into the image), TLS proxy with `FORWARDED_ALLOW_IPS`, `/healthz`+`/readyz` probes, boot gate refuses missing/placeholder secrets.

## Code Style

Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend): Follow standard conventions

## Recent Changes
- 030-finish-soul-integration: Added Python 3.11+ (production image) / 3.13 (local `.venv`) + FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client (`_call_llm` via `llm_config.client_factory`), `cryptography` (Fernet, offline grants), `python-jose` (JWT), astralprims ≥0.2.0 (defines primitives), `shared.external_http`. PHI gate uses already-approved presidio/spacy/tzdata. **No new third-party runtime libraries.**
- 029-agents-adaptive-ui-ci: Added Python 3.11+ (backend); ES5-compatible vanilla JavaScript + CSS maintained by the orchestrator render layer (`backend/webrender/static/`, no build step) + Existing only — FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client used by `_call_llm` (resolved through the feature-006 `llm_config.client_factory`), `shared.external_http` (egress-gated HTTP), astralprims v0.1.0 (consumed unchanged). **Zero new runtime dependencies** (Constitution V). CI-only tooling: ruff, pytest-cov, diff-cover, gitleaks action (Constitution XI carve-out, documented in PR).
- 028-workspace-auth-revival: Added Python 3.11+ (backend); vanilla ES5-compatible JavaScript maintained by the orchestrator render layer (`backend/webrender/static/client.js`, no build step) + Existing only — FastAPI, websockets, `python-jose` (JWT), `cryptography` (Fernet, already used by `offline_grant.py`), httpx/requests (existing Keycloak calls), astralprims (first-party, consumed unchanged per spec A9). **No new third-party libraries** (Constitution V).


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

## Auth lifecycle + persistent workspace (feature 028)

- **Auth gate**: `GET /` redirects unauthenticated visitors straight to Keycloak via `/auth/login?next=…` (no in-app login screen; `/auth/login` pre-flights the IdP and serves a bounded 503 retry page when unreachable). Entry is role-gated at the callback: a token with neither `user` nor `admin` role gets a 403 no-access page, no session, refresh token revoked. Sessions are durable (`web_session` table, Fernet-encrypted, `backend/orchestrator/session_store.py`) and renew silently server-side (`web_auth.ensure_session`); refresh never extends the 365-day interactive anchor (016); `/auth/session` reports `reason:'hard_cap'` at the cap and one-shot `resumed` semantics (shell injects `__ASTRAL_RESUMED__`, client echoes it into `register_ui`). WS auth failure now sends `auth_required` (client refetches `/auth/session`, then redirects). Logout revokes the Keycloak refresh token (offline-tolerant `auth_revocation_queue`) AND feature-025 offline grants. **Fail-closed posture**: `ASTRAL_ENV` unset == production — mock auth refuses to boot and agent registrations without a valid `AGENT_API_KEY` are refused (additive `RegisterAgent.api_key`, enforced in `Orchestrator.register_agent`; `BaseA2AAgent` sends it from env); set `ASTRAL_ENV=development` for local dev. Operator realm settings: [docs/keycloak-realm-settings.md](docs/keycloak-realm-settings.md).
- **Persistent workspace**: every rich component output auto-upserts into the per-chat workspace (`saved_components` + `component_id`/`position`/`updated_at`; `backend/orchestrator/workspace.py`). Identity = author `Primitive.id` → `wc_<sha1(agent|tool|params)>` fingerprint → single-source supersede (fingerprint-derived identities only — an explicit/echoed id never supersedes a different identity; new explicit ids append). REST component verbs (save/delete/combine/condense) write through `WorkspaceManager` like their WS twins; chat deletion ends any open historical view on other tabs. Wire: additive `ui_upsert {chat_id, ops:[{op, component_id, component, html}]}`, fanned out to all of the user's sockets on that chat with per-socket ROTE adaptation; full canvas `ui_render`s wrap components in `<div class="astral-component" data-component-id=…>`. `load_chat` re-hydrates the workspace and adds server-rendered `html` to component-bearing transcript messages. Per-turn `workspace_snapshot` rows power the read-only timeline chrome surface (`webrender/chrome/surfaces/workspace_timeline.py`; `workspace_timeline_mode` WS flag; mutations refused while viewing history). `component_action` ui_event re-executes a component's source tool with the chat path's permission gates and updates it in place (`table_paginate` now routes through it). Audit: `workspace.component_added/updated/removed`, `workspace.action_denied`, `workspace.timeline_viewed` (class `conversation`); `auth.logout`, `auth.token_refresh_failed` (class `auth`).

## Agent catalog, adaptive UI designer & CI (feature 029)

- **Catalog**: email_tracker, grant_budgets, grants, linkedin, nefarious, nocodb agents REMOVED (their LinkedIn OAuth REST flow in `api.py` removed too; qual_audit poisoning tests use a local malicious fixture now). classify + forecaster + llm_factory MERGED into `backend/agents/ml_services/` (agent id `ml-services-1`, shared `_wrapper.py` foundation; the 5 colliding verbs are service-prefixed: `classify_submit_dataset`, `forecaster_get_results`, …). Idempotent boot migrations in `_init_db()` (`_migrate_agent_catalog_029`) remap ownership/scopes/overrides/credentials/chats to `ml-services-1` (scopes OR-merge, overrides AND-merge, verb prefix rewrite) and delete permission/credential rows for the six retired ids. `BaseA2AAgent` gained `predecessor_agent_ids` → fallback ECIES keys so pre-merge E2E credentials still decrypt. Old-transcript `component_action`s: merged sources transparently reroute (`orchestrator.remap_merged_source`), retired sources get an audited retirement Alert (`RETIRED_AGENT_IDS`).
- **New plug-and-play agents**: `web_research` (`web-research-1`: web_search — keyless DuckDuckGo HTML parse or optional Tavily-compatible `SEARCH_API_URL`/`SEARCH_API_KEY` bundle; fetch_page — egress-gated 1 MB/15 s; research_brief — cited multi-component brief, never fabricates sources) and `summarizer` (`summarizer-1`: summarize_text/summarize_url/compare_documents, 24k-char cap with truncation notice, TL;DR/Key points/Quotes Tabs). Zero new dependencies; all HTTP via `shared.external_http`.
- **Adaptive UI designer** (`backend/orchestrator/ui_designer.py`, flag `FF_UI_DESIGNER` default on, budget `UI_DESIGNER_TIMEOUT_SECONDS` default 8 s PER PASS × `UI_DESIGNER_MAX_ROUNDS` default 3): rounds with ≥2 rich components get a bounded multi-round LLM conversation — pass 1 drafts an arrangement (layout tree of existing astralprims types whose leaves are `{"type":"ref","component_id":…}` references), later passes show the model its own current arrangement (structural sketch + JSON) and ask it to critique/improve or reply `DONE`; identical refinement = converged (`outcome=stable`), failed refinement keeps best-so-far, refinements must themselves reference every placed component — round AND canvas refs; omission repair runs only on draft passes (`outcome=rejected:incomplete` otherwise), unusable draft JSON gets format-retries with the failure fed back (pass-1 refusal/timeout/LLM-error falls back exactly like the legacy single pass). Tool output is NEVER rewritten; garnish components carry deterministic `dg_*` ids stamped once on the final arrangement. Layouts persist in the new `workspace_layout` table (overlay model — components keep their `saved_components` rows/identities; later layouts steal claimed refs; component removal prunes refs); `workspace_snapshot.layouts` captures designed state for the timeline. Delivery: components upsert first (identities assigned), then `_deliver_round_components` designs and pushes a full materialized-canvas `ui_render` (`_canvas_components` materializes refs PRE-ROTE; nested refs get `attributes["data-component-id"]` morph anchors — zero client changes); ANY designer failure falls back to the legacy `ui_upsert` flat append (fail-open, logged as `ui_designer.fallback{reason}`). Validators derive their palette from `webrender.allowed_primitive_types()` (the renderer registry — 31 types since the dashboard primitives) instead of hand-copied subsets. **Dashboard primitives** `badge`/`hero`/`keyvalue`/`timeline`/`rating`: classes in astralprims 0.2.0 (Astral-Primitives repo; publish = push main, version-gated), renderers in `webrender/renderer.py`, styles in `astral.css`, voice extraction in `rote/adapter.py`; agents may emit them as plain dicts until the 0.2.0 wheel is in the image (`requirements.txt` floats `>=0.1.0`). The connectors agent's `interactive_artifacts`/`claude_design` tools now emit REAL widgets (hero + metric/chart/table/timeline/keyvalue with sample data, extended input schema for caller-supplied series) instead of placeholder spec cards. FR-027: the constant "Analysis"/"Summary" cards are gone — `_chat_narrative` renders short answers as bare markdown and titles long ones from their own first heading.
- **CI** (`.github/workflows/ci.yml`): lint (ruff from repo root) / build (image artifact, GHA cache) / test (both pytest invocations INSIDE the built image vs postgres:17-alpine service, coverage.xml) / coverage-gate (diff-cover ≥90% on changed lines vs origin/main) / smoke (healthz+readyz dev boot; production-posture boot must exit EXACTLY 78 — run via `--entrypoint python orchestrator/orchestrator.py` because start.py supervises and would exit 0) / secret-scan (gitleaks + `.gitleaks.toml` allowlist) / publish (main only → ghcr.io `sha-<commit>` + `latest`). Deployment to https://sandbox.ai.uky.edu (Keycloak https://iam.ai.uky.edu) documented in docs/production-deployment.md (GHCR pull path). Constitution v2.1.0 added Principle XI codifying these gates.
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
- [specs/031-attachment-upload-parsing/plan.md](specs/031-attachment-upload-parsing/plan.md)
<!-- SPECKIT END -->
