# Implementation Plan: Component Feedback & Tool Auto-Improvement Loop

**Branch**: `004-component-feedback-loop` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-component-feedback-loop/spec.md`

## Summary

Add a per-component feedback affordance to the AstralBody dashboard so users can rate any rendered component (👍 / 👎 + fixed-taxonomy category + optional comment), and feed that feedback into the **existing** `knowledge_synthesis` background loop alongside its current tool-outcome inputs so it can propose admin-reviewed improvements for tools that consistently underperform. Quality is measured per tool over a 14-day rolling window (≥ 25 dispatches; flag at failure ≥ 20% OR negative-feedback ≥ 30%). Free-text feedback is treated as untrusted input and screened for prompt-injection / jailbreak attempts at two points: an inline heuristic pass at submit time (fast, user-acknowledgement path) and an LLM-based pre-pass inside the synthesizer before any prompt is constructed (defense in depth). Tool source code is **never** automatically rewritten — proposals modify only the synthesizer's existing knowledge markdown artifacts and require admin acceptance. The audit log is the source of truth for every action; it gains new event classes for feedback, quarantine actions, proposal review, and tool-flag transitions.

## Technical Context

**Language/Version**: Python 3.11 (backend, per `backend/.venv` + Constitution Principle I); TypeScript 5+ on Vite + React (frontend, per Constitution Principle II)
**Primary Dependencies**: FastAPI + WebSocket (existing); raw `psycopg2` against the existing PostgreSQL instance (no SQLAlchemy / Alembic — schema additions go into `Database._init_db`, matching the convention established by feature 003); Ollama (already used by `backend/orchestrator/knowledge_synthesis.py`) reused for the LLM pre-pass screen and for proposal generation; React + Vite + Vitest + `@testing-library/react` (existing). **No new third-party libraries are introduced** — Constitution Principle V (lead-developer approval) is satisfied by reuse.
**Storage**: PostgreSQL — four new tables co-located with `audit_events`: `component_feedback`, `tool_quality_signal`, `knowledge_update_proposal`, `quarantine_entry`. Per-user isolation enforced at the application layer mirroring the audit-log pattern. Read-only WORM cold archive is **not** required for feedback (it is not a regulatory record on its own; its identity-bearing parent audit events already inherit feature 003's retention).
**Testing**: pytest for backend (`backend/feedback/tests/`, mirroring `backend/audit/tests/`); Vitest + Testing Library for frontend; end-to-end isolation tests run inside the `astralbody` container the same way feature 003's audit tests do. 90% coverage on changed code per Constitution Principle III.
**Target Platform**: Linux server (backend container) + modern browser (Vite dev or built static assets).
**Project Type**: Web application — backend + frontend.
**Performance Goals**: ≤ 1 s feedback-submit acknowledgement on a normal connection (SC-001 → drives inline-screen approach: pure heuristics, no LLM call on the user path); ≤ 24 h between threshold crossing and admin-queue surfacing (SC-003 → drives a daily evaluation cycle, aligned with the existing knowledge-synthesizer cadence of 30 min — comfortably under 24 h).
**Constraints**: Per-user isolation, zero cross-user leaks (SC-004); free-text feedback is untrusted and never reaches an LLM as instructions (FR-025); Constitution Principle VII inputs-must-be-validated applies to every external input including feedback text and admin proposal edits.
**Scale/Scope**: Volume targets are not yet measured in production. Rough working assumption (used only for index choice and dedup-window sizing, not for capacity provisioning): O(10²-10³) feedback submissions / day in early use; O(10²) tools tracked; O(10⁰-10¹) underperforming tools at any time. The Outstanding scale line in spec coverage is acknowledged here; it does not block implementation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status | Notes |
|-----------|------|--------|-------|
| I. Primary Language | Backend in Python | ✅ PASS | New module `backend/feedback/` is Python. |
| II. Frontend Framework | Vite + React + TypeScript | ✅ PASS | New components in `frontend/src/components/feedback/` are `.tsx`. |
| III. Testing Standards | 90% coverage, unit + integration | ✅ PASS | Mirror `backend/audit/tests/` structure; add Vitest tests next to feedback components; integration tests run inside the `astralbody` container. |
| IV. Code Quality | PEP 8 + ESLint enforced in CI | ✅ PASS | No exemptions needed. |
| V. Dependency Management | New libs require lead approval | ✅ PASS — no new libs | Reuse existing Ollama client, `psycopg2`, FastAPI, audit-log substrate. The "knowledge synthesizer" path already exists; we extend its inputs. |
| VI. Documentation | Docstrings + JSDoc + `/docs` | ✅ PASS | New REST endpoints will be FastAPI-routed and appear in `/docs` Swagger UI; new public Python functions get Google-style docstrings; new TS exports get JSDoc. |
| VII. Security | Keycloak + input validation + role enforcement at API + RFC 8693 delegation | ✅ PASS | Admin endpoints gated by Keycloak `admin` role using the existing pattern in [backend/orchestrator/auth.py](../../backend/orchestrator/auth.py); user feedback endpoints gated by JWT subject; all free-text inputs validated and length-capped; feedback comments are quarantined-by-default if the inline heuristic fires. Agents do not directly access feedback storage; if they ever did, RFC 8693 delegation rules from existing infrastructure would apply. |
| VIII. User Experience | Use predefined primitive components; backend-driven dynamic generation | ✅ PASS — needs explicit primitive review | The feedback affordance must be implemented as composition of existing primitives. A small "FeedbackControl" component is proposed; if it cannot be expressed via the existing catalog without a new primitive, a primitive addition will be raised separately for approval, **NOT** added unilaterally in this feature. Phase 1 will confirm. |

**Gate result (initial)**: PASS. No violations require Complexity-Tracking justification.

### Post-design re-evaluation (after Phase 1)

Re-checked after writing [research.md](./research.md), [data-model.md](./data-model.md), and the three contract files in [contracts/](./contracts/). Findings:

| Principle | Re-check | Status |
|-----------|----------|--------|
| I (Python backend) | All new backend files specified are `.py`. | ✅ PASS |
| II (Vite + React + TS) | All new frontend files specified are `.tsx` / `.ts`. | ✅ PASS |
| III (Tests + 90% coverage) | Test directories enumerated in Project Structure; isolation test mandated by R-10. | ✅ PASS |
| IV (PEP 8 + ESLint) | No exemptions introduced. | ✅ PASS |
| V (No new deps) | Confirmed by R-1 / R-2: inline screen is heuristic-only, LLM pre-pass reuses existing Ollama. | ✅ PASS |
| VI (Docs + `/docs`) | All admin and user REST routes in [contracts/rest-admin.md](./contracts/rest-admin.md) and [contracts/rest-user.md](./contracts/rest-user.md) are FastAPI-routed and will appear in `/docs`. | ✅ PASS |
| VII (Security) | Admin endpoints gated by `admin` role; user endpoints scoped to JWT `sub`; cross-user is 404-indistinguishable; free-text inputs length-capped (2048) and dual-screened; proposal apply restricted server-side to `backend/knowledge/` prefix. | ✅ PASS |
| VIII (UI primitives) | R-9 mandates composition of existing primitives only; any new primitive needed will be raised separately for approval — not in this feature. | ✅ PASS — gated on Phase-1 design confirmation |

**Gate result (post-design)**: PASS. No new violations introduced by the Phase 0/1 artifacts. No entries needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/004-component-feedback-loop/
├── plan.md                       # This file
├── research.md                   # Phase 0 output
├── data-model.md                 # Phase 1 output
├── quickstart.md                 # Phase 1 output
├── contracts/
│   ├── ws-protocol.md            # WebSocket additions (UIRender envelope, ui_event actions)
│   ├── rest-admin.md             # Admin REST: flagged tools, proposals, quarantine
│   └── rest-user.md              # User REST: list / retract / amend feedback
├── checklists/
│   └── requirements.md           # Created by /speckit.specify (already passing post-clarify)
└── tasks.md                      # Created by /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── feedback/                     # NEW — mirrors backend/audit/ structure
│   ├── __init__.py
│   ├── schemas.py                # Pydantic / dataclass DTOs for ComponentFeedback, etc.
│   ├── repository.py             # psycopg2 queries (per-user isolation, dedup window, lifecycle)
│   ├── recorder.py               # Inline screening + persistence + audit-log handoff
│   ├── safety.py                 # Inline heuristic screen (regex / keyword / length checks). NO LLM call here.
│   ├── quality.py                # ToolQualitySignal computation (rolling-window aggregation)
│   ├── proposals.py              # Bridge to knowledge_synthesis: produce KnowledgeUpdateProposal records, apply on accept
│   ├── api.py                    # FastAPI routers (user + admin)
│   ├── ws_handlers.py            # WebSocket actions: component_feedback, feedback_retract, feedback_amend
│   └── tests/
│       ├── test_repository.py
│       ├── test_safety_inline.py
│       ├── test_quality_signal.py
│       ├── test_proposals_bridge.py
│       ├── test_api_user.py
│       └── test_api_admin.py
├── audit/
│   └── schemas.py                # MODIFIED — extend EVENT_CLASSES with: component_feedback, tool_quality, proposal_review, quarantine
├── orchestrator/
│   ├── orchestrator.py           # MODIFIED — attach correlation_id to component metadata in send_ui_render path; route new ui_event actions
│   ├── knowledge_synthesis.py    # MODIFIED — accept feedback collector input; add LLM pre-pass screen; produce structured proposals; gate auto-apply on admin accept
│   └── auth.py                   # NO CHANGES — reuse admin-role check pattern
└── shared/
    ├── protocol.py               # MODIFIED — add component_feedback / feedback_retract / feedback_amend UIEvent actions; add correlation_id field on UIRender component metadata
    └── database.py               # MODIFIED — add CREATE TABLE statements for the four new tables in Database._init_db

frontend/
├── src/
│   ├── components/
│   │   ├── feedback/             # NEW
│   │   │   ├── FeedbackControl.tsx           # Per-component thumbs / category / comment popover (composition of existing primitives)
│   │   │   ├── FeedbackAdminPanel.tsx        # Admin overlay (flagged tools + proposals + quarantine), pattern after AuditLogPanel
│   │   │   └── tests/
│   │   │       ├── FeedbackControl.test.tsx
│   │   │       └── FeedbackAdminPanel.test.tsx
│   │   ├── DynamicRenderer.tsx                # MODIFIED — render <FeedbackControl> overlay for each top-level component when correlation_id is present
│   │   └── DashboardLayout.tsx                # MODIFIED — admin-only sidebar entry for the FeedbackAdminPanel with pending-flag badge
│   ├── hooks/
│   │   ├── useFeedback.ts                     # NEW — submit / retract / amend; shows toast acknowledgement
│   │   └── useWebSocket.ts                    # MODIFIED — pass through `correlation_id` on ui_render components; broadcast `feedback:ack` window event
│   ├── api/
│   │   └── feedback.ts                        # NEW — REST helpers for admin and user flows
│   └── types/
│       └── feedback.ts                        # NEW — TS types matching protocol DTOs
└── tests/
    └── (Vitest co-located with components above)
```

**Structure Decision**: Web application with parallel `backend/feedback/` and `frontend/src/components/feedback/` modules. The feedback module mirrors `backend/audit/` very closely (recorder + repository + api + tests) on purpose — this keeps the per-user-isolation, append-only, and audit-cross-cut patterns identical, and makes it cheap for someone familiar with `backend/audit/` to understand. The synthesizer integration lives in `backend/feedback/proposals.py` plus targeted edits to `backend/orchestrator/knowledge_synthesis.py`; we do **not** fork the synthesizer.

## Complexity Tracking

> No Constitution gate violations. Section intentionally empty.
