# Feature Specification: LLM Text-Only Chat When No Agents Enabled

**Feature Branch**: `008-llm-text-only-chat`
**Created**: 2026-05-01
**Status**: Draft
**Input**: User description: "As a user, I want to use the LLM even if no agents are enabled. If a user does not have any agents enabled and they send a chat message. they should be able to have a text-only chat with the llm instead of seeing an alert."

## Clarifications

### Session 2026-05-01

- Q: How should the LLM be instructed in text-only mode? → A: Add a text-only addendum to the existing system prompt instructing the LLM about its limitations and how to surface them.
- Q: When a chat has prior tool_call / tool_result entries in history, what should the LLM see during a text-only turn? → A: Send full history unchanged; rely on the system-prompt addendum to prevent new tool-call attempts.
- Q: Where does the text-only mode indicator live in the UI? → A: Persistent banner/pill at the top of the chat surface while text-only mode is active, with an inline link/button to the agent management surface; disappears on the next turn that has tools. The onboarding tutorial MUST also include a step that tells users to turn on agents.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plain LLM conversation when no agents are available (Priority: P1)

A user opens AstralBody, has a working LLM provider configured, and sends a chat message. No agents are connected, or every available agent's tools are blocked by permissions or system policy. Instead of being told to wait for agents, the user receives a normal text reply from the LLM and can continue a back-and-forth conversation that reads, summarizes, reasons, drafts, or answers questions using only the LLM's built-in knowledge — no tool calls, no file actions, no external integrations.

**Why this priority**: This is the entire feature. Today the user is blocked at the door with a "No agents connected" warning even though the LLM is fully configured and reachable. Removing that blocker turns AstralBody into a usable chat surface from the very first message, well before any agent is set up. It also preserves the value of the LLM configuration the user just completed in feature 006.

**Independent Test**: With a configured LLM provider and zero connected agents (or all tools filtered out), send a plain question such as "What is the capital of France?" and confirm the assistant replies with a normal text answer that is saved to chat history. No warning alert is shown for the absence of agents.

**Acceptance Scenarios**:

1. **Given** a user with a valid LLM configuration and no connected agents, **When** they send a chat message, **Then** the system replies with a text-only LLM response and persists the exchange to chat history.
2. **Given** agents are connected but every tool is filtered out by user permissions or system security flags, **When** the user sends a chat message, **Then** the system replies with a text-only LLM response — the same path as no-agents.
3. **Given** the user is in a draft test chat for a specific agent that exposes no usable tools, **When** they send a chat message, **Then** the system continues to surface the existing draft-test guidance (text-only fallback does not silently mask the misconfigured draft scenario).
4. **Given** the user has no LLM configured AND no connected agents, **When** they send a chat message, **Then** the existing "LLM unavailable — set your own provider in settings." alert is shown (LLM-unavailable takes precedence over the new text-only path).

---

### User Story 2 - Persistent text-only banner with path to enable agents (Priority: P2)

A user in text-only mode sees a persistent banner (or pill) at the top of the chat surface that states the assistant is currently operating without agents and offers an inline link/button to the agent management surface. The banner is visible for as long as text-only mode is active and disappears on the next turn that has at least one tool available. This way, when the user asks for an action that would normally require an agent (e.g., "read this file", "search my drive"), they understand why action-style requests are not being executed and have a one-click path to enable agents.

**Why this priority**: Without this signal, a user who expected agent-backed behavior may believe the system is broken when their "summarize this PDF" request comes back as generic advice. The persistent banner preserves trust, gives a concrete next step, and pairs cleanly with the per-turn re-evaluation rule (FR-005) — toggling on/off based on the same tool-availability state that drives dispatch. It is P2 because the P1 chat path is already valuable on its own — most first messages are exploratory, not action-oriented.

**Independent Test**: With no agents enabled, open a chat. The persistent banner is visible at the top of the chat surface, announces text-only mode, and links to the agent management surface. Enable an agent and send another message; the banner disappears on that next turn without requiring a reload.

**Acceptance Scenarios**:

1. **Given** a user is in a chat session with no available tools, **When** the chat surface is rendered, **Then** a persistent banner/pill is visible at the top of the chat conveying text-only mode and exposing an inline link/button to the agent management surface.
2. **Given** the user enables an agent mid-conversation, **When** they send the next message (the next turn has at least one tool available), **Then** the banner is removed for that turn without requiring a reload.
3. **Given** the user clicks the banner's "enable agents" link, **When** the action fires, **Then** they are navigated to the existing agent management surface.

---

### User Story 3 - Onboarding tutorial step pointing users to agents (Priority: P2)

The first-run / onboarding tutorial includes a dedicated step that tells the user how to turn on agents, so users who land in text-only mode during their first session learn that agents exist and how to enable them rather than assuming the LLM-only experience is the entire product.

**Why this priority**: New users currently have no clear path to discover agents until they are already mid-chat. Adding a tutorial step ahead of the first chat reduces the chance they get stuck in text-only mode by accident, complements the persistent banner (US2), and shortens time-to-first-agent. P2 because it improves discoverability but is not on the critical path of P1's "first chat works".

**Independent Test**: A user going through onboarding for the first time sees a step that explains agents and points to the agent management surface; completing that step is sufficient to demonstrate agent-enablement guidance regardless of whether the persistent banner has been built yet.

**Acceptance Scenarios**:

1. **Given** a new user is going through the onboarding tutorial, **When** they reach the agent-related step, **Then** the step explains what agents are and tells them how to turn agents on.
2. **Given** a user completes the tutorial step, **When** they send their first chat message, **Then** they understand whether they are in text-only mode and how to change it.

---

### Edge Cases

- **Mid-conversation agent state changes**: A user starts text-only, an agent registers partway through, and the next message should be able to use that agent's tools — the system MUST evaluate tool availability per-turn, not once per chat.
- **Mid-conversation agent disconnect**: An agent disconnects between turns. The next turn falls back to text-only without dropping the conversation or showing an error.
- **Streaming/long answers**: Text-only LLM replies that take longer than a typical tool call still surface "thinking" status to the user and stream / arrive without timing out.
- **Tool-call attempts from history**: If chat history contains prior tool calls (from a turn when agents were available), the text-only turn dispatches the full history unchanged (tool_call and tool_result entries preserved). The system-prompt addendum (FR-006a) is the mechanism that prevents the LLM from attempting new tool calls; references to past tool output remain readable as plain text. Dispatch MUST NOT crash or re-invoke missing tools.
- **Draft-agent test chats with zero tools**: A draft test chat targets a specific agent that ends up exposing no tools (filtered or misconfigured). The system MUST keep its existing draft-test diagnostics rather than silently falling through to text-only, because the user explicitly opted into testing that draft.
- **File upload with no agents**: A user uploads a file (feature 002) and then chats with no agents enabled. The text-only LLM MUST be able to discuss the upload by name/metadata, but cannot read its bytes; the response makes that limitation clear if the user asks for content-level work.
- **Long chat history**: Existing chat history is included in the LLM call as it is today, subject to the same context-window handling — text-only mode does not change history behavior.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a user with a working LLM configuration to send and receive chat messages when zero agent tools are available, replacing the current "No agents connected" warning with a normal LLM text response.
- **FR-002**: The system MUST treat "no tools available" as the union of three conditions: no agents are connected, all connected agents are filtered out by user-level tool permissions, and all connected agents are blocked by system security flags. Each of these MUST trigger the text-only path.
- **FR-003**: The system MUST continue to surface the existing "LLM unavailable" alert and refuse to dispatch when neither the user's LLM credentials nor the operator default credentials can produce a working LLM client. LLM-unavailable takes precedence over text-only fallback.
- **FR-004**: User and assistant messages exchanged in text-only mode MUST be persisted to the same chat history (per chat_id, per user) used by tool-augmented conversations, so reloading the chat shows the full thread.
- **FR-005**: The system MUST evaluate tool availability per chat turn, so that enabling or disabling an agent between turns takes effect on the very next message without requiring a chat restart.
- **FR-006**: When an action-requiring request cannot be fulfilled because no tools are available, the assistant's response MUST avoid fabricating tool output and MUST make it clear (in the reply or via UI affordance) that no agents are currently enabled.
- **FR-006a**: In text-only mode, the system MUST extend the existing chat system prompt with a text-only addendum that instructs the LLM (a) that it currently has no tools/agents available, (b) that it MUST NOT fabricate tool output or pretend to invoke tools, and (c) that when the user requests an action that would require an agent, it should briefly state that no agents are enabled and suggest enabling one. The base system prompt used for tool-augmented turns MUST remain unchanged.
- **FR-007**: The user MUST be given a discoverable way, from a text-only chat, to navigate to the place where agents are enabled (consistent with the existing settings/agent management surface).
- **FR-007a**: The system MUST render a persistent banner/pill at the top of the chat surface whenever the current turn would dispatch in text-only mode. The banner MUST (a) state that the assistant is operating without agents and (b) expose an inline link/button to the agent management surface. The banner MUST disappear on the next turn that has at least one tool available, without requiring a reload.
- **FR-007b**: The onboarding tutorial MUST include a dedicated step that tells the user how to turn on agents and points to the agent management surface.
- **FR-008**: Chat status signals ("thinking", "done") shown to the user MUST behave the same way in text-only mode as in tool-augmented mode, so the user does not experience a degraded loading state.
- **FR-009**: Text-only chats MUST emit the same observability signals (structured logs / metrics) that tool-augmented chats emit for dispatch, completion, and failure, distinguishable from agent-backed turns so operators can measure how often the fallback fires.
- **FR-010**: Draft test chats (chats scoped to a specific draft agent) MUST retain their current behavior when that draft agent exposes no usable tools — the text-only fallback MUST NOT mask draft-configuration problems.
- **FR-011**: The change MUST NOT alter behavior of chat turns where at least one tool IS available — those turns continue to use the existing multi-turn ReAct loop without modification.
- **FR-012**: Text-only dispatch MUST send the full chat history (including any prior tool_call and tool_result entries) to the LLM unchanged. The system MUST NOT strip, summarize, or rewrite past tool messages on the fallback path.

### Key Entities *(include if feature involves data)*

- **Chat Turn**: A single user→assistant exchange within a chat. Carries: the user's message, the resolved tool list at dispatch time (which may be empty), the LLM credentials in effect, and the assistant's response. The new feature distinguishes turns dispatched with an empty tool list from turns dispatched with tools.
- **Tool Availability State**: The per-turn computed set of tools the user is allowed to invoke, derived from connected agents + user permissions + system security flags + draft-agent scope. Empty means text-only.
- **Chat History Entry**: An ordered sequence of user/assistant/tool messages persisted per (chat_id, user_id). Text-only turns add user + assistant entries; no tool entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of chat messages sent by a user with a working LLM and zero available tools result in an LLM-generated text response (or an LLM-side error surfaced clearly) — never the legacy "No agents connected" warning.
- **SC-002**: Chat-send latency for text-only turns is no slower than the median tool-augmented turn that does not invoke any tools (text-only must not introduce extra overhead vs. a tool-augmented turn that the model declines to use tools on).
- **SC-003**: Zero regressions on tool-augmented chats: existing acceptance scenarios for chats with at least one available tool continue to pass after this change.
- **SC-004**: A new user who has just configured an LLM but has not yet enabled any agents can send their first useful message and receive a substantive reply within their first session, with no error/warning alert in the chat surface.
- **SC-005**: When users ask action-requiring questions in text-only mode, the rate at which they discover and visit the agent-enablement surface (per the FR-007 affordance) is measurable — operators can quantify how often the fallback nudges users toward enabling agents.
- **SC-006**: Operators can distinguish text-only turns from tool-augmented turns in logs/metrics with no manual log inspection, enabling them to track adoption and abuse of the fallback path.

## Assumptions

- The user's LLM provider, once configured (via feature 006), is able to handle tool-less chat completions; no API or provider-side change is needed to support text-only mode.
- Chat history storage already supports user/assistant message pairs without any required tool-call entries (this is the same shape used today before any tools fire).
- The "LLM unavailable" pre-flight check stays as the higher-priority gate — if the LLM cannot be reached, the user still sees the existing settings prompt rather than a misleading text-only attempt.
- The existing per-turn tool-resolution logic (registered agents × user permissions × security flags × draft scope) is the single source of truth for "are tools available right now" — no new caching layer is needed.
- The mode indicator described in User Story 2 reuses existing primitive UI components per Constitution Principle VIII; no new primitives are introduced by this feature.
