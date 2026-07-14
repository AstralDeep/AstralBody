# Feature Specification: BYO Client-Side Agents — Runtime, Hosting & Authoring UX

**Feature Branch**: `058-byo-agents-runtime`

**Created**: 2026-07-14

**Status**: Draft

**Input**: Continuation of feature 057 (`specs/057-byo-client-agents/`). Feature 057 delivered the **foundation + security core** (registry schema, agent constitution + loader, the deterministic Analyze gate, and the owner-isolation security fixes). This feature delivers the parts 057 deliberately deferred because they require a **live desktop client** to build and verify: the client-side **transport**, desktop **hosting**, the guided **authoring UX**, cross-client **parity**, agent **lifecycle**, and the remaining **boundary hardening**.

## Overview

Feature 057 built everything that could be verified server-side: the `user_agent` registry, `FF_BYO_AGENTS` (default off), the baked agent constitution + loader, the A–L Analyze gate, and the owner-isolation enforcement (including a fix to a pre-existing private-agent grant hole). What it did **not** build is the machinery that makes a user's agent actually **run on their own device and reach the orchestrator**: the persistent tunnel, owner-bound registration, code delivery to the host, the desktop child-process runner, honest-offline, and the guided authoring surface that produces the agent in the first place.

This feature completes the loop end-to-end so a user can, from a supported client, author an agent through the guided flow, have it delivered to and run on their **desktop host as an isolated child process**, connect inward over the **v1 direct tunnel**, use it in chat, manage its lifecycle, and have it go offline when the client closes — with the untrusted-at-the-boundary security model (already built in 057) enforced on every action. It reuses 057's design verbatim: [agent-constitution.md](../057-byo-client-agents/agent-constitution.md), the four [contracts/](../057-byo-client-agents/contracts/) (agent-tunnel, analyze-gate, authoring-surface, user-agent-registry), [data-model.md](../057-byo-client-agents/data-model.md), and [research.md](../057-byo-client-agents/research.md).

**Transport**: the v1 default is the **direct tunnel** over the client's existing authenticated connection (Mode 1). The **Cresco edge-mesh** transport (Mode 2, feature 050 external-infrastructure posture) remains the sanctioned but **deferred** path for the broader cross-device/edge-compute scenario.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an agent and run it on my own device (Priority: P1) 🎯 MVP

The 057 registry/Analyze/isolation core is in place; this story wires the **runtime** so it actually works: author (minimally) → generate → deliver to the desktop host → the host runs it as an isolated child process → it registers inward over the tunnel → usable in chat → offline on client close. No user-agent process ever runs on the orchestrator.

**Independent Test**: create a trivial agent on Windows; invoke it (correct result, user-attributed audit row); confirm no agent process on the orchestrator host; close the client → offline within seconds → invoking it returns an honest offline message; another user cannot see or invoke it.

**Acceptance Scenarios**:

1. **Given** a signed-in user on the Windows client with `FF_BYO_AGENTS` on, **When** they finish creation, **Then** the generated bundle is delivered to their host, run as a supervised child process, and registered inward so it is usable in their chats.
2. **Given** a running user agent, **When** the user invokes it, **Then** the orchestrator routes to the host over the tunnel and the action is attributed to the owning human in the audit trail (FR-012).
3. **Given** a running user agent, **When** the client closes/disconnects, **Then** the agent is offline within seconds and a subsequent invocation returns a prompt honest-offline response, never a hang.
4. **Given** no orchestrator-hosted agent process exists for it, **When** verified, **Then** SC-002 holds (zero user-agent processes on the central server).

---

### User Story 2 - Guided spec-driven authoring against the agent constitution (Priority: P2)

The full hybrid **Specify → Clarify → Plan → Tasks → Analyze** journey as a server-driven chrome surface, replacing US1's minimal one-shot path. Clarify and Analyze (057's gate) are mandatory; an Analyze failure structurally cannot reach code-gen.

**Independent Test**: author an agent that violates a constitution rule → Clarify surfaces the ambiguity, the 057 Analyze gate blocks progression with a plain-language cited reason and generates no code; fixing it proceeds and the live agent's declared tools/scopes match the plan.

**Acceptance Scenarios**:

1. **Given** the authoring surface, **When** the user advances each phase, **Then** the assistant drafts an editable artifact per phase and the state persists on the draft row.
2. **Given** unresolved Clarify or an Analyze violation, **When** the user tries to proceed, **Then** the handler declines to advance with a plain-language notice and does not generate code.
3. **Given** a passing Analyze, **When** the user generates, **Then** the agent's declared surface exactly matches the approved plan.

---

### User Story 3 - Complete the untrusted-at-the-boundary hardening (Priority: P2, co-critical)

057 delivered owner isolation at the permission layer; this story adds the remaining boundary hardening that requires the tunnel to exist: per-owner ingress bounds, no-secrets-to-untrusted-agents, owner-namespaced identity + collision refusal, and the transport-level adversarial suite (forged identity, flood, offline).

**Independent Test**: drive a tampered host over the tunnel (forged identity/token, undeclared tool, flood) → each denied fail-closed and audited; a flooding agent degrades only its owner; no secrets are shipped to the untrusted agent.

**Acceptance Scenarios**:

1. **Given** a user agent over the tunnel, **When** it presents a fabricated token/identity, **Then** the orchestrator derives the principal only from its own record and ignores the forgery (FR-015).
2. **Given** a flooding agent, **When** it issues runaway requests, **Then** a per-owner ingress bound limits it so other users are unaffected (SC-008).
3. **Given** dispatch to a user agent, **When** args are prepared, **Then** the untrusted agent is not handed delegation-token bytes or per-user secrets on the direct path.

---

### User Story 4 - Author from any client except the watch (Priority: P2)

The `agent_authoring` surface renders with parity across web, Windows, Android, Apple (iOS/macOS); the watch is excluded; non-host clients clearly show that the agent runs on the user's desktop host and its online state.

**Independent Test**: complete the journey on each supported client; the watch shows no create affordance; a non-host client shows the "runs on your desktop host / offline when none online" state.

**Acceptance Scenarios**:

1. **Given** any supported non-watch client, **When** the user opens agent creation, **Then** equivalent capability is available (one server-driven surface, dual web+native rendering).
2. **Given** the watch, **When** the user looks for creation, **Then** none is present.
3. **Given** a non-host client, **When** the user authors, **Then** it is explicit that execution binds to the user's desktop host.

---

### User Story 5 - Manage my agents; my agent stays mine (Priority: P3)

List (owner-only, with running/offline status), revise (re-Analyze + rollback; prior version keeps running until the revision validates), delete (soft-delete: stop the host agent, remove routing, retain the row + audit), and constitution-version re-validation. Private by construction; no share/publish surface.

**Independent Test**: list (owner-only); revise (must re-pass Analyze; prior keeps running); delete (host agent stops, disappears from list); confirm no share control and cross-user invisibility.

**Acceptance Scenarios**:

1. **Given** the user's agents, **When** listed, **Then** only their own appear with derived running/offline status.
2. **Given** a revision, **When** it has not passed Analyze, **Then** the prior version keeps running and the revision is not usable.
3. **Given** a delete, **When** it completes, **Then** the host agent stops, routing is removed, and the row + audit are retained (soft delete).
4. **Given** a constitution MAJOR bump, **When** boot runs, **Then** affected agents require re-validation before routing resumes (FR-028).

### Edge Cases

- Client closes mid-task → honest "went offline" outcome; no partial result attributed to a later turn.
- Reconnect / duplicate host instances → authoritative single-instance resolution keyed to owner.
- Author-on-mobile → runs on the user's desktop host; explicit when no host is online.
- Codegen bundle vs desktop-host vendored packages → the bundle targets the host runtime shape or the host ships a shim.
- Self-test must not become a persistent orchestrator process (ephemeral or host-side).
- macOS hosting requires the non-sandboxed direct-download build; the MAS build is author-only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A user agent MUST connect inward over the v1 direct tunnel (frames on the client's authenticated connection) and be routable like any other registered agent; the transport MUST be a seam so Mode 2 (Cresco) can be added without touching owner-binding/dispatch.
- **FR-002**: Registration MUST bind the agent to the owner derived from the authenticated connection (never a card field), refusing unless the `user_agent` row's `owner_user_id` matches and `status ∈ {validated, live}` and `revalidation_required` is false; owner-namespaced ids with collision refusal (built-in/public/reserved/other-user).
- **FR-003**: The generated agent MUST run on the desktop host as an **isolated child process** the client supervises (not in-process), and MUST go offline when the client closes; invoking an offline agent MUST return a prompt honest-offline response.
- **FR-004**: Generated code MUST be delivered to the host and run there — never as an orchestrator subprocess (SC-002); any pre-delivery self-test MUST be ephemeral/host-side.
- **FR-005**: The guided Specify→Clarify→Plan→Tasks→Analyze authoring flow MUST be a server-driven chrome surface with both web and native rendering; Clarify + the 057 Analyze gate are mandatory pre-generation gates.
- **FR-006**: The remaining boundary hardening MUST be enforced: per-owner ingress/rate bounds, no delegation-token bytes/per-user secrets to untrusted agents, and the transport-level adversarial guarantees.
- **FR-007**: The authoring/management experience MUST have cross-client parity (web, Windows, Android, Apple) with the watch excluded; non-host clients MUST make the desktop-host execution explicit.
- **FR-008**: Users MUST be able to list (owner-only, with status), revise (re-Analyze + rollback, prior keeps running), and delete (soft) their agents; a constitution version change MUST force re-validation.
- **FR-009**: The feature MUST remain fail-closed behind `FF_BYO_AGENTS` (default off) and add zero new orchestrator/product-image runtime dependencies.
- **FR-010**: The Cresco Mode-2 transport MUST remain deferred and, if later adopted, land under the feature-050 external-infrastructure posture (no JVM/broker in the product image).

### Key Entities

Reuses 057's entities (`user_agent`, Agent Constitution, Authoring Session, Boundary Verification Record, Owning User) unchanged — see [057 data-model.md](../057-byo-client-agents/data-model.md). No new tables anticipated; any additive column follows the idempotent `_init_db` convention.

## Success Criteria *(mandatory)*

- **SC-001**: A non-expert reaches a working, device-hosted, usable agent for a simple capability in under 10 minutes, first attempt, no hand-editing.
- **SC-002**: Zero user-agent processes on the orchestrator host.
- **SC-003**: Zero successful cross-user accesses in adversarial testing (transport-level), building on 057's isolation.
- **SC-004**: 100% of live agents passed Clarify + Analyze; failures never go live.
- **SC-005**: Offline reported within a few seconds of client close; offline invocation is honest, not a hang.
- **SC-006**: Equivalent authoring on every non-watch client; absent on the watch.
- **SC-007**: No in-product path makes one user's agent visible/usable to another.
- **SC-008**: A flooding agent degrades only its owner.

## Assumptions & Dependencies

- **Builds on feature 057** (must be merged first): registry schema, `FF_BYO_AGENTS`, agent constitution + loader, Analyze gate, `can_user_use_agent` isolation, and the grant-hole fix are all provided by 057 and reused unchanged.
- Design artifacts (agent-constitution, contracts, data-model, research) live in `specs/057-byo-client-agents/` and are the source of truth; this feature implements against them.
- Windows is the v1 host (in-process-free child process, zero new deps); macOS hosting is gated to the non-sandboxed direct-download build; mobile/web author-only and bind to a desktop host.
- The tunnel + desktop-host runtime require live-client integration testing (a running Windows client), which is why 057 deferred them here.
