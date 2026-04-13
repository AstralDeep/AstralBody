# Feature Specification: Real-Time Tool Streaming to UI

**Feature Branch**: `001-tool-stream-ui`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: "Implement streaming from tool to the UI. If a tool in an agent in the agents/ directory can stream real time data it needs to connect to the frontend session and the UI needs to update that component. If the user leaves the current chat session then the stream must stop, then if they return the stream must start again. Unsure whether the stream should go MCP tool -> agent -> orchestrator -> UI or just straight MCP tool -> UI. Security and performance research is required to determine the best path."

## Clarifications

### Session 2026-04-09

- Q: Does a backgrounded-but-open browser tab count as "left the session"? → A: No. Only chat-switching (or disconnect) pauses a stream. While the user is loaded into a chat, the stream continues regardless of tab focus or visibility.
- Q: When the same user has the same chat open in multiple client sessions (e.g. two browser tabs), should each be its own stream or share one? → A: Share one. The system deduplicates by `(user_id, chat_id, tool_name, params)` and fans the chunks out to every client session the user has loaded into that chat. Counts as one against the per-user concurrency cap.
- Q: Should concurrency caps differ by user role (admin/regular/guest)? → A: No. Uniform cap for all users: 10 concurrent active streams and 50 dormant streams per user, regardless of role.
- Q: How quickly must a stream stop after the user's authentication is revoked? → A: Within 60 seconds. A background token introspection sweep is acceptable; per-chunk JWT revalidation is not required.
- Q: On transient stream failure (e.g. brief upstream blip), should the system retry automatically or wait for the user? → A: Automatic retry with exponential backoff up to a cap (3 attempts: 1s, 5s, 15s), then surface a manual retry button. During automatic attempts the UI shows a "reconnecting" state so the user sees activity rather than a frozen component.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Live Data Updates in an Active Chat (Priority: P1)

A user is in an active chat session and asks an agent to monitor or fetch live information (e.g., a weather feed, an inbox, market data, a long-running job). The agent invokes a tool capable of producing a continuous stream of updates. While the user remains in that chat session, the relevant UI component (chart, list, status card, log view) updates in real time as new values arrive — without the user having to refresh, re-ask, or send another message.

**Why this priority**: This is the core capability the feature exists to deliver. Without it, no other behavior matters. A single streaming tool delivering live updates to one UI component is a complete, demonstrable MVP.

**Independent Test**: Open a chat session, ask an agent for a continuously-updating piece of information backed by a streaming-capable tool, and confirm the corresponding UI component visibly updates over time as new data arrives, with each update reflecting the latest value from the tool.

**Acceptance Scenarios**:

1. **Given** a user is viewing a chat session, **When** the user invokes an action that triggers a streaming-capable tool, **Then** a UI component appears and begins receiving live updates within a few seconds of the request.
2. **Given** a streaming UI component is active in a chat session, **When** the underlying tool emits new data, **Then** the visible component reflects the new value without a full page refresh and without requiring a new user message.
3. **Given** multiple streaming tools are active in the same chat session, **When** each emits updates at its own pace, **Then** each corresponding UI component updates independently and correctly attributes each update to the right component.

---

### User Story 2 - Streams Pause When the User Leaves the Session (Priority: P1)

A user is viewing a chat session that has one or more live streaming components. The user navigates away — switching to a different chat session, closing the chat view, navigating to another part of the application, or closing the browser tab. From that moment on, the system must stop pushing updates from those streaming tools to that user, and any underlying work that exists solely to feed those updates must stop consuming resources.

**Why this priority**: Without this, streams will leak: every chat session ever opened keeps consuming bandwidth, server resources, and (for paid upstream APIs) money. This is also a security/privacy concern — data should not continue flowing to a session the user has abandoned. P1 because it is required for the feature to be safe to enable in production.

**Independent Test**: Start a streaming component in a chat session, then navigate away from that session. Observe that no further updates for that stream are delivered to the client and that backend resources backing the stream are released within a defined window.

**Acceptance Scenarios**:

1. **Given** a chat session has an active streaming component, **When** the user switches to a different chat session, **Then** the previous session's stream stops delivering updates and its backing resources are released.
2. **Given** a chat session has an active streaming component, **When** the user closes the chat view, navigates away, or disconnects, **Then** the stream stops and no further data is sent for that session.
3. **Given** a stream has stopped because the user left, **When** an observer inspects backend activity, **Then** there is no continued polling, subscription, or upstream API usage attributable to that stopped stream.

---

### User Story 3 - Streams Resume When the User Returns (Priority: P1)

A user previously had a streaming component active in a chat session, left that session, and now returns to it. When they reopen the session, the streaming component should reappear and begin updating again automatically, without the user having to re-issue their original request. The user perceives the stream as having "picked back up," even though under the hood it was stopped while they were away.

**Why this priority**: Pairs directly with User Story 2. Stopping streams when the user leaves only delivers a good experience if returning to the session restores them. Without resume, users would have to manually re-trigger every streaming tool every time they navigate back, which would make the feature feel broken.

**Independent Test**: Start a stream in a chat session, navigate away (verifying the stream stops per Story 2), then return to the same session and confirm the streaming component is present and resumes producing updates without further user input.

**Acceptance Scenarios**:

1. **Given** a chat session previously had an active stream that was stopped because the user navigated away, **When** the user returns to that chat session, **Then** the streaming component reappears in the UI and begins receiving live updates again automatically.
2. **Given** a user returns to a chat session with a previously active stream, **When** the stream resumes, **Then** the user is shown current/live data (not a stale snapshot frozen at the moment they left).
3. **Given** a user returns to a chat session, **When** the stream cannot be resumed (e.g., the upstream source is no longer available), **Then** the UI clearly shows the stream's unavailable state instead of silently appearing idle.

---

### User Story 4 - Authorization and Isolation Across Users (Priority: P1)

Multiple users use the system concurrently. Each user's streaming data must be delivered only to that user's session, and each stream must respect the same authorization rules as any other action that user takes. A user must never see stream data sourced from another user's tool invocation, and a tool must not stream data the requesting user is not authorized to see.

**Why this priority**: Cross-user data leakage is a critical security failure. Because the user explicitly raised the architecture choice as a security question ("MCP tool → UI direct vs. via orchestrator"), the spec must assert the security guarantee independently of which routing path is chosen. P1 because it gates production deployment.

**Independent Test**: Two distinct authenticated users start streams in their own chat sessions concurrently. Confirm each user receives only their own stream's data, and that an unauthorized user cannot subscribe to another user's stream by guessing or replaying identifiers.

**Acceptance Scenarios**:

1. **Given** two different users each start streaming components in their own chat sessions, **When** both streams are active, **Then** each user only ever receives the data from their own stream.
2. **Given** a user starts a stream that depends on credentials or scopes they hold, **When** another user attempts to attach to that stream, **Then** the attempt is rejected.
3. **Given** a user's authentication becomes invalid (e.g., session expires) while a stream is active, **When** the next update would be sent, **Then** the stream stops and the user is notified to re-authenticate.

---

### User Story 5 - Graceful Failure of a Streaming Tool (Priority: P2)

A streaming tool fails mid-stream — the upstream source goes down, the tool crashes, the network drops, or the data source rate-limits the request. The user should not be left staring at a frozen component with no indication of what happened, and the rest of the chat session (other components, the ability to send new messages) must continue working normally.

**Why this priority**: The core happy path (Stories 1-3) can ship without this, but the feature is not production-ready until failure modes are visible to the user and don't cascade. P2 because it improves robustness rather than enabling new capability.

**Independent Test**: Start a stream, then forcibly interrupt the underlying tool or its data source. Confirm the affected component visibly reflects the failure, the rest of the session remains responsive, and the user has a clear way to retry.

**Acceptance Scenarios**:

1. **Given** a streaming component is active, **When** the underlying tool stops producing data unexpectedly, **Then** the component shows a clear failure or stale-data state within a bounded time.
2. **Given** one streaming component has failed, **When** the user interacts with other parts of the chat session, **Then** other components and chat input continue to work normally.
3. **Given** a failed stream, **When** the user requests a retry, **Then** the system attempts to restart the stream and either resumes updates or surfaces the persistent failure.

---

### Edge Cases

- **Rapid session switching**: A user toggles quickly between sessions (A → B → A → B). Streams must stop and restart cleanly without leaking state, double-subscribing, or producing duplicate components on return.
- **Slow consumer**: The UI cannot keep up with the rate of incoming updates. The system must drop or coalesce intermediate values rather than queueing unboundedly and causing memory growth or lag.
- **High update rate**: A tool emits updates faster than is meaningful for a human (e.g., hundreds per second). The user-perceived component must update at a sane refresh cadence.
- **Multiple identical streams in one session**: A user starts the same streaming tool twice with the same parameters in the same chat (whether from one client or multiple concurrent clients). The system deduplicates to a single underlying upstream subscription and fans the chunks out to every relevant client session, per FR-009a.
- **Reconnect after network blip**: Client briefly loses connection to the backend. On reconnect, any streams that should still be active for the currently-viewed session resume; streams for sessions the user is no longer viewing do not.
- **Long-lived inactive tab**: The chat session remains "open" in a background tab the user hasn't interacted with for a long time. The user is considered still in the session and the stream continues. Tab focus and visibility are NOT leave signals (per Clarifications, Session 2026-04-09).
- **Authorization revoked mid-stream**: User's access to the upstream resource is revoked while the stream is running. The stream must stop and the UI must indicate why.
- **Tool misreports streaming capability**: A tool advertises itself as streaming but only ever emits a single value, or never emits anything. The component must not hang indefinitely with no feedback.

## Requirements *(mandatory)*

### Functional Requirements

#### Streaming capability and discovery

- **FR-001**: The system MUST allow tools provided by agents to declare themselves as capable of producing a real-time stream of updates, distinct from tools that return a single response.
- **FR-002**: When a user action causes a streaming-capable tool to be invoked, the system MUST establish a stream that delivers updates to the user's currently active chat session.
- **FR-003**: The system MUST render a UI component associated with each active stream and update that component in place as new data arrives, without requiring page reloads or new user messages.

#### Session lifecycle: stop on leave, resume on return

- **FR-004**: When a user leaves a chat session that has one or more active streams, the system MUST stop delivering further updates to that user for those streams.
- **FR-005**: When a user leaves a chat session, the system MUST release the backend resources dedicated to feeding those streams (e.g., upstream subscriptions, polling loops, background work) so that no work continues purely to feed an unwatched session.
- **FR-006**: "Leaving a chat session" MUST include: switching to a different chat session, closing the chat view in the application, and disconnecting the client (tab close, navigation away, network loss). It MUST NOT include the chat tab merely losing focus or being backgrounded — as long as the user remains loaded into the chat in some open client, the stream continues.
- **FR-007**: When a user returns to a chat session that previously had streams, the system MUST automatically resume those streams without requiring the user to re-issue the original request.
- **FR-008**: On resume, the UI component MUST reflect current live data, not stale data captured at the moment the user previously left.
- **FR-009**: The system MUST persist enough state about each previously-active stream in a session to know, on the user's return, which streams should be resumed and which UI components should be re-shown.
- **FR-009a**: When the same user has the same chat loaded in multiple concurrent client sessions, the system MUST deduplicate streams by `(user_id, chat_id, tool, parameters)`. There MUST be exactly one upstream subscription per such tuple, and each chunk MUST be delivered to every client session the user has loaded into that chat. Such a deduplicated stream MUST count as one against the per-user concurrency limit defined in FR-015.

#### Security and authorization

- **FR-010**: Each stream MUST be authorized against the requesting user's identity, applying the same authentication and authorization rules used for any other action that user can take in the system.
- **FR-011**: Stream data MUST be delivered only to the authenticated user who initiated the stream. The system MUST prevent any other user — authenticated or not — from receiving that stream's data, even if they obtain or guess any stream identifier.
- **FR-012**: If a user's authentication becomes invalid (token expired or revoked) while a stream is active, the system MUST stop the stream within 60 seconds and surface a re-authentication prompt or equivalent state in the UI.
- **FR-013**: The system MUST NOT expose backend services, internal tool endpoints, or upstream credentials directly to the browser/client as a side effect of enabling streaming.
- **FR-014**: A formal evaluation comparing routing paths for stream data (e.g., "tool → agent → orchestrator → client" vs. "tool → client directly") MUST be produced before implementation, evaluating each path against: authentication boundary, attack surface, resource accounting per user, observability, and per-user fan-out cost. The chosen path MUST be documented with its rationale. *(This requirement is satisfied during the planning phase, not at runtime.)*

#### Performance and resource bounds

- **FR-015**: The system MUST bound the resources consumed by any single stream and by the total set of concurrently active streams, so that a misbehaving or high-frequency tool cannot exhaust shared backend or client resources. Specifically: each authenticated user MUST be limited to at most 10 active stream subscriptions and at most 50 dormant (paused, awaiting return) stream subscriptions. These limits MUST be uniform across all user roles.
- **FR-016**: When a streaming tool produces updates faster than the UI can usefully display, the system MUST coalesce or drop intermediate updates rather than queueing them unboundedly.
- **FR-017**: The system MUST detect and stop streams whose underlying client connection has gone away, even if no explicit "leave" signal was received, within a bounded time window.
- **FR-018**: Starting, stopping, and resuming a stream MUST each complete within a bounded time perceptible to the user as "responsive" (see Success Criteria for specific targets).

#### Failure handling and observability

- **FR-019**: When a stream fails (upstream unavailable, tool error, authorization lost, etc.), the system MUST surface that failure in the corresponding UI component in a way the user can understand, rather than silently freezing. During the automatic retry window (FR-021a) the component MUST show a distinct "reconnecting" state visually different from both "live" and "failed".
- **FR-020**: A stream failure MUST NOT degrade the user's ability to interact with other parts of the same chat session, including other streaming components, chat input, and history.
- **FR-021**: The user MUST be able to retry a failed stream from the UI component without restarting the entire chat session.
- **FR-021a**: On transient stream failures, the system MUST automatically retry up to 3 times with exponential backoff (target intervals: 1 s, 5 s, 15 s) before surfacing the failure to the user as requiring manual retry. Authentication failures (FR-012) and authorization failures MUST NOT be auto-retried — they go directly to the manual-retry / re-authentication state.
- **FR-022**: The system MUST log enough information about each stream's lifecycle (start, stop, resume, failure) — attributed to the owning user and session — to support debugging and abuse investigation, without logging the streamed payload contents by default.

### Key Entities *(include if feature involves data)*

- **Streaming Tool**: A capability provided by an agent that, when invoked, produces an open-ended sequence of updates over time rather than a single response. Has an identity, declares its streaming nature, and is subject to the same authorization as any other tool.
- **Stream Subscription**: The relationship between one user's chat session and one running streaming tool invocation. Owns the lifecycle (start, pause-on-leave, resume-on-return, stop) and the binding to a specific UI component instance.
- **Chat Session**: An identifiable conversation that a user can be "currently viewing" or "not currently viewing." Is the unit at which streams are paused and resumed. May host zero or more concurrent stream subscriptions.
- **Streaming UI Component**: The visible element in the chat session that represents a stream subscription. Is the target of in-place updates and the surface where stream state (live, stale, failed, re-authenticate) is communicated to the user.
- **Stream Update**: A single data point emitted by a streaming tool, addressed to one specific stream subscription, intended to update its UI component.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user invoking a streaming-capable tool sees the corresponding UI component appear and receive its first live update within 2 seconds under normal conditions.
- **SC-002**: After a user leaves a chat session, all backend work attributable solely to that session's streams ceases within 5 seconds. After that window, no upstream API calls, polling loops, or background tasks continue on behalf of the abandoned streams.
- **SC-003**: When a user returns to a chat session, previously active streams resume and show fresh data within 3 seconds of the session becoming visible again, with no manual user action required.
- **SC-004**: Across 1,000 random user navigations between sessions in a load test, zero stream updates are delivered for sessions the user is not currently viewing, and zero updates are delivered to the wrong user.
- **SC-005**: With 100 concurrent users each running 3 streaming components, the system sustains updates without unbounded memory growth on the backend or the client over a continuous 30-minute test.
- **SC-006**: When a streaming tool emits updates faster than the UI can render, the user-visible component updates at no less than 5 frames per second and no more than 30 frames per second (i.e., updates are coalesced rather than queued), and the rest of the chat session remains responsive.
- **SC-007**: When a stream fails, 100% of failures are reflected in the corresponding UI component within 5 seconds, with a user-visible state distinct from "loading" and a way to retry. Transient failures recovered by automatic retry MUST clear the "reconnecting" state and resume normal updates within 25 seconds of the original failure (covering the worst-case 1+5+15 s backoff plus one cycle of jitter).
- **SC-008**: The architectural decision on stream routing (direct from tool to client vs. through the orchestrator) is recorded as a written decision with explicit security and performance reasoning before any production rollout, and is reviewed by the project owner.
- **SC-009**: When a user's authentication is revoked, 100% of that user's active streams stop within 60 seconds, and the corresponding UI components show a re-authentication state.

## Assumptions

- **A-001**: The existing chat-session model already gives the system a notion of "the user is currently loaded into session X"; this feature builds on that signal rather than redefining it. Tab focus and visibility are explicitly NOT leave signals — see FR-006 and the Clarifications section.
- **A-002**: Streaming is opt-in per tool. Existing single-response tools continue to work unchanged and are not retroactively converted into streams.
- **A-003**: "Real-time" in this feature means human-perceptible latency on the order of seconds, not sub-millisecond. Tools whose data is meaningful only at sub-second intervals are out of scope for the first delivery.
- **A-004**: The user's authentication mechanism for streaming is the same one used for the rest of the application; this feature does not introduce a new auth scheme. It does, however, require that the chosen routing path correctly enforces that auth — see FR-014.
- **A-005**: The decision between "tool → agent → orchestrator → client" and "tool → client direct" is treated as a planning-phase concern, not a spec-phase concern. The spec asserts the security, isolation, lifecycle, and performance properties the chosen path must satisfy regardless of which is selected.
- **A-006**: Stream payloads are not assumed to be sensitive enough to require end-to-end encryption beyond the transport security already used by the application. If a specific streaming tool surfaces highly sensitive data, that is handled per-tool, not by this feature.
- **A-007**: There is no requirement to replay missed updates from the period the user was away. On return, the user sees current live data, not a backfill of everything they missed.

## Out of Scope

- Replaying or backfilling stream history that was emitted while the user was away from the session.
- Sharing a single stream across multiple users (e.g., collaborative dashboards) — each user gets their own subscription.
- Persisting stream payloads to long-term storage as a side effect of streaming.
- Converting existing non-streaming tools into streaming tools; this feature only enables tools that opt in.
- Mobile-specific background behavior (push notifications, OS-level wake) — this feature targets the foreground chat session experience.
- Sub-second / high-frequency-trading-style latency requirements.

## Dependencies

- An identifiable concept of "the user's currently active chat session" that the client can signal and the backend can act on.
- The existing user authentication and authorization mechanism, which streaming will inherit rather than replace.
- The existing mechanism by which the UI receives backend-driven component updates in a chat session, which streaming will reuse for in-place updates.
- The existing agent + tool discovery mechanism, extended (not replaced) so a tool can declare itself streaming-capable.
