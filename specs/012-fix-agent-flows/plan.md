# Implementation Plan: Fix Agent Creation, Test, and Management Flows

**Branch**: `012-fix-agent-flows` | **Date**: 2026-05-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/012-fix-agent-flows/spec.md`

## Summary

Restore the full create-and-test-and-promote loop for user-built agents, and unblock the Permissions screen in the Agent Management UI. The work is a focused set of bug fixes against the existing `draft_agents` lifecycle, the `CreateAgentModal` wizard, the agents-modal in `DashboardLayout`, and the backend orchestrator's draft-promotion path. No new entities, no new third-party libraries, and no schema changes are introduced.

The four root causes (named here so the plan stays grounded):

1. **Story 1 — never reaches Test screen**: [`CreateAgentModal.tsx:252`](../../frontend/src/components/CreateAgentModal.tsx#L252) gates the test WebSocket on `draft?.status === "testing"`, but generation completes at status `"generated"`. The user lands on Step 4 with no live WS, types a message, and `sendTestMessage` exits silently because `testWsRef.current` is null.
2. **Story 2 — draft doesn't run/respond**: [`agent_lifecycle.py:458`](../../backend/orchestrator/agent_lifecycle.py#L458) (`start_draft_agent`) starts a subprocess and retries port discovery 6× with 2s waits; on failure the error is logged but never surfaced to the user. Chat routing in [`orchestrator.py:1756`](../../backend/orchestrator/orchestrator.py#L1756) needs the agent in `agent_cards` — if discovery fails, test messages are dropped silently.
3. **Story 3 — approval doesn't reliably go live**: After auto-approve in [`agent_lifecycle.py:858`](../../backend/orchestrator/agent_lifecycle.py#L858), the agent stays in `_draft_processes` rather than being promoted into `orchestrator.agent_cards` permanently; `set_agent_ownership` is not re-called on promotion; and no broadcast tells the frontend to re-fetch its live-agents list.
4. **Story 4 — Permissions modal flashes/closes**: [`DashboardLayout.tsx:230`](../../frontend/src/components/DashboardLayout.tsx#L230) (`openPermissionsModal`) immediately calls `setAgentsModalOpen(false)` and only renders `<AgentPermissionsModal>` when `agentPermissions.agent_id === permModalAgent` ([line 915](../../frontend/src/components/DashboardLayout.tsx#L915)). Between those, the agents modal vanishes and the permissions modal hasn't mounted yet — the user perceives the modal closing and the dashboard "refreshing." If the permissions fetch never resolves with the matching `agent_id`, the modal never appears at all.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x (frontend, Vite + React 18)
**Primary Dependencies**: FastAPI, websockets, the existing OpenAI-compatible LLM client (`_call_llm`); React 18, Tailwind, framer-motion, sonner, the existing `fetchJson` helper. **No new dependencies** (Constitution V).
**Storage**: PostgreSQL — existing `draft_agents` and `agent_ownership` tables. **No schema change required**; FR-016/FR-017 are satisfied by existing columns plus the existing `delete_draft` endpoint at [`api.py:1014`](../../backend/orchestrator/api.py#L1014).
**Testing**: pytest (backend, see `backend/tests/`), Vitest (frontend, configured via `frontend/src/test/setup.ts`).
**Target Platform**: Linux server in Docker (backend), modern evergreen browsers (frontend).
**Project Type**: Web application — backend (FastAPI service + agent processes) + frontend (Vite SPA).
**Performance Goals**: Full draft response within 60 s at the 95th percentile (SC-002); approved draft visible in the live agents list within 10 s of security checks completing (SC-003); zero unintended page reloads in the Agent Management UI (SC-005).
**Constraints**: Must preserve existing Keycloak auth and RFC 8693 attenuated scopes (Constitution VII). No new third-party libs (V). Auto-applied migrations only (IX) — none required here. Production-readiness gate (X) requires browser-verified end-to-end of the four user stories before merge.
**Scale/Scope**: Per-user drafts, low N (single-digit drafts per user during normal use). The fixes are not throughput-bound.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Primary Language (Python backend) | PASS | All backend changes are Python. |
| II. Frontend Framework (Vite + React + TS) | PASS | All frontend changes are TS/TSX. |
| III. Testing Standards (90% coverage) | GATE | New unit tests required for: `start_draft_agent` error surfacing, `approve_agent` live-promotion path, `delete_draft`. New Vitest tests required for: `CreateAgentModal` step-4 WS gating, `DashboardLayout` permissions-modal mount/dismount flow. Integration tests required for the create→test→approve loop and for the permissions-modal click. |
| IV. Code Quality (PEP 8 / ESLint) | PASS | Existing tooling already runs in CI. |
| V. Dependency Management | PASS | No new third-party libraries. |
| VI. Documentation | PASS | Docstrings on changed Python functions; JSDoc on changed exports. |
| VII. Security (Keycloak / RFC 8693 / no secrets) | PASS | Permissions screen fix preserves the existing scope model and credential storage path. Draft-under-test reuses the user's real credentials via the same Permissions surface (per Clarification Q1) — no new secret-handling code. |
| VIII. UX (primitive components) | PASS | No new primitives; only behavior fixes. |
| IX. Database Migrations | PASS | No schema change planned. If implementation discovers a missing column (research.md will confirm), a migration script ships with the PR. |
| X. Production Readiness | GATE | Each of Stories 1–4 must be browser-verified end-to-end in staging before merge. New observability: structured log + user-visible error when `start_draft_agent` fails port discovery; structured log on auto-promotion success/failure with draft_id + agent_id. |

No principle violations; the two GATE items above are addressed by Phase 1 deliverables (test design and observability requirements) and verified in the implementation tasks (Phase 2, produced by `/speckit.tasks`).

## Project Structure

### Documentation (this feature)

```text
specs/012-fix-agent-flows/
├── plan.md              # This file
├── research.md          # Phase 0 — root cause confirmations + decisions
├── data-model.md        # Phase 1 — lifecycle states, ownership/registry semantics
├── quickstart.md        # Phase 1 — manual + automated verification steps
├── contracts/           # Phase 1 — touched HTTP/WS contract notes
│   ├── http-endpoints.md
│   └── websocket-events.md
├── checklists/
│   └── requirements.md  # Already produced by /speckit.specify
└── tasks.md             # Phase 2 — produced by /speckit.tasks (NOT this command)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── agent_lifecycle.py        # start_draft_agent, approve_agent, delete_draft (touched)
│   ├── orchestrator.py           # _is_draft_agent, agent_cards, dashboard broadcast (touched)
│   └── api.py                    # /api/agents/drafts/* routes (touched: response shapes only)
├── shared/
│   └── database.py               # set_agent_ownership, delete_draft_agent (read-only review)
├── agents/
│   └── (per-agent generated dirs — no changes here)
└── tests/
    └── orchestrator/             # New + updated tests for lifecycle + chat routing

frontend/
├── src/
│   ├── components/
│   │   ├── CreateAgentModal.tsx          # Step 4 WS gating + error surfacing (touched)
│   │   ├── DashboardLayout.tsx           # openPermissionsModal flow (touched)
│   │   └── AgentPermissionsModal.tsx     # Mount/dismount + loading state (touched)
│   ├── hooks/
│   │   └── useWebSocket.ts               # Approval → live-agents refetch trigger (touched)
│   ├── api/
│   │   └── (existing helpers reused)
│   └── test/
│       └── setup.ts                       # Vitest config (existing)
└── (no schema/migration changes)
```

**Structure Decision**: This is the existing AstralBody web-application layout (backend + frontend). All changes are localized to the files listed above. No new top-level directories, no new packages, no new services.

## Complexity Tracking

> No constitution violations to justify. Section intentionally empty.
