# Feature Specification: macOS BYO Agent Host

**Feature Branch**: `059-macos-agent-host`

**Created**: 2026-07-15

**Status**: Draft (specify step only — plan/tasks deferred)

**Input**: User description: "macOS BYO agent host — give the macOS desktop client the ability to host a user's BYO agent (features 057/058) as an isolated child process, the macOS equivalent of the shipped Windows host. Today apple-clients is author-only. Closes the platform gap and unblocks live verification on a Mac of T027 revise rollover and offline-on-close."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run my own agent on my own Mac (Priority: P1)

Someone who has authored a personal BYO agent wants it to actually run on their **own Mac**
(through the desktop app) so they can invoke it from chat — without needing a Windows PC. They
open the desktop client, sign in, author (or already have) an agent, generate it, and it comes
to life on their machine and answers from the chat.

**Why this priority**: This is the entire feature — the capability that does not exist today.
Without it, macOS users can only author agents they can never run.

**Independent Test**: On a hosting-capable macOS client: author → generate → the agent is
delivered to this Mac → it registers inward → invoke its tool from chat → its result (an
astralprims component) renders. Fully demonstrable end-to-end on one Mac.

**Acceptance Scenarios**:

1. **Given** a signed-in hosting-capable macOS client with an authored, Analyze-passed agent,
   **When** the user generates it, **Then** the agent runs as a separate process on the Mac,
   registers with the orchestrator, and can be invoked from chat with its output rendered.
2. **Given** a running hosted agent, **When** the user invokes one of its tools, **Then** the
   request reaches the agent and the response returns, with the orchestrator having
   re-authorized the call at its boundary.

---

### User Story 2 - Revise a running agent with no downtime (Priority: P1)

An owner improves an agent that is currently running. The previous version keeps answering
while the revision is prepared and starts; only once the revised version is confirmed running
does it take over. If the revision fails to come up, the previous version keeps running — the
user is never left with a dead agent.

**Why this priority**: This is the T027 behavior already built and tested on the Windows host;
hosting on macOS is the only way to verify it live on a Mac, and a naive "stop then start"
would regress it.

**Independent Test**: With a running hosted agent, deliver a revision → confirm the old version
answers throughout the switch and the new version takes over cleanly; separately, deliver a
revision that never registers → confirm the old version keeps answering.

**Acceptance Scenarios**:

1. **Given** a running hosted agent, **When** a revision is delivered and successfully starts,
   **Then** there is no observable gap in the agent's availability and the new version replaces
   the old.
2. **Given** a running hosted agent, **When** a revision is delivered but fails to start in
   time, **Then** the previous version continues running and the user is told the update was
   not accepted.

---

### User Story 3 - Honest offline on close and stop (Priority: P2)

When the user quits the app, signs out, or stops/deletes an agent, the hosted agent goes
offline honestly: the orchestrator knows it is gone, and any later invocation returns a prompt
"offline" response instead of hanging. There is no server-side fallback keeping it alive.

**Why this priority**: "Offline is honest, no fallback" is a core 058 posture; it is also the
second behavior needing a live Mac host to verify, and it prevents stuck invocations.

**Independent Test**: Close the app while an agent is hosted → confirm the agent shows offline
and a subsequent invocation returns an honest offline response; stop an agent → confirm its
process is terminated and its bundle handled correctly.

**Acceptance Scenarios**:

1. **Given** a hosted, running agent, **When** the app closes or the user signs out, **Then**
   the agent's process is terminated and the orchestrator marks it offline.
2. **Given** an agent that has gone offline, **When** it is invoked, **Then** the caller
   receives a prompt honest offline response, not a hang.

---

### User Story 4 - Author-only clients keep working (Priority: P2)

On the Mac App Store build (and on mobile/web), the user can still author and manage agents. If
they generate an agent with no hosting-capable desktop client connected, they are told honestly
to open their desktop client to run it — no hosting is attempted where it cannot work.

**Why this priority**: Protects the shipping MAS build and every author-only client from
regression; the hosting capability must be additive, not a behavior change elsewhere.

**Independent Test**: On the sandboxed MAS build, author → generate with no host → confirm the
honest "open your desktop client" message and that no hosting is attempted; confirm authoring
and management are unchanged.

**Acceptance Scenarios**:

1. **Given** an author-only client, **When** the user generates an agent and no host is
   connected, **Then** they receive the honest "open your desktop client and run Generate
   again" message.
2. **Given** an author-only client, **When** the user authors or manages agents, **Then** the
   experience is unchanged from before this feature.

### Edge Cases

- **No host at generate**: generation on any client with no hosting-capable desktop connected
  returns the honest "no host" message and delivers no code.
- **Agent crashes at runtime**: the process exits; the agent appears offline (no auto-respawn,
  no flapping); the user is informed.
- **Refused/silent registration**: a delivered agent that never registers within a bounded time
  is reaped and surfaced, rather than left as a stuck or invisible process.
- **Unsafe agent identifier**: an identifier that could escape its storage area (path traversal)
  is refused before anything is written.
- **App quit mid-revision**: closing the app during an in-flight revision must not orphan the
  pending process.
- **Reconnect mid-run**: a dropped-and-restored connection re-registers running agents without
  restarting them; a relaunch restores agents delivered in a prior session.
- **Multiple desktop hosts**: an agent is delivered to a hosting-capable client; behavior with
  more than one connected host is well-defined (no duplicate hosting of the same agent).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The macOS desktop client MUST be able to receive a generated agent bundle and run
  it as an isolated operating-system process, separate from the app.
- **FR-002**: A hosted agent MUST NOT be able to reach the app's stored credentials, session
  tokens, or authenticated socket — enforced by running it in a separate process, not in the
  app's address space.
- **FR-003**: The client MUST relay the agent's messages to and from the orchestrator over the
  client's existing authenticated connection **without interpreting or altering them**, so the
  orchestrator re-applies every authorization gate (owner binding, permissions, delegation,
  PHI) at its boundary.
- **FR-004**: The client MUST declare itself hosting-capable so the orchestrator delivers
  bundles to it, and the orchestrator MUST NOT deliver executable code to a non-hosting client.
- **FR-005**: When an agent is revised while running, the client MUST keep the current version
  serving until the revised version is confirmed running, then switch over with no observable
  gap; a revision that fails to start MUST NOT stop the running version (zero-downtime rollover).
- **FR-006**: The client MUST take a hosted agent honestly offline when the app closes, the user
  signs out, or the agent is stopped/deleted — with no server-side fallback and no hang on a
  later invocation.
- **FR-007**: The client MUST re-register hosted agents after a dropped-and-restored connection,
  and MUST restore agents delivered in a previous session when the app relaunches, so a restart
  does not permanently orphan a user's agents.
- **FR-008**: The client MUST treat a delivered agent as untrusted at rest: reject unsafe
  identifiers, refuse to write outside the agent's own storage area, and never keep executing a
  bundle whose registration the orchestrator refuses.
- **FR-009**: If a delivered agent does not register within a bounded time, the client MUST reap
  it and surface the failure, rather than leave a stuck or invisible process.
- **FR-010**: Author-only clients (the sandboxed Mac App Store build, and mobile/web) MUST
  continue to author and manage agents unchanged, and MUST tell the user honestly to open a
  hosting-capable desktop client when generation has no host to deliver to.
- **FR-011**: Hosting MUST require no manual setup by the user (no installing a language runtime
  or dependencies) — the runtime a delivered agent needs is provided by the client.
- **FR-012**: The feature MUST add zero new runtime dependencies to the orchestrator or its
  server image; the agent runtime is a client-only artifact.

### Key Entities

- **Agent bundle**: the delivered set of files that constitute one runnable agent, carrying an
  owner-namespaced identity and a constitution/version stamp.
- **Hosted agent (child process)**: a running instance of an agent supervised by the client,
  with a derived lifecycle status (starting / running / offline) that is never persisted.
- **Host session**: the client's identity as a host for the life of a session, used by the
  orchestrator to route deliveries and detect the host going away.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent authored on any client can be run on the user's Mac and invoked from
  chat, with its result rendered, **without the user installing anything**.
- **SC-002**: Revising a running agent causes **no observable gap** in availability (it answers
  throughout the switch), and a failed revision leaves the previous version answering.
- **SC-003**: Closing the app takes hosted agents offline within a few seconds, and any
  subsequent invocation returns a prompt honest "offline" response rather than hanging.
- **SC-004**: A hosted agent runs in a process isolated from the app such that it cannot read
  the app's stored credentials (verifiable by inspection/test).
- **SC-005**: Author-only clients (MAS / mobile / web) show **no regression**: authoring and
  management still work, and generation without a host produces the honest "open your desktop
  client" message every time.
- **SC-006**: The two behaviors already built for the Windows host — zero-downtime revision
  (T027) and honest offline-on-close — are demonstrable **live on a Mac**.

## Assumptions

- **MAS cannot host; a new channel is required.** The Mac App Store build's App Sandbox forbids
  spawning child processes and executing a packaged interpreter, so hosting requires a new
  **non-sandboxed, Developer-ID-signed, notarized direct-download** macOS build that does not
  exist yet. The MAS build stays author-only. (057 research §D5; 058 spec; apple-clients README
  §053.)
- **The client provides the agent runtime.** A delivered agent imports only `astralprims`, which
  requires a real Python runtime with pydantic and a native `pydantic-core`; the client bundles
  this runtime as a **client-only artifact** (a frozen helper mirroring the shipped Windows
  model), so there is no user setup and no orchestrator dependency (FR-011, FR-012).
- **Reuse of the Windows host design.** The macOS host reuses the design and behavior of the
  just-hardened `ByoAgentHost` (Windows), **including the T027 staging + swap-on-ack rollover**,
  the register-timeout silence trap, rehydrate/re-register on reconnect, path safety, and
  stop-all on quit/sign-out; it rides the existing authenticated WebSocket tunnel in AstralCore.
- **Phased delivery.** Phase 1 = the Swift host + a non-sandboxed dev build configuration +
  running the child with a development Python, provable end-to-end locally on a Mac (unsigned) —
  this closes the Mac verification gap for SC-006. Phase 2 = the frozen runtime helper + the
  Developer-ID notarized direct-download build target + a CI lane. Architecture fallback if the
  frozen-helper codesigning proves too rough: an embedded `python-build-standalone` Python
  framework (same process model, more signing surface).
- **Unchanged from 058**: delivery-to-host, the untrusted-boundary re-verification, owner
  binding, permission/delegation gates, and the 5-phase authoring flow are inherited unchanged.
- **Dependency**: the shippable (Phase 2) direct-download channel requires an Apple **Developer
  ID Application** certificate and notarization credentials.
- **Non-goals**: Mac App Store hosting; on-device iOS/Android agent runtimes; Cresco Mode-2
  transport.
