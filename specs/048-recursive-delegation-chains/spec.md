# Feature Specification: Recursive, Provenance-Bearing Delegation Chains Over Persistent Transport

**Feature Branch**: `048-recursive-delegation-chains`
**Created**: 2026-07-02
**Status**: Draft
**Input**: User description: "Draft the recursive-delegation extension to `delegation.py` behind a flag (Direction A), with the enforcement property tests first." (Item 4 of [THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md) §8; Direction A of §3 — the thesis's defensible core.)

## Overview

Today `delegation.py` performs a single-hop RFC 8693 token exchange: the orchestrator exchanges a user token for one scoped, DPoP-bound delegation token naming one agent as actor (`act.sub = agent:<id>`). The thesis's primary contribution requires **recursive delegation chains** — when an agent fans out to a sub-agent (035 C-N8) or an auto-created agent is promoted (027/035), the downstream principal must receive a **further-attenuated** token whose authority is provably narrower than its parent's, whose `act` claim chain records the full path back to the human principal, and whose every hop is linked into the tamper-evident hash-chained audit as a **provenance-bearing completion record**. Bound to Astral's persistent WebSocket transport with per-hop, mid-session re-derivation, this is the differentiator no competing protocol (AIP/IBCT, `draft-niyikiza`, WIMSE) owns as a deployed, evaluated system.

This feature extends `delegation.py` (and the dispatch path that consumes it) to mint and verify nested delegation tokens behind a feature flag (`FF_RECURSIVE_DELEGATION`, default **off** — fail-closed), enforcing four invariants — **monotonic scope attenuation**, **no privilege escalation**, **actor-claim-chain completeness**, and **depth-bounding**. Per the instruction and Constitution (test-first), the **enforcement property tests are written first and must fail before implementation**. No new third-party runtime dependency (Constitution V): chained tokens are expressed with the JWT/HMAC/EC primitives and `cryptography` already used by `delegation.py` and `offline_grant.py`.

## Clarifications

### Session 2026-07-02 (resolved by informed default — confirm or override during `/speckit-clarify`)

- Q: Nested-`act` JWT, or adopt a Biscuit/Datalog-style chained token like AIP's IBCT? → A: **Nested RFC 8693 `act` claims** in the existing JWT/DPoP construction — stays within current dependencies (Constitution V) and keeps the contribution a *transport-and-deployment* story, not a competing token format. The AIP differential (spec 046) explicitly informs this choice; the design notes why nested-`act` over a persistent transport is the intended differentiator rather than re-implementing Datalog policy. Revisit only if 046 shows nested-`act` cannot express a required attenuation.
- Q: What does "attenuation" constrain? → A: The child's scope set MUST be a **subset** of the parent's (scope-level claims and `tool:<name>` claims), the child's expiry MUST NOT exceed the parent's, and the child MUST NOT gain any capability (scope, tool, audience, or security-flag relaxation) absent from the parent. Equal-or-narrower only; never wider.
- Q: Depth bound? → A: A configurable maximum chain depth (default small, e.g. 3) enforced at mint time; exceeding it fails closed (no token issued, audited). The bound is recorded in each token so verifiers reject over-depth chains they receive.
- Q: Real Keycloak vs mock for chained exchange? → A: Mirror the current split. Mock mode mints nested tokens locally (dev/test, where the property tests run). Keycloak mode performs a chained exchange where supported; where the realm cannot express a downstream narrowing, the orchestrator enforces the attenuation invariant itself at dispatch and records the effective (enforced) scope — never widening beyond what Keycloak issued. The [keycloak_agent_delegation_setup.md](../../docs/keycloak_agent_delegation_setup.md) posture is extended, not replaced.
- Q: What binds a hop into provenance? → A: Each minted hop emits a delegation-chain record (parent token id/thumbprint, child actor, resulting scope, depth, timestamp) appended to the existing hash-chained audit, so the authority path and the action outcome are both tamper-evident and reconstructable end-to-end to the human principal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enforcement property tests, written first and failing (Priority: P1)

Before any minting code, Sam writes executable property tests that encode the four enforcement invariants against the intended API, and confirms they **fail** (red) — establishing the specification-as-tests that the implementation must satisfy.

**Why this priority**: The instruction is explicit ("enforcement property tests first"), and these tests *are* the formal contribution — they are what a security committee (Calvert/Fei) will scrutinize. Written first, they prevent an implementation that merely appears to attenuate.

**Independent Test**: Run the new property-test module before implementation; every enforcement property is present and fails (or errors on the not-yet-built API), demonstrating the tests genuinely exercise unimplemented behavior rather than vacuously passing.

**Acceptance Scenarios**:

1. **Given** the property-test module, **When** executed pre-implementation, **Then** tests for monotonic attenuation, no-escalation, actor-chain completeness, and depth-bounding are all present and failing/erroring.
2. **Given** the attenuation property, **When** expressed, **Then** it asserts that for any parent→child mint, `child.scopes ⊆ parent.scopes` and `child.exp ≤ parent.exp`, tested over generated scope sets (property-based, not a single example).
3. **Given** the no-escalation property, **When** expressed, **Then** it asserts no child can obtain a scope, tool, audience, or relaxed security flag absent from its parent, including via malformed or hostile mint requests.
4. **Given** the actor-chain-completeness property, **When** expressed, **Then** it asserts every token in a chain carries the full nested `act` path terminating at the human `sub`, with no missing or forged link.
5. **Given** the depth-bound property, **When** expressed, **Then** it asserts mint refuses beyond max depth and verify rejects received over-depth chains.

---

### User Story 2 - Mint further-attenuated child delegation tokens behind a flag (Priority: P1)

With the flag on, when an agent holding a delegation token needs a sub-agent to act, the orchestrator mints a child token whose scopes are the requested subset (never a superset) of the parent's, whose `act` claim nests the parent's actor chain, whose expiry does not exceed the parent's, and whose depth is one greater — DPoP-bound as today.

**Why this priority**: This is the core mechanism of Direction A; the sub-agent fan-out and auto-created-agent promotion paths both depend on it.

**Independent Test**: With `FF_RECURSIVE_DELEGATION=on` in mock mode, request a child token from a parent with a known scope set; confirm the child's scopes are the intersection of requested-and-parent, its `act` nests the parent chain to the human sub, its exp ≤ parent exp, its depth = parent depth + 1, and it is DPoP-bound.

**Acceptance Scenarios**:

1. **Given** a parent delegation token and a child scope request that is a subset, **When** a child is minted, **Then** the child carries exactly the requested subset and the nested `act` chain, DPoP-bound.
2. **Given** a child scope request that exceeds the parent (a superset or a new tool), **When** mint is attempted, **Then** it is refused (or silently narrowed to the intersection, per a stated policy) and the attempt is audited — never widened.
3. **Given** the flag **off**, **When** any recursive mint is attempted, **Then** the system falls back to current single-hop behavior and no chained token is issued (fail-closed default).
4. **Given** a parent near expiry, **When** a child is minted, **Then** the child's expiry is capped at the parent's.

---

### User Story 3 - Enforce the chain at dispatch over the persistent transport (Priority: P1)

When a sub-agent presents a chained token to invoke a tool over the live WebSocket session, the orchestrator verifies the whole chain — attenuation at every hop, depth bound, actor-chain integrity, DPoP possession — before the tool runs, and refuses out-of-chain or escalated requests. This is the transport-binding differentiator: per-tool-call authority re-derivation on a long-lived socket tied to the ReAct turn.

**Why this priority**: Minting narrow tokens is meaningless without enforcement at use; the enforcement point over the persistent transport *is* the novel systems claim.

**Independent Test**: Over a simulated persistent session, present a valid chained token and a tampered/escalated one; confirm the valid one's in-scope tool executes and the escalated/over-depth/broken-chain one is refused and audited, without tearing down the socket.

**Acceptance Scenarios**:

1. **Given** a valid chained token, **When** a sub-agent invokes an in-scope tool, **Then** dispatch verifies the chain and permits execution, recording the delegation depth on the audit event.
2. **Given** a token whose requested tool is outside its (attenuated) scope, **When** invoked, **Then** dispatch refuses and audits a scope violation attributing the acting sub-agent and the human principal.
3. **Given** a tampered `act` chain or an over-depth token, **When** presented, **Then** verification fails closed and the socket/session continues (denial is per-call, not a connection kill).
4. **Given** mid-session re-derivation, **When** the same sub-agent needs a different tool later in the turn, **Then** a fresh per-call attenuation is derived and checked without a new user-token round trip.

---

### User Story 4 - Provenance records link every hop to the human principal (Priority: P2)

Each mint and each enforced use appends a delegation-chain record to the hash-chained audit, so the complete authority path — human → agent → sub-agent → tool effect — is reconstructable and tamper-evident, satisfying the "provenance-aware completion records" gap the field names as open.

**Why this priority**: Provenance is one of the four surviving novelty axes and the clinical/HIPAA conformance bar (§2.5). P2 because it rides on Stories 2–3 but is essential to the thesis claim.

**Independent Test**: Run a two-hop delegation to a tool effect; from the audit chain alone, reconstruct the full principal path and verify the chain's integrity (tamper a record; verification fails).

**Acceptance Scenarios**:

1. **Given** a completed chained delegation, **When** the audit chain is read, **Then** the full path (human sub → each actor → tool + outcome) is reconstructable with parent token linkage at each hop.
2. **Given** the hash chain, **When** any delegation-chain record is altered, **Then** chain verification detects it (tamper-evidence preserved).
3. **Given** a delegation record, **When** mapped to the HIPAA audit-field checklist (§2.5), **Then** it emits the required fields: acting agent identity, the human authorizer, the operation, the scope/policy context, and a tamper-evident timestamp.

---

### User Story 5 - Bind chains to fan-out and to auto-created agents (Priority: P3)

The recursive mint is wired into the two places the thesis needs it: sub-agent fan-out (035) obtains child tokens for spawned workers, and an agent auto-created/promoted by the 027/035 rail is born under an attenuated DAF delegation rather than an ambient grant.

**Why this priority**: This is what makes Directions D (safe self-extension) provable — "delegation for dynamically created principals" is named white space. P3 because it integrates Stories 2–4 into product paths and can follow the core mechanism.

**Independent Test**: Trigger a fan-out and, separately, an auto-created-agent promotion with the flag on; confirm each downstream principal receives an attenuated child token and cannot exceed its delegated scope (ties to spec 047's scope-escalation cases).

**Acceptance Scenarios**:

1. **Given** a fan-out to N workers, **When** the flag is on, **Then** each worker acts under a child token attenuated from the coordinator's, and no worker exceeds the coordinator's scope.
2. **Given** an agent promoted by the creation rail, **When** it goes live, **Then** its delegation is an attenuated child bound to the promoting authority, audited at birth.
3. **Given** the flag off, **When** either path runs, **Then** behavior is exactly today's (no regression).

### Edge Cases

- Requested child scope disjoint from parent (no overlap) → mint yields an empty-scope token or refuses per stated policy; the child can do nothing, never more than the parent.
- Parent token revoked/expired mid-turn while a child is active → the child is invalidated (chain-of-custody: a child cannot outlive its parent); enforced at verify.
- A hop wants to *re-broaden* within the human's original grant (narrowed at hop 1, wants more at hop 2) → refused; attenuation is monotonic down the chain, not re-widenable, even within the root authority.
- DPoP thumbprint mismatch on a presented chained token → fail closed (possession not proven), audited.
- Keycloak can't express the downstream narrowing → orchestrator enforces the invariant itself and records the effective enforced scope; it never trusts a Keycloak-issued token that is *wider* than the invariant permits.
- Clock skew near expiry across hops → expiry comparison uses a stated skew tolerance consistent with existing token handling; child exp never exceeds parent exp beyond that tolerance.
- Flag on but a legacy single-hop consumer presents an old token → still honored as depth-0; the extension is additive and backward-compatible.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Enforcement property tests for all four invariants (monotonic attenuation, no-escalation, actor-chain completeness, depth-bounding) MUST be authored **before** implementation and MUST fail against the unbuilt API; they MUST be property-based (generated inputs), not single-example.
- **FR-002**: The system MUST mint a child delegation token whose scope set is a subset of the parent's (scope-level and `tool:<name>` claims) and whose expiry does not exceed the parent's.
- **FR-003**: The child token MUST carry a nested `act` claim chain recording every actor from the immediate delegate up to and terminating at the human principal (`sub`), with no missing link.
- **FR-004**: The system MUST refuse (or narrow to the intersection, per a single stated policy) any child request that would widen scope, add a tool/audience, relax a security flag, or extend expiry beyond the parent; every refusal/narrowing MUST be audited.
- **FR-005**: The system MUST enforce a configurable maximum chain depth at mint and reject received over-depth chains at verify; the depth MUST be recorded in the token and on the audit event.
- **FR-006**: Dispatch over the persistent WebSocket transport MUST verify the full chain (attenuation, depth, actor-chain integrity, DPoP possession) before executing a tool, per tool call, without requiring a new user-token round trip for mid-session re-derivation.
- **FR-007**: A denied chained request MUST fail closed per call and MUST NOT tear down the session/socket.
- **FR-008**: Each mint and each enforced use MUST append a delegation-chain record to the existing hash-chained audit, linking parent→child and preserving tamper-evidence; the record MUST carry the HIPAA-conformance fields (§2.5): acting agent identity, human authorizer, operation, scope/policy context, tamper-evident timestamp.
- **FR-009**: The entire capability MUST sit behind `FF_RECURSIVE_DELEGATION`, default **off**; with the flag off, behavior MUST be byte-for-byte today's single-hop path (no regression).
- **FR-010**: A child token MUST NOT outlive, exceed, or survive revocation/expiry of its parent (chain-of-custody at verify).
- **FR-011**: The feature MUST add **no new third-party runtime dependency**; chained tokens use the JWT/DPoP/`cryptography` primitives already present (Constitution V).
- **FR-012**: The recursive mint MUST be invocable from the sub-agent fan-out path and the auto-created-agent promotion path such that each downstream principal acts only under an attenuated child token.
- **FR-013**: In Keycloak mode, where the realm cannot express a required downstream narrowing, the orchestrator MUST enforce the attenuation invariant itself and record the effective enforced scope, never honoring a token wider than the invariant allows.
- **FR-014**: All existing delegation tests and security-gate wiring tests MUST remain green; the extension is additive.

### Key Entities

- **Delegation chain**: ordered set of hops from the human principal through each agent/sub-agent, each a further-attenuated token; the unit the invariants constrain.
- **Child (nested) delegation token**: a delegation token with a nested `act` chain, a depth counter, a scope ⊆ parent, exp ≤ parent, DPoP-bound.
- **Attenuation invariant**: the equal-or-narrower rule over scopes, tools, audience, security flags, and expiry, applied at every hop.
- **Delegation-chain audit record**: the provenance/completion record linking a hop into the hash-chained audit with the HIPAA-conformance fields.
- **Depth bound**: configurable maximum chain length, enforced at mint and verify.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The four enforcement property tests exist, are property-based, failed before implementation, and pass after — demonstrable from version history.
- **SC-002**: For randomized parent/child scope sets, no minted child ever holds a scope, tool, audience, relaxed flag, or later expiry absent from its parent (property tests green over the generated space).
- **SC-003**: A two-hop delegation to a tool effect is fully reconstructable from the audit chain to the human principal, and tampering any record is detected.
- **SC-004**: With the flag off, the full existing delegation + security-gate test suites pass unchanged (zero regression); with it on, they still pass plus the new suites.
- **SC-005**: Over the persistent transport, an in-scope chained call executes and an escalated/over-depth/tampered call is refused per-call without dropping the session.
- **SC-006**: Product runtime dependency set is unchanged (Constitution V check green).
- **SC-007**: A delegation-chain record maps field-by-field onto the §2.5 HIPAA audit-trail checklist (feeds the conformance case study).

## Assumptions

- The current DPoP/JWT construction in `delegation.py` and the hash-chained audit are the substrate to extend; no replacement token format is introduced (informed by spec 046).
- `FF_RECURSIVE_DELEGATION` follows the repo's existing feature-flag pattern (`shared/feature_flags.py`), default off, production fail-closed.
- Sub-agent fan-out (035) and the auto-created-agent promotion rail (027/035) expose an injection point where a child mint can be inserted; if not, adding that seam is in scope for Story 5.
- Property-based testing uses the existing test toolchain; if a generator library is needed it is **test-only** and does not enter the product runtime (Constitution V), consistent with spec 047's isolation rule.
- Deployment-log evaluation of real delegation depths (Direction A's deployment eval) is reported in the evaluation chapter and is out of scope for this build beyond emitting the depth on audit events.

## Dependencies & Sequencing

- **Fed by**: 045 (framing: this is the defensible core), 046 (AIP differential justifies nested-`act`-over-transport vs. re-implementing IBCT).
- **Feeds**: 047 (its escalation/confused-deputy cases exercise this enforcement at the system level), 049 (the I-D would specify exactly this mechanism), Direction D (auto-created agents born under attenuated delegation), and the HIPAA conformance case study.
- **Constitution**: IX (idempotent migration if any audit-schema delta is needed), V (no new runtime deps), test-first ordering (FR-001).
