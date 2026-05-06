# Implementation Plan: Agent Visibility, Active-Agent Clarity, Per-Tool Permissions, and In-Chat Tool Picker

**Branch**: `013-agent-visibility-tool-picker` | **Date**: 2026-05-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-agent-visibility-tool-picker/spec.md`

## Summary

Four prioritized, independently shippable user stories that close out the "create + test an agent through the UI" and "select tools per query" stories:

1. **P1 — My Agents visibility**: every agent the user owns (draft / testing / live) appears under "My Agents." Agents the user owns AND has flagged public surface in **both** "My Agents" and "Public Agents."
2. **P2 — Active-agent clarity in chat**: the active agent's name is persistent in the chat header; agent replies are attributed to the agent that produced them; if the active agent becomes unavailable, send is blocked and a banner explains next steps.
3. **P3 — Per-tool permissions with proactive (i) info**: read/write/search/system permissions become per-tool toggles (replacing the four agent-wide scope toggles). The (i) explainer is reachable while the toggle is OFF — pre-consent. Existing scope state migrates 1:1 into per-tool ON/OFF; never widens.
4. **P3 — In-chat tool picker**: a popover affordance in the chat composer lists the agent's permission-allowed tools. Selection is persisted as a **per-user global preference** (with a "reset to default" action), narrows but never widens what the orchestrator considers, and zero-selection blocks send. Logging distinguishes "excluded by user selection" from "excluded by scope/permission."

**Technical approach**: keep the change surface narrow. Reuse existing tables (`agent_ownership`, `tool_overrides`, `user_preferences`, `chats`) and existing modules (`backend/orchestrator/tool_permissions.py`, `backend/orchestrator/orchestrator.py`, `frontend/src/components/DashboardLayout.tsx`, `frontend/src/components/FloatingChatPanel.tsx`, `frontend/src/components/AgentPermissionsModal.tsx`, `frontend/src/components/CreateAgentModal.tsx`). Only one schema additive change (a `chats.agent_id` column) plus a structural reinterpretation of `tool_overrides` (rows now carry a permission kind). No new third-party dependencies (Constitution V).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x (frontend, Vite + React 18)
**Primary Dependencies**: FastAPI, websockets, existing OpenAI-compatible LLM client (`_call_llm`); React 18, Tailwind, framer-motion, lucide-react, existing `fetchJson` helper. **No new third-party libraries** (Constitution Principle V).
**Storage**: PostgreSQL — existing tables `agent_ownership`, `agent_scopes`, `tool_overrides`, `draft_agents`, `chats`, `user_preferences`. Schema delta: add `chats.agent_id` (TEXT NULL); extend `tool_overrides` with `permission_kind` (TEXT) so a single tool can carry independent on/off per permission; add a `tool_permissions_user_pref` JSON key under existing `user_preferences.preferences` for the in-chat tool picker selection (no new table for this).
**Testing**: pytest (backend) + existing frontend test setup. Coverage gate ≥90% on changed code (Constitution Principle III).
**Target Platform**: Linux server (backend), modern evergreen browsers (frontend).
**Project Type**: Web application (existing `backend/` + `frontend/` + `tests/`).
**Performance Goals**: SC-007 — median time-to-send for an existing chat must stay within ±10% of pre-feature baseline. The tool-picker popover and per-tool permissions panel must render an agent with up to ~50 tools without UI jank.
**Constraints**: No new third-party libraries (Constitution V). All schema changes ship with auto-running migrations (Constitution IX). All UI must use existing primitive components; no new primitives without prior approval (Constitution VIII). Authentication via existing Keycloak IAM; agent runtime auth continues to use RFC 8693 attenuated scopes (Constitution VII).
**Scale/Scope**: Existing user/agent scale; no new fan-out. Per-user preference write rate is bounded by user clicks. WebSocket payload increases only by the `selected_tools` array (bounded by tools the agent has — <100).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|---|---|---|
| I. Primary Language (Python backend) | ✅ Pass | All backend changes are Python edits to `backend/orchestrator/*` and `backend/shared/database.py`. |
| II. Frontend Framework (Vite + React + TS) | ✅ Pass | All frontend edits are `.tsx` in existing components. |
| III. Testing Standards (≥90% coverage on changed code, unit + integration) | ✅ Pass (gated) | New backend logic in `tool_permissions.py` (per-tool resolution) and `orchestrator.py` (selected-tool filtering) gets unit tests + an integration test that drives a chat dispatch end-to-end with a narrowed selection. Frontend gets component tests for DashboardLayout filter, FloatingChatPanel agent header / unavailable banner / tool picker, and AgentPermissionsModal per-tool rows. CI enforces coverage. |
| IV. Code Quality (PEP 8 + ruff; ESLint) | ✅ Pass | `cd src; pytest; ruff check .` per CLAUDE.md. Frontend lints under existing ESLint config. |
| V. Dependency Management (no new third-party libs without lead approval) | ✅ Pass | Plan explicitly does not introduce new deps. The popover, modal, banner, and toggle UI are built from existing primitives (lucide-react icons, framer-motion animations, existing Switch / Card / Tabs primitives already used elsewhere). |
| VI. Documentation (docstrings + JSDoc; `/docs` for backend) | ✅ Pass | New/changed Python functions get Google-style docstrings; new TS exports get JSDoc; FastAPI route additions/changes are auto-documented via existing OpenAPI. |
| VII. Security (Keycloak IAM; RFC 8693 attenuated scopes; users MAY set scopes explicitly) | ✅ Pass | Per-tool permissions are an **additional finer layer** under the existing scope model. The runtime token attenuation pipeline is not changed; per-tool toggles act as a deny gate on top of the system-set scopes — narrows, never widens. |
| VIII. User Experience (predefined primitive components; consistent design language) | ✅ Pass | All new UI uses existing primitives — agent header reuses chat-panel header markup; banner reuses `TextOnlyBanner` patterns; tool picker reuses popover/menu patterns from existing composer; per-tool rows reuse the `Switch` primitive used in `AgentPermissionsModal`. No new primitives proposed. |
| IX. Database Migrations (auto-running migrations for any schema change) | ✅ Pass | Two schema deltas — `ALTER TABLE chats ADD COLUMN agent_id TEXT NULL;` and `ALTER TABLE tool_overrides ADD COLUMN permission_kind TEXT NULL DEFAULT NULL` — ship with idempotent migration scripts under `backend/seeds/` (or the project's existing migration framework). The 1:1 carry-forward of agent_scopes → per-tool tool_overrides rows is a data migration that runs automatically on first read, gated by an idempotent flag, with a documented down path (drop the new rows; keep `agent_scopes` in place since it is preserved alongside, not replaced, at the storage layer for safety). |
| X. Production Readiness (no stubs, golden + edge + error tests, observability, prod config, staging validation, browser-verified UI) | ✅ Pass | Plan includes the FR-023 logging extension (distinguish "excluded by user selection" vs "excluded by scope/permission"). UI work is verified in a real browser per Constitution X; backend changes are exercised in staging before merge. No dev-only flags or hard-coded URLs introduced. |

**Result**: All gates pass. No constitutional violations require justification — Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/013-agent-visibility-tool-picker/
├── spec.md              # Feature specification (already exists)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── chat-ws-message.md         # WS payload changes for selected_tools
│   ├── api-agent-permissions.md   # PUT /api/agents/{id}/permissions (per-tool)
│   ├── api-tool-selection-pref.md # GET/PUT /api/users/me/tool-selection
│   └── api-agents-listing.md      # GET /api/agents response shape (unchanged)
├── checklists/
│   └── requirements.md  # already exists
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── api.py                       # +/-: tool-selection pref endpoints; per-tool permissions endpoint shape; agents listing unchanged
│   ├── orchestrator.py              # ~lines 1815-1855: extend tool filter to honor user_selected_tools; FR-023 logging
│   ├── tool_permissions.py          # is_tool_allowed signature + storage layer extended for permission_kind on tool_overrides; new resolver get_effective_tool_permissions(user_id, agent_id) returning {tool: {permission_kind: bool}}
│   └── agent_lifecycle.py           # unchanged for promotion path; ensure live agents continue to populate agent_ownership rows
├── shared/
│   └── database.py                  # +ALTER chats.agent_id; +ALTER tool_overrides.permission_kind; +helpers get/set_chat_agent, get/set_tool_permissions, get/set_user_tool_selection_pref (preferences JSON)
└── seeds/
    └── 013_per_tool_permissions.sql # idempotent migration: chats.agent_id, tool_overrides.permission_kind, data backfill from agent_scopes

frontend/
└── src/
    ├── components/
    │   ├── DashboardLayout.tsx        # ~lines 343-426: My Agents filter widened to include drafts; Public Agents filter no longer excludes owned-public; status badges
    │   ├── FloatingChatPanel.tsx      # +Active agent header strip; +unavailable banner; +ToolPicker button in composer button cluster; +zero-selection send-disable
    │   ├── AgentPermissionsModal.tsx  # rewrite the four scope cards into a per-tool list; (i) icon reachable pre-toggle; warning dialog moves to first-enable per (tool, kind)
    │   ├── CreateAgentModal.tsx       # replace per-tool scope dropdown with a per-permission checkbox cluster per tool; submit payload sends per-tool permissions (not just scope)
    │   └── ToolPicker.tsx             # NEW small popover component built from existing primitives; lists permitted tools with checkboxes + reset action
    ├── api/
    │   └── toolSelection.ts           # NEW: get/set per-user tool-selection preference (uses existing fetchJson)
    └── hooks/
        └── useWebSocket.ts            # ~line 986-1004: include selected_tools in chat_message payload when narrowed

tests/
├── backend/
│   ├── unit/
│   │   ├── test_tool_permissions_per_tool.py   # NEW: is_tool_allowed with permission_kind; migration semantics
│   │   └── test_user_tool_selection_pref.py    # NEW: pref read/write
│   └── integration/
│       └── test_chat_dispatch_with_selection.py # NEW: chat WS message with selected_tools narrows tool list
└── frontend/
    └── (existing test setup) extend with component tests for DashboardLayout filter, FloatingChatPanel agent header + ToolPicker, AgentPermissionsModal per-tool rows, CreateAgentModal per-tool checkboxes
```

**Structure Decision**: Web-application layout (existing). All edits land in established directories — no new top-level packages or modules. The single new frontend file (`ToolPicker.tsx`) is a leaf component composed of primitives already in use.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations. Section intentionally empty.*
