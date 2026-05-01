# Implementation Plan: LLM Text-Only Chat When No Agents Enabled

**Branch**: `008-llm-text-only-chat` | **Date**: 2026-05-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-llm-text-only-chat/spec.md`

## Summary

When a user sends a chat message and no agents/tools are available to them (no agents connected, all blocked by user-level permissions, or all blocked by system security flags), today the orchestrator short-circuits with a "No agents connected" warning at [backend/orchestrator/orchestrator.py:1831-1835](../../backend/orchestrator/orchestrator.py#L1831-L1835). This feature replaces that early return with a normal LLM dispatch using an empty tools list, an extended system prompt that tells the LLM about its limitations (FR-006a), and the same audit/observability shape as agent-backed turns. A persistent UI banner at the top of the chat surface (FR-007a) reflects the per-turn tool-availability state and links the user to the agent management modal. The onboarding tutorial gains a new seeded step (FR-007b) explicitly telling users how to turn on agents.

The existing `_call_llm` already tolerates empty/None `tools_desc`, the existing audit recorder pattern (`_record_llm_call(feature=...)`) already supports per-feature tagging, and the existing `agent_list` WebSocket message already broadcasts agent state — so the feature is mostly a removal of the early-return guard plus three additive surfaces (system-prompt addendum, banner, tutorial step). No new dependencies are introduced.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend)
**Primary Dependencies**: Backend — FastAPI, websockets, the existing OpenAI-compatible client used in `_call_llm`. Frontend — React 18, Tailwind, Framer Motion, sonner (already present).
**Storage**: Postgres (existing). Tutorial steps live in the `tutorial_step` table seeded by [backend/seeds/tutorial_steps_seed.sql](../../backend/seeds/tutorial_steps_seed.sql); no new tables.
**Testing**: Backend — pytest (`backend/tests/`, `backend/onboarding/tests/`). Frontend — Vitest + React Testing Library, co-located in `__tests__/` folders next to components.
**Target Platform**: Linux server (backend container), modern desktop browsers (frontend).
**Project Type**: Web application (separate `backend/` and `frontend/` trees).
**Performance Goals**: Per SC-002 — text-only turn latency must not exceed median tool-augmented turn that does not invoke any tools. No additional p95 budget beyond what `_call_llm` already incurs.
**Constraints**: Per Constitution Principle VII, auth/authorization unchanged (same Keycloak-gated WebSocket handler). Per Principle IX, the new tutorial seed addition must be idempotent (`ON CONFLICT (slug) DO NOTHING`).
**Scale/Scope**: Single-user-session WebSocket. No new scale dimension.

No `NEEDS CLARIFICATION` items remain after the `/speckit.clarify` round.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python backend) | PASS | All backend changes stay in Python within `backend/orchestrator/` and `backend/onboarding/seed.py` (or seed SQL). |
| II. Frontend Framework (Vite + React + TypeScript) | PASS | Banner is a new `.tsx` component; tutorial step renders via existing `TutorialStep.tsx`. |
| III. Testing Standards (90% coverage) | PASS | Plan adds backend pytest cases for the new branch in `handle_chat_message`, audit-event emission, and the agent_list extension; frontend vitest cases for banner render/link, and an onboarding seed test confirming the new step is loaded. |
| IV. Code Quality (ruff/ESLint) | PASS | All new code conforms to existing lint rules; no new lint exceptions. |
| V. Dependency Management | PASS | No new third-party dependencies. All capabilities (Tailwind, framer-motion, sonner, FastAPI WS, OpenAI-compatible client) already in tree. |
| VI. Documentation | PASS | New helpers get Google-style docstrings; new React component gets JSDoc on its props interface. |
| VII. Security | PASS | Same Keycloak-gated WebSocket handler. Tool permissions still enforced per-turn — text-only path runs only AFTER permissions filtering yields zero tools. No new attack surface; no scope changes. |
| VIII. User Experience (primitive components) | PASS with note | The existing frontend doesn't ship a registered "primitives" directory; current chat UI is built directly with Tailwind + Framer Motion (`ChatInterface.tsx`). The banner follows the same convention used by the rest of `ChatInterface.tsx` (Tailwind classes, Framer Motion `<AnimatePresence>`), reusing the visual style of existing chat-surface chrome rather than introducing a new design vocabulary. No new "primitive" is registered. |
| IX. Database Migrations | PASS | No schema changes. Tutorial-step addition is an INSERT into the existing `tutorial_step` table via the idempotent seed SQL (`ON CONFLICT (slug) DO NOTHING`). The seed is re-run on deploy by the existing onboarding seed loader. |
| X. Production Readiness | PASS | Plan covers golden path, edge cases (history with prior tool_calls, mid-conversation agent enable/disable, draft test scope), and adds structured audit event distinguishable from tool-augmented turns (FR-009). |

No violations to track.

## Project Structure

### Documentation (this feature)

```text
specs/008-llm-text-only-chat/
├── plan.md                    # This file
├── research.md                # Phase 0 output
├── data-model.md              # Phase 1 output
├── quickstart.md              # Phase 1 output
├── contracts/
│   ├── ws-agent-list.md       # Existing message — documents the additive `tools_available_for_user` flag
│   └── audit-event-text-only.md  # New audit event shape
├── checklists/
│   └── requirements.md        # From /speckit.specify
└── tasks.md                   # Output of /speckit.tasks (not produced here)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   └── orchestrator.py        # MODIFY: handle_chat_message text-only branch + system-prompt addendum + agent_list extension
├── llm_config/
│   └── audit_events.py        # MODIFY (small): support feature="chat_dispatch_text_only" tagging via existing _record_llm_call
├── onboarding/
│   └── seed.py                # MODIFY (verify): pick up new step from seed SQL on next run
├── seeds/
│   └── tutorial_steps_seed.sql  # MODIFY: add 'enable-agents' step (idempotent INSERT)
└── tests/
    ├── test_chat_text_only.py            # NEW: unit + integration tests for the text-only branch
    └── test_agent_flow.py                 # MODIFY: extend to assert agent_list carries tools_available_for_user
└── onboarding/tests/
    └── test_seed.py                       # MODIFY: assert 'enable-agents' step is loaded

frontend/
├── src/components/
│   ├── ChatInterface.tsx                  # MODIFY: mount <TextOnlyBanner /> at top of messages region; add onOpenAgentSettings prop
│   ├── DashboardLayout.tsx                # MODIFY: pass onOpenAgentSettings={() => setAgentsModalOpen(true)} to ChatInterface
│   └── TextOnlyBanner.tsx                 # NEW: persistent banner component (Tailwind + Framer Motion)
├── src/components/__tests__/
│   └── TextOnlyBanner.test.tsx            # NEW: render + click + state-transition tests
└── src/hooks/
    └── useWebSocket.ts                    # MODIFY: extend Agent state plumbing if `tools_available_for_user` arrives on agent_list
```

**Structure Decision**: Existing two-tree web-app layout (`backend/`, `frontend/`). All changes are localized to the orchestrator chat-dispatch path on the backend, the chat surface + tutorial seed on the frontend/data side. No new top-level directories or modules.

## Complexity Tracking

> No Constitution violations require justification.

(Empty — gate passed without exceptions.)
