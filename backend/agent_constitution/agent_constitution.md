# User Agent Constitution

**Version**: 0.1.0 (Draft)
**Created**: 2026-07-14
**Applies to**: every agent a user authors and runs on their own device (feature 057). Distinct from, and subordinate to, the project constitution (`.specify/memory/constitution.md`).

## Purpose

This document states the **non-negotiable contracts a user-created agent MUST satisfy** to be accepted by the platform. It is the single source the **Analyze** gate checks a drafted agent against, before any agent code is generated or allowed to go live. It also defines what the orchestrator boundary will reject at runtime, so that a well-specified agent and the untrusted-at-the-boundary enforcement describe the *same* set of allowed behaviors.

Two audiences read it: the **author** (as the rules their agent must obey, surfaced in plain language during authoring) and the **enforcement layers** (the local sandbox and the orchestrator boundary, which mechanically hold these lines regardless of what the agent does).

Every principle is stated as testable MUST/MUST NOT so the Analyze gate can pass or fail a draft deterministically and cite the offending part.

## Principles

### A. Owner-Delegated Authority Only

A user agent acts **solely as a delegate of its owning human**. It has no authority of its own.

- The agent MUST act only under the owner's delegated authority; it MUST NOT request, assume, or assert any authority the owner does not currently hold.
- The agent MUST NOT present, forge, or rely on any token, identity, actor claim, user id, or scope of its own; the acting principal is derived **only** from the orchestrator's record of the owning user.
- **Rationale**: this is what makes running user code against a shared server safe — the agent can never exceed its owner, and its owner is already bounded by their own grants.

### B. Declared Capability Surface

Everything the agent will do MUST be declared up front and reviewed in the Plan/Analyze phases.

- Every tool the agent calls, every permission scope it requires, and every category of data it reads/writes MUST be declared in the agent's spec.
- The running agent MUST NOT call a tool, use a scope, or reach data it did not declare — an undeclared reach is a boundary rejection.
- **Rationale**: the boundary can only enforce "in-bounds" against a known surface; an agent whose behavior is not declared cannot be safely admitted.

### C. Least Privilege

The declared surface MUST be the minimum the capability needs.

- The agent MUST request the narrowest scopes that satisfy its stated purpose; it MUST NOT request blanket or unused scopes "just in case."
- Analyze MUST flag any requested scope not justified by a declared capability.
- **Rationale**: minimizes blast radius even within the owner's own authority.

### D. No Cross-User Reach

A user agent touches **only its owner's** world.

- The agent MUST NOT read, reference, address, or act on data, identities, chats, or resources belonging to any user other than its owner.
- The agent MUST NOT take an identity or address a target that could resolve to another user's data.
- Any such attempt MUST be denied fail-closed at the boundary and audited.
- **Rationale**: the core multi-tenant safety guarantee (SC-003: zero cross-user accesses).

### E. Untrusted at the Boundary

The agent MUST be written assuming it is **fully untrusted** once it talks to the orchestrator.

- The agent MUST NOT rely on any client-side/local check for a security decision the boundary is responsible for; local gating protects the owner from themselves, not the platform from the agent.
- The agent MUST tolerate the boundary re-verifying and refusing any action, and MUST surface such refusals honestly rather than working around them.
- **Rationale**: the boundary layer must hold independently of the local sandbox; an agent that assumes trust it doesn't have is non-compliant.

### F. Fail-Closed and Honest

- On any error, missing authority, or ambiguous state, the agent MUST fail closed (do nothing / return an honest error), never fall back to a broader or unverified behavior.
- The agent MUST NOT hide capabilities, take undeclared side effects, or silently degrade; its observable behavior MUST match its declared behavior.
- **Rationale**: consistency with the platform's fail-closed production posture and honesty guarantees.

### G. Bounded Resource Use

- The agent MUST operate within declared and platform-imposed bounds on request rate, concurrency, runtime, and payload size.
- A runaway or flooding agent MUST be bound so it degrades only its own owner's experience (SC-008).
- **Rationale**: one user's agent can never become a denial-of-service against others.

### H. Registration & Identity Integrity

- The agent MUST register through the platform's standard agent-registration path with a valid, owner-scoped identity and the required registration credential.
- The agent's identity MUST NOT collide with a built-in/public agent, another user's agent, or a reserved identity in any way that could misroute a request.
- **Rationale**: routing integrity and non-impersonation.

### I. No Secret or Internal Exfiltration

- The agent MUST NOT read, transmit, or persist the owner's credentials/secrets, platform internals, other agents' tokens, or orchestrator-internal material beyond what it is explicitly and minimally granted for its stated purpose.
- Any per-user secret the platform provides MUST be used only in-boundary for its intended tool and never re-transmitted.
- **Rationale**: prevents credential/secret laundering through user-authored code.

### J. Declared, Gated External Egress

- Any network egress MUST be declared and MUST go through the platform's egress-gated path; the agent MUST NOT make undisclosed outbound calls.
- **Rationale**: no covert data exfiltration channels; egress is observable and policy-controlled.

### K. Privacy by Construction

- A user agent is private to its owner and MUST have no capability, field, or flag that shares, publishes, or transfers it to another user or to the fleet.
- The only path to a fleet-wide agent is an out-of-product, manually-approved repository contribution.
- **Rationale**: "your agent is your agent"; sharing is a deliberate human act outside the product.

### L. Constitution-Version Binding

- Every user agent MUST record the version of this constitution it was validated against.
- A change to this constitution MUST require affected agents to re-validate (re-run Clarify/Analyze) before they are trusted again; a revision resets an agent's accepted state.
- **Rationale**: the accepted set of behaviors never drifts silently from the current rules.

## Analyze Gate Checklist

The Analyze phase mechanically evaluates a drafted agent against every principle. A draft PASSES only if all checks pass; each failure is reported in plain language tied to the offending part of the spec.

- [ ] **A** — No self-authority: the spec requests no token/identity/scope of the agent's own; all authority is owner-delegated.
- [ ] **B** — Every tool/scope/data-category the agent uses is declared; nothing is used that isn't declared.
- [ ] **C** — Every requested scope is justified by a declared capability; no blanket/unused scopes.
- [ ] **D** — No capability references, addresses, or could resolve to another user's data or identity.
- [ ] **E** — No security decision depends on a client-side/local check; the agent tolerates boundary refusal.
- [ ] **F** — Error/edge behavior is fail-closed and honest; observable behavior matches declared behavior.
- [ ] **G** — Resource use is bounded/declared; no unbounded loops or floods.
- [ ] **H** — Registration identity is valid, owner-scoped, and non-colliding; registration credential present.
- [ ] **I** — No reading/transmitting of secrets or platform internals beyond the minimal declared grant.
- [ ] **J** — All external egress is declared and routed through the gated path; no undisclosed calls.
- [ ] **K** — No sharing/publish/transfer surface exists in the spec.
- [ ] **L** — The agent records this constitution's version and re-validates on a version change.

## Governance

- This constitution is versioned (semver). MAJOR = a change that can retroactively fail existing agents; MINOR = an additive rule; PATCH = clarification.
- Its authoritative home and how it is delivered to the runtime Analyze gate are decided in the feature plan (`plan.md`); a copy MUST be readable by the boundary/authoring layer at runtime.
- Amendments follow the project constitution's governance and MUST keep the Analyze Gate Checklist in exact correspondence with the Principles.
