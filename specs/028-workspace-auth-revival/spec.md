# Feature Specification: Persistent SDUI Workspace & Revived Keycloak Authentication

**Feature Branch**: `028-workspace-auth-revival`
**Created**: 2026-06-10
**Status**: Draft
**Input**: User description: "Persistent SDUI workspace with session UI history and component interaction loop (per sdui-evolution-proposal.md, re-interpreted for the post-026 server-driven architecture), plus re-enabled Keycloak authentication with a sign-in gate and full session lifecycle — silent renewal, durable sessions, sign-out revocation, and fail-closed production posture."

## Clarifications

### Session 2026-06-10

- Q: What should unauthenticated users see when they reach the app? → A: A straight redirect to Keycloak's hosted sign-in page. No in-app branded login screen is built; Keycloak conducts the entire credential exchange (Constitution VII).
- Q: How deep should the authentication work go? → A: Full session lifecycle — sign-in gate, server-side silent token renewal, a durable session store that survives service restarts, sign-out that revokes the refresh credential and offline grants, and a fail-closed production posture (mock auth refused outside dev; unauthenticated agent connections refused in production).
- Q: How does the persistent workspace decide what persists? → A: Automatically. Every rich component output joins the per-chat workspace under a stable component identity; updates replace the matching component in place, new components are appended. No user pinning gesture is required.
- Q: How far should UI session history go? → A: Re-hydration plus a read-only timeline. Re-opening a chat restores the workspace exactly; the user can additionally view the workspace as it was at any prior turn, with an explicit "back to live" affordance. Restoring/forking a past state is out of scope for 028.

## Overview

This feature has two co-equal parts.

**Part A — Revived authentication.** The server-side Keycloak sign-in flow built in feature 026 exists but nothing routes users to it: the app shell is served to everyone, and a session quietly breaks minutes after sign-in because nothing renews the short-lived access credential. Part A puts a real gate in front of the application (unauthenticated visitors are sent straight to Keycloak and returned to where they were headed), keeps sessions alive silently for up to the 365-day persistent-login window established by feature 016, makes sessions survive service restarts, makes sign-out actually revoke credentials (including feature 025 offline grants), and makes production deployments fail closed instead of open.

**Part B — SDUI evolution.** Today the workspace canvas is transient: every new agent response wipes and replaces everything on screen, re-opening a chat loses all rich components, and the assistant is told the canvas is persistent when for the user it is not. Part B makes the canvas a true per-chat workspace: rich outputs accumulate under stable component identities and update in place, re-opening a chat restores the exact workspace, a read-only timeline lets the user view the workspace as it was at any prior turn, and a standardized interaction contract lets components behave like small applications — a control on a component can re-run its source capability (with full permission enforcement) and update that component in place, or escalate to the assistant as a user intent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign-in required to enter the app (Priority: P1)

A person opens the application URL without an active session. They are taken directly to the organization's Keycloak sign-in page; after authenticating, they land back in the application at the exact destination they originally requested (including a deep link to a specific chat). No application content, data, or chrome is visible before sign-in completes.

**Why this priority**: The application currently serves its full shell to anyone. Restoring the authentication gate is a security prerequisite for everything else and is independently valuable on its own.

**Independent Test**: With authentication enabled and no session, request the app root and a `?chat=<id>` deep link; verify both redirect to Keycloak, that signing in returns the user to the originally requested destination, and that no application markup is served pre-authentication.

**Acceptance Scenarios**:

1. **Given** no active session, **When** the user requests the application root, **Then** they are redirected to the Keycloak sign-in page without any application content being served.
2. **Given** no active session, **When** the user requests a deep link to a specific chat, **Then** after signing in at Keycloak they land on that chat, not the generic landing state.
3. **Given** a signed-in user, **When** they request the application root, **Then** the app loads immediately with no sign-in redirect and no visible flash of a sign-in state (feature 010/016 no-flash behavior).
4. **Given** a user whose account has neither the `user` nor `admin` role, **When** they complete Keycloak sign-in, **Then** they are shown a clear "no access" outcome rather than a broken or empty application.
5. **Given** Keycloak is unreachable, **When** an unauthenticated user arrives, **Then** they receive a recoverable error state with a retry path — never an infinite redirect loop.

---

### User Story 2 - Stay signed in without interruption (Priority: P1)

A clinician signs in Monday morning and uses the app throughout the day, across page reloads, network blips, and a backend service restart. Their session renews silently in the background; they never see an authentication error or a sign-in page until they sign out or 365 days pass since their last interactive sign-in.

**Why this priority**: Without silent renewal the revived gate would lock users out minutes after sign-in (the access credential is short-lived), making Part A actively worse than useless. Durable sessions are what make feature 016's 365-day promise true.

**Independent Test**: Sign in once, then exercise the app past several access-credential lifetimes, reload the page, restart the backend service, and reconnect — verifying zero interactive re-authentication and zero user-visible auth errors across the 016 resume matrix (+1 minute, +1 hour, +7 days, +30 days).

**Acceptance Scenarios**:

1. **Given** an active session older than the access-credential lifetime, **When** the user reloads the page or the real-time connection re-establishes, **Then** the session renews silently and the app resumes without any user-visible interruption or prompt.
2. **Given** an active session, **When** the backend service restarts, **Then** the user's session survives and their next request or reconnect proceeds without re-authentication.
3. **Given** a session whose last interactive sign-in was 365 days ago, **When** renewal is attempted, **Then** renewal is refused, the user is routed to interactive Keycloak sign-in, and only that interactive sign-in resets the 365-day clock — silent renewals never extend it.
4. **Given** a real-time reconnect with an expired credential, **When** silent renewal succeeds, **Then** the connection is re-established transparently; **When** renewal is impossible, **Then** the user is routed to sign-in with their context preserved — never left on a dead-end "Authentication failed" message.
5. **Given** a resumed session, **When** the app loads, **Then** the resume is recorded under the existing `auth.session_resumed` audit action and a failed resume under `auth.session_resume_failed` (016 audit semantics carried forward).

---

### User Story 3 - A workspace that accumulates and updates in place (Priority: P1)

A researcher asks an agent for a metrics table, then a chart, then asks to refresh the table with new filters. All three artifacts remain visible together in the workspace; the refreshed table updates in its existing position with no flicker and without disturbing the chart. Nothing the agent previously produced silently disappears.

**Why this priority**: The "disappearing UI" is the core defect the SDUI proposal targets — every new response currently wipes the canvas, making multi-step analytical work impossible. This story is the heart of Part B and delivers standalone value.

**Independent Test**: Drive a conversation producing three distinct rich components, then trigger an update to the first; verify all three remain present, the update happened in place (same position, other components' state untouched), and that two outputs of the same capability with different parameters coexist as distinct components.

**Acceptance Scenarios**:

1. **Given** a workspace containing components from earlier turns, **When** a new turn produces a new rich component, **Then** it is added to the workspace and all prior components remain visible and usable.
2. **Given** a component already in the workspace, **When** a turn (or component action) produces an updated version of that same component, **Then** it is updated in place — same position, no full-workspace redraw, and other components keep their state (e.g., an expanded section stays expanded).
3. **Given** the same capability invoked twice with different parameters, **When** both results arrive, **Then** they appear as two distinct workspace components — the second does not overwrite the first.
4. **Given** a plain-text answer or status update, **When** it is delivered, **Then** it appears in the conversation stream, not the workspace — the stream/workspace separation is preserved.
5. **Given** any workspace mutation (add, update), **When** it occurs, **Then** it is recorded in the audit trail.

---

### User Story 4 - Re-open a chat and pick up where you left off (Priority: P2)

A user closes their laptop mid-analysis. Days later they re-open the same chat: the workspace is restored exactly as they left it — every component, with its latest data — and the conversation transcript shows meaningful renderings of past component-bearing responses instead of empty bubbles.

**Why this priority**: Re-hydration converts the workspace from a live-session nicety into a durable artifact, and fixes the visible bug that historical rich responses render as blank messages. It builds directly on Story 3's persistence.

**Independent Test**: Build a workspace, disconnect entirely, re-open the chat from a fresh session and verify the workspace and transcript render fully; verify the assistant's stated awareness of what is on the canvas matches what the user actually sees.

**Acceptance Scenarios**:

1. **Given** a chat with a populated workspace, **When** the user re-opens that chat (same or different device), **Then** the workspace is restored to exactly the state they left, without re-running any capabilities.
2. **Given** a transcript containing component-bearing assistant messages, **When** the chat is loaded, **Then** those messages render meaningfully in the stream — no empty bubbles.
3. **Given** a restored workspace, **When** the user continues the conversation, **Then** the assistant's view of "what is currently on the canvas" matches what the user sees, and updates target the restored components correctly.
4. **Given** a chat is deleted, **When** deletion completes, **Then** its workspace and all its history snapshots are deleted with it.

---

### User Story 5 - Components that act like small apps (Priority: P2)

A user clicks "Refresh" on a data table in the workspace. The table's source capability re-runs with its original parameters and the table updates in place within seconds — no chat round-trip, no canvas wipe. A filter control on one component updates a companion chart component. Where an interaction expresses intent rather than a deterministic refresh, it is handed to the assistant as a high-priority user message.

**Why this priority**: This is the proposal's "actually useful" pillar — but it depends on stable component identity (Story 3), so it follows it.

**Independent Test**: Exercise a deterministic refresh action, a cross-component action, and an intent-style action on seeded components; verify in-place results, permission enforcement, and that a user without access to the underlying capability is denied and the denial audited.

**Acceptance Scenarios**:

1. **Given** a workspace component with a refresh-style control, **When** the user activates it, **Then** the component's source capability re-runs deterministically and the result updates that same component in place.
2. **Given** a component action, **When** it executes, **Then** it is subject to exactly the same per-user agent-scope and per-tool permission rules as the equivalent chat-driven invocation; a denial is communicated to the user and audited.
3. **Given** an action on component A that targets component B, **When** it executes, **Then** component B updates in place; if B no longer exists the user receives a graceful explanation, not silent failure.
4. **Given** an interaction defined as an intent (e.g., a parameter-picker submission), **When** the user submits it, **Then** it enters the conversation as a user message and is processed by the assistant — the contract explicitly distinguishes deterministic actions from intent actions.
5. **Given** existing built-in component behaviors (table pagination, parameter pickers), **When** 028 ships, **Then** they behave identically or better under the standardized contract — pagination no longer wipes the rest of the workspace.
6. **Given** workspace changes caused by component actions, **When** they occur, **Then** they are captured in the workspace history just like turn-driven changes.

---

### User Story 6 - View the workspace as it was at any prior turn (Priority: P2)

A user reviewing a long analysis steps the workspace back to "as of turn 4" to see an earlier version of a table, compares it with the present, and returns to live with one action. Viewing the past never changes the present.

**Why this priority**: The timeline delivers the proposal's "UI time-travel" in its safe, read-only form. It depends on Stories 3–4's snapshots existing.

**Independent Test**: Produce a multi-turn workspace with at least one in-place update, open the timeline at several past turns, verify each view matches what was on screen at that turn, verify live state is untouched afterward, and verify historical viewing is audited.

**Acceptance Scenarios**:

1. **Given** a chat with N turns of workspace history, **When** the user selects any prior turn, **Then** the workspace displays exactly the components (and their values) as of that turn, clearly marked as a historical view.
2. **Given** a historical view is open, **When** the user chooses "back to live", **Then** the current workspace is restored exactly, including any updates that arrived while they were viewing the past.
3. **Given** a historical view is open, **When** new live updates arrive, **Then** the historical view does not change, and the user is made aware that live has moved on.
4. **Given** a historical view, **When** the user attempts component actions, **Then** mutating actions are unavailable — the historical view is strictly read-only in 028.
5. **Given** historical workspace states may contain sensitive data, **When** a user views one, **Then** the access is recorded in the audit trail.

---

### User Story 7 - Sign out everywhere, even offline (Priority: P2)

A user signs out on a shared workstation. Their server session ends, their long-lived refresh credential is revoked at Keycloak, and any standing offline grants for unattended jobs are revoked too. If Keycloak is unreachable at that moment, local sign-out still completes immediately and revocation is retried.

**Why this priority**: Sign-out is the only off-switch for a 365-day session (016 decision); today it neither revokes the refresh credential nor touches offline grants.

**Independent Test**: Sign out and verify the session cookie/state is unusable, the refresh credential can no longer mint new access credentials, offline grants are revoked, and an offline sign-out still locally completes with revocation following when connectivity returns.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they sign out, **Then** their server session is ended, their refresh credential is revoked with the identity provider, and all of their offline grants are revoked.
2. **Given** the identity provider is unreachable, **When** the user signs out, **Then** local sign-out completes unconditionally and credential revocation is completed best-effort when connectivity returns (016 offline-tolerant semantics).
3. **Given** a different user signs in on the same browser, **When** the new interactive sign-in completes, **Then** the previous user's session is revoked and none of their state is accessible (016 user-switch revocation).
4. **Given** any sign-out, **When** it completes, **Then** it is recorded in the audit trail under the existing `auth` event class.

---

### User Story 8 - Production deployments fail closed (Priority: P2)

An operator deploys to production with mock authentication accidentally left enabled, or without agent-connection credentials configured. The service refuses to start (or refuses the unauthenticated connections) instead of silently running open.

**Why this priority**: The current defaults fail open — mock auth is the shipped default and unauthenticated agent connections are allowed when no key is configured. A security feature that can be silently disabled by a missing env var is not a security feature.

**Independent Test**: Start the service in a production-mode configuration with mock auth enabled and verify it refuses to serve; attempt an agent connection with no credentials configured and verify refusal; verify explicit dev mode preserves today's local development experience.

**Acceptance Scenarios**:

1. **Given** a production-mode configuration with mock authentication enabled, **When** the service starts, **Then** it refuses to serve with a clear operator-facing explanation.
2. **Given** a production-mode deployment with no agent credentials configured, **When** an agent attempts to connect without authenticating, **Then** the connection is refused (fail closed), and the refusal is logged.
3. **Given** an explicitly dev-mode environment, **When** the developer uses mock auth, **Then** local development works exactly as today.
4. **Given** an operator preparing a realm, **When** they consult the project documentation, **Then** a current, committed document describes every required Keycloak realm setting (session windows for the 365-day promise, credential lifetimes, required roles, client configuration).

---

### User Story 9 - The same workspace on every connected device (Priority: P3)

A user has the same chat open on a desktop and a tablet. A component update — whether from an agent turn or a component action on either device — appears on both within moments, each rendered appropriately for its device.

**Why this priority**: Valuable polish that builds entirely on Stories 3 and 5; the feature is coherent without it.

**Independent Test**: Connect two clients as the same user to the same chat, trigger a workspace mutation from one, and verify the other reflects it promptly in its device-appropriate form.

**Acceptance Scenarios**:

1. **Given** the same user connected from two devices viewing the same chat, **When** the workspace changes, **Then** both devices reflect the change promptly, each in its device-adapted rendering.
2. **Given** a second device with different capabilities (e.g., no chart support), **When** it receives a workspace update, **Then** the update arrives in that device's adapted form, not the originating device's form.

---

### Edge Cases

- **Expired credential at reconnect**: A real-time reconnect carrying an expired credential MUST trigger silent renewal, not the current dead-end failure alert; only an unrenewable session routes to interactive sign-in, preserving the user's destination.
- **Redirect loop protection**: If Keycloak repeatedly errors or the callback fails, the user gets a bounded, recoverable error state — never an infinite shell→IdP→shell loop.
- **365-day cap mid-session**: When the cap is reached during active use, the current interaction completes or fails gracefully, and the next renewal attempt routes to interactive sign-in.
- **Clock skew**: Credential validity decisions tolerate reasonable clock skew between services (016 precedent: ±5 minutes).
- **Sign-out racing in-flight work**: Background or in-flight agent work for a user who signs out must not continue minting credentials on their behalf after revocation takes effect.
- **Same capability, different parameters**: Two results of one capability with different parameters are distinct components; identity must incorporate enough provenance to keep them apart (the current matcher would clobber one with the other).
- **Update for a component the user deleted from history**: An in-place update whose target identity no longer exists in the workspace is treated as an append (or gracefully dropped per contract), never an error shown as raw failure.
- **Timeline open while live moves**: Live updates continue to be applied to live state and broadcast to other devices; the historical viewer is informed live has changed but their view is stable.
- **Very long chats**: Timeline and re-hydration must behave acceptably for chats with hundreds of turns (bounded load times; the full snapshot set need not arrive at once).
- **Concurrent component actions**: Two actions targeting the same component (same or different devices) resolve in a deterministic order; the final state corresponds to the last completed action, with no interleaved corruption.
- **Permission lost between render and click**: If a user's access to a capability is revoked after a component rendered, a later component action against it is denied at execution time, communicated clearly, and audited.
- **Legacy saved-component behaviors**: The previously dormant save/combine/condense/replace behaviors are reconciled into the workspace model or explicitly retired — no path may remain that mutates server state invisibly to the user.
- **Unattended jobs vs durable sessions**: Scheduled/unattended work continues to rely on offline grants, not on the new durable interactive sessions; revoking either one independently behaves correctly.
- **Chat deletion during historical viewing**: Deleting a chat that another tab is time-traveling through ends the historical view gracefully.

## Requirements *(mandatory)*

### Functional Requirements

#### Authentication gate & sign-in (Story 1)

- **FR-001**: The system MUST require an authenticated session for every application surface — the app shell, all data/API access, and the real-time channel. Unauthenticated shell requests MUST be redirected directly to the Keycloak sign-in page; unauthenticated data and real-time requests MUST be refused.
- **FR-002**: The application MUST NOT present its own credential-collecting login screen; Keycloak conducts the entire credential exchange (Constitution VII). The redirect-out and return-in MUST be the only application-owned steps.
- **FR-003**: After successful sign-in, the user MUST land on the destination they originally requested, including chat deep links; a destination MUST never be silently dropped.
- **FR-004**: Sign-in failure modes (identity provider unreachable, callback rejected, user denied at IdP) MUST yield a bounded, recoverable error state with a retry path and MUST NOT produce redirect loops.
- **FR-005**: Authorization MUST continue to derive from Keycloak-issued roles: `user` or `admin` required for entry; `admin` required for admin surfaces, enforced server-side per request/action (027 precedent). A signed-in account with neither role MUST receive an explicit no-access outcome.

#### Session continuity (Story 2)

- **FR-006**: The system MUST renew sessions silently on the server side so that an active session never breaks when the short-lived access credential expires; renewal MUST be invisible to the user across page loads, real-time reconnects, and idle gaps.
- **FR-007**: Silent renewal MUST NOT extend the hard 365-day session lifetime anchored to the last interactive sign-in; only interactive sign-in resets the anchor (016 FR-001 semantics). At cap expiry, renewal MUST be refused and the user routed to interactive sign-in.
- **FR-008**: Sessions MUST be durable: they MUST survive service restarts and MUST function correctly when the service runs as multiple instances.
- **FR-009**: A real-time reconnect with an expired credential MUST recover via silent renewal without user action; if renewal is impossible the client MUST be routed to interactive sign-in with context preserved — the current dead-end failure alert MUST be eliminated.
- **FR-010**: The sign-in experience MUST preserve 016's negative requirements: no "Remember me"/"Stay signed in" choice (FR-001), no presence or biometric prompt on resume (FR-014), and no transient flash of a signed-out state when an authenticated user loads the app (FR-018 / feature 010).
- **FR-011**: The existing `auth` audit action types (`auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed`) MUST continue to be emitted with the same meanings; sign-out and revocation events MUST also be audited under the `auth` event class. Routine silent renewals MUST NOT flood the audit trail.

#### Sign-out & revocation (Story 7)

- **FR-012**: Sign-out MUST end the server session, revoke the user's refresh credential with the identity provider, and revoke all of the user's offline grants (feature 025) in the same flow.
- **FR-013**: Sign-out MUST complete locally and unconditionally even when the identity provider is unreachable, with revocation completed best-effort afterwards (016 FR-009 offline-tolerant semantics, now owned server-side).
- **FR-014**: An interactive sign-in by a different user in the same browser MUST revoke the prior user's session and make none of the prior user's state accessible (016 FR-008).

#### Production posture (Story 8)

- **FR-015**: Mock authentication MUST be refused outside an explicitly declared development mode; a production-mode start with mock auth enabled MUST fail fast with an operator-facing explanation.
- **FR-016**: Agent/automation connections MUST be authenticated in production; the absence of configured agent credentials MUST result in refused connections (fail closed), replacing the current fail-open behavior. Explicit dev mode MAY preserve today's local-development allowances.
- **FR-017**: The project MUST ship a committed, current operator document covering every Keycloak realm/client setting the feature depends on (session windows compatible with the 365-day promise, credential lifetimes, required roles, client and token-exchange configuration), replacing the referenced-but-never-committed realm-settings document.

#### Persistent workspace (Story 3)

- **FR-018**: Every rich component output produced in a chat MUST automatically become part of that chat's workspace under a stable component identity assigned by the system; no user gesture is required for persistence.
- **FR-019**: Component identity MUST be stable across updates and MUST distinguish outputs of the same capability invoked with different parameters; an update bearing an existing identity MUST update that component in place, and a new identity MUST append.
- **FR-020**: In-place updates MUST NOT redraw or disturb unrelated workspace components; user-visible state of untouched components (scroll, expanded sections, in-progress inputs) MUST be preserved through another component's update.
- **FR-021**: The workspace MUST be persisted server-side per chat and MUST NOT depend on any single client connection's lifetime; its state survives reloads, disconnects, and service restarts.
- **FR-022**: The existing separation of conversation stream and workspace MUST be preserved: textual answers, alerts, and status belong to the stream; rich components belong to the workspace.
- **FR-023**: Workspace mutations (component added, updated) MUST be auditable.
- **FR-024**: The structured component representation MUST remain on the wire alongside any rendered form for every workspace operation — including partial updates — so non-web client targets can participate (026 wire-contract preservation); all new real-time message types MUST be additive.
- **FR-025**: Per-device adaptation MUST continue to apply to workspace content, including partial updates and re-hydrated state — a device MUST never receive a component form its profile cannot present, and a device profile change MUST re-adapt the whole current workspace, not only the most recent update.
- **FR-026**: The legacy saved-component behaviors (manual save, combine, condense, replace) MUST be reconciled with the workspace model — each either subsumed by it, re-exposed through it, or explicitly retired — such that no server-side path mutates user-visible state invisibly.

#### Session re-hydration (Story 4)

- **FR-027**: Re-opening a chat MUST restore its workspace to exactly the state the user left, from persisted state, without re-running capabilities.
- **FR-028**: Component-bearing messages in a loaded transcript MUST render meaningfully in the conversation stream; the current empty-bubble rendering MUST be eliminated.
- **FR-029**: The assistant's working context about current workspace contents MUST be consistent with what the user actually sees, so that follow-up requests update the restored components rather than duplicating them.

#### Read-only workspace timeline (Story 6)

- **FR-030**: The system MUST capture the workspace state at each turn boundary (and after component-action mutations) such that the workspace as of any prior turn can be reproduced exactly.
- **FR-031**: Users MUST be able to view the workspace as of any prior turn in a clearly marked, strictly read-only historical view; mutating component actions MUST be unavailable there.
- **FR-032**: An explicit "back to live" affordance MUST restore the current workspace exactly, including changes that occurred during historical viewing; viewing the past MUST never mutate live state.
- **FR-033**: Historical workspace states MUST receive the same protection class as chat messages (they may contain the same sensitive data), MUST be deleted with their chat, and viewing them MUST be audited.

#### Component interaction loop (Story 5)

- **FR-034**: Every interaction emitted by a workspace component MUST carry the component's stable identity.
- **FR-035**: A standardized action contract MUST distinguish, explicitly and per action, between (a) deterministic actions that re-execute the component's source capability with defined parameters and update a workspace component in place, and (b) intent actions that enter the conversation as a user message for the assistant to handle.
- **FR-036**: Deterministic component actions MUST enforce exactly the same per-user agent-scope and per-tool permission rules as the equivalent chat-initiated invocation; denials MUST be user-visible and audited.
- **FR-037**: A deterministic action MAY target a different component than the one emitting it (cross-component links); a missing or stale target MUST produce a graceful, user-visible outcome.
- **FR-038**: Existing bespoke component behaviors (table pagination, parameter-picker submission) MUST be expressed through the standardized contract with no regression — and pagination MUST no longer replace unrelated workspace content.
- **FR-039**: Workspace changes produced by component actions MUST be captured in workspace history (FR-030) equivalently to turn-driven changes.

#### Multi-device consistency (Story 9)

- **FR-040**: Workspace changes MUST propagate promptly to all of the user's connected clients viewing the same chat, each receiving its own device-adapted rendering.

### Key Entities

- **User Session** *(existing concept, upgraded)*: A server-held record of an authenticated user — identity, roles, renewal credential, and the interactive sign-in anchor that bounds it to 365 days. Becomes durable (survives restarts, shared across service instances) and renewable (silent renewal without user action).
- **Offline Grant** *(existing — feature 025)*: A user's standing consent enabling unattended jobs. Gains a new lifecycle edge: revoked on sign-out.
- **Workspace**: The per-chat, ordered collection of live rich components a user sees alongside the conversation. Owned by exactly one chat; deleted with it.
- **Workspace Component**: One unit of rich content in a workspace. Carries a stable identity, source provenance (which agent/capability/parameters produced it), current content, and position. Updated in place when new content arrives under the same identity.
- **Workspace Snapshot**: An immutable record of a workspace's full state at a turn boundary or after a component-action mutation; the unit of the read-only timeline. Message-grade protection; deleted with its chat.
- **Component Action**: A user interaction emitted by a component — component identity, action kind (deterministic vs. intent), payload, and optional target component identity.
- **Chat** *(existing)*: Gains a one-to-one workspace and a one-to-many snapshot history.
- **Audit Event** *(existing)*: Extended with action types covering sign-out/revocation, workspace mutation, and historical-state viewing, under existing event classes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of application surfaces (shell, data access, real-time channel) are unreachable without an authenticated session; an unauthenticated visitor reaches the Keycloak sign-in in one redirect with zero application content disclosed.
- **SC-002**: A user who signs in once can work continuously for a full working day and resume at +1 minute, +1 hour, +7 days, and +30 days (016 matrix) with zero interactive re-authentications and zero user-visible authentication errors.
- **SC-003**: A backend service restart logs out zero active users; sessions resume on next request without re-authentication.
- **SC-004**: After sign-out, 100% of the user's credentials are unusable within one access-credential lifetime, and 100% of their offline grants are revoked.
- **SC-005**: A production-mode start with mock authentication enabled is refused 100% of the time; unauthenticated agent connections in production are refused 100% of the time.
- **SC-006**: After ten consecutive rich-output turns in one chat, all ten components remain visible and usable (today: only the last); zero components disappear without explicit user or assistant action.
- **SC-007**: An in-place component update renders within 1 second of arrival and leaves 100% of unrelated components' visible state untouched.
- **SC-008**: Re-opening a chat restores 100% of its workspace components and renders zero empty transcript bubbles for component-bearing history.
- **SC-009**: The timeline reproduces the workspace at any of the chat's prior turns, and "back to live" returns to a state identical to the current workspace 100% of the time.
- **SC-010**: A deterministic component refresh completes round-trip (interaction to updated component) within 2 seconds for typical data sets, without disturbing any other component.
- **SC-011**: 100% of component actions attempted without the required permissions are refused and audited.
- **SC-012**: A workspace change appears on a user's other connected device within 2 seconds in that device's adapted form.

## Assumptions

- **A1**: The organization's Keycloak realm (with `user`/`admin` roles, the existing clients, and token exchange for agent delegation) exists and is operator-managed; Keycloak's hosted sign-in page is acceptable UX, and theming it is out of scope.
- **A2**: Feature 016's persistent-login semantics carry forward wholesale (365-day hard cap from interactive sign-in, silent resume, offline-tolerant sign-out, user-switch revocation, the three `auth.*` audit action types) — with ownership now fully server-side. Building an in-app branded login screen is explicitly out of scope per the 2026-06-10 clarification.
- **A3**: The existing server-side OIDC flow, role model, and RFC 8693 agent delegation are reused, not replaced; no alternative identity provider is introduced (Constitution VII).
- **A4**: The workspace is scoped per chat (not global per user); deleting a chat deletes its workspace and snapshots. Cross-chat or global workspaces are out of scope.
- **A5**: Snapshot granularity is one snapshot per assistant turn plus one per component-action mutation; retention is the chat's lifetime (no separate retention regime).
- **A6**: The timeline is strictly read-only in 028; restoring or forking a past workspace state is deferred to a future feature.
- **A7**: No new third-party dependencies are introduced (Constitution V); the web client remains no-build vanilla JS; no SPA returns (Constitution II).
- **A8**: Any schema change ships as an idempotent auto-run migration consistent with house practice (Constitution IX).
- **A9**: Existing astralprims primitives (including their optional identity field) are sufficient; no new primitive types are expected. If one proves necessary, it follows the Constitution VIII define-approve-document flow as a dependency of this feature.
- **A10**: The timeline control and any minimal workspace toolbar are app chrome (server-rendered, outside per-device adaptation, per the 027 chrome pattern); workspace content itself stays on the primitives path. The remaining chrome deferred by 027 (sidebar/recent chats, dashboard empty-state, floating chat panel, onboarding spotlight) stays out of scope here except where this feature strictly needs it.
- **A11**: Snapshots and workspace state inherit the protection and audit posture of chat messages; no new PHI-handling regime is introduced.
- **A12**: Wiring the scheduler's unattended-turn execution seam is out of scope; this feature only adds offline-grant revocation at sign-out. Unattended jobs continue to use offline grants, independent of interactive sessions.
- **A13**: Local development with mock authentication remains fully supported under an explicitly declared dev mode.
- **A14**: Non-web client targets participate in workspace operations at the structured-data level; building a new native renderer is out of scope.

## Dependencies

- Reachable, operator-configured Keycloak realm (sign-in, silent renewal, revocation, and token exchange all depend on it); the FR-017 operator document records the required settings.
- Feature 016 (persistent-login semantics and audit action types), feature 025 (offline grants), feature 026 (server-driven rendering pipeline and wire contract), feature 027 (chrome surfaces and event dispatch) — all build surfaces this feature extends.
- The first-party astralprims package as published; this feature expects to consume it unchanged (A9).
