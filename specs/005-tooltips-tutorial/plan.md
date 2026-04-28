# Implementation Plan: Tool Tips and Getting Started Tutorial

**Branch**: `005-tooltips-tutorial` | **Date**: 2026-04-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/005-tooltips-tutorial/spec.md`

## Summary

Ship a backend-anchored, per-user onboarding tutorial plus a unified tooltip layer. On a user's first sign-in (defined as no `onboarding_state` row), a guided overlay walks them through chat → agents → audit → feedback (with admin-only steps appended for admins). Tutorial step copy lives in PostgreSQL and is editable through an admin-only panel without redeploy. Tooltip text is split by surface: static UI (sidebar, panels, modals) is authored in a frontend catalog; server-driven (SDUI) components carry tooltip text in a new optional `tooltip` field on the base `Component` primitive. Tutorial lifecycle events and admin copy edits are recorded through the existing feature 003 audit log. No new third-party libraries are introduced.

## Technical Context

**Language/Version**: Python 3.11 (backend, per `backend/.venv` + Constitution Principle I); TypeScript 5+ on Vite + React (frontend, per Constitution Principle II)
**Primary Dependencies**: FastAPI + WebSocket (existing); raw `psycopg2` against the existing PostgreSQL instance (no SQLAlchemy / Alembic — schema additions go into `Database._init_db`, matching the convention established by features 003 and 004); React + Vite + Vitest + `@testing-library/react` (existing); Keycloak JWT validation via existing middleware. **No new third-party libraries** — Constitution Principle V (lead-developer approval) is satisfied by reuse.
**Storage**: PostgreSQL — three new tables co-located with `audit_events` and `component_feedback` family: `onboarding_state` (one row per user), `tutorial_step` (canonical step content, soft-delete), `tutorial_step_revision` (per-edit history for traceability). Per-user isolation enforced at the application layer mirroring the audit-log and feedback patterns. No WORM cold archive required (this is product copy, not a regulatory record).
**Testing**: `pytest` for backend (alongside existing `backend/audit/tests/` and `backend/feedback/tests/`); Vitest + `@testing-library/react` for frontend. Constitution Principle III: 90% coverage on changed code.
**Target Platform**: Backend runs in the existing FastAPI process on port 8001; frontend served by the existing Vite SPA. Tutorial UI must work on desktop (primary), tablet, and touch devices via the existing ROTE device-capability pipeline.
**Project Type**: Web application (existing backend + frontend repo, see Constitution).
**Performance Goals**: Tooltip first-paint within 500 ms of hover/focus (SC-004). Tutorial overlay appears within 2 s of sign-in (User Story 1, AC 1). Onboarding-state read on dashboard mount: target p95 < 50 ms (single-row primary-key lookup). Step list read: p95 < 100 ms.
**Constraints**: No new third-party libraries. All schema changes go into `Database._init_db`. All tutorial lifecycle events and step edits emit through the existing feature 003 audit recorder. Admin operations require Keycloak admin role (per Constitution Principle VII). Tooltip primitive extension MUST NOT break existing SDUI consumers (additive optional field only).
**Scale/Scope**: Onboarding state — one row per user (small, indexed by `user_id`). Tutorial steps — ~10–20 rows total system-wide (revision history grows slowly). Frontend tooltip catalog — ~30–60 entries for static UI; SDUI tooltips travel inline on each component payload.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Primary Language (Python)** — PASS. All backend code is Python 3.11 in the existing `backend/` tree.
- **II. Frontend Framework (Vite + React + TypeScript)** — PASS. New frontend code is `.tsx`/`.ts` under the existing Vite + React project.
- **III. Testing Standards (90% coverage, unit + integration)** — PASS (planned). Backend: new `backend/onboarding/tests/` module with unit tests for repository, recorder, schemas, and integration tests for REST endpoints (admin RBAC, per-user isolation, copy edit → user-visible). Frontend: Vitest + Testing Library coverage on `TutorialOverlay`, `Tooltip`, `OnboardingContext`, `TutorialAdminPanel`. Coverage gate enforced as part of the existing CI flow.
- **IV. Code Quality (PEP 8, ESLint)** — PASS. Existing lint config applies; no exceptions requested.
- **V. Dependency Management (lead-developer approval for new third-party deps)** — PASS. No new third-party libraries — reuses FastAPI, psycopg2, React, Vitest, Testing Library, the existing Keycloak middleware, and the existing audit recorder. Same posture as feature 004.
- **VI. Documentation (docstrings, /docs)** — PASS. Backend: Google-style docstrings on all public functions; new REST endpoints will appear automatically in FastAPI's `/docs`. Frontend: JSDoc on exported components and hooks.
- **VII. Security (Keycloak, RFC 8693, input validation, per-user isolation)** — PASS. Onboarding state endpoints use `actor_user_id` derived **only** from the verified JWT (mirrors the audit log's strict per-user policy from feature 003). Admin endpoints enforce Keycloak admin role. Step copy is rendered as plain text on the frontend (no HTML injection). Cross-user reads are not possible — the API never accepts a user-id parameter.
- **VIII. User Experience (primitive components, dynamic generation)** — PASS. The tooltip extension is an additive **optional field** (`tooltip: Optional[str] = None`) on the base `Component` dataclass — it is not a new primitive, so the "new primitive components MUST be approved and documented" rule does not trigger. The TutorialOverlay, Tooltip wrapper, and TutorialAdminPanel are frontend-only constructs that compose existing primitive React components; they do not introduce new primitives to the SDUI catalog.

**Result**: All gates pass. No entries in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-tooltips-tutorial/
├── plan.md              # This file
├── spec.md              # Feature specification (already written)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (REST endpoint contracts)
│   ├── onboarding-state.md
│   ├── tutorial-steps.md
│   └── admin-tutorial-steps.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── onboarding/                   # NEW — mirrors backend/audit/ and backend/feedback/
│   ├── __init__.py
│   ├── schemas.py                # Pydantic models: OnboardingState, TutorialStep, StepRevision
│   ├── repository.py             # psycopg2 CRUD against onboarding_state, tutorial_step, tutorial_step_revision
│   ├── recorder.py               # Wires onboarding/copy events into the existing audit recorder
│   ├── api.py                    # FastAPI router: /api/onboarding/* and /api/admin/tutorial/*
│   └── tests/
│       ├── test_repository.py
│       ├── test_api_user.py
│       ├── test_api_admin.py
│       └── test_recorder.py
├── shared/
│   └── primitives.py             # MODIFIED — add `tooltip: Optional[str] = None` to base Component dataclass
├── orchestrator/
│   ├── api.py                    # MODIFIED — register the new onboarding router
│   └── database.py (or wherever Database._init_db lives)
│                                 # MODIFIED — add three CREATE TABLE statements + indices
└── seeds/
    └── tutorial_steps_seed.sql   # NEW — initial step content; idempotent INSERT … ON CONFLICT DO NOTHING

frontend/
├── src/
│   ├── components/
│   │   └── onboarding/                        # NEW — mirrors components/audit/ and components/feedback/
│   │       ├── TutorialOverlay.tsx            # Full-screen overlay, anchors to target element
│   │       ├── TutorialStep.tsx               # Step renderer (title/body/next/back/skip)
│   │       ├── TutorialAdminPanel.tsx         # Admin step-content editor
│   │       ├── OnboardingContext.tsx          # State machine: not_started → in_progress → completed/skipped
│   │       ├── Tooltip.tsx                    # Hover/focus tooltip; touch long-press support
│   │       ├── TooltipProvider.tsx            # Single keyboard/escape listener; manages active tooltip
│   │       ├── tooltipCatalog.ts              # Static-UI tooltip strings keyed by element id
│   │       ├── useOnboardingState.ts          # Hook for backend state + replay action
│   │       ├── useTutorialSteps.ts            # Hook for the user-visible step list
│   │       └── __tests__/
│   │           ├── TutorialOverlay.test.tsx
│   │           ├── Tooltip.test.tsx
│   │           ├── OnboardingContext.test.tsx
│   │           └── TutorialAdminPanel.test.tsx
│   ├── components/
│   │   ├── DashboardLayout.tsx                # MODIFIED — mount TutorialOverlay; add "Take the tour" sidebar entry; conditionally surface admin TutorialAdminPanel
│   │   └── DynamicRenderer.tsx                # MODIFIED — wrap rendered SDUI components in <Tooltip text={component.tooltip}> when present
│   └── hooks/
│       └── useWebSocket.ts                    # No change required — onboarding does not need WS
└── ...
```

**Structure Decision**: Web-application split, following the established AstralBody pattern from features 003 (audit) and 004 (feedback). New backend module is `backend/onboarding/` (sibling of `backend/audit/` and `backend/feedback/`). New frontend folder is `frontend/src/components/onboarding/` (sibling of `frontend/src/components/audit/` and `.../feedback/`). Database schema additions go directly into `Database._init_db` (no SQLAlchemy / Alembic). The base `Component` primitive in `backend/shared/primitives.py` gains a single optional `tooltip` field — additive change, no breaking impact on existing consumers.

## Phase 0 — Research

See [research.md](research.md). Resolves the architecture decisions implied by the spec's clarifications: tooltip authoring split, onboarding-state schema, tutorial-step storage and editability, admin RBAC reuse, audit-log integration shape, accessibility/touch-device approach, and resume-on-reload semantics.

## Phase 1 — Design & Contracts

- **Data model**: see [data-model.md](data-model.md). Three new tables (`onboarding_state`, `tutorial_step`, `tutorial_step_revision`) plus the additive `tooltip` field on `Component`.
- **Contracts**: see [contracts/](contracts/). Five REST endpoints split across user (`/api/onboarding/*`, `/api/tutorial/steps`) and admin (`/api/admin/tutorial/steps[/...]`) surfaces. No new WebSocket messages needed.
- **Quickstart**: see [quickstart.md](quickstart.md). End-to-end manual walkthrough: fresh user sign-in → tutorial → admin edits step → next user replay sees updated copy.
- **Agent context update**: ran `update-agent-context.ps1 -AgentType claude` after writing the design; the new technologies and module path are appended to `CLAUDE.md` between the managed markers.

## Complexity Tracking

> No constitution gate failed. Table intentionally empty.
