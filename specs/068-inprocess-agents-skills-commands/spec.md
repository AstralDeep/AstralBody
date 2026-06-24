# Feature Specification: In-Process Built-In Agents, Owner-Safe Marking, and Skills + Slash Commands

**Feature Branch**: `068-inprocess-agents-skills-commands`
**Created**: 2026-06-24
**Status**: Draft
**Input**: User description: "Mark the agents that ship with the system as safe (owner-approved), keep them fully auditable with security paramount, cut the network overhead of running each shipped agent on its own host and port by building them into the system and making them as performant as possible, investigate skills and slash commands like Claude Code and implement/improve what fits, remove the etf_tracker_1 agent, and keep + review the rest."

## Clarifications

### Session 2026-06-24

- Q: What should the "safe" marker concretely do for shipped agents? → A: Record an audited owner-approved provenance marker **and** auto-enable each safe agent's default tool scopes so they work out-of-the-box. All runtime per-call gates stay fully enforced; "safe" is never a runtime bypass, and genuinely flagged/destructive tools stay gated.
- Q: For "skills and slash commands like Claude Code," what should be built? → A: **Both** — authored, version-controlled, progressive-disclosure skill packs the model loads on demand by relevance (including wiring the dormant per-agent technique loader), **and** a user-typed `/command` surface in chat routed through the existing permission/audit/PHI rails.
- Q: Which agents move in-process, and do bundled agents stop running their own process/port? → A: **All 9 bundled first-party agents run in-process with no per-agent port.** Genuinely external A2A agents keep their networked transport. User-created draft agents keep today's subprocess + self-test isolation.
- Q: How are per-user credentials handled once agents are in-process? → A: **Keep per-agent end-to-end (ECIES) decryption inside each agent's own boundary.** The orchestrator must never materialize plaintext per-user secrets, even though there is no longer a network boundary.
- Q: When a built-in agent is marked safe, which of its tool scopes auto-enable? → A: **All of the agent's scopes/tools auto-enable by default**, except (a) any scope or specific tool the user has explicitly disabled — explicit user opt-out always wins — and (b) tools the security analyzer hard-blocks, which still require a separate, audited owner action.
- Q: How is that auto-enable applied across users? → A: **As a system-level default consulted at the per-call permission check** — no per-user permission rows are written, and a user's explicit disable overrides the safe default.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Built-in agents run inside the system, not as separate networked services (Priority: P1)

A person chats with the assistant and triggers a tool that belongs to one of the agents that ship with the product (e.g. asking for the weather, a summary, or a journal-fit analysis). Today each of those agents runs as its own operating-system process listening on its own network port, and the orchestrator reaches it over a WebSocket round-trip for every call. In this story the same request is served by the agent running **inside** the orchestrator process — no separate process, no port, no network hop — and the person sees exactly the same answer, components, streaming, and progress as before, only faster and with less moving infrastructure.

**Why this priority**: This is the core of the request ("running these agents on their own host and port is ridiculous… build these agents into the system and have them act as performant as possible"). It removes per-call network overhead and a whole class of process/port lifecycle fragility, and it is the foundation the other stories build on. It delivers value on its own.

**Independent Test**: With the in-process flag on, run the full existing agent test suite plus a manual chat against each bundled agent (unary tool, streaming tool, long-running job, credentialed tool). Confirm results, UI components, progress, and streaming are byte-for-byte equivalent to the networked path, that no per-agent port is listening, and that turn latency is no worse (and measurably better for the local hop).

**Acceptance Scenarios**:

1. **Given** the in-process execution flag is enabled, **When** a chat turn calls a bundled agent's unary tool, **Then** the response payload, UI components, error shape, and correlation id are identical to the previous WebSocket path, and no separate agent process/port was contacted.
2. **Given** a bundled agent exposes a push-streaming tool (e.g. live temperature), **When** a user starts and then cancels the stream, **Then** partial chunks arrive in order, fan out to all of the user's sockets on that chat, and cancellation stops the stream — exactly as before.
3. **Given** a bundled agent starts a long-running training job, **When** the tool is invoked, **Then** the call returns a "started" response promptly while the background job continues, posts progress, persists its terminal result to the workspace, and releases its concurrency slot.
4. **Given** a genuinely external A2A agent is connected, **When** one of its tools is called, **Then** it is still reached over its networked transport (the in-process path is used only for registered built-ins).
5. **Given** a slow synchronous tool is running for one user, **When** other users send turns, **Then** their chats and streams are not blocked or delayed by the slow tool.

---

### User Story 2 - Trusted built-in agents work out of the box (Priority: P1)

The product owner has reviewed and approved the agents that ship with the system. In this story those agents carry an explicit, recorded "safe / owner-approved" status, and a brand-new person can use each safe agent's tools immediately without first hunting through settings to enable permissions — while tools the security analyzer genuinely blocks still require a separate owner action, anything a user has personally turned off stays off, and every action remains in the audit log.

**Why this priority**: Directly fulfills "mark them as safe (since they are approved by me)" while honoring "everything should still be auditable and security of these approved agents is still paramount." The auto-enable of default scopes is what turns "approved by the owner" into "usable by people without friction," which is the practical payoff of marking safe.

**Independent Test**: As a fresh user account with no prior permission grants, open a chat and invoke a default tool of a safe built-in agent; confirm it runs without a manual enable step. Then attempt a flagged/sensitive tool and confirm it is still gated. Inspect the audit log and confirm a `marked_safe` provenance event and normal per-call tool events exist.

**Acceptance Scenarios**:

1. **Given** a bundled agent has been marked safe by the owner, **When** a brand-new user invokes any of that agent's tools, **Then** the tool runs without requiring the user to manually enable a scope first (the safe default grants access at the permission check).
2. **Given** a safe agent also exposes a tool the security analyzer hard-blocks (e.g. a genuinely blocked threat category), **When** a user triggers that tool, **Then** the runtime block still applies (the safe marker does not auto-clear it).
3. **Given** a non-owner/non-admin user, **When** they attempt to mark an agent safe, **Then** the action is refused server-side.
4. **Given** a safe agent is revised through the agent-revision path, **When** the revision is applied, **Then** the safe marker is reset and re-approval is required before the revision is treated as safe.
5. **Given** any safe-marking change, **When** it is applied, **Then** an audited lifecycle event records the actor, the agent, and the prior state.
6. **Given** a user has explicitly disabled a scope or a specific tool of a safe agent, **When** they invoke that tool, **Then** their explicit opt-out wins and the tool is gated despite the safe default.

---

### User Story 3 - Retire the etf_tracker_1 agent cleanly (Priority: P2)

The owner no longer wants the `etf_tracker_1` agent in the product. In this story it is removed entirely — it disappears from the agent catalog, the agents surface, chat tool lists, and history glyphs — and any leftover data tied to it (ownership, scope, override, credential rows, and conversation references) is cleaned up so the removal is complete rather than half-done.

**Why this priority**: A direct, explicit instruction ("Remove the etf_tracker_1 agent"). It is low-risk and independently shippable, but lower value than the in-process and safe-marking work, so it is P2.

**Independent Test**: After removal, confirm the agent and its tools are absent everywhere a user could encounter them, the test suite is green, a fresh startup leaves no orphaned rows for the retired id, and opening an old transcript that used its tools shows a graceful retirement notice rather than an error.

**Acceptance Scenarios**:

1. **Given** the agent is removed, **When** the system starts and a user opens the agents surface and a new chat, **Then** `etf_tracker_1` and its tools appear nowhere.
2. **Given** prior runtime rows existed for the retired agent id, **When** the startup migration runs (and re-runs), **Then** orphaned ownership/scope/override/credential rows are purged idempotently and any conversation references are retired or reassigned.
3. **Given** an old chat transcript that invoked a retired tool, **When** the user reopens it, **Then** they see a clear retirement notice instead of an error.

---

### User Story 4 - The assistant draws on the right know-how at the right time (Priority: P2)

When a person's request maps to a particular agent or domain, the assistant should be able to pull in concise, authored guidance about how to use that capability well (effective patterns, anti-patterns, recommended tool sequences) — but only the guidance relevant to that turn, not a dump of everything every time. In this story curated "skill packs" exist for capabilities, the assistant loads only the ones relevant to the current request, and authored guidance is protected from being silently overwritten by the system's automatic knowledge generation.

**Why this priority**: Implements the "skills … like Claude Code" investigation outcome (progressive disclosure of capability know-how). It improves answer quality and tool-use reliability and unlocks the lowest-effort win found in discovery (per-agent technique knowledge that is currently produced but never delivered to the model). It is valuable but not a prerequisite for the in-process or safe work, so P2.

**Independent Test**: Issue a request clearly tied to one capability and confirm only that capability's pack is loaded into the turn (not every agent's). Confirm a request unrelated to any pack loads none and the per-turn context does not grow. Re-run the automatic knowledge generation and confirm authored packs are not clobbered.

**Acceptance Scenarios**:

1. **Given** authored skill packs exist for several capabilities, **When** a user makes a request clearly tied to one capability, **Then** only the relevant pack(s) are loaded into the model's context for that turn.
2. **Given** a request unrelated to any pack, **When** the turn is processed, **Then** no skill pack is injected and the baseline per-turn context size is unchanged.
3. **Given** the automatic knowledge synthesizer runs, **When** it regenerates knowledge, **Then** human-authored packs are preserved (stored where synthesis cannot overwrite them).
4. **Given** skill loading fails for any reason, **When** a turn is processed, **Then** the turn proceeds as it does today (fail-open) without error.

---

### User Story 5 - People can invoke shortcuts with typed slash commands (Priority: P3)

A person types a `/command` in the chat input (for example a command that prefills a common request, or one that kicks off a specific flow). The command surface offers discoverable options as they type, and the command runs through the same permission, audit, and privacy checks as any other message — it is a convenience, not a way to skip the rules.

**Why this priority**: Implements the "slash commands like Claude Code" half of the request. It is the most net-new surface, depends on nothing else here, and is a convenience layer rather than core infrastructure, so it is P3.

**Independent Test**: Type a known command and confirm it expands/triggers as specified and executes through the normal gates (a command that would call a gated tool still respects the user's scopes and is audited). Type an unknown/malformed command and confirm a friendly message, not an error. Confirm the command UI renders through the server-driven UI layer and adapts across device targets.

**Acceptance Scenarios**:

1. **Given** the slash-command surface is enabled, **When** a user types a known `/command`, **Then** it either expands into a normal model turn or triggers its defined flow.
2. **Given** a command whose flow would invoke a permission-gated tool, **When** the user lacks the required scope, **Then** the normal consent/permission gate applies — the command does not bypass it.
3. **Given** a user typing `/`, **When** they pause, **Then** available commands are discoverable (typeahead/help), and an unknown or malformed command yields a friendly message rather than an error.
4. **Given** any command invocation, **When** it executes, **Then** it is recorded in the audit log like any other turn, and its input is treated as untrusted (subject to the same PHI/taint/policy handling).

---

### Edge Cases

- **Credentialed in-process tool with a stale/undecryptable secret**: the agent must still detect the stale-credential condition inside its own boundary and surface the same "credentials need attention" outcome as today, without the orchestrator seeing plaintext.
- **A bundled agent tool raises an exception in-process**: it must be caught and classified (retryable vs not) the same way the networked path classified it, so retry/backoff and any fallback behave identically.
- **An external A2A agent shares an id-shaped name with a built-in**: routing must select in-process only for the positively-registered built-in and never misroute an external agent into a missing in-process object.
- **Audit backend is temporarily unavailable during an in-process call**: the call must still succeed and the audit write must queue for retry (best-effort, non-blocking) exactly as today — never block or fail the tool because of audit.
- **A turn dispatches multiple tools in parallel**: each parallel tool call must be audited (closing the current gap where the parallel path emits no tool events).
- **Marking an agent safe when a tool of it is genuinely blocked by a security flag**: "safe" must not silently clear the block; the owner must take an explicit, separately-audited action to accept a flagged tool.
- **Skill pack relevance is ambiguous**: loading must remain bounded (a small, capped selection) so context/token budget and cache stability are not degraded.
- **A slash command collides with normal text starting with "/"**: parsing must distinguish a real command from ordinary text and never swallow a legitimate message.
- **Removing etf_tracker_1 while a scheduled job or open transcript references it**: must degrade gracefully via the existing retired-agent handling.

## Requirements *(mandatory)*

### Functional Requirements

#### In-process built-in agents (US1)

- **FR-001**: System MUST execute every bundled first-party agent (connectors, dice_roller, general, journal_review, medical, ml_services, summarizer, web_research, weather) in-process within the orchestrator, with no per-agent network port or standalone server, when the in-process feature flag is enabled.
- **FR-002**: A chat-initiated tool call to a built-in agent MUST produce a response identical in shape and content to the prior networked path — result payload, UI components, error `{code, message, retryable}`, and correlation id.
- **FR-003**: System MUST preserve per-request runtime injection (the `_runtime` handle) and per-agent argument filtering, so tools that do not accept internal keyword arguments continue to run unchanged and internal arguments never leak into tools that would reject them.
- **FR-004**: System MUST continue to deliver incremental progress notifications and push-streamed partial results for in-process agents, fanned to all of the user's sockets on the chat, and MUST honor stream cancellation, with the same ordering and coalescing behavior as today.
- **FR-005**: System MUST continue to support long-running background jobs: the originating tool call returns promptly while the background poller continues, its terminal result persists to the workspace, and its concurrency slot is released on completion.
- **FR-006**: System MUST keep blocking/synchronous tool code off the orchestrator's event loop (offloaded to a worker thread) so a slow tool for one user cannot stall other users' chats or stream delivery.
- **FR-007**: System MUST preserve, for in-process agents, the per-(user, agent) concurrency cap, the per-tool wall-clock timeout, and the error-classification + retry/backoff semantics that the networked path provides.
- **FR-008**: System MUST select the in-process path only via a positive built-in-agent registry check; genuinely external A2A agents MUST continue to use their networked transport.
- **FR-009**: User-created draft agents MUST continue to run as isolated subprocesses with the existing self-test lifecycle; this feature MUST NOT change their isolation model.

#### Owner-safe marking (US2)

- **FR-010**: System MUST record an explicit owner-approved "safe" provenance marker per bundled first-party agent, persisted durably and kept distinct from the visibility (public/private) flag.
- **FR-011**: Marking (or unmarking) an agent safe MUST be restricted to an admin/owner principal and enforced server-side; an ordinary user MUST NOT be able to self-mark an agent safe.
- **FR-012**: When an agent is marked safe, the system MUST treat all of that agent's tool scopes as enabled-by-default via a system-level default consulted at the per-call permission check, so its tools are usable without each user manually enabling them — and MUST do so WITHOUT writing per-user permission rows.
- **FR-013**: The safe marker MUST NOT bypass any runtime per-call gate. A user's explicit disable of a scope or specific tool MUST always win over the safe default (explicit opt-out wins), and security-flag hard-blocks, the policy engine, taint, egress gating, PHI handling, and audit MUST all remain fully enforced for safe agents. The safe default is necessary-but-not-sufficient: it flips the permission baseline from deny to allow but never overrides an explicit user opt-out or a hard block.
- **FR-014**: A tool that the security analyzer genuinely blocks MUST remain blocked for a safe agent; clearing such a flag MUST require an explicit, separately-audited owner action and MUST NOT be implied by the safe marking.
- **FR-015**: The safe marker MUST be reset (re-approval required) whenever a previously-safe agent is revised through the agent-revision path, because a revision can reintroduce un-reviewed code.
- **FR-016**: Every safe-marking transition MUST emit an audited lifecycle event capturing the acting principal, the agent id, and the prior state.

#### Retire etf_tracker_1 (US3)

- **FR-017**: System MUST remove the `etf_tracker_1` agent entirely so it appears nowhere a user could encounter it — agent catalog, agents surface, chat tool lists, and history glyphs.
- **FR-018**: System MUST run an idempotent, guarded startup migration that purges orphaned ownership, scope, tool-override, and credential rows for the retired agent id and retires or reassigns any conversation rows that referenced it; re-running the migration MUST be a no-op.
- **FR-019**: Old chat transcripts that referenced the retired agent's tools MUST degrade gracefully with a clear retirement notice (consistent with existing retired-agent handling), not an error.
- **FR-020**: The agent-catalog consistency tests MUST be updated so the full test suite remains green after the removal.

#### On-demand skill packs (US4)

- **FR-021**: System MUST load capability/technique knowledge into the chat model's context selectively by relevance to the current request and the agents in play for the turn (progressive disclosure), instead of injecting every agent's summary on every turn.
- **FR-022**: System MUST deliver per-agent technique knowledge into the chat turn (wiring the capability that is currently produced but never invoked) so authored guidance actually reaches the model.
- **FR-023**: Authored skill packs MUST be human-authored, version-controlled, and stored where the automatic knowledge synthesizer cannot overwrite them; auto-synthesized knowledge MUST remain a separate surface.
- **FR-024**: On-demand skill loading MUST be selective and bounded so it does not increase the baseline per-turn context size for unrelated turns or degrade prompt-cache stability; if skill loading fails it MUST fall back to today's behavior without error.

#### User-typed slash commands (US5)

- **FR-025**: Users MUST be able to invoke a typed `/command` in the chat input that either expands into a normal model turn (e.g. a prefilled prompt) or triggers a defined flow.
- **FR-026**: Slash-command input and arguments MUST be treated as untrusted and routed through the same permission, audit, PHI, taint, and policy handling as any other chat input; a command MUST NOT confer any privileged bypass of tool scopes.
- **FR-027**: Available commands MUST be discoverable to the user (typeahead/help), and an unknown or malformed command MUST produce a friendly message rather than an error.
- **FR-028**: The slash-command surface MUST be delivered through the server-driven UI layer (no new client framework) and MUST adapt across device targets.

#### Cross-cutting: audit, security, migrations, dependencies, flags

- **FR-029**: In-process tool calls MUST emit the same paired start/end audit events as the networked path, attributed to the correct on-behalf-of user actor, acting principal, agent id, and conversation id, sharing one correlation id — and MUST NEVER be recorded as "legacy" or silently dropped because the call lacks a real network session.
- **FR-030**: Per-user credential confidentiality MUST be preserved: in-process agents decrypt per-user secrets inside their own boundary, and the orchestrator MUST NOT materialize plaintext per-user secrets.
- **FR-031**: Removing the network boundary MUST NOT weaken the agent authorization posture: in-process agents MUST act under the same delegated authority and attenuated scoping as today, so audit's acting-principal/scope attribution and the fail-closed trust posture remain correct.
- **FR-032**: Every tool call MUST be auditable regardless of dispatch path — the parallel-tool dispatch path MUST also emit tool audit events, closing the existing gap where parallel batches produced none.
- **FR-033**: Each new behavior MUST ship behind a feature flag. Security-relevant flags MUST fail closed; UI-convenience behavior MUST fail open to today's behavior; with a flag off, behavior MUST match the current system exactly.
- **FR-034**: All schema changes MUST ship as idempotent, guarded startup migrations with a documented rollback.
- **FR-035**: The feature MUST add zero new third-party runtime dependencies.

### Key Entities *(include if feature involves data)*

- **Built-in agent (in-process)**: a first-party agent that ships with the system and now runs as a live in-process object (its tool registry, its per-agent decryption key, its runtime/streaming emitters) addressed through a built-in registry by agent id — as opposed to an external A2A agent (networked) or a draft agent (isolated subprocess).
- **Safe marker / agent trust record**: a durable, per-agent owner-approval status (safe yes/no, approving principal, timestamp, prior state) distinct from visibility; drives a check-time system default that flips the permission baseline to allow for the agent's scopes (no per-user rows written; explicit user opt-out and hard security blocks still win); reset on revision.
- **Skill pack**: an authored, version-controlled unit of capability/technique guidance (name, target capability/agent or domain, relevance cues, body) with explicit "authored" provenance that the automatic synthesizer must not overwrite; loaded on demand by relevance.
- **Slash command**: a user-invocable command (name, kind — prompt-expansion vs defined flow, expected arguments, the scopes/gates its flow is subject to) surfaced with discovery in the chat input.
- **Tool-dispatch audit event**: the paired start/end record (actor user, acting principal, agent id, conversation id, correlation id, outcome) that must be produced for every tool call on every dispatch path.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the existing agent/tool behavior tests pass with built-in agents running in-process, with no functional difference in results, UI components, streaming, or progress versus the networked path.
- **SC-002**: With the feature enabled, no first-party agent runs as a separate process or listens on a network port; the built-in fleet is served entirely within the orchestrator.
- **SC-003**: Per-call dispatch overhead for built-in agents is reduced relative to the networked baseline (the network/WebSocket round-trip is eliminated), with no measured latency regression on any built-in tool path.
- **SC-004**: A brand-new user with no prior permission grants can use a safe built-in agent's tools with zero manual setup steps; a tool the user has explicitly disabled stays disabled, and a hard-blocked tool stays blocked.
- **SC-005**: 100% of built-in tool calls — on both the single-tool and parallel-tool paths — produce a verifiable, hash-chain-intact audit trail attributed to the acting user and the correct agent; chain verification returns no divergence.
- **SC-006**: No plaintext per-user secret is observable in the orchestrator process for in-process agents (verified by test/inspection).
- **SC-007**: `etf_tracker_1` is absent from every user-facing surface, the test suite is green, and a fresh startup leaves zero orphaned permission/credential rows for its id.
- **SC-008**: Capability/technique knowledge reaches the model only when relevant; for a request unrelated to any pack, the per-turn injected-knowledge size is unchanged from today's baseline.
- **SC-009**: A user can invoke a documented `/command` and see it execute through the normal permission and audit gates; unknown commands never produce an error.
- **SC-010**: All changes pass the project's continuous-integration gates (lint, full test suite against a real database, ≥90% changed-code coverage, image build, boot smoke including the production-posture fail-closed exit, and secret scan).

## Assumptions

- "Shipped / built-in / first-party agents" means the nine agents committed under the product's agents directory and reviewed in pull requests — not user-created drafts and not externally-hosted A2A agents.
- Genuinely external A2A agents (the external-AI-agent and connector-interop work) are out of scope for the transport change and keep their networked path unchanged.
- The admin/owner principal authorized to mark agents safe is the existing owner/admin role used elsewhere for server-side gating (e.g. the same authority that approves auto-created parser drafts and toggles agent visibility); for the bundled fleet, safe marking is applied as an owner/deploy-time action.
- Marking the bundled fleet safe enables all of each agent's tool scopes by default via a check-time system default (no per-user rows written); a user's explicit per-scope/per-tool opt-out always wins, and tools the security analyzer hard-blocks still require a separate, audited owner action.
- Authored skill packs are committed to the repository in a location separate from the gitignored, auto-synthesized knowledge directory, so a container rebuild reproduces them and the synthesizer cannot clobber them.
- The initial slash-command set is a curated, first-party set; user-defined command authoring (per-user macros) is not required for this feature and can be a later addition.
- Existing identity, audit, permission, PHI, taint, policy, egress, and credential mechanisms are reused as-is; this feature changes where built-in agent code runs and adds provenance/skills/command surfaces on top of them, rather than replacing any security control.
- Development posture remains as today (the environment flag governs dev vs fail-closed production); no production secret is baked into the image.
- Zero new third-party runtime dependencies are introduced; all work is built on the existing stack and first-party packages.
