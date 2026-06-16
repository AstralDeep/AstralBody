# Feature Specification: Frontier Capabilities Research & Novel-Technique Roadmap

**Feature Branch**: `033-frontier-techniques-research`
**Created**: 2026-06-16
**Status**: Draft
**Input**: User description: "Create a new spec. This spec will include much more research than implementation this time. Compare this system with commercial (OpenAI, Google, Meta, Anthropic, etc.) offerings and see in what ways they are pulling ahead where those items could be implemented in this system. Also look at recent agentic AI framework literature from scholarly sources (no medium articles) and do the same comparison. I want a large corpus of ideas and new techniques to implement into this current system. Novelty is of the utmost importance, user experience is next, then device adaptation and agentic security."

## Overview

This feature is **research-led**: its primary deliverable is a rigorously sourced, deduplicated, and prioritized **corpus of novel techniques** drawn from both the mid-2026 commercial AI frontier (OpenAI, Google/DeepMind, Anthropic, Microsoft, Meta, Amazon, Vercel, and notable agent startups) and the recent scholarly literature on agentic AI, generative/adaptive UI, agent memory, agentic security, and device adaptation (primary venues only — arXiv, CHI/UIST/IUI, NeurIPS/ICML/ICLR, ACL, IEEE S&P/USENIX/CCS/NDSS, IETF, OWASP — explicitly **no** Medium or content-farm articles). That corpus already exists in this feature's [`research/`](research/) folder: eight per-domain findings files (~164 raw findings) and a cross-stream [`research/SYNTHESIS.md`](research/SYNTHESIS.md) that collapses them into **71 consolidated, deduplicated capabilities** ranked by the project's priority order.

The corpus is organized so AstralBody can see **exactly where the frontier is ahead of it and what is worth adopting**, scored for novelty, impact, and effort, cross-referenced to primary sources, and de-duplicated across streams (convergent findings — those surfaced independently by three or more streams — are flagged as the highest-confidence signals). It is filtered through AstralBody's non-negotiable constraints (Python backend only, **no new third-party runtime libraries**, the SDUI mandate of *astralprims defines → orchestrator renders → ROTE adapts*, idempotent startup migrations, fail-closed posture) so every retained capability is implementable without violating the constitution.

The second deliverable is a **prioritized implementation roadmap**: the consolidated capabilities grouped into capability initiatives and sequenced into waves, with the project's priority order (**novelty paramount → user experience → device adaptation → agentic security**) driving depth of investment. Per the clarifications below, **branch 033 ships research + roadmap only — no product code.** Every implementation capability is delivered as its own approved follow-on feature branch; the roadmap designates the **co-flagship trio — generative model-grounded UI (US2), self-improving agent architecture (US3), and living memory & personalization (US4) — as the first follow-on initiatives**, selected with a novelty-forward bias. Execution of any implementation work begins only when the user grants permission to open those follow-on specs.

This feature deliberately does **not** rebuild or regress AstralBody's existing differentiators (the adaptive UI designer's layout intelligence, in-process `VirtualWebSocket` self-test, hash-chained audit, deterministic PHI gate, RFC 8693 delegated scopes, agentic creation, persistent workspace, cross-session memory). The frontier moves it adopts are *depth and contract* improvements on those strengths, not parallel reimplementations — and §5 of the synthesis enumerates the strengths to protect from regression.

## Clarifications

### Session 2026-06-16 (resolved with user)

- Q: What does branch **033** ultimately deliver as code? → A: **Research + roadmap only.** This branch ships the research corpus and the prioritized roadmap — **no product/implementation code**. Every implementation wave is delivered as its own approved follow-on feature branch. The "permission to implement" step becomes "permission to open the follow-on implementation specs." This feature's `tasks.md` therefore covers *finalizing the corpus and structuring the roadmap*, not code implementation.
- Q: Which initiative leads implementation when the follow-on specs are approved? → A: **Co-flagship trio: generative model-grounded UI (US2) + self-improving agent architecture (US3) + living memory & personalization (US4) lead together** — the three highest-novelty/UX clusters, sequenced as the first follow-on specs (each pulling in the Wave-0 enablers it depends on). Device adaptation (US5) and preventive security (US6) follow, except for the security controls that must ship with the autonomy increases they guard (FR-011).
- Q: How to bias selection within the backlog for the lead work? → A: **Novelty-forward (highest-novelty structural bets).** Lead with the boldest moves (task-model-first UI, generative primitives, optimizable agent graph, evolutionary auto-create, sleep-time memory, the VOICE renderer), each paired with the cheap convergent enabler it depends on so it is measurable and not built on sand.
- Q: Is the research corpus complete? → A: **Locked as sufficient.** 71 consolidated capabilities across eight primary-sourced streams is enough to plan from; no further research pass before finalizing.

### Session 2026-06-16 (informed defaults — superseded above where they conflict)

- Q: How much of the roadmap does **this feature** implement vs defer to follow-on features? → A: **Research + roadmap + an approved first slice.** This feature's committed deliverable is the research corpus and the prioritized roadmap (already produced). Implementation begins only on the user's go-ahead and, by default, starts with **Wave 0 (foundational quick wins) + the Wave 1 flagship generative-UI core**; Waves 2–5 are scoped here but delivered as their own follow-on feature branches so each meets the constitution's production-ready + 90%-changed-coverage bar without an unreviewably large PR. (Confirm the exact first-slice boundary at clarify.)
- Q: Does "novelty is of the utmost importance" mean prioritizing genuinely novel/unproven techniques over high-confidence convergent ones? → A: **Novelty drives selection and investment depth; convergence drives sequencing.** The roadmap invests deepest in the highest-novelty structural moves (task-model-first generative UI, generative primitives, self-improving agent architecture, the VOICE renderer), but sequences the low-effort, high-confidence convergent enablers (structured output, context engineering, the eval backbone) into Wave 0 first because they de-risk and measure everything novel that follows.
- Q: The corpus contains capabilities that brush the "no new third-party runtime libraries" line (realtime voice transport, browser pixel-automation, on-device decoding). In/out? → A: **Out of scope, tracked as future negotiations.** They are catalogued in [`SYNTHESIS.md` §6](research/SYNTHESIS.md) with the *portable-now* part of each idea routed into an in-constraint capability (e.g. realtime voice → the VOICE *output* renderer C-D4; computer-use → the typed must-ack safety gate C-S11). Any genuine new-dependency request is a separate lead-developer approval per Constitution V.
- Q: Where does agentic security sit, given it is priority #4 but guards autonomy increases? → A: **#4 for investment depth, but timed to its dependents.** Security capabilities that protect a specific shipping autonomy increase (sandboxed codegen C-S6, red-team self-test C-S7, memory-poisoning defense C-S9, MAS defenses C-S14) ship *with or before* the Wave-2 capabilities they protect, even though the security tier as a whole is the lowest investment priority.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A vetted, prioritized corpus of novel techniques the team can act on (Priority: P1)

A maintainer wants to know, concretely and with citations, **where the AI frontier is ahead of AstralBody and which advances are worth adopting** — ranked by the project's own priorities, deduplicated across sources, and pre-filtered to what is buildable within AstralBody's constraints. They open this feature's `research/` folder and find eight per-domain findings files plus a synthesis that presents every consolidated capability with a stable ID, the primary sources it rests on, novelty/impact/effort scores, a cross-source consensus indicator, and a concrete "how to implement in AstralBody (no new deps)" note — then a recommended wave sequence and an explicit list of what *not* to regress.

**Why this priority**: This is the heart of the request ("much more research than implementation"; "a large corpus of ideas and new techniques"; "novelty is of the utmost importance"). It stands alone as a complete, valuable deliverable: even if no capability is ever implemented, the corpus is a durable, citeable competitive-intelligence and roadmap artifact. It is the foundation every other story builds on.

**Independent Test**: Open `research/SYNTHESIS.md` and any one stream file; confirm that (a) each consolidated capability cites at least one primary source and carries novelty/impact/effort scores, (b) cross-stream duplicates are merged with consensus noted, (c) every retained capability has an in-constraint implementation note, (d) capabilities are grouped and ordered by the four priority dimensions, and (e) a "do not regress" list and an "out-of-constraint/deferred" list both exist. Fully verifiable with no capability implemented.

**Acceptance Scenarios**:

1. **Given** the research folder, **When** a reviewer reads the synthesis, **Then** they find a single deduplicated backlog of consolidated capabilities (each with a stable `C-*` ID, primary-source citations, novelty/impact/effort, and a consensus/confidence indicator) covering all four priority dimensions, plus the eight underlying stream files for full per-finding detail.
2. **Given** any consolidated capability, **When** the reviewer inspects it, **Then** it names the commercial product(s) and/or scholarly paper(s) it derives from with working source references, states what AstralBody lacks and why it matters, and gives a concrete implementation approach that respects Python-only / no-new-deps / SDUI / idempotent-migration constraints.
3. **Given** the commercial-vs-AstralBody comparison, **When** the reviewer looks for OpenAI/Google/Anthropic/Microsoft/Meta/Amazon/Vercel/startup coverage, **Then** each vendor's relevant frontier surface is represented and mapped to a gap or an explicit "AstralBody already at/above frontier — do not regress" note.
4. **Given** the scholarly comparison, **When** the reviewer checks sourcing, **Then** every scholarly finding cites a primary venue (arXiv/conference/journal/standard) and there are **zero** Medium/listicle/content-farm sources in the scholarly streams.
5. **Given** the priority order (novelty → UX → device → security), **When** the reviewer reads the recommended sequencing, **Then** investment depth follows the priority order while low-effort convergent enablers are sequenced first to de-risk later work, and the rationale is stated.
6. **Given** the corpus, **When** the reviewer looks for honesty signals, **Then** vendor hype, preview-vs-GA status, unverifiable benchmark claims, and source-extraction caveats are explicitly flagged rather than presented as fact.

---

### User Story 2 - Co-flagship: generative, model-grounded adaptive UI (Priority: P1)

> **Roadmap note**: A co-flagship follow-on initiative (with US3 and US4), not built on branch 033. Delivered as its own approved spec; this story defines the target capability and its independently-testable acceptance.

Acting on the highest-novelty + highest-UX cluster, AstralBody's UI generation moves from "arrange finished components" to **"model the task, then render and adapt the UI"**. For a component-rich turn the orchestrator first derives a typed task/data model (entities, typed attributes, dependency edges), maps attributes to primitives by deterministic rules, and lets a **deterministic layout scorer** (not the LLM's free-text self-critique) select among LLM-proposed arrangements — conservatively, charging a disruption cost so the canvas does not churn turn-to-turn. The same path can compose **gated open-ended/generative primitives** beyond the closed palette (constrained grammar + post-validator + the existing draft→self-test→admin-approval rail), and it lints generated UI for dark patterns and surfaces provenance/uncertainty so a hallucinated card never looks identical to a verified one.

**Why this priority**: This is the project's signature SDUI thesis taken to the frontier and the single largest novelty+UX delta in the corpus (task-model-first generation, deterministic scoring, conservative adaptation, generative primitives, trust-as-UX). It is independently valuable: shipping even the task-model + deterministic-scorer core measurably improves layout quality and stability without any other story.

**Independent Test**: For a multi-component turn, confirm the orchestrator emits a typed task model, that the rendered layout is selected by a deterministic score over multiple candidates (not a single free-text "looks best"), that re-running a similar turn does not needlessly re-arrange a stable canvas, and that designer-added garnish is lint-checked and provenance-annotated — all behind feature flags, fail-open to today's behavior.

**Acceptance Scenarios**:

1. **Given** a component-rich turn, **When** the designer runs, **Then** a typed task/data model is produced first and the layout tree is derived from it by deterministic attribute→primitive rules (C-N1), persisted alongside the existing `workspace_layout` overlay.
2. **Given** several candidate arrangements, **When** the designer selects one, **Then** selection is made by a pure-Python `score_arrangement` objective (alignment/grouping/density/device-fit/effort), with the LLM proposing and the scorer deciding (C-U1).
3. **Given** a user who already has a stable canvas, **When** a new turn would re-arrange it, **Then** the redesign is applied only if its score beats the current layout by more than a disruption-cost margin (C-U2), avoiding gratuitous churn.
4. **Given** a designer-added garnish component, **When** it is finalized, **Then** a deterministic dark-pattern lint strips/downgrades manipulative emphasis and an audit event records the action (C-U7), and entity facts in components are gated to trace to a tool/search result with a provenance/uncertainty signal (C-U6).
5. **Given** a request that warrants a widget the closed palette cannot express, **When** generative-primitive mode is enabled, **Then** the LLM emits grammar-constrained structure that passes a post-validator and renders through the escape-by-default sanitizer, with any genuinely new primitive routed through the draft→self-test→admin-approval pipeline (C-N2), never as arbitrary unvalidated HTML.
6. **Given** any failure in the above (model error, timeout, invalid structure), **When** the designer path runs, **Then** it falls open to today's flat-append behavior and logs the fallback — no regression to current functionality.

---

### User Story 3 - Co-flagship: self-improving agent architecture (Priority: P1)

> **Roadmap note**: A co-flagship follow-on initiative (with US2 and US4), not built on branch 033. Delivered as its own approved spec; this story defines the target capability and its independently-testable acceptance.

The orchestration layer gains the frontier's self-improvement machinery, all measured by a new **trajectory-evaluation backbone** (an Agent-as-a-Judge over the existing hash-chained audit/tool-dispatch trace, plus `pass^k` reliability and debiased judging). The flagship agentic-creation loop becomes **evolutionary and archive-conditioned** (every draft's code + self-test score is archived and fed back as exemplars; a cheap surrogate pre-scores drafts before the costly self-test). Hard turns gain a **dual-ledger self-correcting controller**, optional **mixture-of-agents/debate**, and **async parallel fresh-context fan-out** that fixes the documented >8-item context-degradation. Successful tool traces are distilled into a **procedural skill/recipe memory**, and idle time is used for **sleep-time precompute**.

**Why this priority**: This is the second pillar of "novelty is of the utmost importance" — it upgrades AstralBody's most distinctive feature (agentic creation) from one-shot to self-improving, and adds the measurement backbone every other self-improving loop needs. Co-flagship with US2 and US4; it pulls in the Wave-0 eval-backbone and structured-output enablers it depends on.

**Independent Test**: Confirm a draft agent's creation now (a) records its code + self-test score to an archive and conditions future codegen on it, (b) is pre-scored by a surrogate before the full self-test runs, and (c) is evaluated by a trajectory judge over the audit trail rather than a single pass/fail; and confirm a list task over >8 items runs as isolated fresh-context sub-runs rather than degrading in one context.

**Acceptance Scenarios**:

1. **Given** a capability gap, **When** `create_capability`/`extend_agent` runs, **Then** it retrieves top archived exemplars for similar gaps as codegen context and writes the new draft's code + self-test score + gap fingerprint back to the archive (C-N4).
2. **Given** a freshly generated draft, **When** the pipeline runs, **Then** a cheap surrogate rubric pre-scores it and likely-failing drafts are auto-refined *before* the costly `VirtualWebSocket` self-test (C-N4).
3. **Given** any agent run or self-test, **When** it completes, **Then** a trajectory judge scores the recorded tool-dispatch sequence (requirement coverage, tool-use correctness, safety adherence) with order-swap debiasing, and self-tests run `pass^k` (all-of-k) rather than single-shot (C-N5).
4. **Given** a list/fan-out task over more than ~8 items, **When** it runs, **Then** the controller decomposes it into isolated fresh-context sub-runs executed concurrently under a bounded pool, each self-verifying before the controller aggregates (C-N8) — and any inter-agent edges carry provenance/integrity per the security tier (C-S14).
5. **Given** a successful multi-tool turn, **When** consolidation runs, **Then** the trace is distilled into a self-verified, parameterized recipe retrievable for similar future turns and replayed under the existing RFC 8693 scopes + audit (C-N10).

---

### User Story 4 - Co-flagship: living memory & proactive personalization (Priority: P1)

> **Roadmap note**: A co-flagship follow-on initiative (with US2 and US3), not built on branch 033. Delivered as its own approved spec; this story defines the target capability and its independently-testable acceptance.

AstralBody's memory/"soul" moves from store-and-summarize to **store, link, reconcile, and anticipate**. Consolidation gains an LLM-mediated write path (ADD/UPDATE/DELETE/NOOP with supersession), self-organizing linked memory notes that let new experience rewrite the interpretation of old, graph/Personalized-PageRank associative retrieval for multi-hop "connect-the-dots" recall, multi-signal retrieval (recency × importance × relevance), temporal validity with contradiction resolution and abstention, principled decay (which doubles as PHI/data minimization), and an **evolving, optimizable per-user persona**. "Dreaming" additionally **anticipates** likely questions and precomputes derived facts. A proactive card-grid digest surface turns this machinery into a visible daily product.

**Why this priority**: Directly serves "user experience is next" and carries high novelty (sleep-time compute, memory evolution). All capabilities are designed for Postgres + the existing LLM client — **no vector DB, no new dependency** — and several (decay-as-PHI-minimization, provenance/unlearning) reinforce the security posture.

**Independent Test**: Confirm that a contradicting fact supersedes (not appends to) the old memory; that retrieval ranks by a recency×importance×relevance composite; that a multi-hop personal question is answered via graph/PageRank recall; and that the consolidation job precomputes anticipated derived facts — all per-user isolated and audited.

**Acceptance Scenarios**:

1. **Given** new information that contradicts a stored memory, **When** consolidation runs, **Then** an LLM-mediated write path supersedes the stale memory (soft-delete + `superseded_by`, retained for audit) rather than accumulating a contradiction (C-M1), with temporal validity intervals recorded (C-M6).
2. **Given** a multi-hop personal question, **When** retrieval runs, **Then** a Postgres-backed entity graph + pure-Python Personalized PageRank surfaces connected memories the user never stated together (C-M3), and ranking combines recency × importance × relevance (C-M4).
3. **Given** memories interconnect, **When** a new note is consolidated, **Then** it links to neighbors and may rewrite their contextual interpretation (C-M2).
4. **Given** idle time, **When** the dreaming job runs, **Then** it precomputes anticipated next-question answers/derived facts to a TTL-bounded, per-user, PHI-gated cache reused on later turns (C-N11).
5. **Given** stale or sensitive memories, **When** the decay sweep runs, **Then** unused memories fade and flagged PHI is actively forgotten (C-M7), and a user-facing surface lets a person view provenance and correct/forget specific memories with genuine deletion (C-M9).

---

### User Story 5 - Device adaptation & multimodal reach (Priority: P3)

> **Roadmap note**: A follow-on initiative after the co-flagship trio (US2/US3/US4), not built on branch 033. Serves the device-adaptation priority; delivered as its own approved spec.

ROTE evolves from a one-shot, coarse, per-device-type code transform into a **capability-negotiated, declarative, multi-objective adaptation layer**. Each renderer target publishes a declared primitive vocabulary + contract version; ROTE filters/substitutes via a deterministic fallback ladder and a per-target declarative host-config (data, not code). Adaptation becomes a weighted-objective scorer that also makes the UI designer **device-aware**. A real **structured VOICE renderer** (SSML + navigable tree + verbosity tiers + earcons/sonification) and an AOM-style semantic-tree renderer fill the emptiest targets; a **compute-placement model router** picks a model tier per device (with an optional on-device browser-AI lane, server still authoritative); a live viewport/theme feedback loop replaces one-shot adaptation; and accessibility becomes a generation/render constraint with ability profiles.

**Why this priority**: Serves "then device adaptation." Every capability lands as a new orchestrator renderer or a ROTE extension — exactly the constitutionally-sanctioned extension point ("add a target = add a renderer") — with no primitive changes and no new dependency. The VOICE renderer is the highest-novelty, currently-emptiest target in the whole corpus.

**Independent Test**: Confirm a target that cannot render a primitive triggers a deterministic fallback (timeline→list, chart→table→text) rather than shipping an unrenderable component; that the VOICE target emits a navigable structured auditory tree with verbosity tiers rather than flat text; and that a simple turn on a constrained device is routed to a cheaper model tier.

**Acceptance Scenarios**:

1. **Given** a connecting target with a declared primitive vocabulary, **When** ROTE adapts, **Then** unsupported component types are filtered/substituted by a deterministic fallback ladder under a versioned contract (C-D1), and per-target behavior is read from a declarative host-config dict (C-D2).
2. **Given** any component, **When** the VOICE target renders, **Then** it emits SSML + a navigable axis→series→point / header→rows structure + three verbosity tiers + deterministic earcon/sonification tokens, not flat narration (C-D4).
3. **Given** the connecting device's capabilities, **When** the orchestrator picks a model, **Then** a device-capability-aware router selects a tier (cheap-first cascade, escalate on low confidence), optionally delegating tagged simple tasks to an on-device browser-AI lane with automatic server fallback (C-D6).
4. **Given** a viewport/theme/orientation change, **When** the client reports it, **Then** ROTE re-adapts the current canvas and pushes a targeted update rather than ignoring the change until the next turn (C-D7).
5. **Given** the UI-designer loop, **When** it arranges for a specific target, **Then** the target's objective weights (glanceability, speakability, width-fit, interaction-cost) feed the designer so arrangement is device-aware (C-D3), and rendered HTML meets WCAG-by-construction with optional ability profiles (C-D9).

---

### User Story 6 - Preventive agentic security (Priority: P3)

> **Roadmap note**: A follow-on initiative, not built on branch 033. Lowest investment priority overall — BUT the specific controls that guard a shipping autonomy increase (sandboxed codegen, red-team self-test, memory-poisoning defense, MAS defenses) ship *with or before* the co-flagship US3/US4 work they protect (FR-011).

AstralBody's security posture shifts from largely **reactive** (a tamper-evident audit of what already happened) to **preventive and by-construction**. Untrusted-ingest flows (`fetch_page`, `summarizer`, auto-created parsers) are routed to the minimal security-by-construction pattern (plan-then-execute / dual-LLM / map-reduce / context-minimization) so injected instructions in fetched/parsed content cannot trigger consequential actions; a **taint/provenance graph** labels every value and refuses untrusted-tainted data reaching write/egress sinks; a single **deterministic pre-action policy engine** (absorbing the PHI and scope gates as seed rules) authorizes every tool call fail-closed; **spotlighting/datamarking** marks untrusted spans; a **runtime supervisor** reviews outputs before they reach the user; generated code runs **sandboxed**; the self-test gains an **adversarial red-team pass** and an **AstralDojo CI suite**; delegation gains **single-use transaction tokens + agent identity**; and the memory feature is hardened against **poisoning**.

**Why this priority**: Serves "and agentic security" (priority #4). Per the clarification, the tier as a whole is the lowest investment priority, but the specific controls that protect a shipping autonomy increase (sandboxed codegen, red-team self-test, memory-poisoning defense, MAS defenses) are timed to ship *with or before* the Story-3/Story-4 capabilities they guard. All controls reuse existing scopes/audit/PHI infrastructure with no new dependency.

**Independent Test**: Drive an indirect-injection payload through `fetch_page`/`summarizer`/a malicious file fixture and confirm zero out-of-scope tool calls, zero egress, and zero PHI emission; confirm a deny/confirm decision is made by a single pre-action policy chain before the tool runs and is audited; and confirm generated parser code cannot open a socket or touch the filesystem outside its temp scope.

**Acceptance Scenarios**:

1. **Given** a read-only fetch/summarize turn, **When** it runs, **Then** the untrusted text is processed by a toolless model call whose output can only become an answer/component — never a new tool call — and a multi-tool turn commits its tool plan before any untrusted data returns, refusing out-of-plan calls (C-S1).
2. **Given** any tool result, **When** it flows through the turn, **Then** it carries a trust label whose effective value is the minimum over its data ancestors, and a tool call whose arguments carry untrusted-tainted values into a write/egress sink is denied or escalated (C-S2).
3. **Given** any tool call, **When** dispatch occurs, **Then** a single deterministic policy engine (trigger/predicate/enforcement) authorizes it fail-closed before execution — with the existing PHI gate and scope check expressed as two seed rules — and records the decision in the audit chain (C-S3).
4. **Given** generated agent/parser code, **When** it executes, **Then** it runs in a resource-limited child process with blocked sockets and a temp-scoped filesystem, with all cross-agent/egress calls mediated by the dispatch chokepoint (C-S6); and before go-live the candidate is driven through an adversarial red-team self-test plus the AstralDojo CI suite asserting zero out-of-scope calls/egress/PHI (C-S7).
5. **Given** consolidation into durable memory, **When** content is untrusted-derived, **Then** it is refused without explicit human confirmation, memory rows are integrity-signed, and retrieval applies trust filtering (C-S9); and every consequential/irreversible action requires a provenance-showing human confirmation that names the untrusted source (C-S11).

---

### Edge Cases

- **A source could not be fully fetched/parsed**: the corpus records the finding from the available abstract/secondary evidence and **flags the reduced confidence** rather than fabricating detail or omitting it silently (already done in the generative-UI and OpenAI streams).
- **A finding is vendor marketing, not capability**: it is flagged as hype with the testable mechanism (if any) separated from the claim; unverifiable benchmark numbers are labelled vendor-internal.
- **AstralBody is already at or ahead of a "frontier" capability**: it is recorded in the "do not regress" list, not as a gap to close.
- **A capability requires a new runtime dependency or hardware**: it is moved to the deferred/out-of-constraint list with the *portable-now* sub-idea routed into an in-constraint capability; any genuine dependency ask becomes a separate Constitution-V approval.
- **Two streams surface the same idea with different framings**: they are merged into one consolidated capability with both sources cited and a consensus indicator; they are not double-counted.
- **A high-novelty idea is also high-risk/low-confidence**: it is retained but its scores and caveats make the risk explicit, and its sequencing places verification (eval backbone, red-team) before reliance.
- **An implemented capability's LLM-assisted step fails (timeout, model error, invalid output)**: the capability must fail open to today's behavior and log the fallback — never block or regress an existing flow.
- **A security capability would be bypassed by laundering untrusted content through an intermediate tool**: the taint model uses min-over-ancestors so transitive taint survives multi-hop laundering.
- **Implementation begins before approval**: it must not — every implementation wave is gated on explicit user go-ahead, and the spec/plan/tasks exist to define and sequence the work, not to authorize its execution.

## Requirements *(mandatory)*

### Research corpus & method (US1)

- **FR-001**: The feature MUST deliver a research corpus covering **both** the commercial frontier (at minimum OpenAI, Google/DeepMind, Anthropic, Microsoft, Meta, Amazon, Vercel, and notable agent startups) **and** the recent scholarly literature, each compared against AstralBody to identify where the frontier is ahead and what is worth adopting.
- **FR-002**: Every scholarly finding MUST cite a **primary** source (arXiv, peer-reviewed conference/journal, official standard, or first-party lab page); **no** Medium, listicle, or content-farm sources are permitted in the scholarly streams. Commercial findings MUST cite official vendor sources with preview-vs-GA status noted.
- **FR-003**: The corpus MUST be **consolidated and deduplicated** across streams into a single ranked backlog of capabilities, each with a stable ID, its source finding(s), a what/why-gap statement, an in-constraint implementation note, and **novelty/impact/effort** scores plus a cross-stream **consensus/confidence** indicator.
- **FR-004**: Every retained capability MUST be filtered through AstralBody's constraints (Python-only, **no new third-party runtime libraries**, the SDUI mandate, idempotent migrations, fail-closed) such that its implementation note does not violate them; capabilities that cannot be made to fit MUST be moved to an explicit **deferred/out-of-constraint** list with the portable-now sub-idea routed into an in-constraint capability.
- **FR-005**: The corpus MUST be **organized and ranked by the project's priority order** — novelty (paramount) → user experience → device adaptation → agentic security — and MUST include a recommended **wave sequencing** whose rationale reconciles "invest deepest in novelty" with "sequence low-effort convergent enablers first."
- **FR-006**: The corpus MUST include a **"do not regress"** list of capabilities where AstralBody is already at or above the frontier, and MUST flag vendor hype, unverifiable benchmark claims, preview-vs-GA status, and any source-extraction caveats rather than presenting them as fact.
- **FR-007**: The corpus MUST be self-contained in this feature's `research/` folder (per-stream findings files + a cross-stream synthesis) and MUST be human-readable by a non-specialist stakeholder for the executive-summary and sequencing portions.

### Capability-roadmap definition & gating (cross-cutting)

- **FR-008**: The roadmap MUST group consolidated capabilities into **independently shippable initiatives** mapped to the four priority dimensions, each describing the capability behavior in terms that are testable without prescribing internal implementation beyond the constraint envelope.
- **FR-009**: Branch 033 MUST ship **research + roadmap only — zero product/implementation code**. Implementation of every capability is delivered as its own approved follow-on feature branch; no implementation begins until the user grants permission to open those specs. The roadmap MUST designate the **co-flagship trio (US2 generative UI + US3 self-improving agent architecture + US4 living memory)** as the first follow-on initiatives, each pulling in the Wave-0 enablers it depends on, with selection biased toward the highest-novelty structural bets.
- **FR-010**: Each capability MUST, when implemented, be **flag-gated and fail-open** to AstralBody's current behavior, introduce **zero new third-party runtime dependencies**, ship behind **idempotent guarded migrations** for any schema delta, and meet the constitution's production-ready + ≥90% changed-code-coverage bar.
- **FR-011**: The roadmap MUST sequence each **security capability that guards a specific autonomy increase** (sandboxed codegen, adversarial red-team self-test, memory-poisoning defense, multi-agent-system defenses) to ship **with or before** the capability it protects, regardless of the security tier's overall lower investment priority.
- **FR-012**: The roadmap MUST preserve AstralBody's existing differentiators (adaptive UI designer layout intelligence, in-process self-test, hash-chained audit, deterministic PHI gate, RFC 8693 delegated scopes, agentic creation, persistent workspace, cross-session memory) — capabilities are depth/contract improvements on these, never parallel reimplementations.

### Flagship generative model-grounded UI (US2)

- **FR-013**: For component-rich turns, the system MUST be able to derive a **typed task/data model first** (entities, typed attributes, dependency edges) and derive the layout tree from it by deterministic attribute→primitive rules, persisted alongside the existing `workspace_layout` overlay (C-N1/C-N2 annotation rules).
- **FR-014**: The designer MUST be able to select among candidate arrangements via a **deterministic, pure-Python scoring function** (alignment, grouping, density, device-fit, effort proxies) — LLM proposes, scorer decides — replacing reliance on free-text self-critique as the sole judge (C-U1), with optional per-archetype priors (C-U3).
- **FR-015**: Layout adaptation MUST be **conservative**: a re-arrangement is applied only when its score beats the user's current persisted layout by more than a disruption-cost margin tied to a user predictability preference (C-U2).
- **FR-016**: Generated/garnish UI MUST pass a deterministic **dark-pattern/persuasion lint** (strip/downgrade false urgency, confirmshaming, destructive-CTA emphasis, preselected opt-ins) and MUST surface **provenance/uncertainty**, with entity facts in components gated to trace to a tool/search result (C-U6/C-U7), auditing any blocked pattern.
- **FR-017**: Any **open-ended/generative primitive** beyond the closed palette MUST be expressed as grammar-constrained structure validated by a post-validator and rendered through the escape-by-default sanitizer; a genuinely new primitive MUST ride the existing draft→self-test→admin-approval pipeline and MUST NOT render arbitrary unvalidated markup (C-N2).
- **FR-018**: Reliability foundations MUST be available to these loops: **enforced structured output** via the client's schema-constrained decoding with capability-probe + graceful fallback (C-N14), and a **two-tier tool/component output** split (model-visible digest vs render-only payload) so large/untrusted payloads render without entering the model context (C-N15).

### Self-improving agent architecture (US3)

- **FR-019**: Agentic creation MUST become **archive-conditioned**: store each draft's code + self-test score + gap fingerprint and feed top exemplars back into codegen, with a **cheap surrogate pre-score** that auto-refines likely-failing drafts before the costly self-test (C-N4).
- **FR-020**: The platform MUST provide a **trajectory-evaluation backbone** — an Agent-as-a-Judge over the existing audit/tool-dispatch trace, `pass^k` reliability self-tests, and order-swap-debiased judging — usable as the metric for every self-improving loop and as a regression gate (C-N5).
- **FR-021**: The orchestrator MUST support **multi-step self-correcting control** (a dual-ledger plan/progress loop with stall-counter replanning, C-N7) and **difficulty-gated multi-agent quality multipliers** (mixture-of-agents / pairwise debate, C-N9), both bounded and fail-open.
- **FR-022**: The platform MUST support **async parallel fresh-context fan-out** for list/high-volume tasks (isolated `VirtualWebSocket` sub-runs, bounded pool, per-child self-verification, controller aggregation) to defeat single-context degradation past ~8 items (C-N8).
- **FR-023**: The platform MUST be able to distill successful tool-call traces into **self-verified, parameterized procedural recipes** retrievable for similar future turns and replayed under the existing scopes + audit (C-N10), and use idle time for **anticipatory sleep-time precompute** (C-N11).

### Living memory & personalization (US4)

- **FR-024**: Consolidation MUST use an **LLM-mediated write path** (ADD/UPDATE/DELETE/NOOP) that supersedes contradicted memories (soft-delete + `superseded_by`, retained for audit) instead of monotonic accumulation, with **temporal validity** intervals and an **abstention/clarify** branch on conflict or low confidence (C-M1/C-M6).
- **FR-025**: Memory MUST support **self-organizing linked notes** whose interpretation evolves as new memories arrive (C-M2) and **graph/Personalized-PageRank associative retrieval** plus **multi-signal ranking** (recency × importance × relevance) — all on Postgres + the existing LLM client with **no vector DB** (C-M3/C-M4).
- **FR-026**: Memory MUST support **principled decay/forgetting** (reinforcement-on-recall + safety-triggered forgetting that doubles as PHI/data minimization, C-M7), an **evolving optimizable per-user persona** refined from recent turns and feedback (C-M8), and a **user-facing provenance/edit/forget** surface with genuine deletion (C-M9).
- **FR-027**: The memory machinery MAY be surfaced proactively as a **card-grid digest** produced by the dreaming sweep and as **conversationally-scheduled tasks** with model-proposed schedule confirmation and push/email via the egress-gated HTTP path (C-U8), and MAY be **project/namespace-scoped** (C-U9).

### Device adaptation & multimodal reach (US5)

- **FR-028**: ROTE MUST support **capability negotiation**: each renderer target declares its supported primitive vocabulary + contract version; ROTE filters/substitutes unsupported components via a deterministic fallback ladder, driven by a per-target **declarative host-config** dict rather than per-type code branches (C-D1/C-D2).
- **FR-029**: Device adaptation MUST become a **weighted multi-objective scorer** (width-fit, interaction-cost, glanceability, speakability, info-density) that also feeds the connecting target's objective weights into the UI-designer loop so arrangement is **device-aware** (C-D3), optionally with an LLM-judged suitability cost, fail-open.
- **FR-030**: ROTE MUST gain a real **structured VOICE renderer** (SSML + navigable axis→series→point/header→rows tree + three verbosity tiers + deterministic earcon/sonification tokens) and SHOULD add an **AOM-style semantic-tree renderer**, each as a new orchestrator renderer with primitives unchanged (C-D4/C-D5).
- **FR-031**: The orchestrator MUST support a **device-capability-aware model router** in front of the client factory (cheap-first cascade, escalate on low confidence), with an optional on-device browser-AI lane that remains server-authoritative and falls back automatically (C-D6); and a **live viewport/theme/context feedback loop** that re-adapts the current canvas on change (C-D7).
- **FR-032**: Rendering MUST be able to enforce **accessibility as a constraint** (WCAG-by-construction HTML, a designer-side WCAG checklist + deterministic post-validator, and ability profiles for low-vision/motor/reduced-motion/cognitive-load) and a **tiered level-of-detail ladder** with per-surface modality routing (C-D9/C-D10).

### Preventive agentic security (US6)

- **FR-033**: Untrusted-ingest flows (`fetch_page`, `summarizer`, auto-created parsers) MUST be routed to the **minimal security-by-construction pattern** (context-minimization/action-selector for read-only; plan-then-execute for multi-tool with refusal of out-of-plan calls; map-reduce for parsing) so ingested untrusted input cannot trigger consequential actions (C-S1).
- **FR-034**: The orchestrator MUST maintain a **taint/provenance graph** (effective trust = minimum over data ancestors) and enforce a **value-level data-flow policy** that refuses untrusted-tainted values reaching write/egress sinks, surviving multi-hop laundering (C-S2).
- **FR-035**: A single **deterministic pre-action policy engine** (trigger/predicate/enforcement: allow/deny/confirm/rewrite) MUST authorize every tool call fail-closed before execution, with the existing PHI gate and scope check expressed as seed rules and admin-extensible rules stored as data, each decision audited (C-S3); the pre-execution **plan MUST be persisted to the audit chain** so intended-vs-actual deviation is detectable (C-S12).
- **FR-036**: Untrusted spans entering any model prompt MUST be **spotlighted/datamarked** (per-turn sentinel + token marking), and a **runtime supervisor** MUST review draft outputs/tool-call intent before delivery (revise/block/escalate) (C-S4/C-S5).
- **FR-037**: Generated agent/parser code MUST execute **sandboxed** (resource-limited child process, blocked sockets, temp-scoped filesystem, mediated cross-agent/egress), and the self-test MUST gain an **adversarial red-team pass** plus an **AstralDojo CI suite** asserting zero out-of-scope tool calls / egress / PHI emission (C-S6/C-S7).
- **FR-038**: Delegation MUST gain **single-use transaction tokens** bound to `(agent, user, tool, hash(args))` via the existing HMAC and a first-class **agent identity** claim, with third-party tokens partitioned by {agent, user} (C-S8); the memory feature MUST be hardened against **poisoning** (refuse untrusted-derived durable consolidation without human confirm, integrity-sign rows, trust-filter retrieval) (C-S9); and consequential/irreversible actions MUST require a **provenance-showing human confirmation** (C-S11).
- **FR-039**: Any multi-agent flow introduced by US3 MUST ship with **multi-agent-system attack defenses** (inter-agent message provenance/integrity over the audit chain, per-edge scoping, a TAMAS-style red-team suite) (C-S14), and the security posture MUST be tracked against an **OWASP ASI01–ASI10 coverage matrix** (C-S12).

### Key Entities *(include if feature involves data)*

- **Research Stream**: One per-domain findings file (e.g. commercial-openai, scholarly-agentic-security) containing raw findings with sources, gap analysis, priority mapping, in-constraint implementation notes, and novelty/impact/effort scores.
- **Finding**: A single frontier technique observed in one stream, with its primary source(s), what-it-is, frontier evidence, AstralBody gap, priority, implementation note, and scores. ~164 across the corpus.
- **Consolidated Capability**: A deduplicated, cross-stream-merged unit with a stable `C-*` ID, contributing finding(s), priority-dimension tier, novelty/impact/effort, consensus/confidence indicator, and dependencies. 71 in the synthesis. The atomic unit of the roadmap.
- **Priority Dimension**: One of {novelty, user experience, device adaptation, agentic security}, the ranking axis ordered per the user's stated priority.
- **Capability Initiative (User Story)**: An independently shippable grouping of consolidated capabilities mapped to a priority dimension (Stories 2–6).
- **Wave**: A sequencing bucket (0–5) ordering initiatives by dependency + risk-adjusted leverage while honoring the priority order for investment depth.
- **Constraint Envelope**: The non-negotiable filter (Python-only, no-new-deps, SDUI mandate, idempotent migrations, fail-closed) every retained capability and its implementation note must satisfy.
- **Approval Gate**: The explicit user go-ahead that must precede execution of any implementation wave; the default first slice is Wave 0 + the Wave 1 flagship core.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The corpus covers **100%** of the named commercial vendors (OpenAI, Google/DeepMind, Anthropic, Microsoft, Meta, Amazon, Vercel) plus notable startups, and the five scholarly domains (agentic frameworks, generative/adaptive UI, memory/personalization, agentic security, device adaptation), each compared against AstralBody — verifiable by the eight stream files plus the synthesis.
- **SC-002**: The corpus yields **at least 60 consolidated, deduplicated capabilities** (achieved: 71) spanning all four priority dimensions, each with a stable ID, ≥1 primary-source citation, novelty/impact/effort scores, and a consensus indicator.
- **SC-003**: **100%** of scholarly findings cite a primary venue/standard, with **zero** Medium/listicle/content-farm sources in the scholarly streams (commercial streams cite official vendor sources with preview-vs-GA status).
- **SC-004**: **100%** of retained capabilities carry an implementation note that respects the constraint envelope; every capability that does not fit is on the explicit deferred/out-of-constraint list with a portable-now sub-idea routed into an in-constraint capability.
- **SC-005**: The synthesis ranks capabilities by the priority order and presents a recommended **wave sequencing** with stated rationale, plus a **"do not regress"** list and a **hype/caveats** log.
- **SC-006**: At least the **convergent** capabilities (those surfaced independently by ≥3 streams) are explicitly identified as the highest-confidence signals and concentrated in the earliest waves.
- **SC-007**: A non-specialist stakeholder can read the synthesis executive summary, the prioritized backlog, and the sequencing, and from them name the top novelty, UX, device, and security moves and the recommended first slice — without reading any source paper.
- **SC-008**: For each implementation initiative (Stories 2–6), the spec states an **independently testable** acceptance condition that requires no other initiative to be implemented, and a flag-gated, fail-open, no-new-dependency delivery posture — so any single initiative can be approved and shipped on its own.
- **SC-009**: No implementation work begins, and no product behavior changes, until the user grants explicit approval; the spec/plan/tasks define and sequence the work without authorizing its execution.
- **SC-010**: Every implemented capability (once approved) introduces **zero** new third-party runtime dependencies, ships any schema change as an idempotent guarded migration, fails open to current behavior on any LLM-assisted-step failure, and meets ≥90% changed-code coverage — verifiable per follow-on PR against the constitution's CI gates.

## Assumptions

- **Research-first scope**: The committed deliverable of this feature is the research corpus + the prioritized roadmap (already produced in `research/`). Implementation is real but **approval-gated and phased**, with later waves delivered as their own feature branches; the exact first-slice boundary is confirmed at `/speckit-clarify`.
- **Constraint envelope is binding**: Python-only backend, **no new third-party runtime libraries**, the SDUI mandate (astralprims defines → orchestrator renders → ROTE adapts), idempotent guarded startup migrations, and the fail-closed posture are treated as inviolable; capabilities needing a new dependency or hardware are deferred, not smuggled in.
- **Priority order governs investment depth, not blind ordering**: novelty is paramount and gets the deepest investment, but low-effort, high-confidence convergent enablers (structured output, context engineering, the eval backbone) are sequenced first because they de-risk and measure the novel work.
- **Existing differentiators are reused, not rebuilt**: the adaptive UI designer, in-process `VirtualWebSocket` self-test, hash-chained audit, deterministic PHI gate, RFC 8693 delegation, agentic creation, persistent workspace, and cross-session memory are the substrate every capability extends.
- **The model behind `_call_llm` is provider-flexible**: structured-output, reasoning-budget, tool-choice, and (where present) hosted-tool/grounding/caching capabilities are accessed via the existing OpenAI-compatible client with a capability-probe + graceful fallback, never by importing a vendor SDK.
- **Memory stays on Postgres**: all memory/personalization capabilities are designed for Postgres + the existing LLM client (embeddings computed via that client or simple methods) — **no vector database** is introduced.
- **Fail-open everywhere**: every LLM-assisted capability degrades to AstralBody's current behavior on timeout/model-error/invalid-output and logs the fallback, so adoption never reduces reliability of an existing flow.
- **Sources reflect a moving frontier**: products and papers cited are mid-2026 snapshots with preview-vs-GA status noted; exact model strings/benchmark numbers should be reconfirmed before being quoted in production, and vendor-internal metrics are treated as illustrative of mechanism, not as verified fact.
