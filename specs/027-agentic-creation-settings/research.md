# Phase 0 Research: Agentic Creation & Top-Bar Settings Menu

All decisions below are grounded in a symbol-level survey of the codebase (5 research passes:
lifecycle, chat-loop, settings data sources, webrender/client seams, cross-cutting infra).

## D1 — Capability-gap detection: orchestrator meta-tools, not output parsing

**Decision**: Inject orchestrator-internal "meta-tools" into the LLM tool list (`tools_desc`)
built in `handle_chat_message` (orchestrator.py:2290–2426): `create_capability(name, description,
tools_spec)` and `extend_agent(agent_id, instruction)`. They map to the reserved pseudo-agent id
`__orchestrator__` in `tool_to_agent`; `execute_single_tool` / `execute_parallel_tools` intercept
that id before the agent-existence gate (orchestrator.py:3765) and route to a new
`backend/orchestrator/agentic_creation.py` handler. The system prompt instructs the LLM to call
`create_capability` only when no offered tool can serve the request (and to point at
disabled/unauthorized capability instead — FR-008; the prompt lists disabled-tool names the
diagnostic gate already computes).

**Rationale**: The Re-Act loop already routes everything through tool calls; a meta-tool makes
gap detection a first-class, auditable decision by the same LLM that knows what tools were
offered — no fragile parsing of refusal text. The dispatch seam (7-gate `execute_single_tool`)
has a natural interception point.

**Alternatives considered**: (a) Post-hoc classification of "final response" text for
inability-phrases — brittle, no structured args, double LLM cost. (b) A separate
gap-detection LLM pass per turn — latency + cost on every message. Rejected.

## D2 — Auto-create + self-test reuses the 012 lifecycle verbatim

**Decision**: `create_capability` executes: dedup check (D8 fingerprint) → `db.create_draft_agent`
(origin `auto_chat`) → `AgentLifecycleManager.generate_code(draft_id)` (existing: template files +
LLM `mcp_tools.py` + syntax check + `CodeSecurityAnalyzer` + `AgentSpecValidator` with auto-fix
retries) → `start_draft_agent(draft_id)` → **self-test**: run the user's originating request as a
draft-test chat turn through `handle_chat_message(vws, original_request, test_chat_id,
draft_agent_id=draft_id)` on a `VirtualWebSocket` via `BackgroundTaskManager` (async_tasks.py:56–215),
bounded by a hard timeout and at most one auto-refine retry (A11). Outcome (tools called, result
summary or failure) is stored in `draft_agents.self_test` and presented in chat as a server-rendered
card with `approve / refine / discard` buttons (`ui_event` actions backed by the existing
`approve_agent` / `refine_agent` / `delete_draft`).

**Rationale**: Every stage already exists and is battle-tested (generate/test/refine/approve,
security gates, ownership rows, dashboard broadcast on promotion). `VirtualWebSocket.client`
returns `('background', task_id)` so the self-test is audit-attributable. FR-003's "no second
lifecycle" falls out for free.

**Alternatives considered**: directly invoking the draft's tool functions in-process for the
self-test — bypasses scope/credential gates and the MCP boundary, diverges from what the user
will actually experience. Rejected.

## D3 — Live-agent tool addition = revision draft + gated swap

**Decision**: `extend_agent(agent_id, instruction)` (owner-verified) clones the live agent's
directory to `agents/{slug}__rev{n}/`, creates a draft row (origin `revision`,
`revises_agent_id`), applies `refine_tools_file` with the instruction, and self-tests the clone
as a normal draft on its own port. On user approval, the swap path: stop live agent → back up its
`mcp_tools.py` → install the revised file → re-run the full approval gate (security analyzer +
compile + validator) against the live directory → restart. Any gate failure restores the backup
and restarts the original — the live agent is never left changed by a failed revision
(spec FR-006, edge case "live agent modified while in use"). The rev clone is deleted after
apply/discard.

**Rationale**: `auto_fix_tool_error` proves stop→edit→restart works mechanically but explicitly
refuses LIVE agents (agent_lifecycle.py:766–779) precisely because there's no gate — the
revision-draft flow adds the missing approval + re-gate. Cloning to a sibling slug lets ALL
existing draft machinery (start on a port, draft-test chat, refine) work unmodified.

**Alternatives considered**: in-place edit with checks-before-restart (no isolated self-test
possible; failure window while live code is replaced) — rejected. Versioned agent directories
with symlink flips — overkill, Windows-hostile. Rejected.

## D4 — Chrome lives in `backend/webrender/chrome/` as pure-Python HTML render functions

**Decision**: App chrome (top bar, settings menu, modal surfaces) is NOT expressed as astralprims
primitives. It is a set of pure-Python render functions (same `esc()` escape-by-default pattern as
`renderer.py`) under `backend/webrender/chrome/`. Canvas/chat *content* continues to flow
astralprims → ROTE → `render_for_target`. Chrome render functions MAY embed rendered primitives
(via `render_one`) inside a surface (e.g., color pickers in the Theme surface).

**Rationale**: Constitution II assigns rendering to the orchestrator; astralprims stays a
general-purpose primitive library (the chrome spec's recorded recommendation). ROTE's adapter
passes unknown types through untouched (adapter.py:78), so routing chrome through
ROTE would add nothing; chrome is web-target-specific by definition.

**Alternatives considered**: new astralprims chrome primitives (`Sidebar`, `Modal`) — bloats the
shared package with app-specific UI and requires a package release per chrome tweak. Rejected.

## D5 — Top bar + menu render statically into the shell; surfaces push over WS

**Decision**: `GET /` renders the top bar **and the full settings menu** into `shell.html`
server-side at request time, role-gated from the server session (admin group included only when
the session's roles contain `admin` — mock auth path included). Menu open/close, keyboard
navigation, Escape/outside-click are client-local (client.js; no round trip — FR-017).
Selecting an entry sends `ui_event {action: "chrome_open", payload: {surface}}`; the orchestrator
renders the surface and pushes a new additive WS message `chrome_render {region: "modal", html,
mode: "replace"}`; `chrome_close` (or client-local Escape/backdrop) clears the modal root.
Surface-internal actions (save permissions, run LLM test, pause job, …) are `ui_event` actions
handled by a new dispatcher module `backend/orchestrator/chrome_events.py` (single hook line in
`handle_ui_message`'s dispatch chain) that calls the same service/DB functions the existing REST
endpoints use, then re-pushes the re-rendered surface with a success/error notice.

**Rationale**: "Static settings menu" (spec A2) = always present, zero-latency open. Server-side
role gating at render time satisfies FR-014's DOM-absence requirement verifiably. One new WS
message type keeps the 026 protocol additive (FR-018 untouched). A separate dispatcher module
avoids growing orchestrator.py's 1,700-line if/elif chain and keeps 027 testable in isolation.

**Alternatives considered**: menu rendered per-open via WS round trip — adds latency to the most
common interaction and contradicts "static". REST-driven surfaces with client-side fetch+render —
would require a client-side templating layer, recreating the SPA we removed. Rejected.

## D6 — Settings surfaces map 1:1 onto existing backends (no new domain logic)

Verified data sources (all existing):

| Surface | Source |
|---|---|
| Agents & permissions | `GET /api/agents` internals; `GET/PUT /api/agents/{id}/permissions` (per_tool_permissions `{tool: {permission_kind: bool}}`); `PUT .../visibility`; credentials CRUD (api.py:479–963); per-user agent-enabled (api.py:796) |
| Drafts (create/resume/approve/delete) | draft_router endpoints api.py:1306–1631 + lifecycle manager |
| LLM settings | `POST /api/llm/test`, `POST /api/llm/list-models` (llm_config/api.py:137–306), WS `llm_config_set/clear` (session-scoped creds) |
| Personalization | `GET/PUT/DELETE /api/personalization/profile`; memory list/update/delete; `GET/PUT /api/skills`; scheduler CRUD + pause/resume; dreaming get/enable/disable/trigger |
| Audit log | `GET /api/audit` (cursor pagination, event_class/outcome/q filters), `GET /api/audit/{id}` |
| Theme | WS `save_theme` → `user_preferences.theme`; `user_preferences` frame on connect; client `applyTheme` |
| Tour | `GET /api/tutorial/steps` (target_kind static/sdui/none), onboarding state/replay/dismiss endpoints |
| User guide | former React `UserGuidePanel.tsx` content is frontend-static → port content into `chrome/guide_content.py` |
| Tutorial admin | `/api/admin/tutorial/steps` CRUD + archive/restore + revisions (admin-gated) |
| Tool quality admin | feedback admin router (`backend/feedback/api.py` admin section: quality signals / proposals / quarantine; exact endpoints read during implementation) |
| Sign out | `GET/POST /auth/logout` (web_auth.py:186–206) + `OfflineGrantManager.revoke_for_user`; 016 offline queue is client-side (sessionStorage revocation queue semantics) |

Chrome event handlers call these **internally** (services/DB), not over HTTP.

## D7 — Tour without full chrome: skip-unresolvable-targets step runner

**Decision**: The tour is a client-run step sequence fetched from `GET /api/tutorial/steps`
(rendered server-side into a tour payload at `chrome_open {surface: "tour"}`). For each step,
client.js highlights `[data-tour-target="<target_key>"]` if present (top bar, menu entries, chat
input, canvas carry `data-tour-target` attributes); steps whose target does not resolve render as
a centered card, and `target_kind: static` steps pointing at deferred chrome are skipped with a
"skipped (surface not yet available)" note (spec A10). Completion/replay recorded via the existing
onboarding state endpoints.

## D8 — Dedup fingerprint + schema delta on `draft_agents` (no new tables)

**Decision**: Extend `draft_agents` with idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
(the established `_init_db()` pattern, Constitution IX): `origin TEXT NOT NULL DEFAULT 'manual'`
(`manual | auto_chat | revision`), `source_chat_id TEXT`, `gap_fingerprint TEXT`,
`revises_agent_id TEXT`, `self_test TEXT` (JSON: status, summary, tools_called, evidence,
tested_at). Dedup (FR-007): before creating, look up a non-terminal draft with the same
`(user_id, source_chat_id, gap_fingerprint)`; fingerprint = normalized hash of the meta-tool's
requested capability name + tool names. Partial index on those columns.

**Rationale**: A gap proposal that the user acts on IS a draft — a separate `capability_gap`
table would duplicate draft state and create sync bugs. Discard = existing `delete_draft`.

## D9 — Audit: one new event_class `agent_lifecycle`; settings reuse existing classes

**Decision**: Append `agent_lifecycle` to `EVENT_CLASSES` (audit/schemas.py:30–60) with
action_types `lifecycle.gap_detected`, `lifecycle.auto_created`, `lifecycle.self_test`,
`lifecycle.refined`, `lifecycle.approved`, `lifecycle.rejected`, `lifecycle.discarded`,
`lifecycle.revision_applied`, `lifecycle.revision_rolled_back` — recorded via the process-wide
`get_recorder()` with one `correlation_id` per gap (in_progress → terminal pairs). Settings-menu
actions ride existing classes (`settings`, `personalization`, `memory`, `skill`, `schedule`,
`dreaming`, `audit_view`, `auth`) — the underlying endpoints/services already record most of them;
chrome handlers add the missing `settings` events (theme save already audited via save_theme path;
menu open is NOT audited — it is navigation, not an action).

## D10 — Feature flag, lint, and code-review findings disposition

- New flag `agentic_creation` (env `FF_AGENTIC_CREATION`, default **enabled**) gates meta-tool
  injection only — chrome/settings ships ungated (it is the app's only management UI).
- client.js stays build-free; ruff continues to cover Python (root `ruff.toml`, py311 target).
- Code-review findings verified during research: **render error placeholders already exist**
  (`astral-render-error` / `astral-unsupported`, renderer.py:615–622 — review's "empty string"
  claim is outdated); **theme persistence already works** (save_theme → user_preferences →
  user_preferences frame on connect); **login flow verified live** in 026 T030 (mock-auth path).
  Remaining true gaps from the review — chrome, settings surfaces, tour/tooltips/guide, generic
  event delegation — are exactly this feature's scope. The `astralprims` package concern is
  acknowledged: it is published and installed in the image (out of 027 scope).
- ROTE caching risk (chrome HTML cached per-websocket re-adapt) avoided because chrome never
  enters `ROTE.adapt` — only canvas/chat content does.
