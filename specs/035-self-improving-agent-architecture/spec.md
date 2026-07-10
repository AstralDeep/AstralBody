# Feature Specification: Self-Improving Agent Architecture (co-flagship US3)

**Feature Branch**: `035-self-improving-agent-architecture`
**Created**: 2026-06-16
**Status**: In progress
**Input**: Co-flagship initiative **US3** of the feature-033 roadmap, built novelty-forward. Source capabilities: `specs/033-frontier-techniques-research/` (`SYNTHESIS.md` §3.1; `research/scholarly-agentic-frameworks.md`, `research/commercial-others.md`, `research/commercial-google.md`).

## Overview

Upgrade AstralDeep's most distinctive feature — agentic creation — from one-shot to **self-improving**, and give the orchestration layer the frontier's measurement + control machinery. Every self-improving loop is graded by a new **trajectory-evaluation backbone**, so improvement is measurable rather than asserted. All work respects the constraint envelope (Python-only · no new third-party runtime libraries · idempotent migrations · fail-closed) and is flag-gated and fail-open.

## Capabilities & status

| ID | Capability | Status | Notes |
|----|-----------|--------|-------|
| **C-N5** | **Trajectory-evaluation backbone** — ADK/Vertex-style tool-sequence metrics (exact / in-order / any-order / precision / recall / single-tool) + a weighted aggregate + τ-bench `pass^k` reliability | ✅ **done** | `backend/orchestrator/agent_eval.py` — pure, dependency-free, no LLM required. Tests: `test_agent_eval.py` (14 cases). The metric every loop below optimises. |
| C-N4 | **Evolutionary, archive-conditioned auto-create + surrogate pre-score** — archive each draft's code + self-test score + gap fingerprint; condition codegen on top exemplars; cheap LLM rubric pre-scores a draft before the costly `VirtualWebSocket` self-test; self-test becomes `pass^k` | ⏳ next | Consumes C-N5 (`pass_k_from_outcomes`, `score_trajectory`). The flagship upgrade. |
| C-N7 | **Dual-ledger self-correcting orchestration** — Task Ledger + per-step Progress Ledger JSON + stall-counter replanning | ⏳ planned | Pure prompt + two dicts + a counter over `_call_llm`. |
| C-N8 | **Async parallel fresh-context fan-out** — user-launchable concurrent background sub-runs, each an isolated `VirtualWebSocket` with a clean context; controller scatter → self-verify → gather | ⏳ planned | Fixes >8-item context degradation. |
| C-N9 | **Mixture-of-agents / debate for hard turns** — difficulty-gated propose→aggregate / pairwise debate | ⏳ planned | |
| C-N10 | **Procedural / skill memory** — distill successful tool traces into self-verified, parameterized recipes | ⏳ planned | Overlaps US4; replay under existing scopes + audit. |
| C-S14 | **Multi-agent-system attack defenses** — inter-agent provenance/integrity + per-edge scoping + a TAMAS-style red-team suite | ⏳ co-ship | Ships with/before the C-N8/C-N9 multi-agent flows it guards (FR-011). |

Full acceptance scenarios for the initiative are in `specs/033-frontier-techniques-research/spec.md` (User Story 3). FR mapping: FR-019…FR-023 (+ FR-039 for C-S14).

## What C-N5 delivers (this increment)

AstralDeep's self-test checks *that* a new agent runs, and component-feedback is user-facing — there is **no automated measure of an agent run's quality** beyond a single pass/fail, and self-tests are single-shot (`pass^1`), which masks flakiness (τ-bench shows SOTA agents with `pass^1`≈50% drop below `pass^8`≈25%). C-N5 ships the deterministic backbone: pure functions that score a **tool-call trajectory** against a reference (the six named ADK/Vertex metrics), a weighted aggregate (the single number a loop optimises), and the τ-bench `pass^k` estimator (`C(c,k)/C(n,k)`) for reliability. It is dependency-free and requires no LLM — an LLM judge may layer on top, but the deterministic gate never depends on model availability. Intended consumers: the evolutionary auto-create loop (C-N4), a `pass^k`-gated self-test, and a regression harness over the existing hash-chained audit/tool-dispatch trace.

### Acceptance (this increment)

1. **Given** a predicted and a reference tool sequence, **Then** each of the six metrics returns its defined value (exact/in-order/any-order/precision/recall/single-tool), verified across order-sensitive, subsequence, subset, and empty cases.
2. **Given** counts of trials/successes, **When** `pass^k` is computed, **Then** it equals the unbiased `C(c,k)/C(n,k)` estimator, returns 0 below `k` successes/trials, and validates its inputs.
3. **Given** a partial score dict, **When** aggregated, **Then** weights renormalise over the present metrics to a clean [0,1].

## Constraints & posture

- **No new third-party runtime libraries**; stdlib `math.comb` only. **No schema change** in this increment.
- **Fail-closed / deterministic**: the eval gate is pure and never depends on an LLM; downstream loops remain fail-open.
- **Tests**: ≥90% changed-code coverage; metric edge cases + validation paths all covered.

## Assumptions

- The feature-033 corpus and roadmap define the capabilities and sequencing; this branch implements US3 incrementally, novelty-forward, the eval backbone first because every later loop (C-N4/C-N7/C-N9) optimises against it.
- Larger capabilities (C-N8 fan-out) may land in their own follow-on branch if a single branch would exceed a reviewable, production-ready PR.
