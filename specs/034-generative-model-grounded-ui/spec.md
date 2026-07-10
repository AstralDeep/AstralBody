# Feature Specification: Generative, Model-Grounded Adaptive UI (co-flagship US2)

**Feature Branch**: `034-generative-model-grounded-ui`
**Created**: 2026-06-16
**Status**: In progress
**Input**: First follow-on implementation of the feature-033 roadmap — co-flagship initiative **US2**, built novelty-forward. Source capabilities: `specs/033-frontier-techniques-research/` (`SYNTHESIS.md` §3.1–§3.2; `research/scholarly-generative-ui.md`, `research/commercial-google.md`, `research/commercial-openai.md`).

## Overview

Move AstralDeep's UI generation from "arrange finished components" toward **"model the task, then render and adapt the UI"** — the single largest novelty+UX delta in the 033 corpus, and the project's signature SDUI thesis pushed to the frontier. All work respects the constraint envelope (Python-only · no new third-party runtime libraries · SDUI mandate · idempotent migrations · fail-closed) and is **flag-gated and fail-open** to today's behavior so adoption never reduces reliability.

This branch delivers the capabilities incrementally; each is independently testable and ships green against the constitution's ≥90% changed-code coverage gate.

## Capabilities & status

| ID | Capability | Status | Notes |
|----|-----------|--------|-------|
| **C-U1** | **Deterministic layout scorer** — pure-Python `score_arrangement` objective (anchor, headline, grid grouping, titled containers, texture runs, wall-of-components) so the **LLM proposes and code decides** which arrangement to keep | ✅ **done** | `backend/orchestrator/ui_designer.py` (`score_arrangement`, `scorer_enabled`, `design_round` keep-highest-score selection). Flag `FF_UI_DESIGNER_SCORER` (default on), fail-open. Tests: `backend/tests/test_ui_designer_scorer.py` (16 cases). |
| C-N14 | **Enforced structured output** — `response_format`/JSON-schema-constrained decoding threaded through `_call_llm` (capability-probe + graceful fallback) to remove the designer's JSON repair/retry loop | ⏳ next | The cheapest, highest-confidence enabler; unblocks C-N1. |
| C-N1 | **Task-model-first generation** — derive a typed task/data model (entities, typed attributes, dependency edges) first; map attributes → primitives by deterministic rules; persist alongside the `workspace_layout` overlay | ⏳ planned | The flagship novelty move. |
| C-U2 | **Conservative adaptation** — penalize redesign by edit-distance from the user's current persisted layout; re-arrange only when the score beats it by a disruption-cost margin | ⏳ planned | Builds on C-U1's score; cheap, high-UX. |
| C-U3 | **Interaction-archetype selection** — classify the turn {compare, monitor, explore, summarize, decide, form} and seed a layout prior + scorer weights | ⏳ planned | |
| **C-U7** | **Dark-pattern / persuasion-safety lint** — deterministic strip of manipulative garnish (false urgency, forced scarcity, confirmshaming); never touches `ref` tool output | ✅ **done** | `lint_arrangement` in `ui_designer.py`; flag `FF_UI_DESIGNER_LINT` (default on), fail-open. Tests: `test_ui_designer_lint.py` (11 cases). |
| C-U6 | **Provenance/uncertainty surfacing** — entity facts trace to a tool/search result; confidence/provenance badge | ⏳ planned | Trust-as-UX; also a security win. |
| C-N2 | **Gated generative primitives** — grammar-constrained structure + post-validator + escape-by-default sanitizer; genuinely new primitives ride the draft→self-test→admin-approval rail | ⏳ planned | Highest novelty; largest effort. |

Full acceptance scenarios for the initiative are in `specs/033-frontier-techniques-research/spec.md` (User Story 2). FR mapping: FR-013…FR-018.

## What C-U1 delivers (this increment)

The adaptive UI designer (feature 029) ran a bounded multi-round LLM loop and returned **whatever arrangement the conversation last settled on** (DONE / stable / keep-best) — its own DESIGN RULES (anchor, hierarchy, balance, titles, texture) were enforced *only* by the LLM's free-text self-critique, which the generative-UI literature (Draco/DracoGPT; Stanford *Generative Interfaces*) shows is unreliable and unmeasurable.

C-U1 adds a **pure-Python `score_arrangement(layout, *, ref_types, allowed_types)`** that turns those rules into a numeric objective, and makes `design_round` return the **highest-scoring** arrangement among the draft + refinements. `ref` leaves are scored by the real component type they place (so a table+chart pair is not mistaken for a same-type run). Strictly **fail-open**: any scoring error — or `FF_UI_DESIGNER_SCORER` off — reverts to the legacy last-wins selection, so the change can never reduce reliability. No schema change, no new dependency, no primitive change.

### Acceptance (this increment)

1. **Given** an LLM that drafts a well-structured arrangement (hero + grid of grouped components) then "improves" it into a worse flat stack, **When** the designer runs with the scorer on, **Then** the higher-scoring draft is returned (verified: `test_driver_scorer_keeps_higher_scoring_draft`).
2. **Given** the same sequence with `FF_UI_DESIGNER_SCORER=false`, **Then** legacy last-wins behavior is intact (`test_driver_scorer_off_is_legacy_last_wins`).
3. **Given** a scorer that raises, **When** the designer runs, **Then** it never crashes and falls back to last-wins (`test_driver_scorer_failure_is_fail_open`).
4. **Given** representative arrangements, **Then** the scorer deterministically ranks anchored/grouped/titled/varied layouts above flat/lonely/untitled/same-type-run layouts (unit tests).

## Constraints & posture

- **No new third-party runtime libraries**; pure Python over the existing dict-based layout model.
- **SDUI mandate** intact — the scorer operates on the validated layout tree *before* materialize/ROTE; primitives and renderers are unchanged.
- **Flag-gated + fail-open**: `FF_UI_DESIGNER_SCORER` (default on); every LLM-assisted/optional step degrades to current behavior on error.
- **Tests**: ≥90% changed-code coverage; golden path + flag-off + fail-open + edge cases all covered.

## Assumptions

- The feature-033 corpus and roadmap are the source of truth for capability definitions and sequencing; this branch implements US2 incrementally, novelty-forward, each capability paired with the enabler it depends on.
- Later capabilities (C-N1 task model, C-N2 generative primitives) may land in their own follow-on branches if a single branch would exceed a reviewable, production-ready PR.
