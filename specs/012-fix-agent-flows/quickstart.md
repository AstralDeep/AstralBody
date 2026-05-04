# Quickstart: Fix Agent Creation, Test, and Management Flows

**Feature**: 012-fix-agent-flows
**Date**: 2026-05-01

This is the manual + automated verification recipe for the feature. It mirrors the four user stories so each can be exercised independently (per the spec's Independent Test guidance).

## Prerequisites

- Local dev environment up: `docker compose up` (or the project's standard runner) with backend and frontend reachable.
- A Keycloak account that can sign in to the frontend.
- A clean drafts list for the test user (or be ready to create new drafts; existing ones won't interfere).
- Browser dev tools open (Network + Console + WS frame inspector).

## 1. Verify Story 1 — reach the Test screen

**Goal**: After generating an agent, land on a working Test screen.

1. Open the app in a browser; sign in.
2. Click "Create Agent" → fill name, description, one tag, one tool. Advance through Steps 1–3.
3. Click **Generate Agent** on the Review step.
4. Wait until generation completes (status badge → "Ready to Test").

**Expected**:
- Modal advances to Step 4 within a few seconds of generation completing.
- Step 4 shows the draft name, current status, and a chat input ready for typing.
- Browser dev tools show a WebSocket connection to the test channel established **immediately on Step 4 entry** (not after the user types).

**Failure modes the fix must prevent**:
- Step 4 mounts but no WS connection appears in the Network tab.
- The user types a message and the input clears with no chat bubble shown.

## 2. Verify Story 2 — draft actually responds

**Goal**: The draft starts and answers a test message.

1. Continuing from Story 1's verification, type a message into the test chat that the draft should be able to handle (e.g., "list your tools" if it has any tool-listing capability, or "say hello").
2. Send.

**Expected**:
- A `chat_message` user bubble appears immediately.
- A `draft_status` event shows `status: testing` (verifiable in the WS frame inspector).
- The draft's response renders in full within 60 seconds (SC-002).
- A second message in the same chat works without a manual restart.

**Failure modes the fix must prevent**:
- The user message appears but no response ever arrives (the previous silent-drop bug).
- Subprocess port-discovery times out and the user sees no error.

**Forced-failure verification**: Manually break the generated agent (e.g., introduce a syntax error in `backend/agents/<slug>/main.py`) and re-run the test. The Test screen MUST show a `draft_runtime_error` with reason and a Retry action, not a frozen chat.

## 3. Verify Story 3 — approval promotes to live

**Goal**: Approving a draft makes it visible in the live agents list within 10 seconds, without a page reload.

1. With a passing draft on the Test screen, click **Approve**.
2. Watch the Network/WS panel.

**Expected**:
- HTTP response `200 OK` with `{ "status": "live", "agent_id": "...", "draft_id": "..." }`.
- A `draft_promoted` event arrives on the test WS.
- An `agent_list` event arrives on the dashboard WS.
- The drafts list status badge flips to "Live."
- Without reloading the page, open the agents modal → "My" tab → the new agent is listed.

**Failed-checks variation**: Force a security failure (e.g., add a forbidden import to the draft) and re-approve. Expected: HTTP `200 OK` with `{ "status": "rejected", "failures": [...] }`. The drafts list shows the agent as Rejected with the failure messages. The user can refine and re-approve.

## 4. Verify Story 4 — Permissions modal stays open

**Goal**: Clicking an agent in the Agent Management UI opens the Permissions screen and keeps it open.

1. Open the agents modal (lightning bolt or similar entry point).
2. Switch to the "My" tab; click any owned agent.

**Expected**:
- The Permissions modal mounts immediately with a loading skeleton (no blank dashboard flash, no full page reload).
- Once permissions data arrives, the loading state swaps for the scopes UI.
- Toggling a scope or entering a credential keeps focus inside the Permissions modal.
- Pressing Escape, clicking the close button, or clicking the backdrop dismisses the modal cleanly and returns to the dashboard with the agents modal NOT auto-reopened.

**Failure modes the fix must prevent**:
- Modal flashes open and immediately closes.
- Page appears to reload (URL stays the same but the dashboard re-renders from scratch).
- Modal never appears (the previous race where `agentPermissions.agent_id !== permModalAgent` blocked render).

## 5. Verify Story 1–4 together end-to-end

A new user, given an agent idea, can in a single session:

1. Open Create Agent
2. Reach the Test screen
3. Send a test message and get a response
4. Approve → see the agent in the live list
5. Open Permissions for the new agent and toggle a scope, all without a page reload

This is the SC-006 acceptance check.

## Automated checks

- Backend: `cd backend && pytest tests/orchestrator -k "lifecycle or chat_routing or approve"` — covers `start_draft_agent` error paths, `approve_agent` live promotion, and chat-routing the typed-error fallback.
- Frontend: `cd frontend && npm run test -- CreateAgentModal DashboardLayout AgentPermissionsModal` — covers Step 4 WS gating, openPermissionsModal mount/dismount, and modal loading-state rendering.
- Lint/typecheck: `cd src && pytest; ruff check .` (per CLAUDE.md) and `cd frontend && npm run lint && npm run typecheck`.

## Rollback

No schema migration is included in this feature, so rollback is just a code revert. If post-merge the Permissions modal regresses, the fastest mitigation is to revert the `openPermissionsModal` and `<AgentPermissionsModal>` mount changes in `DashboardLayout.tsx` — the rest of the feature is independently revertable per-story.
