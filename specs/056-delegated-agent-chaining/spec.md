# Feature Specification: Delegated Agent Chaining

**Feature Branch**: `056-delegated-agent-chaining`

**Created**: 2026-07-13

**Status**: Draft

**Input**: User description: "Wire the recursive delegation chains (feature 048's tested-but-unwired mechanism layer) into the product so agents can initiate sub-requests to other agents and the orchestrator stops being the sole planner — while preserving the DAF (Delegated Authority Framework) and RFC 8693 guarantees end-to-end. Orchestrator-mediated chaining via both seams (agent-runtime callback + nested scoped sub-turns), plus machine-turn authority (offline-grant → token-exchange wiring). Retire the unattenuated P2P path. Thesis Direction A."

## Why now (verified problem statement)

A multi-agent code audit (2026-07-13) confirmed the owner's observation and mapped its causes:

1. **The orchestrator does all the planning.** Every chat turn is one orchestrator-side reasoning loop (bounded at 10 rounds) that selects and fans out tool calls in parallel; agents are pure tool servers. No live path lets an agent invoke another agent — the one built path (`call_peer_tool`) is dead code that would forward the caller's delegation token **unattenuated** (a confused-deputy seam), and the runtime injected into agents exposes only long-running-job registration.
2. **The authority mechanism for chaining already exists and is idle.** Feature 048 merged and property-tested the full recursive-delegation layer — child-token minting with monotonic scope attenuation, nested actor chains terminating at the human, depth bound 3, per-call chain verification, HIPAA-mapped hop audit records — behind a default-off flag with **zero production call sites**. Its own tasks defer the wiring (T014) and the two-hop audit-reconstruction evidence (T018) to "flag-on integration". This spec is that integration.
3. **Machine-initiated work cannot act in production at all.** Scheduled jobs, attachment-parser replay-after-approval, and draft self-tests all run turns through a virtual connection that has no session token, so production posture refuses every real-agent dispatch fail-closed — features 027/031's flagship behaviors are effectively development-mode-only. The sanctioned consent primitive (offline grants: encrypted refresh tokens, 365-day cap, logout revocation, per-run fresh tokens) mints exactly the subject-token shape the token exchange needs, and the scheduler already computes the consented-scope intersection — but no consent-capture flow exists, and the minted token is dropped instead of threaded into the turn.
4. **The weakest dispatch path bounds the whole chain.** The parallel dispatch path skips policy, taint, supervisor/HITL, delegation-token, and concurrency-cap gates that the single path applies. Chaining amplifies whatever the weakest path allows, so parity is a prerequisite.
5. **Attribution gaps**: machine turns are audited as "legacy"/"unknown" instead of a defined machine principal, and there is no global depth/budget bound across nested turns.

This feature is the thesis's primary contribution made real (Direction A): *"the first implemented, deployed, evaluated system that binds attenuated, provenance-bearing agent delegation to a persistent transport and to a self-extension loop, and measures its enforcement."* The 047 benchmark harness measures it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agents chain on my behalf, safely (Priority: P1)

A user asks for something that spans agent specialties ("research the top 3 NSF programs for my lab and summarize each as a comparison table"). Instead of the orchestrator micro-planning every step, the research agent itself requests the summarizer's help mid-task. Each such hop acts under a strictly narrower authority than its parent — scoped to the user's grants, expiring no later, at most three hops deep, always traceable back to the user — and every hop passes the same permission, security, and audit gates as if the user had invoked that tool directly. The user sees attributed progress ("web_research → summarizer") and can trust that an agent can never do more via a chain than it could directly.

**Why this priority**: This is the core capability gap (agents don't talk to agents) and the thesis core; the authority mechanism is already built and tested, making this the highest-leverage slice. Independently shippable behind its flag.

**Independent Test**: With the chaining flag on, drive a turn whose primary agent requests a peer tool. Verify: the hop carries a child authority strictly narrower than the parent (scopes ∩, expiry ≤, depth+1), the full gate stack ran for the hop, paired audit records exist with a shared correlation thread, and a complete two-hop chain can be reconstructed from the audit log alone. With the flag off, behavior is byte-identical to today.

**Acceptance Scenarios**:

1. **Given** a user whose grants allow both agents, **When** agent A requests a tool of agent B mid-task, **Then** the hop executes under a child authority whose scopes are the intersection of the parent's and the request's, whose expiry does not exceed the parent's, and whose actor chain names A and terminates at the user.
2. **Given** a user who explicitly disabled agent B, **When** any chain attempts a hop to B, **Then** the hop is refused (explicit opt-out always wins), the refusal is audited, and the parent task receives an honest error it can work around — the session is never torn down.
3. **Given** a chain already at maximum depth, **When** a further hop is requested, **Then** it is refused fail-closed with a depth-bound denial that is audited and reported honestly in the turn.
4. **Given** any hop, **When** it dispatches, **Then** security-flag blocks, per-user tool permissions, policy, taint, supervisor/HITL, and PHI gates all apply exactly as on a direct call — and one agent's stored credentials are never forwarded to another.
5. **Given** a completed chained turn, **When** an auditor inspects the audit chain, **Then** every hop appears as paired start/end records with correlation linkage, the acting agent and human authorizer are identifiable per hop, and the full chain reconstructs from records alone (048's deferred evidence, now proven).
6. **Given** the chaining flag is off, **Then** the wire behavior, test suites, and token contents are byte-for-byte today's single-hop behavior.

---

### User Story 2 - Background work acts with my real, revocable consent (Priority: P1)

A user schedules recurring work ("check arXiv for new SDUI papers every morning") or approves a parser that should re-read their file. At scheduling/approval time they grant explicit, scoped, durable consent. Thereafter, each background run acts under fresh, narrowed authority derived from that consent — in production, not just dev mode. If the user logs out, revokes consent, or their grants shrink, background work stops with an honest notification, never a silent failure or a silent over-reach.

**Why this priority**: Without it, every machine-initiated behavior the product already shipped (scheduled jobs, parser replay, self-tests) is inert in production. It also feeds US1: a background turn's chain needs a root authority.

**Independent Test**: Capture consent for a scheduled job; run it under production posture; verify real-agent tools dispatch under an authority scoped to (consented ∩ current) grants, audit rows carry the defined machine principal and the owning human, and revocation (logout or explicit) pauses the job with a user-visible notification on the next run.

**Acceptance Scenarios**:

1. **Given** a user scheduling background work, **When** they confirm, **Then** the consent captured names the scopes being granted, its durable nature, and how to revoke — nothing is captured without this explicit step.
2. **Given** a scheduled run under production posture, **When** it dispatches a real-agent tool, **Then** the dispatch acts under authority derived from the stored consent narrowed to the user's *current* grants — never wider than either — and the same hop rules as US1 apply if the run chains further.
3. **Given** a user who logs out or revokes, **When** the next run fires, **Then** no tool dispatch occurs, the run records an authority-skip outcome, and the user is notified honestly.
4. **Given** an approved attachment parser's replay or a draft self-test, **Then** the same consent-derived authority path applies (all machine-turn classes inherit it at one shared seam), and their audit rows carry a defined machine principal attributable to the owning human — never "legacy"/"unknown".
5. **Given** the system-level AI credential is used for a background run (existing owner decision), **Then** the audit record distinguishes the paying credential from the authorizing human, so cost and authority attribution never blur.
6. **Given** the scheduler-execution flag remains off pending its security review, **Then** nothing in this story changes runtime behavior until that review is recorded — the consent capture and threading ship dark.

---

### User Story 3 - Every dispatch path enforces the same rules (Priority: P2)

A security reviewer (or the 047 benchmark) probes the system: whatever path a tool call takes — single, parallel batch, chained hop, machine turn — the identical gate stack applies. There is no "cheaper" path an attacker or a confused model can steer toward.

**Why this priority**: Prerequisite hardening — chains amplify the weakest path. Must land with or before US1 flag-on; ships independently as pure hardening either way.

**Independent Test**: For each gate (security flags, permissions, policy, taint, supervisor/HITL, delegation requirement, concurrency cap, audit pairs), drive the same violating call down the single path, the parallel path, and a chained hop; verify identical refusals and identical audit evidence on all three.

**Acceptance Scenarios**:

1. **Given** a tool call that the single path would refuse (any gate), **When** it is dispatched inside a parallel batch, **Then** it is refused identically with equivalent audit evidence.
2. **Given** orchestrator-internal capability calls (meta-tools) in a parallel batch, **Then** they dispatch correctly on both paths — and their gate-bypass precedent is structurally unavailable to real-agent hops.
3. **Given** a parallel batch under production posture, **Then** each call carries its own delegation authority exactly as a single call would.
4. **Given** long-running work started from any path, **Then** per-user concurrency accounting applies with a defined rule for how chained hops count, so fan-out cannot multiply a user's effective concurrency unboundedly.

---

### User Story 4 - Plans decompose without losing control (Priority: P2)

For a broad request ("audit my grant budget across these five programs and build me a dashboard"), the turn can spawn bounded, isolated sub-tasks — each with fresh context, its own narrowed authority, and its own budget — that run concurrently and return distilled results to the parent. The user sees hierarchical progress attributed to their chat, total work is bounded by a global chain budget, and the legacy unattenuated peer-call path is gone.

**Why this priority**: Delivers the "orchestrator isn't the sole planner" experience beyond single hops, fixes the documented degradation on wide fan-outs, and completes the confused-deputy cleanup. Depends on US1's authority machinery.

**Independent Test**: Drive a request that decomposes into 3+ sub-tasks; verify each sub-task ran isolated with narrowed authority and per-subtree budget, the parent received distilled results, cumulative depth/budget limits held across nesting, all inter-agent payloads passed the multi-agent defense scan, and the retired peer-call path no longer exists.

**Acceptance Scenarios**:

1. **Given** a decomposable request, **When** the turn spawns sub-tasks, **Then** each runs in a fresh, isolated context with authority derived from (and narrower than) the parent's, and its results return to the parent as bounded, provenance-tagged digests.
2. **Given** nested sub-tasks, **Then** a global chain budget (cumulative depth, total hop count, and wall-clock ceiling) bounds the whole tree; exhaustion produces honest partial results, never runaway recursion.
3. **Given** sub-task progress, **Then** the originating chat shows attributed hierarchical progress (which agent, for which sub-task, under whose authority), consistent with existing progress surfaces on every client.
4. **Given** any inter-agent payload (hop result or sub-task digest), **Then** it is scanned by the multi-agent defense layer before entering another agent's or the planner's context, and flagged payloads are quarantined with an audited reason.
5. **Given** this feature ships, **Then** the dormant direct peer-call path is removed (or hard-refused), with a regression test proving an agent cannot bypass orchestrator mediation.

---

### User Story 5 - Chaining is measured, not assumed safe (Priority: P3)

The security benchmark gains chained-attack scenarios — confused deputy, cross-hop scope escalation, depth-bound violation, chain-forgery — run through the real dispatch path. The measured attack-success-rate with chaining ON is no worse than the single-hop baseline, producing the thesis's enforcement evidence.

**Why this priority**: The thesis claim is "measured enforcement"; this converts US1-US4 into defensible evaluation artifacts. Depends on all prior stories but is independently executable as a measurement campaign.

**Independent Test**: Run the extended benchmark suite against the deployed configuration with chaining off, then on; produce the comparison report showing per-scenario outcomes and no ASR regression, with every blocked attack traceable to the specific gate that stopped it.

**Acceptance Scenarios**:

1. **Given** the benchmark's chained scenarios, **When** run with chaining enabled, **Then** every confused-deputy, escalation, depth-violation, and forgery case is blocked by a named layer, and overall ASR does not regress versus the single-hop baseline.
2. **Given** a blocked chained attack, **Then** its audit trail alone suffices to reconstruct what was attempted, by which principal chain, and which gate refused it.

---

### Edge Cases

- **Empty scope intersection**: a hop whose requested scopes intersect the parent's to nothing must be refused (not silently narrowed to nothing) with an audited narrowing/refusal record — resolving 048's open policy question toward fail-closed.
- **Mid-chain revocation**: the user logs out or revokes consent while a chain is in flight — in-flight hops complete or abort per their gates, but no *new* hop may mint after revocation; background chains stop at the next authority derivation.
- **Chained hop to a just-created agent**: a hop targeting an agent the user has no permission rows for follows the same resolution as direct calls (including the safe-agent baseline and its public-only restriction) — chains grant nothing extra.
- **Cycles and self-delegation**: A→B→A and A→A are bounded by depth and budget; verification refuses malformed or cyclic actor chains outright.
- **Parent turn ends before a sub-task**: orphaned sub-tasks are cancelled and audited; their partial results are discarded, never silently attached to a later turn.
- **Clock skew**: hop verification tolerates bounded skew (existing 60s tolerance) without weakening expiry inheritance.
- **Legacy tokens**: single-hop tokens remain honored as depth-0 roots; mixed old/new traffic must interoperate during rollout.
- **Dev-mode fail-open**: development posture retains today's unscoped fallback for *direct* dispatch, but chained hops and machine turns must exercise real minting even in dev (else the paths ship untested) — with the same observable refusals.
- **In-process hops**: hops between in-process agents have no network transport at which to "present" a token; verification runs as the same authority check at the mediation point, with identical audit output.
- **Concurrency-cap interplay**: a chain that fans out long-running jobs across agents must respect the defined accounting rule; rejection (not queueing) semantics are preserved.
- **PHI gate**: any hop that persists memory/signals passes the PHI gate independently of its delegation authority.
- **Notification fatigue**: repeated authority-skip notifications for a paused job collapse into one actionable notification, not one per scheduled firing.

## Requirements *(mandatory)*

### Functional Requirements

**Chained authority (US1)**

- **FR-001**: Agents MUST be able to request a peer agent's tool mid-task through orchestrator mediation only; every such hop MUST act under a newly minted child authority — never the parent's token, never ambient authority.
- **FR-002**: Child authority MUST satisfy the 048 invariants: scopes = intersection(parent, requested); audience/issuer never widened; expiry ≤ parent; depth = parent + 1, refused beyond the configured bound (default 3); actor chain complete and terminating at the human principal.
- **FR-003**: Every hop MUST re-enter the full single-path gate stack (security-flag block, per-user tool permission, policy, taint, supervisor/HITL, credential injection per (user, callee), PHI where applicable, concurrency accounting, paired audit) keyed to the human principal — the meta-tool bypass is structurally unavailable to real-agent hops.
- **FR-004**: Chained tokens MUST be signed and verifiable at the mediation point; possession-proof binding remains with the orchestrator's key custody (hops stay orchestrator-mediated); verification failures refuse the hop per-call without tearing down any session.
- **FR-005**: An empty scope intersection MUST refuse the hop; every refusal AND every narrowing MUST be audited with the requested-vs-granted scopes recorded (closes 048's FR-004 gap).
- **FR-006**: Mid-chain revocation MUST prevent any new hop mint after the revocation event; revocation checks are part of authority derivation, not only expiry.
- **FR-007**: Hop results returned to the requesting agent or planner MUST pass the multi-agent defense payload scan; flagged payloads are quarantined with an audited reason and an honest error to the requester.
- **FR-008**: One agent's stored credentials MUST never be forwarded to another agent on any hop; each hop's credentials are injected per (user, callee agent) under the existing encryption discipline.
- **FR-009**: The chaining capability ships behind its existing default-off flag; flag-off behavior is byte-for-byte today's single-hop path with zero regression to the existing delegation and permission test suites; legacy single-hop tokens are honored as depth-0.
- **FR-010**: The dormant direct peer-call path MUST be retired (removed or hard-refused with audit), with a regression test proving agents cannot bypass mediation.

**Machine-turn authority (US2)**

- **FR-011**: The system MUST provide an explicit consent-capture step when a user schedules background work or approves a capability that runs on their behalf later, recording the granted scopes, durability, and revocation path; no durable consent is created implicitly.
- **FR-012**: Every machine-initiated turn (scheduled run, parser replay, draft self-test, and any future class) MUST derive per-run authority from stored consent — fresh at each run, narrowed to (consented ∩ the user's current grants) — via one shared mechanism all machine-turn classes inherit.
- **FR-013**: A machine turn without derivable authority (missing, revoked, expired consent) MUST refuse all real-agent dispatch fail-closed, record an authority-skip outcome, and notify the user actionably (collapsed, not per-firing).
- **FR-014**: Machine turns MUST be audited under a defined machine principal that preserves attribution to the owning human (no more "legacy"/"unknown"), and MUST distinguish the paying AI credential (system) from the authorizing human in cost/authority records — acknowledging the existing owner decision that machine turns bill the system credential.
- **FR-015**: Chains originating in machine turns MUST use the same child-mint rules as interactive chains — one authority model, two roots (session token / consent-derived token).
- **FR-016**: The scheduler-execution flag stays default-off until its pending security review is recorded; all US2 machinery must be shippable dark behind it, and the review gate is inherited, not bypassed.

**Dispatch-path parity (US3)**

- **FR-017**: The parallel dispatch path MUST apply the same gate stack as the single path with equivalent refusals and audit evidence; conformance is proven by a shared gate-contract test run against both paths (and against chained hops).
- **FR-018**: Orchestrator-internal meta-tools MUST dispatch correctly from both paths; their gate exemption remains limited to consent-carded orchestrator-internal capabilities and is structurally closed to real agents.
- **FR-019**: Long-running-work concurrency accounting MUST define how chained hops count (both the initiating agent's and the executing agent's user-scoped slots are charged), preserving reject-not-queue semantics so fan-out cannot multiply effective concurrency.

**Planning decomposition (US4)**

- **FR-020**: The turn planner MUST be able to spawn bounded, isolated sub-tasks with fresh context, each holding child authority derived from the turn's root and a per-subtree budget; sub-task results return as bounded, provenance-tagged digests.
- **FR-021**: A global chain budget MUST bound cumulative depth, total hop count, and wall clock across all nesting in one user turn (including machine turns); exhaustion yields honest partial results and an audited budget-stop.
- **FR-022**: Sub-task and hop progress MUST surface in the originating chat with per-hop attribution (acting agent, sub-task, authorizing chain), riding existing progress surfaces on every client without new client requirements.
- **FR-023**: Orphaned sub-tasks (parent ended, socket gone, budget exhausted) MUST be cancelled and audited; their partial output is never silently attached to later turns.

**Measurement (US5)**

- **FR-024**: The security benchmark MUST gain chained scenarios — confused deputy, cross-hop scope escalation, depth-bound violation, actor-chain forgery, chained-consent replay — executed through the real dispatch path, each attributed to the defense layer that blocks it.
- **FR-025**: A comparison run (chaining off vs. on) MUST be producible on demand, reporting per-scenario outcomes and overall attack-success-rate, with the acceptance bar: no ASR regression with chaining on.
- **FR-026**: Two-hop chain reconstruction from the tamper-evident audit log alone MUST be demonstrated and kept as a regression test (closes 048 T018).

**Cross-cutting**

- **FR-027**: No new third-party runtime dependencies; tokens and signing ride existing cryptographic machinery; any schema change ships as an idempotent guarded migration with documented rollback.
- **FR-028**: All refusals in this feature are per-call and fail-closed, never session-terminating, and always audited without recording secret values.
- **FR-029**: Explicit user opt-out (disabled agent/tool) always wins over any chain, trust baseline, or consent; hard security-flag blocks are never clearable by chaining.

### Key Entities

- **Delegation chain**: the authority lineage of a piece of work — human principal → root token (session or consent-derived) → child hops (each attenuated) — with depth, scopes, expiry, and actor chain; verifiable and reconstructible from audit alone.
- **Chained hop**: one agent-to-agent (or planner-to-agent) sub-request: requested tool, requesting principal, child authority, gate outcomes, paired audit records, correlation linkage to its parent.
- **Durable consent (offline grant)**: the user-approved, revocable, scope-listing record from which machine-turn root authority derives; encrypted at rest, hard-capped lifetime, revoked on logout, freshly exercised per run.
- **Machine principal**: the defined audit identity for machine-initiated turns, always carrying the owning human's identity and the run's consent reference.
- **Sub-task**: an isolated planning subtree with fresh context, child authority, per-subtree budget, and a distilled result contract back to its parent.
- **Chain budget**: the global per-turn ceiling (depth, hop count, wall clock) governing all nesting.
- **Chained-attack scenario**: a benchmark case exercising a specific chain abuse, mapped to the defense layer expected to stop it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With chaining enabled, a two-agent chained request (e.g., research → summarize) completes end-to-end with every hop under attenuated authority, and 100% of hops in a 50-chain soak show scopes ⊆ parent, expiry ≤ parent, depth ≤ 3, and actor chains terminating at the human — verified from tokens and audit alone.
- **SC-002**: 100% of gate-violating hop attempts (disabled agent, blocked tool, out-of-scope, over-depth, empty intersection) are refused per-call with audit evidence, and zero refusals tear down a live session, across the negative-path suite.
- **SC-003**: Two-hop chain reconstruction from the audit log alone succeeds and is pinned as a regression test (048 T018 closed); auditors can answer "who did what under whose authority" for every hop in the soak without any other data source.
- **SC-004**: Under production posture with consent captured, scheduled runs dispatch real-agent tools successfully in 100% of authorized trials; after logout or revocation, 0% dispatch and the user receives exactly one actionable notification per paused job.
- **SC-005**: Machine-turn audit rows carry the defined machine principal with human attribution in 100% of runs across all three machine-turn classes — zero "legacy"/"unknown" attributions.
- **SC-006**: The dispatch-path parity suite (same violating call driven down single, parallel, and chained paths) shows identical refusal outcomes and equivalent audit evidence for every gate — zero asymmetries remaining.
- **SC-007**: A decomposed request spawning ≥3 sub-tasks completes with per-subtree budgets enforced, global chain budget never exceeded in a 20-run soak, and zero orphaned sub-tasks attaching results after parent end.
- **SC-008**: The extended benchmark reports ASR with chaining ON ≤ ASR with chaining OFF across the scenario matrix, with every blocked chained attack attributed to a named defense layer; the report is reproducible on demand.
- **SC-009**: With all feature flags OFF, the full existing test suite (including the 11 delegation and 26 tool-permission tests) passes unchanged, and wire/token behavior is byte-identical to pre-feature — demonstrating safe rollback.
- **SC-010**: An agent-initiated hop attempt via the retired direct peer path fails 100% of the time with an audited refusal.

## Assumptions

- **Both chaining seams are in scope** (owner decision 2026-07-13): deterministic agent-initiated peer calls via the injected runtime, and LLM-planned nested sub-turns; both are orchestrator-mediated. Direct agent-to-agent transport is out of scope and the existing dormant path is retired.
- **Machine-turn authority is in scope** (owner decision 2026-07-13) and inherits the pending offline-grant security-review gate: consent capture and token threading ship dark behind the existing default-off scheduler-execution flag until that review is recorded.
- **Child-token signing** is expected to be orchestrator-local using existing key material (the mediation point is both minter and verifier), with the effective enforced scope recorded per hop because the IdP cannot express downstream narrowing; a per-agent key model is explicitly out of scope.
- **Per-hop permission semantics** default to both-ANDed: token-scope attenuation AND the per-(user, callee) permission resolution both must pass — chains never grant more than a direct call would.
- **Concurrency accounting** defaults to charging both the initiating and executing agents' user-scoped slots; the planner treats cap rejections as honest hop failures.
- **Depth bound** stays at the 048 default (3) with the existing claim-carried maximum; making it operator-configurable is a nice-to-have, not a requirement.
- **Progress surfaces**: hierarchical hop/sub-task progress reuses existing progress frames and requires no new native-client renderers; native manifest updates occur only if a new frame proves unavoidable, and then follow the drift-guard constitution.
- **The known pre-existing supervisor-gate test failures** (flagged by 048 as out of its scope) are in scope here only insofar as US3 touches those gates; fixing them is expected but bounded.
- **Thesis alignment**: this spec is Direction A's system evidence; the 049 IETF document decision and 046 differential remain separate documentation tracks that will cite this feature's artifacts.
- **The 050 precedent holds**: external agent fabrics (e.g., Cresco) chain in only as flag-gated first-party bridge agents through these same gates; nothing here opens a platform-level integration.

## Dependencies

- **Builds on (existing, merged)**: 048's recursive-delegation mechanism layer + property tests; the RFC 8693/DPoP single-hop delegation service; offline-grant store (025/030); scheduler + job runner (030); tool permission/trust/security-flag stack (013/040); hash-chained audit (003+); MAS-defense payload scanner (033 C-S14 scaffolding); concurrency cap; 047 security-benchmark harness; VirtualWebSocket machine-turn substrate (027/031/032).
- **Owner review gate inherited**: the offline-grant security review (025 T057 / 030 FR-004/FR-005) must be recorded before the scheduler-execution flag defaults on; this spec does not bypass it.
- **Sibling spec**: 055 (uniform artifacts) is independent; chained/sub-task progress attribution should compose with 055's artifact delivery but neither blocks the other.
- **Evidence base**: 2026-07-13 research digest (dispatch control-flow trace, 048 implementation-maturity audit, machine-turn authority probe) with file:line citations, reproducible from the cited modules.
