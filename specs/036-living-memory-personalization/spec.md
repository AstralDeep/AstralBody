# Feature Specification: Living Memory & Proactive Personalization (co-flagship US4)

**Feature Branch**: `036-living-memory-personalization`
**Created**: 2026-06-16
**Status**: In progress
**Input**: Co-flagship initiative **US4** of the feature-033 roadmap, built novelty-forward. Source capabilities: `specs/033-frontier-techniques-research/` (`SYNTHESIS.md` §3.3; `research/scholarly-memory-personalization.md`).

## Overview

Move AstralDeep's memory/"soul" from store-and-summarize to **store, link, reconcile, and anticipate**. All capabilities are designed for the existing **PostgreSQL + the existing LLM client — no vector DB, no new dependency** — and are flag-gated and fail-open.

## Capabilities & status

| ID | Capability | Status | Notes |
|----|-----------|--------|-------|
| **C-M4** | **Multi-signal retrieval** — rank durable memory by a recency × importance × relevance composite (Generative Agents recipe) instead of a single signal | ✅ **done** | `backend/personalization/retrieval_scoring.py` + wired into `memory_tools.memory_search`. Importance reuses the existing `salience` column (source-based floor otherwise) → **no schema change**. Flag `FF_MEMORY_MULTISIGNAL` (default on), fail-open to legacy overlap rank. Tests: `tests/test_retrieval_scoring.py` (12 cases). |
| C-M1 | **Reconcile-don't-append write path** — LLM-mediated ADD/UPDATE/DELETE/NOOP with supersession (soft-delete + `superseded_by`) | ⏳ next | The biggest memory gap; needs a guarded migration (`superseded_by`, `valid_from/valid_to`). |
| C-M2 | **Self-organizing linked memory notes + evolution** — keywords/tags/context/links; new memories rewrite neighbors' interpretation | ⏳ planned | Powers C-M3 graph retrieval. |
| C-M3 | **Graph / Personalized-PageRank associative retrieval** — multi-hop "connect-the-dots" recall, ~40 lines pure Python over Postgres edges | ⏳ planned | |
| C-M6 | **Temporal validity + contradiction resolution + abstention** | ⏳ planned | |
| C-M7 | **Principled decay / safety-triggered forgetting** — doubles as PHI/data minimization | ⏳ planned | |
| C-M8 | **Evolving optimizable persona** + feature-004 preference feedback | ⏳ planned | |
| C-N11 | **Sleep-time compute** — anticipatory precompute in the dreaming sweep | ⏳ planned | Reuses the scheduler. |
| C-S9 | **Memory-poisoning defense** — refuse untrusted-derived durable consolidation w/o human confirm; integrity-sign rows; trust-filter retrieval | ⏳ co-ship | Ships with/before the autonomous write paths it guards (FR-011). |

Full acceptance scenarios are in `specs/033-frontier-techniques-research/spec.md` (User Story 4). FR mapping: FR-024…FR-027 (+ FR-038 for C-S9).

## What C-M4 delivers (this increment)

Memory recall was single-signal: `repository.list_memory` orders by `created_at` (recency) and `memory_search` ranked by raw token overlap (relevance) — never combined. The Generative Agents recipe (Park et al., UIST 2023) combines **recency × importance × relevance**, which beats any single signal and is the canonical baseline. C-M4 adds a pure scoring core (each signal normalised to [0,1], renormalised weights) and wires it into `memory_search`: among relevant memories, recent and important ones now rank higher. **Importance reuses the existing `salience` column** (with a source-based floor — explicitly-remembered facts outrank auto-promoted ones), so there is **no schema change**. Recency is rank-based (timezone/format-robust). Flag-gated `FF_MEMORY_MULTISIGNAL` (default on); fail-open to the legacy overlap ranking on any error.

### Acceptance (this increment)

1. **Given** a recent, lower-overlap memory and an older, higher-overlap one, **When** searched with the composite on, **Then** the recent+relevant memory can rank above the higher-overlap older one (verified).
2. **Given** the flag off, **Then** legacy overlap-only ranking is intact.
3. **Given** an empty query, **Then** recency order is returned unchanged.
4. Each signal (recency rank, overlap relevance, salience/source importance) and the composite are unit-tested incl. clamping and zero-weight edges.

## Constraints & posture

- **No new third-party runtime libraries; no vector DB; no schema change** in this increment (importance via the existing `salience` column). Later capabilities (C-M1/C-M6) add guarded idempotent migrations.
- **Fail-open**: any scoring error reverts to the legacy ranking.
- **PHI posture preserved**: retrieval scoring does not change the PHI gate; C-M7/C-S9 strengthen it.
- **Tests**: ≥90% changed-code coverage.

## Assumptions

- The feature-033 corpus and roadmap define the capabilities and sequencing; this branch implements US4 incrementally, novelty-forward, the cheapest-big-win retrieval composite first.
- Larger capabilities (C-M1 reconcile path, C-M3 graph retrieval) land in their own follow-on branches with their guarded migrations.
