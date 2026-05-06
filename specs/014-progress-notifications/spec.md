# Feature Specification: In-Chat Progress Notifications & Persistent Step Trail

**Feature Branch**: `014-progress-notifications`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "As a user, I want to see progress notifications in the chat when my query is being processed. While waiting for tools to be aggregated, display rotating cosmic-themed words (Accelerating, Aligning, …, Traversing). Output the steps the system is taking. Instead of showing which tools are being called in the processing message, have those messages persist in the chat so a user can see what is being called (collapsible, with collapse state persisted across a session)."

## Clarifications

### Session 2026-05-06

- Q: What counts as a "step" that gets its own persistent chat entry? → A: Tool invocations + agent hand-offs + any explicit orchestrator phase (e.g., planning, retrieval, synthesis) — i.e., every step the system takes that is externally observable, not just raw tool calls.
- Q: How much detail does each step entry expose when expanded? → A: Step name + truncated arguments + a brief, truncated result summary. Full payloads are not stored or rendered; truncation policy applies uniformly across step types. **Constraint:** the rendered/persisted entry MUST NOT expose HIPAA-protected health information (PHI). Any PHI present in upstream arguments or results MUST be redacted before the entry is rendered or persisted.
- Q: Default collapse state for errored / cancelled step entries after the turn completes? → A: Successful entries collapse by default; errored and cancelled entries default to expanded so failures stay visible. The user's manual collapse/expand override still wins and persists for the session.
- Q: When the user cancels a query mid-flight, what happens to in-progress steps? → A: Best-effort abort. The system fires a cancellation signal so cancellable work stops as soon as possible; steps already in flight that cannot be cancelled (e.g., outstanding external API requests) are allowed to complete, but their results are discarded — not used in the assistant's reply and not rendered into the step entry beyond the cancelled marker.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ambient progress feedback while waiting (Priority: P1)

When a user submits a query and the system is busy thinking or calling tools, the chat surface immediately shows a single, gently animated progress indicator that cycles through cosmic-themed words ("Astralizing…", "Resonating…", "Traversing…"). The indicator never names what is actually being done internally — it only signals that work is in flight.

**Why this priority**: Without any feedback, users currently stare at a blank chat for several seconds and often think the system is stuck. This is the minimum viable improvement and the highest-value piece of the feature: it can ship by itself and immediately reduces perceived latency and anxiety, even before the persistent-step trail is built.

**Independent Test**: Submit any query that takes longer than ~500 ms. Verify a rotating word from the approved list appears within half a second of submission, the word changes periodically while work continues, and the indicator disappears once the assistant's reply is delivered.

**Acceptance Scenarios**:

1. **Given** the user has submitted a query, **When** the system begins processing, **Then** a progress indicator appears in the chat showing one of the approved cosmic words.
2. **Given** the progress indicator is visible, **When** processing continues for several seconds, **Then** the displayed word rotates to a different word from the approved list at a regular cadence.
3. **Given** the progress indicator is visible, **When** the assistant's reply is fully delivered (or the query is cancelled/errors out), **Then** the indicator is removed from view.
4. **Given** a query completes very quickly (under ~500 ms), **When** the response is returned, **Then** the indicator either does not appear or appears only briefly without flickering jarringly.

---

### User Story 2 - Persistent in-chat trail of system steps (Priority: P2)

As the system invokes tools to answer the query, each tool invocation is rendered as its own entry in the chat conversation — appearing live as it starts, updating as it completes, and remaining visible in the conversation thread after the assistant's reply has finished. The user can scroll back through any prior turn and see exactly which steps the system took to produce that answer.

**Why this priority**: This delivers transparency and trust — users (especially researchers reviewing grant outputs or audit trails) can see what the system actually did. It builds on top of P1 but is meaningful even if collapse-state persistence (P3) is not yet implemented.

**Independent Test**: Submit a query that is known to trigger one or more tool calls. Verify that each tool invocation appears as a labeled entry in the chat as it begins, that those entries remain in the chat after the assistant reply finishes, and that scrolling back to that turn later in the same chat still shows them.

**Acceptance Scenarios**:

1. **Given** the system invokes a tool while processing a query, **When** the tool call begins, **Then** a step entry labeled with that tool/step name appears in the chat between the user's message and the assistant's eventual reply.
2. **Given** a step entry is visible, **When** the tool call completes, **Then** the entry's status updates (e.g., from "in progress" to "complete") without being removed.
3. **Given** the assistant's reply has finished delivering, **When** the user reviews the conversation, **Then** every step entry from that turn remains visible in the chat alongside the user message and assistant reply.
4. **Given** multiple tools are invoked during a single turn, **When** the user views the chat, **Then** each tool invocation is shown as a distinct entry in the order it began.
5. **Given** a tool call fails or returns an error, **When** the entry's final state is rendered, **Then** the entry visually indicates the error state and remains in the chat.

---

### User Story 3 - Collapsible step entries with session-persistent state (Priority: P3)

Step entries are collapsible. By default, while a step is in progress it is expanded (so the user can watch live updates). Once it finishes successfully, it collapses to a single-line summary to keep the chat scannable; if it ends in an errored or cancelled state, it stays expanded so the user immediately sees what went wrong. The user can manually expand or collapse any entry, and that choice is remembered across page reloads within the same browser session.

**Why this priority**: This is a polish/usability layer on top of P2. It keeps long histories tidy without losing information and respects the user's preference within the working session. Lower priority because the core value lands once P2 ships.

**Independent Test**: After a query that produces several step entries has completed, manually expand and collapse different entries. Reload the chat page within the same browser session. Verify each entry's expanded/collapsed state matches what the user last set.

**Acceptance Scenarios**:

1. **Given** a step entry is in progress, **When** it first appears in the chat, **Then** it is shown in its expanded (detailed) form by default.
2. **Given** a step entry has completed successfully, **When** the assistant's reply finishes delivering, **Then** the entry collapses to a compact summary by default.
3. **Given** a step entry ends in an errored or cancelled state, **When** the assistant's reply finishes delivering, **Then** the entry remains expanded by default so the user can see what failed.
4. **Given** a collapsed step entry, **When** the user clicks the entry's expand affordance, **Then** the entry expands to show its details.
5. **Given** the user has manually changed the expanded/collapsed state of one or more entries, **When** the user reloads the chat page within the same browser session, **Then** each entry's state matches what the user last set.
6. **Given** the user opens a different chat and returns to this one within the same session, **When** the step entries are re-rendered, **Then** their per-entry collapse state is preserved.

---

### Edge Cases

- **Query completes with no tool calls** — the rotating word indicator still shows during whatever processing time exists; no persistent step entries are created for that turn.
- **Tool call errors out** — the step entry persists with a clearly visible error state; it does not silently disappear.
- **Tool calls run in parallel** — each is a distinct entry, ordered by start time; concurrent in-progress entries are all visible.
- **Very long-running tool call** — the rotating word indicator continues cycling indefinitely; the corresponding step entry stays in its in-progress state until the call completes or is cancelled.
- **User cancels the query mid-flight** — the rotating indicator disappears immediately; the system fires a cancellation signal so cancellable in-flight steps stop as soon as possible. Non-cancellable in-flight steps (e.g., already-issued external API calls) are allowed to complete, but their results are discarded — not used in the assistant's reply, not rendered beyond the entry's cancelled marker. All in-progress step entries are marked as cancelled and remain visible in the chat.
- **Connection drops during processing** — on reconnection or refresh, completed step entries (which are part of the chat record) are still visible; an in-progress entry that never completed is visibly marked as interrupted rather than appearing eternally in-progress.
- **User scrolls up while processing** — the chat does not force-scroll the user back down; the indicator and new step entries appear at the bottom and the user can continue reading prior content uninterrupted.
- **Many step entries in one turn** — the chat remains scrollable and readable; successful entries collapse by default after the turn (US3) to keep the visible footprint small, while errored/cancelled entries remain expanded so failures are not buried.
- **User collapses an entry, then views the same chat in a different browser/device** — collapse state does not need to follow the user across devices; it is scoped to the local browser session.

## Requirements *(mandatory)*

### Functional Requirements

#### Rotating progress indicator

- **FR-001**: While a user query is being processed, the system MUST display a single progress indicator in the chat associated with that turn.
- **FR-002**: The indicator MUST display one word at a time, drawn from the following approved set: Accelerating, Aligning, Ascending, Astralizing, Attuning, Beamforming, Bending, Binary-pairing, Cascading, Coalescing, Collapsing, Colliding, Condensing, Conjoining, Converging, Crystallizing, Decelerating, Decoupling, Detaching, Dilating, Discerning, Displacing, Drifting, Emanating, Entangling, Expanding, Fluctuating, Fluxing, Gravitating, Illuminating, Inflating, Ionizing, Iterating, Launching, Levitating, Manifesting, Materializing, Merging, Navigating, Orbiting, Oscillating, Phasing, Polarizing, Projecting, Pulsating, Quantizing, Radiating, Refracting, Resonating, Rotating, Shimmering, Superposing, Syncing, Transmogrifying, Transmuting, Traversing.
- **FR-003**: The indicator's displayed word MUST change at a regular, perceptible cadence so long as work is still in flight, conveying ongoing activity.
- **FR-004**: The indicator MUST NOT name specific tools, internal services, or other implementation details — it is purely an ambient signal of activity.
- **FR-005**: The indicator MUST appear within a perceptibly short interval of query submission (so users feel immediate acknowledgement) and MUST be removed once the assistant's reply has finished delivering, the query is cancelled, or an error terminates the turn.
- **FR-006**: At most one rotating indicator MUST be visible per in-flight turn (regardless of how many tools or steps run in parallel beneath it).

#### Persistent step trail

- **FR-007**: For each discrete step the system takes while answering a query, the system MUST render a corresponding step entry in the chat for that turn. "Step" includes (a) tool invocations, (b) agent hand-offs (when the orchestrator routes the turn to a sub-agent), and (c) explicit orchestrator phases such as planning, retrieval, and synthesis. It does not include the LLM's internal "thinking"/reasoning blocks.
- **FR-008**: Each step entry MUST appear in the chat at (or near) the moment its underlying step begins, not only after the full response completes.
- **FR-009**: Each step entry MUST clearly label which tool or step it represents (e.g., the tool's display name).
- **FR-009a**: When expanded, each step entry MUST display three things: the step's name, a truncated representation of its inputs/arguments, and (once available) a brief, truncated summary of its result. Full raw inputs and full raw results MUST NOT be rendered or persisted as part of the entry; they remain in upstream logs/telemetry only. Truncation MUST be applied consistently across all step types (tool calls, agent hand-offs, orchestrator phases) so users get a uniform level of detail regardless of step type.
- **FR-009b**: Step entries MUST NOT expose HIPAA-protected health information (PHI) in either their truncated arguments or their truncated result summary. Any PHI present in the underlying step's inputs or outputs MUST be redacted before the entry is rendered or persisted as part of chat history. This applies to the entry both in real time during processing and to the saved entry retrieved later from chat history.
- **FR-010**: Each step entry MUST visually convey its current status, distinguishing at minimum: in progress, completed successfully, errored, and cancelled/interrupted.
- **FR-011**: Once the assistant's reply is delivered, all step entries from that turn MUST remain visible in the chat as part of the conversation history for that turn — they are not transient processing artifacts.
- **FR-012**: When the user revisits an existing chat, step entries from prior turns MUST still be visible in the order they originally occurred, alongside the user message and assistant reply for that turn.
- **FR-013**: When multiple step entries exist in the same turn, they MUST be displayed in the order their underlying steps began.

#### Collapsible behaviour & state persistence

- **FR-014**: Each step entry MUST provide a clear, accessible affordance to collapse or expand it.
- **FR-015**: Step entries that are still in progress MUST default to expanded so the user can see live updates.
- **FR-016**: Once a step entry has reached a terminal state and the surrounding turn has finished, the entry's default collapse state MUST depend on the terminal status: entries that completed successfully default to collapsed (showing a compact summary), while entries that errored or were cancelled default to expanded so failures stay visible. In all cases, the user's manual collapse/expand override (FR-017) takes precedence over this default.
- **FR-017**: The user's manual collapse/expand choice for any specific step entry MUST override the default.
- **FR-018**: A user's collapse/expand choice MUST persist across page reloads, navigation away from and back to the chat, and switching between chats — for the duration of the active browser session.
- **FR-019**: Collapse state persistence is NOT required to survive the end of the browser session, logout, or movement to a different device — it is scoped to the local session.

#### Cancellation

- **FR-020**: When the user cancels an in-flight query, the system MUST fire a cancellation signal so that cancellable in-progress steps stop as soon as possible. Steps that cannot be cancelled (e.g., outstanding external requests already in flight) MAY complete in the background, but their results MUST be discarded — they MUST NOT influence the assistant's reply and MUST NOT be rendered into the step entry beyond the cancelled marker.
- **FR-021**: On cancellation, every step entry that was still in progress MUST be marked as cancelled, MUST remain visible in the chat, and MUST default to expanded per FR-016.

### Key Entities *(include if feature involves data)*

- **Progress Indicator**: An ephemeral, per-turn display element. Has a single user-visible attribute — the currently displayed word, drawn from the approved set. Lives only for the duration of the in-flight turn; is not stored.
- **Step Entry**: A persistent record of one step (tool invocation, agent hand-off, or orchestrator phase) performed while processing a turn. Attributes: identifier, label/name shown to the user, status (in progress / complete / error / cancelled), start time, end time (when applicable), a truncated representation of the step's inputs/arguments, and a brief truncated summary of the step's result (when available). Full raw inputs and full raw results are not part of the entry. Belongs to a single turn within a chat and is part of the chat's saved history.
- **Step Collapse State**: A per-user, per-session mapping of step entry identifier → collapsed boolean, scoped to the user's local browser session. Not persisted to long-term storage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Within 500 ms of submitting a query, 100% of users see a visible progress indicator showing one of the approved words.
- **SC-002**: While a query is in flight for at least 3 seconds, the indicator's word changes at least once per second on average, never stalls on a single word for more than 3 seconds, and never displays a word outside the approved set.
- **SC-003**: For every tool/step the system invokes during a turn, a corresponding step entry appears in the chat within 1 second of that step beginning, with no missing entries — verifiable by comparing the system's step log against the entries shown in the chat for the turn.
- **SC-004**: After a query completes, 100% of step entries from that turn remain visible when the user scrolls within the chat and when the user navigates away and returns within the session.
- **SC-005**: A user who collapses or expands a step entry, then reloads the page within the same session, sees that entry in the same state they left it, in 100% of cases.
- **SC-006**: After this feature ships, the rate at which users cancel an in-flight query or refresh the page during the first 10 seconds of processing drops by at least 30% compared to the prior baseline (proxy for reduced uncertainty).
- **SC-007**: At least 80% of surveyed users report (within one month of release) that they can tell what the system did to answer their query, without needing to ask support or look at logs.
- **SC-008**: Across an audit sample of step entries (rendered live and retrieved from history), 100% are free of HIPAA-protected health information — verifiable by sampling step entries from chats that involve clinical or patient-related content and confirming PHI is redacted in both arguments and result summaries.

## Assumptions

- **"Across a session" = local browser session.** The user's collapse/expand state for individual step entries persists for the lifetime of the active browser session (surviving page refreshes and chat-switching) but is not required to follow the user to a different browser, device, or post-logout session.
- **The step entries themselves are part of chat history.** They are persisted alongside the chat's messages and remain retrievable whenever the chat itself is retrievable (existing chat-history behaviour applies). This is distinct from collapse state, which is session-scoped UI preference.
- **Default collapse behaviour after completion is status-dependent.** Once a turn finishes, successful step entries collapse to a compact summary by default to keep long chats scannable; errored and cancelled entries default to expanded so failures stay visible. Users can override either default per entry, and overrides persist for the session.
- **One rotating indicator per turn.** Even when many tools run in parallel, the user sees a single ambient indicator at a time; per-step status lives in the step entries themselves.
- **Word rotation is randomized.** Words are chosen at random from the approved list rather than cycled in order, matching the conversational/playful feel the cosmic vocabulary implies.
- **"Steps" is defined in FR-007** — tool invocations, agent hand-offs, and explicit orchestrator phases (planning, retrieval, synthesis). LLM internal reasoning is excluded.
- **Existing chat rendering accommodates new entry types.** The chat surface already supports rendering structured turn content alongside user/assistant messages, so step entries can be added as a new entry type without redesigning the chat shell.
- **Existing tool-call telemetry is sufficient.** The orchestrator already emits start/complete/error events for each tool call (used elsewhere for logging and audit); the same stream drives the step entries — no new instrumentation is assumed beyond surfacing this data to the chat.
- **Accessibility baseline.** The progress indicator and collapse affordances meet the project's existing accessibility expectations (keyboard reachable, screen-reader announcements on state change, no reliance on motion alone) — no new accessibility infrastructure is introduced.
