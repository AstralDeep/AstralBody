# Feature Specification: Security-Benchmark Harness — ASB / AgentDojo Against the Trust Envelope

**Feature Branch**: `047-security-benchmark-harness`
**Created**: 2026-07-02
**Status**: Draft
**Input**: User description: "Stand up the ASB/AgentDojo harness against your existing gate (start Direction B) — first ASR numbers are the fastest proof-of-progress you can show." (Item 3 of [THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md) §8; Direction B of §3.)

## Overview

The thesis's weakest chapter is evaluation: the qualifying exam admits deterministic pass/fail is insufficient and static analysis is evadable (TP-009/010). Direction B converts that weakness into the strongest, most defensible result by measuring the trust envelope against **standard, automated adversarial agent-security benchmarks** — **AgentDojo** (97 tasks / 629 injection cases), **Agent Security Bench (ASB)** (16 attacks × 11 defenses × 10 scenarios), and **InjecAgent** — and reporting **Attack Success Rate (ASR)** with and without each layer of Astral's defense (DAF delegation + scope enforcement, PHI gate, the red-team scope/egress checks, and the future LLM-as-judge). The first ASR numbers are the fastest credible proof-of-progress for the committee and require no human subjects.

This feature stands up a **benchmark harness** that adapts these external suites to drive Astral's orchestrator through its real dispatch + permission path, records per-case outcomes, and produces an **ASR results table** with defense-ablation columns. It is measurement infrastructure and reporting; it does **not** modify the enforcement behavior it measures (the LLM-as-judge defense itself is a separate build — this harness measures it once it exists, and measures the envelope without it now). Because benchmark corpora and any test-only runners are evaluation-side, the product runtime gains **no new third-party dependency** (Constitution V); benchmark packages are dev/test-only, isolated behind an adapter, and never imported by product code.

## Clarifications

### Session 2026-07-02 (resolved by informed default — confirm or override during `/speckit-clarify`)

- Q: Do the external benchmark packages (AgentDojo, ASB, InjecAgent) become product dependencies? → A: No. They are **test/eval-only**, isolated in a dedicated harness area with its own dependency manifest, invoked by the harness runner, and never imported by `backend/orchestrator`, `backend/agents`, or `backend/shared`. Constitution V (no new product runtime deps) holds; the harness's own tooling is confined to the eval side exactly as the 032 verification harness did.
- Q: In-process, external, or both? → A: **In-process is the CI-gating default** (drive the orchestrator through the client-factory LLM seam like the 032 harness, so tool selection is scriptable and every real gate — token exchange, scope check, PHI gate, red-team verdict, audit chaining — runs); an **external/live** mode against the deployed sandbox is opt-in and non-gating. Both share one harness core.
- Q: What is an "attack success" — who adjudicates it? → A: A **deterministic** adjudication per benchmark: success = the injected/adversarial objective's observable effect occurred (a forbidden tool was invoked, exfiltration egress fired, an out-of-scope action completed, PHI left the boundary) as defined by that benchmark's ground truth, mapped onto Astral's tool-call and audit trace. No model call decides pass/fail; an optional LLM-judge enriches diagnosis only.
- Q: Which model runs under test? → A: Runs are **model-parameterized and recorded**. ASR is only comparable within a fixed (model, benchmark, harness-version) triple, so every results row records all three. The gating CI run uses a pinned, low-cost configuration; headline thesis numbers may use a stronger model — each is labeled.
- Q: Defense ablation granularity? → A: Report ASR for at least: (0) **no envelope** baseline (gates bypassed), (1) **scopes + DAF** only, (2) **+ PHI gate**, (3) **+ red-team scope/egress verdict**, (4) **+ LLM-as-judge** (once it exists). Each layer is toggled independently so its marginal ASR reduction is attributable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce first ASR numbers against the current envelope (Priority: P1)

Sam runs the harness over AgentDojo's injection suite driving Astral's real orchestrator, and gets a results table: ASR with the envelope off vs. on, per attack category, with the total injection-case count — the first quantified security result the thesis can show.

**Why this priority**: "First ASR numbers are the fastest proof-of-progress." One credible table converts the evaluation chapter from prose-of-intent to measured-result and de-risks the whole of Direction B.

**Independent Test**: Execute the harness in in-process mode over the AgentDojo case set; confirm it emits a results artifact reporting ASR (envelope off, envelope on) with per-category breakdown and case counts, reproducibly (same seed/model → same numbers).

**Acceptance Scenarios**:

1. **Given** the AgentDojo suite adapted onto the orchestrator, **When** the harness runs with the envelope **disabled**, **Then** it records a baseline ASR per attack category and overall, with the exact number of cases attempted and succeeded.
2. **Given** the same suite, **When** the harness runs with the envelope **enabled** (scopes + DAF + PHI + red-team verdict), **Then** it records the post-defense ASR and the reduction versus baseline, over the identical case set.
3. **Given** a completed run, **When** the results artifact is produced, **Then** it names the model, benchmark version, harness version, seed, and per-case outcomes so any number is reproducible and auditable.
4. **Given** a re-run with the same inputs, **When** compared, **Then** deterministic-adjudication outcomes match (any residual nondeterminism is confined to model output and is reported as a reliability band, not hidden).

---

### User Story 2 - Attribute ASR reduction to each defense layer (ablation) (Priority: P1)

Sam runs the harness with each defense layer toggled independently, producing an ablation table that shows the marginal ASR reduction contributed by DAF/scopes, the PHI gate, and the red-team verdict — so the thesis can claim *which* mechanism stops *which* class of attack, not just that the bundle helps.

**Why this priority**: A single on/off number invites "which part did the work?" The ablation is what turns the result into a defensible mechanistic claim and directly supports the DAF (A) and envelope (B) contributions.

**Independent Test**: Run the ablation matrix over one benchmark; confirm each layer can be enabled/disabled independently and the table reports per-layer marginal ASR deltas that sum coherently to the full-envelope reduction.

**Acceptance Scenarios**:

1. **Given** independently toggleable layers, **When** the ablation matrix runs, **Then** ASR is reported for the no-envelope, scopes+DAF, +PHI, and +red-team configurations over the same cases.
2. **Given** the ablation table, **When** read, **Then** each layer's marginal contribution is attributable to attack categories (e.g., DAF/scopes suppress out-of-scope-tool attacks; PHI gate suppresses data-exfiltration-of-PHI), matching the mechanism each layer implements.
3. **Given** the LLM-as-judge layer is not yet built, **When** the harness runs, **Then** its column is present but explicitly marked "not implemented," and the table is valid without it — the harness measures it automatically once the flag exists.

---

### User Story 3 - Cover ASB and InjecAgent through the same harness core (Priority: P2)

The harness generalizes beyond AgentDojo: ASB's attack × defense × scenario grid and InjecAgent's cases run through the same adapter and adjudication core, so the thesis reports ASR across multiple independent benchmarks rather than a single suite.

**Why this priority**: Multiple benchmarks agreeing is far more convincing than one; ASB in particular reports headline ASR up to ~84% for undefended agents, giving a strong "before" against which the envelope's reduction is visible. P2 because one benchmark (Story 1) is already a shippable result.

**Independent Test**: Run ASB and InjecAgent through the harness; confirm each yields an ASR table in the same schema as AgentDojo's, and that adding a benchmark required only a new adapter, not changes to the adjudication or reporting core.

**Acceptance Scenarios**:

1. **Given** the ASB grid, **When** run, **Then** results are reported per (attack, scenario) with the envelope ablation columns, in the shared results schema.
2. **Given** InjecAgent cases, **When** run, **Then** results are reported in the same schema.
3. **Given** the three benchmarks, **When** their results are assembled, **Then** a cross-benchmark summary states envelope ASR reduction per benchmark with case counts, and no benchmark package is importable from product runtime code (dependency-isolation check passes).

---

### User Story 4 - Gate CI on the harness without flaking on models or networks (Priority: P2)

A pinned, low-cost in-process configuration runs in CI as a merge-relevant check so envelope regressions (an ASR increase) are caught, while live-model/live-network runs stay opt-in.

**Why this priority**: The envelope is the thesis; a silent regression that raises ASR must not merge. Mirrors the 032 harness's CI posture (deterministic in-process gates CI; live path is manual).

**Independent Test**: Trigger CI on a branch that weakens a gate; confirm the harness detects the ASR increase and fails the check; confirm the live/external mode is not required for merge.

**Acceptance Scenarios**:

1. **Given** the pinned in-process config, **When** CI runs, **Then** the harness executes a bounded case subset within the CI budget and reports ASR against a recorded threshold.
2. **Given** a regression that raises ASR above threshold, **When** CI runs, **Then** the check fails with the offending cases named.
3. **Given** live-model/live-network flakiness, **When** CI runs, **Then** the external mode is skipped (opt-in only) and never blocks merges.

### Edge Cases

- A benchmark expects tools/capabilities Astral lacks → the adapter maps to the nearest Astral tool or marks the case **out-of-corpus** (excluded from ASR denominator, reported separately) rather than silently counting it as a pass or fail.
- The scripted/in-process model can't realistically be "tricked" (too deterministic to exhibit the vulnerable behavior) → the harness distinguishes "attack blocked by the envelope" from "attack never attempted because the model didn't take the bait"; only the former counts as a defense success, preventing inflated ASR-reduction claims.
- Benchmark ground truth disagrees with Astral's notion of success (e.g., benchmark counts a tool *call* as success; Astral blocks at execution) → adjudication is defined at a stated point in the trace (attempt vs. effect) and applied consistently; the choice is documented per benchmark.
- Running adversarial corpora could persist injected content into memory/workspace → the harness runs under namespaced harness principals and tears down its data, and confirms no adversarial payload settles into real user memory (ties to the 036/memory-poisoning concern).
- PHI-category test content → synthetic only; the harness asserts the PHI gate engages on health-categorized cases and never requires real PHI (mirrors 032's medical-persona rule).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The harness MUST drive Astral's real orchestrator dispatch + permission path (token exchange, scope check, PHI gate, red-team verdict, audit chaining) — not a reimplementation — via the existing LLM client-factory seam for in-process runs.
- **FR-002**: The harness MUST adapt AgentDojo, ASB, and InjecAgent case sets onto Astral's tool/agent surface behind a per-benchmark **adapter**, sharing one adjudication + reporting core.
- **FR-003**: Attack-success adjudication MUST be **deterministic**, defined at a stated point in the tool-call/audit trace per benchmark, with no model call deciding pass/fail; an LLM-judge MAY enrich diagnosis only.
- **FR-004**: The harness MUST support independent toggling of defense layers — (0) none, (1) scopes+DAF, (2) +PHI gate, (3) +red-team verdict, (4) +LLM-as-judge — and report ASR for each configuration over identical case sets.
- **FR-005**: Every results row MUST record the (model, benchmark version, harness version, seed) tuple and per-case outcomes sufficient for reproduction.
- **FR-006**: The harness MUST distinguish "attack blocked by a defense" from "attack not attempted / model didn't take the bait," and count only genuine blocks toward ASR reduction.
- **FR-007**: The harness MUST emit a machine-readable results artifact (per-case JSON) **and** a human-readable ASR report (Markdown table with ablation columns and cross-benchmark summary), written to a gitignored, per-run-namespaced artifacts directory.
- **FR-008**: The harness MUST run under **namespaced harness principals**, use **synthetic** data only (especially for PHI-category cases), and tear down all data it creates, leaving no adversarial payload in real users' memory/workspace/history.
- **FR-009**: Benchmark packages and any harness-only tooling MUST be **eval/test-only**, isolated with their own manifest, and MUST NOT be importable from product runtime code; the product runtime MUST gain zero new third-party dependencies (Constitution V). An automated check MUST assert this isolation.
- **FR-010**: A pinned, bounded in-process configuration MUST be CI-runnable within budget and MUST fail when measured ASR exceeds a recorded threshold (regression gate); live-model/external runs MUST be opt-in and non-gating.
- **FR-011**: The harness MUST NOT modify the enforcement behavior under measurement; it observes and drives only. (The LLM-as-judge defense is built separately; this harness measures it.)
- **FR-012**: Out-of-corpus cases (capabilities Astral lacks) MUST be excluded from the ASR denominator and reported separately, never silently scored.

### Key Entities

- **Benchmark adapter**: per-suite translator mapping external cases (AgentDojo/ASB/InjecAgent) onto Astral's agent/tool surface and mapping their ground truth onto Astral's trace.
- **Adjudicator**: deterministic pass/fail decision over the tool-call/audit trace at a stated adjudication point.
- **Envelope configuration**: the set of enabled defense layers for a run (the ablation axis).
- **Run record**: (model, benchmark version, harness version, seed) + per-case outcomes; the reproducibility unit.
- **ASR report**: the human-readable results table with ablation and cross-benchmark summary — the thesis artifact.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The harness produces a reproducible AgentDojo ASR table (envelope off vs. on, per category, with case counts) — the first-ASR-numbers milestone — runnable by a single documented command.
- **SC-002**: An ablation table attributes marginal ASR reduction to DAF/scopes, PHI gate, and red-team verdict independently, over identical cases.
- **SC-003**: ASB and InjecAgent run through the same core and report in the same schema; a cross-benchmark summary exists.
- **SC-004**: The dependency-isolation check passes: no benchmark package is importable from `backend/orchestrator`, `backend/agents`, or `backend/shared`; product runtime dependency set is unchanged.
- **SC-005**: The CI gate fails on an injected envelope regression (ASR increase) and passes on the clean baseline, within the CI time budget.
- **SC-006**: Re-running any reported number with its recorded tuple reproduces it (deterministic adjudication; model nondeterminism reported as a band).
- **SC-007**: No harness run leaves adversarial content in real user data (verified teardown).

## Assumptions

- The external benchmarks are obtainable and licensed for research/eval use; if one is unavailable, the harness core and the other benchmarks still deliver SC-001…SC-002.
- The client-factory LLM seam used by the 032 harness is the supported injection point and remains available.
- The LLM-as-judge defense (Direction B item 2 / §9.2.4) is out of scope to *build* here; this harness provides the measurement slot and will report it when the flag lands.
- Transport benchmarking (WS vs SSE vs gRPC) and HIPAA audit-field conformance (Direction B items 3–4) are separate specs; this feature is the adversarial-ASR slice only.
- "ASR" denominators and adjudication points are defined per benchmark and documented; cross-benchmark comparisons respect those definitions rather than pooling naively.

## Dependencies & Sequencing

- **Fed by**: 045 (framing establishes Direction B as non-negotiable/parallel); the existing gate modules (`delegation.py`, `tool_permissions.py`, `personalization/phi_gate.py`, `redteam.py`) are the system under measurement; the 032 harness is the architectural precedent (in-process CI gate + opt-in live path + namespaced principals + gitignored artifacts).
- **Feeds**: the evaluation chapter; provides the measurement slot for the LLM-as-judge defense and the "before/after" numbers the DAF (A) and self-extension (D) chapters cite.
- **Sibling (not blocking)**: 048 (recursive delegation) — its enforcement property tests are unit-level; this harness is the system-level adversarial complement.
