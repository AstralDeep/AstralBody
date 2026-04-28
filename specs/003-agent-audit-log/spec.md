# Feature Specification: Agent Action Audit Log

**Feature Branch**: `003-agent-audit-log`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: "As a user, I need to be able to see the audit log of agent actions."

## Clarifications

### Session 2026-04-28

- Q: Audit log retention period? → A: 6 years retention to satisfy HIPAA recordkeeping requirements.
- Q: How are sensitive payloads represented in the audit row? → A: Metadata + pointer to source artifact; raw payload bytes are never copied into the audit store. Caveats apply to filename handling, hash construction, pointer-vs-artifact retention, and access control (see FR-004 / FR-015 / FR-016 / FR-017).
- Q: UI surface for the audit log? → A: Dedicated route/page in the main app, scoped per user; opened from a button in the main chrome.
- Q: Live update vs. manual refresh on the audit-log page? → A: Live push over the existing user WebSocket while the route is open, with a manual refresh control as a reconnect/gap fallback.
- Q: Compliance scope and admin visibility? → A: Audit logs MUST satisfy both HIPAA recordkeeping and the NIST SP 800-53 AU (Audit and Accountability) control family. Audit visibility is strictly per-user: even system administrators MUST NOT be able to view another user's audit entries through this feature. The user who performed the action is the only principal authorized to read its audit entries. (See FR-007, FR-019, FR-020.)
- Q: Scope of recorded events? → A: The audit log records every user-attributable action in the system, not only agent actions — direct user actions (login, logout, conversation creation, file upload, settings change, etc.) and agent actions taken on the user's behalf are both recorded under the same audit log scoped to that user. (See FR-001, FR-021.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Audit Log of Agent Actions (Priority: P1)

As a user, I want to open an audit log view that shows a chronological history of every action my agents have taken on my behalf, so I can verify what happened, troubleshoot unexpected behavior, and trust that the system is acting correctly.

**Why this priority**: This is the core value of the feature — without a viewable log, recording actions in the database delivers no user-facing benefit. It is the smallest slice that proves the audit-log loop works end-to-end and gives the user transparency into agent behavior.

**Independent Test**: Trigger one or more agent actions in a session, open the audit-log view, and confirm each action appears with the correct agent, action description, and timestamp. The feature is fully demonstrable on its own — the user gains visibility into agent activity even before any filtering or advanced controls are added.

**Acceptance Scenarios**:

1. **Given** an agent has performed at least one action during the user's session, **When** the user opens the audit log view, **Then** the view lists each action with the agent name, a human-readable action description, and a timestamp, ordered most-recent first.
2. **Given** the user has multiple past sessions with recorded agent actions, **When** the user opens the audit log view, **Then** entries from prior sessions are also visible (not limited to the current session).
3. **Given** no agent actions have ever been recorded for the user, **When** the user opens the audit log view, **Then** the view displays a clear empty state explaining that no agent activity has been recorded yet.
4. **Given** the audit-log route is open and the user's WebSocket is connected, **When** an agent performs a new action, **Then** the new entry appears in the log within the SC-001 freshness target without requiring user interaction.
5. **Given** the audit-log route is open but the WebSocket dropped and reconnected, **When** the user activates the manual refresh control, **Then** any entries created during the gap appear in the log.

---

### User Story 2 - Inspect Action Details (Priority: P2)

As a user, I want to see additional context for any single audit-log entry — including which conversation it belonged to, the inputs that triggered it, and the outcome (success or failure) — so I can understand exactly what the agent did and why.

**Why this priority**: Once the high-level log is visible (P1), users will want to drill into individual entries to investigate concerns. This deepens trust and makes the log useful for troubleshooting, but the feature is still valuable without it.

**Independent Test**: Open the audit log, select any entry, and confirm a detail view shows the action's inputs, outcome status, and originating conversation. Can be tested with a single recorded action.

**Acceptance Scenarios**:

1. **Given** the audit log is open with at least one entry, **When** the user selects an entry, **Then** the user sees the full action details including agent name, action type, inputs/parameters, outcome status (success or failure), and originating conversation reference.
2. **Given** an action failed, **When** the user views its detail, **Then** the failure reason or error summary is shown in plain language.

---

### User Story 3 - Filter and Search the Audit Log (Priority: P3)

As a user with many recorded agent actions, I want to filter the audit log by agent, by date range, and by outcome (success/failure), and search by keyword, so I can quickly find the entries that matter to me.

**Why this priority**: Filtering becomes valuable only after enough history accumulates. Early users with few entries can scroll the list; this enhances usability at scale but is not required for an MVP.

**Independent Test**: Generate a mix of actions across different agents and outcomes, apply each filter, and confirm only matching entries appear. Can be tested independently once basic log viewing is in place.

**Acceptance Scenarios**:

1. **Given** the audit log contains entries from multiple agents, **When** the user filters by a specific agent, **Then** only that agent's actions are shown.
2. **Given** the user selects a date range, **When** the filter is applied, **Then** only actions whose timestamp falls within that range are shown.
3. **Given** the user enters a keyword, **When** the search is applied, **Then** entries whose action description, inputs, or outcome contain the keyword are shown.

---

### Edge Cases

- **High-volume sessions**: When an agent performs many actions in rapid succession (e.g., a chained tool-use loop), all actions are still recorded individually and the log remains readable (e.g., grouping or pagination prevents the view from becoming unusable).
- **Long-running actions**: An action that is in-flight when the user opens the log should appear with a clear "in progress" status, then transition to its final outcome once complete.
- **Failed or interrupted actions**: Actions that error mid-execution or are interrupted by disconnect must still be recorded with a status indicating the failure or interruption.
- **Sensitive inputs**: When an action's inputs contain content the user expects to be private (e.g., uploaded medical files, secrets), the audit entry stores only non-PHI metadata plus a pointer to the original artifact (FR-004). Filenames are not persisted in plaintext (FR-015), payload digests are constructed to resist re-identification (FR-016), and viewing an audit entry does not by itself unlock the pointed-to artifact (FR-018).
- **Source artifact already purged**: If an audit entry's pointer references an artifact whose own retention has elapsed before the audit's 6-year window ends, the entry remains visible and the detail view shows "source artifact no longer available" rather than failing or hiding the entry.
- **Other users' activity**: A user must never see audit-log entries for actions performed on behalf of another user.
- **Deletion of conversations**: If a conversation referenced by an audit entry is deleted, the audit entry remains intact but indicates the conversation is no longer available.
- **Clock skew / out-of-order arrival**: Entries display in the order they actually occurred (server-recorded time), not the order in which the client received them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST record an audit entry for every discrete user-attributable action, covering (at minimum): direct user actions (authentication events, conversation lifecycle, file uploads, settings changes, audit-log views themselves) AND agent actions performed on behalf of the user (tool calls, UI renders that change state, external system interactions). Both classes of event live in the same per-user audit log.
- **FR-002**: System MUST persist audit entries durably so they remain available across sessions, application restarts, and reconnects.
- **FR-003**: Each audit entry MUST capture the acting agent's identity, the action type, a human-readable description, the originating conversation reference, the user the action was performed for, the timestamp the action started, the timestamp it completed (if applicable), and the outcome status (success, failure, in-progress, interrupted).
- **FR-004**: Each audit entry MUST capture a representation of the action's inputs and outputs sufficient for the user to understand what the agent did. Raw payload bytes (e.g., uploaded file bodies, message content that may contain PHI) MUST NOT be copied into the audit store; instead the entry MUST hold non-identifying metadata (e.g., file size, MIME type, originating message reference) and a stable pointer/identifier to the underlying source artifact in its original store.
- **FR-015**: Filenames and other free-text identifiers attached to source artifacts MUST be treated as potentially PHI. The audit entry MUST NOT persist user-supplied filenames in plaintext; instead it MUST store either (a) the file extension plus a generated artifact identifier, or (b) the filename in an encrypted/access-controlled field separate from the main audit row. The chosen approach MUST be applied uniformly across all audit entries.
- **FR-016**: Any cryptographic digest of payload contents stored in the audit entry MUST be constructed in a way that resists brute-force re-identification of small or structured documents (e.g., HMAC with a server-held key, or per-tenant salting). Plain unsalted hashes (e.g., raw SHA-256) of payload contents MUST NOT be persisted in the audit store.
- **FR-017**: Pointer integrity over the 6-year retention window MUST be handled explicitly. The system MUST document that source artifacts may be purged before the audit retention window ends, and audit entries MUST display a clear "source artifact no longer available" state when their pointer can no longer be dereferenced. The audit log MUST NOT extend artifact retention or store sealed copies of payloads in order to keep pointers live.
- **FR-018**: Read access to an audit entry MUST NOT, by itself, grant dereference rights to the artifact it points to. Access to the underlying artifact MUST continue to be governed by that artifact's own access-control rules, evaluated at dereference time.
- **FR-005**: Users MUST be able to open the audit log from a clearly labeled control in the main application chrome. Selecting that control MUST navigate to a dedicated, deep-linkable audit-log route/page (not a modal, drawer, or embedded settings section). Filter and pagination state SHOULD be reflected in the route's URL so views can be shared or restored.
- **FR-006**: The audit-log view MUST show entries in reverse chronological order (most recent first) by default.
- **FR-007**: The audit-log view MUST be scoped per user. The route MUST only show entries belonging to the currently authenticated user, regardless of how the route is reached (direct navigation, deep link, or refresh). A user MUST NOT see audit entries belonging to any other user under any circumstances. This restriction is absolute and admin-blind: see FR-019.
- **FR-008**: Users MUST be able to view full details of a single audit entry, including inputs, outputs/outcome, and originating conversation reference.
- **FR-009**: The audit-log view MUST display a clear empty state when no entries exist for the user.
- **FR-010**: While the audit-log route is open, the view MUST receive new entries via a live push over the existing user-scoped WebSocket connection and render them without requiring navigation away from the route. The view MUST also expose an explicit manual refresh control that re-fetches from the authoritative store; this control MUST recover any entries missed during a disconnect or subscription gap. Live pushes MUST be filtered server-side to the authenticated user (consistent with FR-007).
- **FR-011**: The audit-log view MUST handle large histories gracefully (e.g., via pagination, virtualized list, or "load more") so performance does not degrade as entry count grows.
- **FR-012**: System MUST retain audit entries for at least 6 years from the action's recorded timestamp to satisfy HIPAA recordkeeping requirements. Entries MUST remain queryable through the audit-log view for the entire retention window, and any purge or archival of entries older than 6 years MUST itself be auditable.
- **FR-013**: System MUST record audit entries even when the user is disconnected at the time the action runs, and surface them once the user next opens the audit log.
- **FR-014**: System MUST prevent users from modifying or deleting audit entries through the audit-log UI — the log is append-only from the user's perspective, to preserve its integrity as a historical record.
- **FR-019**: Audit-log read access MUST be restricted to the user who initiated the action. No administrator, support, or operator role MUST be able to view another user's audit entries through this feature, irrespective of role, scope, or token claim. There is no "view as user" or admin-impersonation path that exposes another user's audit log. Any out-of-band access (e.g., subpoena/forensic) MUST occur through a separate, explicitly-scoped flow outside this feature, and any such access MUST itself be recorded as an audit event in the affected user's log.
- **FR-020**: The audit log MUST satisfy the NIST SP 800-53 AU (Audit and Accountability) control family at a level appropriate for a system handling PHI. Specifically: AU-2 (event selection covers user and agent actions per FR-001), AU-3 (each entry contains the content fields per FR-003/FR-004), AU-8 (timestamps are recorded with timezone in a tamper-resistant fashion), AU-9 (audit records are protected from modification — append-only, integrity-checkable), AU-11 (records retained for the 6-year window per FR-012), and AU-12 (the recording mechanism is always-on and not user-disableable).
- **FR-021**: Recording of user-attributable events MUST happen at the system boundaries where authority is asserted (API request handlers, WebSocket message handlers, the orchestrator's tool-dispatch path), so that events cannot enter the system without producing an audit entry. Bypass paths (e.g., direct DB writes from internal scripts) MUST be reviewed and either eliminated or wrapped in audit-emission middleware before they enter steady state.

### Key Entities

- **Audit Entry**: A single recorded agent action. Captures who acted (agent), on whose behalf (user), in what context (conversation), what was done (action type, description, non-PHI input/output metadata, pointers to source artifacts), when (start/end timestamps), and the outcome (success / failure / in-progress / interrupted). The audit entry never stores raw payload bytes and treats filenames and payload digests per FR-015 / FR-016. A pointer field may resolve to "artifact unavailable" once the underlying source's own retention has elapsed.
- **Agent**: The actor that performed the recorded action. Already an existing concept in the system; the audit entry references it by identity.
- **User**: The owner of the audit log. Each audit entry belongs to exactly one user, and audit-log views are scoped per user.
- **Conversation**: The session/thread in which the action was triggered. Audit entries reference a conversation so the user can navigate back to the context.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After triggering an agent action, the user can see that action in the audit log within 5 seconds, in 95% of cases.
- **SC-002**: Users can locate a specific past agent action in their audit log in under 30 seconds for histories of up to 1,000 entries.
- **SC-003**: 100% of agent actions performed on behalf of a user produce a corresponding audit entry — there are no silent actions.
- **SC-004**: Audit entries remain retrievable across application restarts and across sessions for the full 6-year HIPAA retention window, with zero data loss observed in normal operation.
- **SC-005**: In user testing, at least 90% of users can correctly answer "what did the agent just do?" by consulting the audit log without needing assistance.
- **SC-006**: The audit-log view loads its first page of entries in under 2 seconds for users with up to 10,000 historical entries.

## Assumptions

- Authentication is already in place; the audit log scopes entries to the authenticated user via the existing identity provider.
- "Agent actions" includes tool invocations, server-driven UI render events that change state, and external system interactions — wherever the orchestrator mediates agent activity is the natural recording point.
- The audit log is read-only from the user's perspective; administrative or compliance-driven export/erase flows are out of scope for this feature.
- Recording an audit entry is a side-effect of performing the action; it does not block the action from completing if the recording layer is briefly unavailable, but the recording layer must be reliable enough to meet SC-003 in steady state.
- "View" in this context means a UI surface (button + container) within the existing application, consistent with the linked task breakdown.
- Sensitive content handling defaults to summarization rather than full redaction; future work may add per-field redaction policies.
