# Implementation Plan: In-Chat Progress Notifications & Persistent Step Trail

**Branch**: `014-progress-notifications` | **Date**: 2026-05-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from [`/specs/014-progress-notifications/spec.md`](./spec.md)

## Summary

Surface what the orchestrator is doing while a chat turn is in flight by adding two parallel layers to the chat surface:

1. A single ephemeral **rotating cosmic-word indicator** that replaces today's static "Processing…" loader — driven by extending the existing `chat_status` WebSocket event with no new state.
2. A **persistent step trail** rendered as new chat-message items (one per orchestrator step) that live alongside `user`/`assistant` messages in the existing `messages` table — driven by a new `chat_step` WebSocket event emitted from the orchestrator's tool-call / agent-handoff / phase-transition seams. Step entries are collapsible, with collapse state held in browser `sessionStorage` per FR-018/019.

Both layers are wired into the cancellation path of [`task_state.py`](../../backend/orchestrator/task_state.py): cancel fires a best-effort signal, in-flight steps that cannot stop are allowed to complete with their results discarded, and any step still running at cancel time is rendered with a `cancelled` status (FR-020/021). All step content (truncated args + truncated result summary) flows through a new redaction layer that strips HIPAA/PHI before persistence and before transmission to the browser (FR-009b).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend) — matches every prior feature in [CLAUDE.md](../../CLAUDE.md).
**Primary Dependencies**: FastAPI, the existing WebSocket plumbing in [`backend/orchestrator/orchestrator.py`](../../backend/orchestrator/orchestrator.py), the existing `chat_status` event channel, the `TaskManager`/`Task` state machine in [`backend/orchestrator/task_state.py`](../../backend/orchestrator/task_state.py); React 18, Tailwind, framer-motion, lucide-react, the existing `useWebSocket` hook ([frontend/src/hooks/useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts)) and `ChatInterface` ([frontend/src/components/ChatInterface.tsx](../../frontend/src/components/ChatInterface.tsx)). **No new third-party libraries** — Constitution V.
**Storage**: PostgreSQL/SQLite via [`backend/shared/database.py`](../../backend/shared/database.py). New table `chat_steps` (one row per step entry, FK to `messages` and `chats`) plus a `step_count` cache column on `messages` for fast list rendering. Idempotent auto-migration in `Database._init_schema()` per Constitution IX, matching the `agent_id`-on-`chats` pattern added in feature 013.
**Testing**: pytest for backend (unit + integration covering the new orchestrator emitters, the redaction layer, the cancellation path, and migration). Vitest + React Testing Library for frontend (rotating-indicator behaviour, step-entry rendering, collapse-state persistence in `sessionStorage`). 90% coverage on changed code per Constitution III.
**Target Platform**: Modern evergreen browser front-end against the existing FastAPI backend; no new platform targets.
**Project Type**: Web application (existing `backend/` + `frontend/` split).
**Performance Goals**: SC-001 (indicator visible within 500 ms of submit), SC-002 (word changes ≥ 1×/sec, never stalls > 3 sec), SC-003 (step entry visible within 1 sec of step beginning). All achievable on the existing WebSocket transport — no new pub/sub needed.
**Constraints**: HIPAA-protected health information MUST NOT appear in any rendered or persisted step entry (FR-009b, SC-008). Truncation policy uniform across step types (FR-009a). One indicator per turn (FR-006). Collapse state is sessionStorage-scoped, NOT persisted to the database (FR-019).
**Scale/Scope**: Per-turn step counts are typically 1–10 (occasionally up to ~30 for grant-aggregation flows); a chat may carry hundreds of turns. The new table is bounded by existing chat retention. No expected change to per-user chat count.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Python backend | ✓ Pass | Backend changes confined to `backend/orchestrator/` and `backend/shared/database.py`. |
| II. Vite + React + TypeScript | ✓ Pass | Frontend changes confined to `frontend/src/` (`.tsx`/`.ts`). |
| III. Testing standards (≥ 90% coverage) | ✓ Pass | Test plan covers new emitters, redactor, migration, frontend hook + components. Coverage measured in CI. |
| IV. Code quality (PEP 8 / ESLint) | ✓ Pass | No new lint exceptions. |
| V. Dependency management (no new libs) | ✓ Pass | Reuses `framer-motion`, `lucide-react`, existing WebSocket and state. |
| VI. Documentation | ✓ Pass | New backend functions get Google-style docstrings; new TS exports get JSDoc. New `chat_step` event documented in [`contracts/`](./contracts/). |
| VII. Security | ✓ Pass with **deliberate strengthening**: a new redaction layer enforces FR-009b (HIPAA/PHI). Auth/scopes unchanged — step events flow over the same authenticated WebSocket as `chat_status`. |
| VIII. UX primitives | ✓ Pass | Step entries render via existing primitives (`Card`, `Text`, `List_`); collapse uses existing pattern from `ProgressDetails.tsx`. No new primitives proposed. |
| IX. Database migrations | ✓ Pass | New `chat_steps` table + new `step_count` column added via the existing idempotent `_init_schema` pattern (auto-runs on startup, safe under repeated deploys). Down path: drop table / drop column. |
| X. Production readiness | ✓ Pass | No stubs, no debug-only code paths planned. New observability: structured logs around step lifecycle and redaction events; metrics for step latency. UI exercised in real browser per Principle X. |

**Result: PASS** — no violations to justify in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/014-progress-notifications/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # /speckit-specify + /speckit-clarify output
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── chat_step_event.md          # WebSocket message shape (server → client)
│   ├── chat_status_extension.md    # rotating-word payload extension
│   └── chat_steps_rest.md          # REST contract for retrieving steps when loading chat history
├── checklists/
│   └── requirements.md  # spec quality checklist
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── orchestrator.py             # MODIFY: emit chat_step events from execute_tool_and_wait,
│   │                                #         agent-handoff seams, and orchestrator phase boundaries
│   ├── task_state.py               # MODIFY: integrate cancellation signal into Task.transition;
│   │                                #         emit cancelled chat_step events for in-flight steps
│   ├── coordinator.py              # MODIFY: thread step emitter through agent hand-offs
│   ├── api.py                      # MODIFY: GET /chats/{id}/steps endpoint for history rehydrate
│   └── chat_steps.py               # NEW: ChatStepRecorder, lifecycle (started/completed/errored/
│                                       #     cancelled), redaction integration, persistence
├── shared/
│   ├── database.py                 # MODIFY: idempotent schema for chat_steps table + step_count
│   │                                #         column on messages
│   └── phi_redactor.py             # NEW: HIPAA/PHI redaction utility used by ChatStepRecorder
│                                       #     before any args/result is rendered or persisted
└── tests/
    ├── test_chat_steps.py          # NEW: lifecycle, redaction, ordering, parallel calls
    ├── test_chat_steps_cancel.py   # NEW: best-effort abort, discard policy, cancelled rendering
    └── test_chat_steps_migration.py # NEW: idempotent migration, no-op on re-run

frontend/
├── src/
│   ├── components/
│   │   ├── ChatInterface.tsx       # MODIFY: render <CosmicProgressIndicator/> in loading slot;
│   │   │                            #         interleave step entries between user msg and reply
│   │   ├── chat/
│   │   │   ├── CosmicProgressIndicator.tsx   # NEW: rotating cosmic word, fade transitions
│   │   │   ├── ChatStepEntry.tsx             # NEW: collapsible step row (in-progress/done/error/cancelled)
│   │   │   └── chatStepWords.ts              # NEW: the 55-word approved list (single source)
│   ├── hooks/
│   │   ├── useWebSocket.ts                   # MODIFY: handle "chat_step" message; surface chatSteps state
│   │   ├── useChatSteps.ts                   # NEW: thin selector + mutation API for step state
│   │   └── useStepCollapseState.ts           # NEW: sessionStorage-backed collapse state per step id
│   ├── api/
│   │   └── chatSteps.ts                      # NEW: GET /chats/{id}/steps for history rehydrate
│   ├── types/
│   │   └── chatSteps.ts                      # NEW: ChatStep, ChatStepStatus, ChatStepKind types
│   └── __tests__/
│       ├── CosmicProgressIndicator.test.tsx  # NEW
│       ├── ChatStepEntry.test.tsx            # NEW
│       └── useStepCollapseState.test.ts      # NEW
```

**Structure Decision**: Existing `backend/` + `frontend/` web-application split (CLAUDE.md confirms this is the project shape across all 13 prior features). New backend module `orchestrator/chat_steps.py` keeps step-lifecycle logic out of the already-large `orchestrator.py`. New frontend folder `components/chat/` localises new components without polluting the flat `components/` directory and keeps tests next to consumers.

## Complexity Tracking

> No constitutional violations to justify; this section is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _none_ | _n/a_ | _n/a_ |
