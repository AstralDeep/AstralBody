# Feature Specification: Agent Visibility, Active-Agent Clarity, Per-Tool Permissions, and In-Chat Tool Picker

**Feature Branch**: `013-agent-visibility-tool-picker`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Tasks remaining for the user story 'As a user, I want to be able to create and test a new agent through the UI.' — (1) Make agents the user created appear in My Agents, not just Public Agents; (2) Make it clear what agent is being used when starting a new chat or message; (3) Per-tool read/write/etc. permissions, with the (i) info popups appearing before the on toggle is switched on. Plus the related story 'As a user, I want to select the tools I want to call with a query.' — (1) Add an option in chat to allow the user to pick which tools they want to use; (2) Ensure the system still respects scopes and only consults the selected tools for the query."

## Clarifications

### Session 2026-05-06

- Q: When the user has explicitly deselected every tool in the in-chat tool picker, what should happen on send? → A: Block sending until at least one tool is selected; show a clear tooltip/message on the send button explaining why.
- Q: How should existing agent-wide scope settings carry forward when per-tool permissions ship? → A: For each tool, set its per-tool permission ON iff the corresponding scope was previously enabled on that agent (1:1 preserve of prior intent; never widens).
- Q: What happens when a user tries to send a message in a chat whose active agent is no longer available (deleted, deprecated, or critical permission revoked)? → A: Block send; keep the chat history visible; show a banner that explains the agent is unavailable and offers actions (start a new chat or pick another agent).
- Q: Where do agents that are owned by the current user AND flagged public appear? → A: In both "My Agents" (because the user owns them) and "Public Agents" (because they are public), exactly as other users see them.
- Q: How long does a user's in-chat tool selection persist? → A: As a per-user global preference that applies across chats and agents, plus a "reset to default" action that reverts the selection to the agent's full permission-allowed tool set.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Created agents appear under "My Agents" (Priority: P1)

A user who has created an agent through the UI — whether the agent is still a draft, currently being tested, or published — expects to find that agent listed under the "My Agents" view of their workspace, not only under "Public Agents" or buried in a separate "Drafts" surface they have to remember to open.

**Why this priority**: This is a discoverability/correctness gap that breaks the core "create and test a new agent through the UI" story. If a user cannot find what they just made in the place labelled "mine," the rest of the agent-management UX is undermined. Highest priority because it is a small, foundational fix that other stories depend on (e.g., the active-agent indicator only matters once the user can locate their agent).

**Independent Test**: Sign in as a user, create a new agent through the UI, then open the agents listing and confirm the new agent appears in "My Agents" regardless of its lifecycle state (draft, testing, live), without needing to check the "Public Agents" or any separate tab.

**Acceptance Scenarios**:

1. **Given** the user has just created a new agent via the create-agent flow, **When** they open the agents listing and select "My Agents," **Then** the newly created agent is listed there with its name, current status (e.g., draft, testing, live), and an entry point to open or test it.
2. **Given** the user owns one or more agents in different lifecycle states (draft, testing, live), **When** they open "My Agents," **Then** all agents they own appear in that view, sorted in a consistent order, with their status visually indicated.
3. **Given** the user has agents that are also published as Public, **When** they look at "My Agents" vs. "Public Agents," **Then** their owned-and-public agents appear in **both** views — under "My Agents" because the user owns them, and under "Public Agents" because they are public — and the entries are clearly identifiable as the same agent (consistent name and identity across tabs).
4. **Given** the user has not created any agents yet, **When** they open "My Agents," **Then** they see an empty-state message that points them to the create-agent flow.

---

### User Story 2 - Active agent is clearly indicated in chat (Priority: P2)

When a user starts a new chat or sends a message, the chat interface clearly shows which agent is handling the conversation, so the user is never uncertain about who they are talking to or whose tool/scope settings are in effect.

**Why this priority**: Once users can find their agents (Story 1), the next confusion point is "which one am I actually using right now?" Affects every chat interaction, but is purely a clarity/labeling change rather than a correctness blocker, so it sits below Story 1.

**Independent Test**: Open a chat with a specific agent, observe that the agent's name (and a distinguishing visual cue) is shown clearly in the chat surface, then send a message and confirm replies are also attributed to that same agent.

**Acceptance Scenarios**:

1. **Given** the user opens a new chat, **When** the chat surface renders, **Then** the active agent's name and a distinguishing visual cue are visible in a persistent location of the chat (such as the chat header) before the user types anything.
2. **Given** the user is mid-conversation, **When** an agent reply arrives, **Then** the reply is visually attributed to the agent that produced it.
3. **Given** the user has multiple agents and switches between them, **When** they switch the active agent, **Then** the displayed active-agent indicator updates immediately and is unambiguous.
4. **Given** an agent is being deprecated, deleted, or unavailable, **When** the user has that chat open, **Then** the indicator reflects the unavailable state, the prior chat history remains visible, the send affordance is blocked, and a banner explains the situation and offers actions (start new chat, pick another agent) — the system never silently re-routes to a different agent.

---

### User Story 3 - Per-tool permissions with proactive info popups (Priority: P3)

When configuring an agent's tools, the user controls read / write / search / system permissions on a per-tool basis (not as one switch that applies to every tool the agent owns). The "(i)" info popup that explains what each permission grants is reachable and readable **before** the user flips the toggle on, so they understand the implication before consenting.

**Why this priority**: Improves correctness of consent and reduces the blast radius of accidental permission grants. It depends on the agent being discoverable (Story 1) but is independent of the chat-surface stories (2 and 4), so it can ship in parallel.

**Independent Test**: Open an agent's tool-permissions panel, locate any tool that defaults to off, hover or otherwise invoke its (i) info affordance, read the explanation while the toggle is still off, then enable the toggle for that single tool and confirm only that tool's permission changed — not all tools sharing that permission category.

**Acceptance Scenarios**:

1. **Given** the user is viewing an agent's tool-permissions panel, **When** they look at any tool's row, **Then** each permission (read, write, search, system, or whichever apply to that tool) appears as its own toggle scoped to that specific tool — not as a single agent-wide switch.
2. **Given** a tool's permission toggle is currently off, **When** the user hovers, taps, or focuses the (i) info affordance for that permission, **Then** an explanation appears describing exactly what enabling it would let the agent do, **before** the toggle has been flipped on.
3. **Given** the user enables one permission on one tool, **When** they save and re-open the panel, **Then** only that specific tool–permission pair is enabled; sibling tools remain at whatever state they had previously.
4. **Given** an agent has many tools, **When** the user opens the panel, **Then** the panel makes it easy to scan tools and their per-permission states without having to expand each one individually.
5. **Given** the user disables a permission on a tool that was previously enabled, **When** they save and that tool is later invoked, **Then** the system refuses calls that would have required the disabled permission for that specific tool.

---

### User Story 4 - User picks which tools the agent may use for a query (Priority: P3)

Within a chat, the user can choose which subset of an agent's tools the agent is allowed to consider for the next query (or an ongoing chat), so they can constrain behavior on demand without changing the agent's underlying configuration. The system continues to enforce existing scope and per-tool permissions on top of the user's selection — selection narrows, never widens, what the agent may do.

**Why this priority**: Adds a useful expressivity layer for power users, but the agent still functions correctly without it (the existing scope/permission enforcement is the safety net). Same priority tier as Story 3 because they are both refinements rather than blockers, and they can ship independently.

**Independent Test**: Start a chat with an agent that has multiple tools enabled, open the in-chat tool picker, select a strict subset of tools, send a query that would normally hit a deselected tool, and confirm the agent does not invoke any deselected tool — even if it would have been allowed by the underlying scopes.

**Acceptance Scenarios**:

1. **Given** the user is in a chat with an agent that has multiple tools available, **When** they open the in-chat tool picker, **Then** they see a list of tools the agent is permitted to use (i.e., the set already allowed by scopes and per-tool permissions), with each tool selectable.
2. **Given** the user has selected a subset of tools, **When** they send a query, **Then** the agent only considers the selected subset for that query and ignores deselected tools entirely, even if a deselected tool would otherwise have matched.
3. **Given** the user has not made an explicit selection yet, **When** they send a query, **Then** the system uses the agent's full permission-allowed tool set as the default, preserving today's behavior.
4. **Given** the user selects a tool that is blocked by scope or per-tool permission, **When** they attempt to send a query, **Then** the system either prevents the selection or surfaces a clear notice that the tool is disabled by permissions and will not be used.
5. **Given** the user changes the selection mid-chat, **When** they send a subsequent message, **Then** the new selection applies to that message; behavior on prior messages is not retroactively altered.
6. **Given** the system would normally select a tool not on the user's allowed list, **When** processing the query, **Then** logs/observability reflect that the tool was excluded due to user selection (not just scope), so the decision is auditable.
7. **Given** the user has previously chosen a subset of tools for one agent, **When** they later open a chat (with the same or a different agent), **Then** their saved per-user selection is reapplied: tools shared with the new agent reflect the saved on/off state; tools the new agent does not have are silently ignored; the user does not have to redo the selection.
8. **Given** the user has narrowed their selection and wants to undo it, **When** they click the "reset to default" action, **Then** the selection for the current agent reverts to that agent's full permission-allowed tool set, the persisted per-user preference is updated, and subsequent messages use the full permitted set unless the user narrows again.

---

### Edge Cases

- **Renamed or deleted agent while a chat is open**: the active-agent indicator must reflect the new state; for deleted/deprecated/permission-revoked cases, send is blocked and a banner offers next steps (per FR-009). The system never silently routes to a different agent.
- **Agent owned by the user but published as public**: it appears in both "My Agents" (owned) and "Public Agents" (public), as the same identifiable agent across both tabs.
- **Tool with no read/write distinction** (e.g., a pure search or system tool): the per-tool permissions panel should only show toggles relevant to that tool — not greyed-out toggles for permissions that do not apply.
- **User selects zero tools in the in-chat picker**: send is blocked until at least one tool is selected, and the chat surface explains why and how to recover.
- **User selects a tool, then the underlying permission for that tool is revoked elsewhere**: subsequent queries must respect the revocation regardless of the prior selection.
- **User's saved per-user selection contains tools the new agent does not have**: those tools are silently ignored; the user does not see an error or a list of "missing" tools; only tools that exist on the current agent and are permitted are honored.
- **Long tool names or many tools**: the in-chat tool picker and the per-tool permissions panel must remain usable (scrollable / searchable) for agents with dozens of tools.
- **(i) popup on touch-only devices**: the explanation must be accessible without hover (tap, focus, or persistent disclosure).
- **Migration from existing global scopes**: each tool's per-tool permission is initialized to ON iff the corresponding agent-wide scope was previously enabled; no widening, no forced re-toggling.

## Requirements *(mandatory)*

### Functional Requirements

#### Agent visibility (Story 1)

- **FR-001**: The agents listing MUST place every agent the user owns under "My Agents," regardless of lifecycle state (draft, testing, live, deprecated).
- **FR-002**: "My Agents" MUST visually indicate each agent's current lifecycle state.
- **FR-003**: When the user owns an agent that is also flagged public, that agent MUST appear in both "My Agents" (because the user owns it) and "Public Agents" (because it is public). The two tab entries MUST refer to the same underlying agent (same name, same identity) so the user understands they are seeing one agent surfaced in two views, not two distinct agents.
- **FR-004**: "My Agents" MUST show a clear empty state pointing to the create-agent flow when the user owns no agents.
- **FR-005**: "My Agents" MUST update to include a newly created agent without requiring a manual page reload.

#### Active-agent clarity in chat (Story 2)

- **FR-006**: Every chat surface MUST display the name of the agent currently handling the chat in a persistent location that is visible before the user sends a message.
- **FR-007**: Each agent reply MUST be visually attributed to the specific agent that produced it.
- **FR-008**: When the user switches the active agent, the indicator MUST update immediately to reflect the change.
- **FR-009**: If the active agent becomes unavailable (deleted, deprecated, permission revoked), the indicator MUST reflect the unavailable state, the chat history MUST remain visible, the send affordance MUST be blocked, and a clear banner MUST explain the unavailability and offer actionable next steps (e.g., start a new chat, pick another agent). The system MUST NOT silently route messages to a different agent or substitute a fallback agent.

#### Per-tool permissions with proactive info (Story 3)

- **FR-010**: Tool permissions (read, write, search, system, or whichever apply) MUST be configurable on a per-tool basis. A single toggle MUST NOT apply the same permission to every tool the agent owns.
- **FR-011**: For every per-tool permission toggle, the (i) info affordance MUST be reachable while the toggle is in the off state, and the explanation MUST describe exactly what enabling the toggle would allow.
- **FR-012**: Toggling a permission on or off for one tool MUST NOT change the state of any other tool.
- **FR-013**: When a per-tool permission is off, the system MUST refuse any agent action that would require that permission on that specific tool — even if the same permission is enabled on a sibling tool.
- **FR-014**: The per-tool permissions panel MUST surface only the permissions that apply to each specific tool — not greyed-out toggles for permissions a tool does not support.
- **FR-015**: When per-tool permissions are introduced, every existing agent's per-tool permissions MUST be initialized by a 1:1 carry-forward from its existing agent-wide scope settings: for each tool that supports a given permission kind (read / write / search / system), the per-tool permission MUST be set to ON if and only if the corresponding scope was previously enabled for that agent. The migration MUST NOT enable a permission that was not previously enabled at the scope level (no widening), and MUST NOT require the user to re-toggle previously consented permissions.

#### In-chat tool picker (Story 4)

- **FR-016**: The chat surface MUST provide an affordance for the user to pick which subset of the active agent's tools may be used for upcoming queries in that chat.
- **FR-017**: The picker MUST list only tools that are already permitted by the agent's scope and per-tool permissions; tools blocked by permissions MUST NOT appear as selectable, OR if shown, MUST be visibly marked as unavailable with the reason.
- **FR-018**: When the user has made a selection, the system MUST consider only selected tools when handling the query and MUST NOT invoke any deselected tool, even if it would otherwise have matched.
- **FR-019**: When the user has made no explicit selection, the system MUST default to the agent's full permission-allowed tool set (preserving current behavior).
- **FR-020**: The system MUST continue to enforce all existing scope and per-tool permission rules independently of the user's selection — selection narrows but never widens.
- **FR-021**: When the user has explicitly deselected every tool in the in-chat tool picker, the system MUST block sending until at least one tool is selected and MUST display a clear, persistent message on or near the send affordance that explains why send is disabled and how to re-enable it (i.e., select at least one tool).
- **FR-022**: A change to the selection MUST apply only to messages sent after the change; prior messages MUST NOT be retroactively reinterpreted.
- **FR-023**: The system MUST record (in logs/observability) when a tool was excluded specifically because of the user's in-chat selection, distinguishing that exclusion from scope/permission exclusion.
- **FR-024**: The user's in-chat tool selection MUST persist as a per-user global preference that survives page reload, browser/device switch, and re-opening any chat. The preference MUST apply across every chat and every agent the user opens. When the active agent does not include a tool that is in the saved preference, that tool MUST be silently ignored for the current agent (no error). When the active agent includes a tool that is permitted but not in the saved preference, that tool MUST be treated as deselected.
- **FR-025**: The in-chat tool picker MUST provide a clearly visible "reset to default" action that reverts the user's selection for the current agent back to that agent's full permission-allowed tool set. Reset MUST take effect immediately and MUST update the persisted per-user preference accordingly.

### Key Entities *(include if feature involves data)*

- **Agent**: An assistant the user can chat with. Has an owner (the creator), a lifecycle state (e.g., draft, testing, live), an optional public-visibility flag, and a set of tools.
- **Tool**: A capability an agent can invoke. Each tool has a name, a description, an (i) info explanation, and a set of permissions that apply to it (a subset of read / write / search / system, depending on the tool).
- **Per-Tool Permission**: A per-(user, agent, tool, permission-kind) on/off setting that gates whether the agent may use a given capability of a given tool on the user's behalf.
- **Active Agent (per chat)**: The agent currently associated with a given chat session. Surfaced in the chat UI and used to route messages.
- **In-Chat Tool Selection**: A per-user global preference recording which tools the user wants agents to consider for queries. Applied across all chats and agents; tools that do not exist on the current agent are silently ignored. Defaults to the full permitted set for each agent when the user has not narrowed the selection. Includes a "reset to default" action that reverts the current agent's selection to its full permission-allowed set.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After creating a new agent, **100%** of users find that agent listed under "My Agents" without first having to look anywhere else (verified by usability test or instrumentation that records where users first locate their newly created agent).
- **SC-002**: In observed chat sessions, **at least 95%** of users can correctly identify which agent is currently handling the conversation within 5 seconds of opening a chat (verified by usability test or by surveying users after the fact).
- **SC-003**: Among users who change tool permissions, **at least 90%** report that the (i) info popup gave them enough understanding of the permission **before** they enabled it — measured via in-product feedback or post-task survey.
- **SC-004**: After the per-tool permissions change ships, the rate of incidents/support tickets describing "an agent did something I did not intend it to" attributable to overly broad permissions drops by **at least 50%** compared to the baseline measured in the prior equivalent period.
- **SC-005**: The system enforces the in-chat tool selection with **100% correctness** in automated tests: across all test queries, no deselected tool is invoked, and selection never grants access to a tool that scope/permissions would have disallowed.
- **SC-006**: For users who use the in-chat tool picker at least once, **at least 80%** report (via in-product feedback) that it helped them get a more focused or predictable response than the default behavior.
- **SC-007**: No regression in the time it takes to send a message from an existing chat — median time from "open chat" to "first message sent" stays within **±10%** of the pre-feature baseline.

## Assumptions

- "My Agents" is defined as the set of agents the user owns, regardless of lifecycle state. Drafts, in-testing, and live agents the user created all qualify.
- "Public Agents" continues to mean agents flagged public. Agents the user owns AND has flagged public surface in both "My Agents" (ownership) and "Public Agents" (visibility), as the same identifiable agent across both tabs (see FR-003).
- Per-tool permissions replace, not augment, the previous agent-wide scope toggles for the purposes of the user-facing UI. Existing scope settings are migrated forward 1:1: for each tool, a per-tool permission is initialized ON iff the corresponding scope was previously enabled for that agent (see FR-015).
- The in-chat tool picker stores the user's selection as a per-user global preference that applies across all chats and agents (see FR-024). When the user opens an agent whose available tools differ from the saved selection, only tools that exist for the current agent and are permitted by scope/per-tool permissions take effect; tools in the saved preference that are not part of the current agent are silently ignored. A "reset to default" action reverts the selection to the current agent's full permission-allowed tool set (see FR-025).
- Default behavior when the user has made no explicit selection is identical to today's behavior: the agent considers its full permission-allowed tool set.
- The (i) info content for each permission already exists in the system (or is straightforward to author); the change here is surfacing it pre-toggle, not authoring new copy from scratch.
- No new external integrations or third-party services are introduced by this feature.
- Accessibility (keyboard, screen reader, touch) for the (i) info affordance and the in-chat picker follows existing product accessibility standards.
