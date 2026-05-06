# Quickstart — Verify the Feature End-to-End

Use this checklist to validate each user story locally and in staging before merging. Each section maps to one prioritized story plus its clarifications. The acceptance scenarios in the spec ([spec.md](./spec.md)) are the source of truth — this is the operational version.

## 0. Prerequisites

- Backend running locally with the migration applied:

  ```powershell
  # apply migrations (project's existing mechanism — auto-applies on startup per Constitution IX)
  # then start the orchestrator
  cd backend; python -m orchestrator
  ```

- Frontend running:

  ```powershell
  cd frontend; npm run dev
  ```

- A test user with: at least one owned **draft** agent, at least one owned **live** agent, at least one owned **live + public** agent, and at least one **public agent owned by someone else**. Create them via the create-agent flow before starting.

## 1. Story 1 — My Agents visibility

1. Sign in as the test user. Open the agents listing modal.
2. Switch to the **My Agents** tab.
   - **Expect**: every agent the user owns appears, including drafts and the live + public one. Each row shows a status badge (FR-002).
3. Switch to **Public Agents**.
   - **Expect**: every public agent appears, including the user's **own** live + public agent (Q4 / FR-003) AND the public agent owned by someone else.
4. Open the **Drafts** tab.
   - **Expect**: drafts the user owns are listed (existing behavior), AND the same drafts also appear under My Agents (FR-001).
5. Create a brand-new agent through the create-agent flow.
   - **Expect**: without reloading, the new agent appears under My Agents (FR-005).
6. As a different user (or signed out), the test user's owned-and-public agent should appear in **Public Agents** but not in **My Agents** for them.

## 2. Story 2 — Active agent indicator + unavailable banner

1. Open a chat with a specific agent.
   - **Expect**: the chat header shows the active agent's name and a `Bot` icon, **before** typing anything (FR-006).
2. Send a message; observe the agent's reply.
   - **Expect**: the assistant bubble is visually attributed to the agent that produced it (FR-007).
3. Without closing the chat, in another browser/tab as an admin, delete or deprecate that agent (or, more simply, revoke the user's access to its required scopes).
4. Return to the chat and try to send another message.
   - **Expect**: send is disabled; a banner appears across the top of the message area explaining "This agent is no longer available — start a new chat or pick another agent" (FR-009 / Q3 clarification). Chat history remains visible. The system does **not** silently route the message elsewhere.
5. Click "Pick another agent" / "Start a new chat" actions and confirm they work.

## 3. Story 3 — Per-tool permissions with proactive (i) info

1. Open an existing agent (one with multiple tools spanning different permission kinds — e.g., one read-only tool and one write tool) and open its **Permissions** modal.
   - **Expect**: instead of four scope cards, you see a row per tool, each with only the permission toggles applicable to that tool (FR-010, FR-014).
2. For a tool whose permission is currently **OFF**, hover or focus the (i) icon next to that toggle.
   - **Expect**: an explainer appears describing what enabling this permission would let the agent do, **before** the toggle has been flipped (FR-011 / Story 3 scenario 2).
3. Enable the toggle. Save and re-open.
   - **Expect**: only that exact (tool, permission) pair is on; other tools' identical-kind toggles are unchanged (FR-012 / scenario 3).
4. Test migration semantics: as a user who had a particular scope (e.g., `tools:write`) enabled before this feature shipped, open the modal.
   - **Expect**: every tool that supports `tools:write` shows that permission ON (1:1 carry-forward, FR-015 / Q2 clarification). No re-toggling is required.
5. Disable a permission and try to invoke that tool through chat.
   - **Expect**: the tool is refused at the orchestrator (`is_tool_allowed` returns False); the LLM never sees it in the `tools_desc` list (FR-013).

## 4. Story 4 — In-chat tool picker

1. Open a chat with an agent that has multiple permission-allowed tools.
2. Click the new tool-picker icon in the composer's right-side button cluster (between voice-input and send).
   - **Expect**: a popover lists the agent's permission-allowed tools, each with a checkbox; an (i) tooltip per tool; a "Reset to default" link at the bottom.
3. Deselect one or two tools. Send a message that would normally have used a deselected tool.
   - **Expect**: the agent does not invoke the deselected tool (FR-018, Story 4 scenario 2). Backend logs include `reason=user_selection` for the excluded tool (FR-023).
4. Open the popover again — your selection is preserved.
5. Sign out and back in (or open the app on a different device).
   - **Expect**: the same selection is reapplied (FR-024 / Q5 clarification).
6. Open a chat with a **different** agent that does not have the same tools.
   - **Expect**: the other agent's session uses its own default; tools in your saved selection that don't exist on this agent are silently ignored (FR-024 second half + Edge Case "saved selection contains tools the new agent does not have").
7. Click "Reset to default" inside the popover for the first agent.
   - **Expect**: selection reverts to the agent's full permission-allowed set; the saved per-user preference for that agent is cleared (FR-025 / Story 4 scenario 8).
8. Deselect every tool.
   - **Expect**: send is disabled with a tooltip explaining why and how to recover (FR-021 / Q1 clarification).
9. Try sending a message via the WS layer with `selected_tools=[]` (e.g., via dev tools).
   - **Expect**: the backend logs `reason=empty_selection_received` at WARN and falls back to no-narrowing — the UI gate is the primary defense (per [`chat-ws-message.md`](./contracts/chat-ws-message.md)).

## 5. Cross-cutting verification

- **Constitution III (≥90% coverage on changed code)**: run the test suite and confirm coverage for the changed paths is ≥90%.

  ```powershell
  cd src; pytest --cov; ruff check .
  ```

- **Constitution VIII (UI primitives)**: visually scan the changed components — agent header, banner, ToolPicker popover, per-tool rows — and confirm no new primitive components were introduced.
- **Constitution IX (auto migrations)**: drop the local DB, restart the backend, confirm the schema delta is applied automatically and the backfill runs idempotently on a second restart with no errors.
- **Constitution X (browser-verified UI)**: every story above must be exercised in a real browser before declaring complete.
- **SC-007 (no regression in send latency)**: open a chat, hit "send" and time from click to first frame of "thinking" — confirm within ±10% of pre-feature baseline.
