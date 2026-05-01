# Quickstart: Verify Feature 008 Locally

**Feature**: 008-llm-text-only-chat
**Audience**: A developer who just pulled the branch and wants to confirm the feature works end-to-end.

---

## Prerequisites

- Backend can boot against the project's local Postgres + Keycloak stack.
- Frontend dev server runs (`npm run dev` from `frontend/`).
- A user account exists in Keycloak that you can sign in with.
- An LLM provider is configured (either via the user's settings, see feature 006, or the operator default `.env`).

---

## Path 1 — User Story 1 (P1): plain LLM reply with no agents

1. Boot the backend with **no agent containers running** (or stop them all). Verify in logs that `len(self.agents) == 0`.
2. Sign in to the frontend.
3. Open a new chat. **Expected**: the persistent text-only banner is visible at the top of the messages region (per FR-007a).
4. Type "What is the capital of France?" and send.
5. **Expected**: a normal LLM text reply arrives ("Paris."). No "No agents connected" warning appears.
6. Reload the chat. **Expected**: the user message and assistant reply are both restored from history.

---

## Path 2 — Edge case: LLM unavailable still wins

1. Clear all LLM credentials (user-level and operator default).
2. Send a chat. **Expected**: the existing "LLM unavailable — set your own provider in settings." alert appears (FR-003); no fall-through to text-only.

---

## Path 3 — User Story 1 (P1, scenario 2): all tools blocked

1. Start the backend with at least one agent running.
2. From the agent management modal, revoke ALL tool permissions for the agent for your user.
3. Send a chat message.
4. **Expected**: the text-only branch fires (banner is visible, LLM replies in text). No warning.

---

## Path 4 — Mid-conversation transition

1. Start with no agents. Send a message and receive a text-only reply.
2. Start an agent container and confirm the frontend's `agent_list` updates (banner disappears).
3. Send the next message in the same chat.
4. **Expected**: the new turn dispatches with that agent's tools available; banner is gone for this turn.
5. Stop the agent container again.
6. Send another message.
7. **Expected**: the new turn dispatches in text-only mode; banner reappears. Prior tool_calls in history (from step 4) are sent unchanged to the LLM (FR-012) — no crash, no re-invocation attempts.

---

## Path 5 — User Story 2 banner action

1. While the banner is visible, click its inline "enable agents" link/button.
2. **Expected**: the existing agent management modal opens (the same one reachable from the dashboard).

---

## Path 6 — User Story 3 onboarding step

1. As a fresh user (or after resetting onboarding state from the tutorial admin panel), trigger the tutorial.
2. Step through the tour.
3. **Expected**: a new step `enable-agents` (display order between "Browse available agents" and "Review the audit log") explicitly tells the user to turn on an agent and points to the agents panel.

---

## Path 7 — Audit / observability

1. After running Path 1, query the audit log (or whichever inspector your env provides).
2. **Expected**: one event with `action_type=llm.call` and `feature=chat_dispatch_text_only` exists for the dispatch.
3. After running Path 4 step 4 (tool-augmented turn), query again.
4. **Expected**: that turn recorded a `feature` other than `chat_dispatch_text_only` — fallback events are distinguishable in the log (FR-009).

---

## Automated tests to run

From repo root:

```pwsh
cd backend; pytest tests/test_chat_text_only.py tests/test_agent_flow.py onboarding/tests/test_seed.py
cd ../frontend; npm test -- TextOnlyBanner
```

All tests should pass. Coverage on the modified `orchestrator.handle_chat_message` branch and the new `TextOnlyBanner` component must meet the Constitution Principle III 90% threshold for changed code.
