# Feature Specification: Bring-Your-Own Client-Side Agents

**Feature Branch**: `057-byo-client-agents`

**Created**: 2026-07-14

**Status**: Draft

**Input**: User description: "Allow users to create agents through any of the clients (except watch). This is partially implemented already but there needs to be a better, more user-friendly way to do it. When a user creates a new agent it runs alongside the client that it's running on — the agent should NOT be run on the orchestrator (central) server. Bring-your-own-agents is the mentality. All security features are implemented with the agent on the user's local computer, then another layer whenever it connects with the orchestrator, so that nefarious users cannot access anything they shouldn't be able to. Agents go offline when the client closes. User-created agents cannot be shared — your agent is your agent; a public agent is added via a manually-approved PR. Agent creation mimics the project's spec-driven development: a separate agent constitution, then the client guides the user through specify, clarify, plan, tasks, and analyze so the generated agent works with the system without much rewriting."

## Overview

Today a user gets a custom capability only when the assistant notices a gap mid-chat and drafts an agent that runs **inside the orchestrator** (feature 027 agentic creation). This feature makes agent creation a **deliberate, guided, user-initiated act** and moves the resulting agent **off the central server onto the user's own device**, connecting inward to the orchestrator like any other registered agent. The user owns their agent; nobody else can see or run it. Trust is established in two independent layers: the user's own machine gates what the agent may do locally, and the orchestrator re-verifies — treating the local agent as fully untrusted — everything the agent tries to reach across the boundary.

Authoring itself mirrors how this very project is built: an **agent constitution** states the non-negotiable contracts a user agent must satisfy, and the client walks the author through **Specify → Clarify → Plan → Tasks → Analyze** so that a non-expert produces an agent that plugs into the platform on the first try instead of iterating against runtime failures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an agent and run it on my own device (Priority: P1)

A user opens the agent-creation experience from their client, describes the capability they want, and — after a short guided authoring flow — the client produces a personal agent that **starts running on that user's device** and appears among their available agents in chat. When the user asks for that capability, the orchestrator routes the request to the user's locally-running agent, the agent does its work under the user's own authority, and the result comes back into chat. When the user closes the client, the agent goes offline and is simply unavailable until the client is reopened.

**Why this priority**: This is the whole point of the feature — a personal, self-hosted agent authored and run from the user's own client. Even with only the thinnest guided authoring and only the baseline boundary safety, this delivers the "bring your own agent" value end-to-end and is demonstrable on its own.

**Independent Test**: From a supported client, create a trivial agent (e.g., "greet me by name"), invoke it in chat and see a correct result, confirm no agent process was created on the orchestrator host, then close the client and confirm the agent is reported offline/unavailable.

**Acceptance Scenarios**:

1. **Given** a signed-in user on a supported client, **When** they complete agent creation, **Then** an agent process starts on the user's device (not on the orchestrator), registers inward, and becomes usable in that user's chats within the same session.
2. **Given** a user-created agent is running, **When** the user invokes one of its capabilities, **Then** the orchestrator routes the request to that user's local agent and returns the result, with the action attributed to the user in the audit trail.
3. **Given** a user-created agent is running, **When** the user closes (or loses connection from) the client that hosts it, **Then** the agent is marked offline, is removed from that user's active agent list, and invoking it yields an honest "this agent is offline" response rather than an error or a silent hang.
4. **Given** a user has never created an agent, **When** another user is signed in, **Then** the first user's agent is entirely invisible and unusable to the second user.

---

### User Story 2 - Be guided through spec-driven authoring against an agent constitution (Priority: P2)

Instead of a single free-text prompt, the client leads the author through the same phases the platform itself uses: **Specify** (what the agent does and why), **Clarify** (the client asks targeted questions to remove ambiguity), **Plan** (how the capability maps onto allowed tools, scopes, and data), **Tasks** (the concrete steps to build it), and **Analyze** (a consistency/quality pass against the **agent constitution** before any code is generated). The agent constitution is presented to the author as the rules their agent must obey to be accepted (how it registers, what it may request, what the boundary will reject). Clarify and Analyze are mandatory gates: an agent that would violate the constitution is caught and corrected **before** generation, not at runtime.

**Why this priority**: This is the "better, more user-friendly way" the user asked for and the mechanism that makes a non-expert's agent work without rework. It deepens US1's authoring but US1 can ship with a minimal version first.

**Independent Test**: Author an agent whose described behavior violates a constitution rule (e.g., it asks for a capability outside any grantable scope). Confirm the Clarify step surfaces the ambiguity and the Analyze step blocks progression with a specific, plain-language reason, and that correcting the spec lets authoring proceed to a successful generation.

**Acceptance Scenarios**:

1. **Given** a user starts agent creation, **When** they finish the Specify step, **Then** the client runs a Clarify step that asks only the questions needed to make the spec unambiguous and records the answers into the spec.
2. **Given** a drafted agent spec, **When** the Analyze step runs, **Then** it checks the spec against the agent constitution and either passes or reports each violation in plain language with the offending part of the spec.
3. **Given** an Analyze failure, **When** the user has not resolved it, **Then** the client does not generate agent code and does not allow the agent to go live.
4. **Given** a passing Analyze, **When** the user proceeds, **Then** the generated agent's declared capabilities, tools, and scopes match the approved plan exactly (no capability appears that was not specified).

---

### User Story 3 - Nefarious local agents cannot cross the boundary (Priority: P2)

A user's agent is untrusted the moment it talks to the orchestrator. Independently of whatever the agent does or claims locally, the orchestrator re-verifies every action against the **owning user's** current permissions and refuses anything outside them — reading another user's data, calling a tool the user was never granted, impersonating another agent or user, escalating its own scope, or exhausting shared resources. On the local side, the agent runs sandboxed under the user's own authority so its worst case is limited to that user's own resources. A tampered, buggy, or hostile user agent therefore cannot harm other users or the platform.

**Why this priority**: This is the security guarantee that makes running user-authored code against a shared multi-tenant server acceptable. It is non-negotiable for production; US1's baseline re-verification is the minimum, and this story is the hardened, adversarial-tested version.

**Independent Test**: Drive a deliberately-modified local agent that (a) requests a tool the owning user has not been granted, (b) references another user's data/identifier, and (c) claims to be a different agent. Confirm the orchestrator refuses each, fail-closed, with an audited reason, and that no other user's data is ever returned.

**Acceptance Scenarios**:

1. **Given** a user-created agent connected to the orchestrator, **When** it requests any tool or scope the owning user does not currently hold, **Then** the boundary denies it fail-closed and records the denial, regardless of what the agent asserts.
2. **Given** a user-created agent, **When** it attempts to act on or reference data belonging to a different user, **Then** the boundary blocks the access and the other user's data is never exposed.
3. **Given** a user-created agent, **When** it presents a token, identity, or request field it fabricated, **Then** the orchestrator ignores agent-supplied authority and derives the actor solely from its own record of the owning user.
4. **Given** a user-created agent under load, **When** it issues excessive or runaway requests, **Then** the orchestrator bounds its resource consumption so other users are unaffected.

---

### User Story 4 - Author from any client except the watch (Priority: P2)

The create-and-manage-agents experience is available and consistent on every supported client — the web client, the Windows desktop client, the Android client, and the Apple clients (iOS, macOS) — with equivalent capability and a consistent look and flow per the platform's cross-client rules. The watch client is explicitly excluded.

**Why this priority**: Reach and consistency matter, but the experience is valuable on even a single client first; parity is layered on.

**Independent Test**: Complete the same agent-creation journey on each supported client and confirm equivalent capability and outcome; confirm the watch client offers no agent-creation entry point.

**Acceptance Scenarios**:

1. **Given** any supported non-watch client, **When** the user opens agent creation, **Then** they can complete the full guided authoring journey with capability equivalent to every other supported client.
2. **Given** the watch client, **When** the user looks for agent creation, **Then** no create-agent affordance is present.
3. **Given** a client whose device cannot host a running agent, **When** the user authors an agent there, **Then** the client clearly communicates where/when the agent will actually run (see Clarifications) rather than implying it runs on the watch/phone silently.

---

### User Story 5 - Manage my agents; my agent stays mine (Priority: P3)

A user can see the agents they have created, edit/revise one (which re-runs the Clarify/Analyze gates and requires re-validation before the revision goes live), and delete one. User-created agents are private by construction: there is no in-product control to share an agent with another user or make it public. The only route to a fleet-wide agent is a human submitting it as a repository contribution that a maintainer approves manually.

**Why this priority**: Necessary for a complete, trustworthy experience but not required to demonstrate the core value.

**Independent Test**: Create two agents, list them, revise one (confirm the revision must re-pass Analyze before it is usable), delete the other (confirm it stops running and disappears), and confirm no UI path exists to share or publish either.

**Acceptance Scenarios**:

1. **Given** a user with created agents, **When** they open agent management, **Then** they see only their own agents with each agent's status (running / offline).
2. **Given** a user revises an agent, **When** the revision has not passed Analyze, **Then** the previous version keeps running and the revision is not usable until it validates.
3. **Given** a user deletes an agent, **When** the deletion completes, **Then** the local agent stops running and the agent is removed from the user's list and can no longer be invoked.
4. **Given** any user-created agent, **When** the user looks for a share/publish control, **Then** none exists; the documented path to a public agent is an external, manually-approved contribution.

---

### Edge Cases

- **Client closes mid-task**: an in-flight request to a user agent whose client disconnects returns an honest "agent went offline" outcome; no partial result is silently attributed to a later turn.
- **Reconnect / duplicate instances**: the same agent identity reappearing (client reopened, or the same user signed in on two devices) must not create a confused or ambiguous routing state; the orchestrator resolves which instance (if any) is authoritative.
- **Author on one device, run on another**: if authoring happens on a client that cannot host a runtime, the agent's actual execution location must be explicit to the user (see Clarifications).
- **Constitution changes after an agent exists**: an agent authored against an older agent-constitution version must be re-validated (or flagged) before it is trusted again — a revision resets its accepted state.
- **Offline / degraded network**: creation, local execution, and boundary verification each fail closed with honest messaging rather than proceeding unverified.
- **Malformed or crashing user agent**: a user agent that crashes or emits malformed frames is dropped cleanly (offline), never destabilizing the orchestrator or other users' sessions.
- **Resource abuse**: a user agent that spins or floods requests is bounded so it degrades only its own owner's experience.
- **Name/identity collision**: a user-created agent may not take an identity that collides with a built-in/public agent or another user's agent in a way that could misroute a request.

## Requirements *(mandatory)*

### Functional Requirements

**Authoring experience**

- **FR-001**: Users MUST be able to initiate agent creation deliberately (not only via an assistant-detected gap) from any supported non-watch client.
- **FR-002**: The system MUST guide the author through five explicit phases — Specify, Clarify, Plan, Tasks, Analyze — before an agent can go live.
- **FR-003**: The Clarify and Analyze phases MUST be mandatory gates; an agent MUST NOT be generated or activated while unresolved clarifications or Analyze violations remain.
- **FR-004**: The system MUST maintain a dedicated **agent constitution** — distinct from the project constitution — stating the contracts a user agent must satisfy (registration, declared tools/scopes, security posture, and what the boundary will reject), and MUST present its relevant rules to the author.
- **FR-005**: The Analyze phase MUST validate the drafted agent against the agent constitution and report each violation in plain, non-technical language tied to the offending part of the spec.
- **FR-006**: A generated agent's declared capabilities, tools, and requested scopes MUST match the author-approved plan; no capability, tool, or scope may appear that was not specified and analyzed.
- **FR-007**: The system SHOULD reuse the existing draft/agentic-creation lifecycle (gap→draft→self-test→approve/refine/discard) where it fits, rather than introducing a parallel unreviewed path.

**Client-side execution**

- **FR-008**: A user-created agent MUST run on the user's own device and MUST NOT run as a process hosted on the orchestrator/central server. Agent hosting is a device capability: in this feature the host is a desktop client (Windows, macOS) running the agent as a real local process; the design MUST NOT preclude adding on-device mobile/web runtimes later.
- **FR-009**: A user-created agent MUST connect inward to the orchestrator using the platform's existing agent-registration/transport path and be routable like any other registered agent for that user.
- **FR-010**: A user-created agent MUST go offline when the client that hosts it closes or disconnects, with no server-side fallback, keep-alive, or re-hosting.
- **FR-011**: Invoking an offline user agent MUST return an honest "offline/unavailable" response promptly, never an indefinite hang or a misleading error.
- **FR-012**: The orchestrator MUST attribute a user agent's actions to the owning human in the audit trail, using the platform's delegated-authority model (the agent acts as a delegate of its owner).

**Two-layer security**

- **FR-013**: The user's device MUST gate what the local agent can do (local sandbox), constraining it to the user's own resources and authority.
- **FR-014**: The orchestrator MUST treat every user-created agent as untrusted and MUST independently re-verify every action it attempts across the boundary against the owning user's CURRENT permissions and scopes, fail-closed.
- **FR-015**: The boundary MUST NOT accept authority, identity, or scope from anything the agent presents; the acting principal and grants MUST be derived from the orchestrator's own record of the owning user.
- **FR-016**: A user agent MUST NOT be able to read, reference, or act on another user's data, or invoke a tool/scope the owning user does not hold — any such attempt MUST be denied and audited.
- **FR-017**: The orchestrator MUST bound a user agent's resource consumption so a runaway or hostile agent degrades only its own owner's experience, not other users or the platform.
- **FR-018**: All existing server-side gates (permission checks, delegation minting, taint/PHI, supervisor/HITL where applicable) MUST apply to user-agent actions with no bypass; the boundary layer's guarantees MUST hold independently of the local sandbox.

**Privacy & sharing**

- **FR-019**: User-created agents MUST be private to their owner; no other user may see, list, route to, or invoke them.
- **FR-020**: The product MUST provide no control to share, publish, or transfer a user-created agent to another user or to the fleet.
- **FR-021**: The only supported path to a fleet-wide/public agent MUST be an out-of-product, manually-approved repository contribution.

**Cross-client parity**

- **FR-022**: The create-and-manage-agents experience MUST be available with equivalent capability on the web, Windows, Android, and Apple (iOS, macOS) clients, consistent with the platform's cross-client consistency rules.
- **FR-023**: The watch client MUST NOT offer any agent-creation affordance.
- **FR-024**: On a client whose device is not an agent host (the web client, Android, iOS), the user MUST be able to author and manage agents, and the experience MUST make explicit that the agent runs on the user's desktop host and is available only while that host is online (including an honest state when the user has no desktop host running).

**Lifecycle management**

- **FR-025**: Users MUST be able to list their own created agents with each agent's current status (running / offline).
- **FR-026**: Users MUST be able to revise a created agent; a revision MUST re-pass the Clarify/Analyze gates and re-validate before it becomes usable, and the prior version MUST keep running until the revision is validated.
- **FR-027**: Users MUST be able to delete a created agent, which stops the local agent and removes it from the user's list and routing.
- **FR-028**: A change to the agent constitution MUST cause affected existing agents to require re-validation before they are trusted again.

**Constraints**

- **FR-029**: The feature MUST honor the platform's fail-closed production posture; any unverifiable step (creation, execution, boundary check) MUST refuse rather than proceed.
- **FR-030**: The feature MUST introduce zero or minimal new third-party runtime dependencies, consistent with the dependency-management principle.
- **FR-031**: Any authoring/management chrome MUST follow the server-driven UI model (primitives defined centrally, rendered by the orchestrator, adapted per device) and the cross-client theming/layout rules.

### Key Entities *(include if feature involves data)*

- **User Agent**: a capability authored and owned by one user, running on that user's device. Attributes: owner, declared capabilities/tools/requested scopes, constitution-version it was validated against, current runtime status (running/offline), authoring-phase state, private-by-construction. Relationships: belongs to exactly one user; delegates from that user; never shared.
- **Agent Constitution**: the versioned set of contracts a user agent must satisfy to be accepted (registration shape, allowable tools/scopes, security posture, boundary-rejection rules). Relationships: every User Agent is validated against a specific version of it; a version change triggers re-validation.
- **Authoring Session**: the guided Specify→Clarify→Plan→Tasks→Analyze journey that produces (or revises) a User Agent, including the clarifications captured and the Analyze result. Relationships: produces one User Agent draft/revision.
- **Boundary Verification Record**: the per-action, server-side re-verification outcome for a user-agent request (allowed/denied, owning user, derived scopes, reason). Relationships: attributed to the owning human; feeds the audit trail.
- **Owning User**: the human who created the agent and whose authority it delegates; the sole principal the boundary derives grants from.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A non-expert user can go from "start creating an agent" to "a working agent running on my device and usable in chat" for a simple capability in under 10 minutes, on their first attempt, without editing generated code by hand.
- **SC-002**: 100% of user-created agents run off the orchestrator host — zero user-agent processes are hosted on the central server.
- **SC-003**: 0 successful cross-user accesses: no user-created agent, including deliberately hostile ones in adversarial testing, ever reaches another user's data or a tool/scope its owner does not hold; every such attempt is denied and audited.
- **SC-004**: 100% of agents that reach "live" status passed the Clarify and Analyze gates; agents that fail Analyze never go live.
- **SC-005**: When a hosting client closes, its agents are reported offline within a few seconds and subsequent invocations return an honest offline response rather than hanging.
- **SC-006**: The guided authoring journey is completable with equivalent capability on every supported non-watch client, and is absent on the watch.
- **SC-007**: There is no in-product path by which one user's agent becomes visible or usable to another user.
- **SC-008**: A runaway or flooding user agent measurably degrades only its owner's experience; other users' latency and success rates are unaffected during adversarial load testing.

## Assumptions

- The existing agent-registration/transport, delegated-authority (RFC 8693), and server-side permission/taint/audit gates are the intended foundation for the boundary layer and are reused rather than replaced.
- The existing draft/agentic-creation lifecycle and its self-test/approval machinery are reused for the generation and go-live steps where they fit.
- Agent hosting is a device capability resolved per the Clarifications: desktop clients (Windows, macOS) are the v1 host; the web client, Android, and iOS author and manage agents whose execution binds to the user's desktop host. On-device mobile/web runtimes are a future extension the design must not preclude.
- A user with no desktop host running can still author and manage agents; those agents are simply offline until a desktop host is available — consistent with the offline-on-client-close model.
- Personal user agents are expected to be modest in scope (personal utilities and integrations), not high-availability shared services — consistent with offline-on-client-close.
- The agent constitution is authored and versioned in the repository (like the project constitution), and is the single source the Analyze gate checks against.
- Watch is excluded because it is a companion surface without an agent-hosting or full-authoring role.

## Clarifications

### Session 2026-07-14

- **Q: Where does a user's agent run on clients that can't host an OS process (web, Android, iOS)?** → **A: Agent hosting is a device capability. In this feature, desktop clients (Windows, macOS) are the agent host — they run the agent as a real local process. Mobile (Android, iOS) and the web client are full authoring + management surfaces, but their authored agents run on the user's own desktop host and are online only while that host client is running.** Rationale: keeps one uniform runtime and one uniform untrusted-at-the-boundary security model, reuses the existing agent stack, and honors zero/minimal-new-dependency and fail-closed constraints; a portable in-app runtime on mobile/web would be a large new dependency and a second security surface, and the web client is deliberately thin/server-driven. On-device mobile/web runtimes are a deliberate future extension — the design MUST NOT preclude them, but they are out of scope here.

- **Q: What form does a user agent take, and how is it sandboxed locally?** → **A: The platform's existing (Python) agent form, reusing the current agent-registration, code-generation, and self-test machinery, sandboxed on the user's desktop host.** A separate portable capability form is out of scope for this feature (folded into the future on-device-runtime extension above).

- **Q: How should the guided Specify → Clarify → Plan → Tasks → Analyze journey feel?** → **A: Hybrid — the client's assistant drafts a structured artifact for each phase, which the author reviews and edits before proceeding.** Clarify and Analyze remain mandatory gates.
