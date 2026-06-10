# Implementation Plan: Persistent SDUI Workspace & Revived Keycloak Authentication

**Branch**: `028-workspace-auth-revival` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/028-workspace-auth-revival/spec.md`

## Summary

Two co-equal parts. **Part A** puts a real authentication gate in front of the app: unauthenticated `GET /` redirects straight to Keycloak via the existing 026 server-side OIDC flow (`backend/orchestrator/web_auth.py`), sessions renew silently server-side using the stored refresh token (today it is stored and never used), the session store moves from a process-memory dict to a Postgres-backed durable store with the 016 365-day interactive-login anchor, sign-out revokes the refresh token at Keycloak and revokes feature-025 offline grants, and production boots fail closed (mock auth and keyless agent connections refused outside explicit dev mode). **Part B** makes the canvas a persistent per-chat workspace: the `saved_components` table becomes the workspace store keyed by a stable `component_id`, the orchestrator emits additive `ui_upsert` messages carrying per-component HTML fragments + structured dicts, the thin client morphs by `data-component-id` (generalizing the proven `mergeStream` pattern), `load_chat` re-hydrates the full workspace and renders component-bearing history messages, per-turn `workspace_snapshot` rows power a read-only timeline chrome surface, and a standardized `component_action` ui_event generalizes `table_paginate` into a permission-gated deterministic re-execution path with cross-component targets and per-user multi-socket broadcast.

## Technical Context

**Language/Version**: Python 3.11+ (backend); vanilla ES5-compatible JavaScript maintained by the orchestrator render layer (`backend/webrender/static/client.js`, no build step)
**Primary Dependencies**: Existing only — FastAPI, websockets, `python-jose` (JWT), `cryptography` (Fernet, already used by `offline_grant.py`), httpx/requests (existing Keycloak calls), astralprims (first-party, consumed unchanged per spec A9). **No new third-party libraries** (Constitution V).
**Storage**: PostgreSQL via existing `shared/database.py` `_init_db()` idempotent migrations. Deltas: new `web_session` table; new `workspace_snapshot` table; new columns on `saved_components` (`component_id`, `position`, `updated_at`); new `auth_revocation_queue` table for offline-tolerant revocation. Rollback documented in [data-model.md](data-model.md).
**Testing**: pytest (backend unit + integration, ≥90% changed-code coverage per Constitution III); golden/structural renderer tests (026 pattern); real-browser evidence gate with screenshots under `evidence/` (026/027 pattern).
**Target Platform**: Linux server container (`:8001` orchestrator) + evergreen browsers; external Keycloak realm (`KEYCLOAK_AUTHORITY`).
**Project Type**: Web service with server-driven UI (backend-only repo; client assets emitted by the render layer).
**Performance Goals**: In-place component update applied <1 s after arrival (SC-007); deterministic component refresh round-trip <2 s typical (SC-010); cross-device propagation <2 s (SC-012); zero auth interruptions across the 016 resume matrix (SC-002).
**Constraints**: Additive WS wire contract only (026 FR-018); chrome never enters ROTE (027); escape-by-default HTML (026 FR-017); no SPA, no new deps; idempotent auto-migrations; fail-closed production posture.
**Scale/Scope**: Single-org deployment, dozens of concurrent users, chats with up to hundreds of turns (timeline must stay bounded); multi-instance backend deployments must work (durable sessions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — PASS.*

| Principle | Status | Notes |
|---|---|---|
| I. Primary Language | PASS | All backend work in Python; client delta confined to the render layer's emitted `client.js`. |
| II. UI Delivery Architecture | PASS | Workspace content stays astralprims → orchestrator render → ROTE. New `ui_upsert` carries structured dicts + web-rendered fragments; non-web targets consume the structured layer. Timeline control + workspace banner are chrome (`webrender/chrome/`), never entering ROTE. No SPA. |
| III. Testing Standards | PASS | pytest for web_auth lifecycle, workspace store, snapshots, component_action gates; renderer structural tests; ≥90% changed-code coverage. |
| IV. Code Quality | PASS | ruff for Python; emitted JS kept lint-clean (JSDoc on new exports). |
| V. Dependency Management | PASS | Zero new third-party dependencies. Fernet/jose/httpx already in the tree. |
| VI. Documentation | PASS | Docstrings on new modules; `docs/keycloak-realm-settings.md` recreated (FR-017); contracts documented under `contracts/`. |
| VII. Security | PASS | Keycloak remains sole IdP; gate enforced server-side; component_action enforces the same scope/tool permission stack as chat; RFC 8693 delegation untouched; secrets out of VCS (and the leaked secret in `docs/keycloak_agent_delegation_setup.md` is scrubbed as part of this feature). |
| VIII. User Experience | PASS | No new primitive types expected (spec A9); existing `Primitive.id` field reused as the author-supplied identity override. |
| IX. Database Migrations | PASS | All deltas are idempotent `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` inside `_init_db()` (house pattern per 013/027); rollback documented in data-model.md. |
| X. Production Readiness | PASS | Fail-closed startup checks are themselves part of the feature; observability via audit events + structured logs; real-browser gate before completion. |

No constitutional violations — Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/028-workspace-auth-revival/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 — decisions D1–D18
├── data-model.md        # Phase 1 — schema deltas + entities + rollback
├── quickstart.md        # Phase 1 — dev setup + manual verification walkthrough
├── contracts/
│   ├── auth-session.md          # Shell gate, refresh, logout/revocation, fail-closed boot
│   ├── ws-workspace-protocol.md # ui_upsert / re-hydration / timeline WS messages
│   └── component-action.md      # Standardized component_action ui_event contract
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── web_auth.py            # MODIFIED HEAVILY: durable sessions, silent refresh, next-URL, logout revocation
│   ├── session_store.py       # NEW: Postgres-backed web_session store + revocation queue worker
│   ├── orchestrator.py        # MODIFIED: shell gate, auth_required WS path, workspace engine wiring,
│   │                          #   component_action handler, multi-socket broadcast, ROTE re-adapt from state
│   ├── workspace.py           # NEW: WorkspaceManager — upsert/identity/snapshots/timeline reads
│   ├── history.py             # MODIFIED: workspace-aware component methods; get_chat keeps shape
│   ├── chrome_events.py       # MODIFIED: timeline surface handlers (chrome_workspace_timeline_*)
│   ├── auth.py                # MODIFIED: fail-closed agent key check; (mock gate at startup)
│   ├── offline_grant.py       # unchanged (revoke_for_user called from logout)
│   └── delegation.py          # unchanged
├── webrender/
│   ├── renderer.py            # MODIFIED: data-component-id wrapper for top-level components
│   ├── chrome/surfaces/workspace_timeline.py   # NEW chrome surface (TITLE/render/HANDLERS)
│   ├── chrome/topbar.py       # MODIFIED: timeline entry point (per-chat)
│   ├── static/client.js       # MODIFIED: ui_upsert morph, timeline mode, auth_required redirect,
│   │                          #   /auth/session refresh-before-reconnect, history message html
│   └── templates/shell.html   # MODIFIED: (minimal) workspace container attrs
├── shared/
│   ├── database.py            # MODIFIED: _init_db() idempotent deltas (web_session, workspace_snapshot,
│   │                          #   saved_components columns, auth_revocation_queue)
│   └── protocol.py            # MODIFIED: additive UIUpsert / AuthRequired dataclasses
├── rote/rote.py               # MODIFIED: re-adapt sources from server workspace state (not _last_components)
├── audit/hooks.py             # MODIFIED: workspace + logout action types
└── tests/
    ├── test_auth_gate.py              # NEW
    ├── test_session_store_refresh.py  # NEW
    ├── test_logout_revocation.py      # NEW
    ├── test_fail_closed_boot.py       # NEW
    ├── test_workspace_manager.py      # NEW
    ├── test_workspace_snapshots.py    # NEW
    ├── test_component_action.py       # NEW
    ├── test_ui_upsert_render.py       # NEW (renderer wrapper + fragment golden tests)
    └── test_rehydration.py            # NEW

docs/
├── keycloak-realm-settings.md         # NEW (FR-017; replaces never-committed doc, CLAUDE.md ref fixed)
└── keycloak_agent_delegation_setup.md # MODIFIED: scrub leaked client secret
```

**Structure Decision**: Single backend project (established repo layout). Part A concentrates in `orchestrator/web_auth.py` + new `session_store.py`; Part B introduces one new module (`orchestrator/workspace.py`) and threads it through the existing send/render paths rather than scattering workspace logic across `orchestrator.py`. Client changes stay inside the render layer's emitted assets per Constitution II.

## Phase 1 highlights

- **Session durability + refresh (D2/D3)**: `web_session` rows hold Fernet-encrypted access/refresh tokens, the 365-day interactive anchor, and rotation metadata. `session_token()` becomes refresh-aware: if the access token is within 60 s of expiry it refreshes at Keycloak (`grant_type=refresh_token`), rotates stored tokens, and never moves the anchor. The in-memory dict becomes a read-through cache over the table.
- **Shell gate (D1)**: `serve_shell` 302s to `/auth/login?next=<relpath>` when no valid session exists; `next` is validated as a same-origin relative path (open-redirect guard) and carried through the OIDC `state`.
- **WS recovery (D4)**: on token-validation failure the server sends an additive `auth_required` message; the client re-fetches `/auth/session` (which silently refreshes) and re-registers, falling back to a full redirect to `/auth/login?next=…` only when the session is truly gone. The dead-end alert is removed.
- **Workspace identity (D11)**: `component_id` = author-supplied `Primitive.id` if present, else orchestrator fingerprint `wc_<sha1(agent|tool|canonical-params)[:16]>`. The LLM system prompt's canvas block lists live `component_id`s and instructs reuse-for-update; deterministic actions always target an explicit id.
- **Wire protocol (D12)**: additive `ui_upsert {chat_id, ops:[{op:'upsert'|'remove', component_id, component, html}]}`; full `ui_render` remains for re-hydration/timeline/device-change, now rendering the *whole* workspace from server state. `webrender.render()` wraps each top-level component in `<div class="astral-component" data-component-id="…">`.
- **Timeline (D14)**: `workspace_snapshot` written per assistant turn + per component-action mutation; timeline is a chrome surface listing turns; viewing pushes a full historical `ui_render` + chrome banner; client `timelineMode` defers live canvas applications and surfaces a "live has moved on" notice; "back to live" re-renders from live state.
- **Interaction loop (D15)**: `component_action` resolves the workspace row's provenance, re-checks the *current* chat-path permission stack (scope + tool_overrides + security flags), executes, upserts (originating or `target_component_id`), snapshots, broadcasts. `table_paginate` is re-expressed on this path; `param_picker` stays the intent idiom.
- **Multi-device (D16)**: broadcast `ui_upsert` to every socket of the user whose `_ws_active_chat` equals the chat, adapting per socket via ROTE before fragment rendering; ROTE's `_last_components` single-slot cache is replaced by reads of the server workspace state (D17).

## Complexity Tracking

No constitutional violations to justify.
