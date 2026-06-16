# Implementation Plan: Frontier Capabilities Research & Novel-Technique Roadmap

**Branch**: `033-frontier-techniques-research` | **Date**: 2026-06-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/033-frontier-techniques-research/spec.md`

## Summary

This is a **research-led, no-implementation-code** feature. Its deliverable is a primary-sourced, deduplicated, prioritized **corpus of novel techniques** drawn from the mid-2026 commercial AI frontier and the recent scholarly literature, compared against AstralBody to find where the frontier is ahead and what is worth adopting — plus a **prioritized implementation roadmap** that groups the consolidated capabilities into initiatives and sequences them into waves under the project's priority order (novelty → UX → device → security). The corpus already exists in [`research/`](research/) (eight primary-sourced stream files, ~164 findings) collapsed into 71 consolidated capabilities in [`research/SYNTHESIS.md`](research/SYNTHESIS.md). Per the clarifications, **branch 033 ships research + roadmap only — no product code**; implementation is delivered as approved follow-on feature branches, led by the co-flagship trio (US2 generative UI + US3 self-improving agent architecture + US4 living memory), selected novelty-forward. The "technical approach" of this feature is therefore a *research method + an artifact-quality contract*, not a code architecture.

## Technical Context

**Language/Version**: N/A for branch 033 (deliverables are Markdown research artifacts). The roadmap's *future* implementation envelope is Python 3.11+ (backend) under the SDUI mandate.
**Primary Dependencies**: None added. Research used the harness's web search/fetch + parallel sub-agents only. The roadmap mandates **zero new third-party runtime libraries** for every future capability (Constitution V).
**Storage**: N/A for 033 (no schema change). Future memory/security capabilities are designed for the existing PostgreSQL via `shared/database.py::_init_db` idempotent guarded migrations — **no new datastore, no vector DB**.
**Testing**: For 033, verification is artifact review against the Success Criteria (coverage, sourcing, dedup, scoring, constraint-fit). Future capabilities inherit the constitution's ≥90% changed-code coverage + pytest suites.
**Target Platform**: N/A for 033. Future targets are the existing orchestrator (`:8001`) + ROTE render targets (browser/tablet/mobile/watch/TV/voice).
**Project Type**: Research & roadmap (documentation deliverable) within an existing server-driven-UI agentic platform.
**Performance Goals**: N/A for 033. Roadmap notes per-capability bounds (e.g., bounded LLM passes with per-pass timeouts, fail-open) but sets no runtime SLO in this feature.
**Constraints**: The **constraint envelope** is the load-bearing technical context: Python-only backend, **no new third-party runtime libraries**, SDUI mandate (astralprims defines → orchestrator renders → ROTE adapts), idempotent guarded startup migrations, fail-closed posture. Every retained capability's implementation note must satisfy it; capabilities that cannot are on the deferred list with a portable-now sub-idea.
**Scale/Scope**: 8 research streams · ~164 raw findings · 71 consolidated capabilities · 6 user-story initiatives · 6 sequencing waves · 4 priority dimensions.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Branch 033 introduces **no product code, no dependency, no schema, no UI**, so it is structurally compliant. Each principle is evaluated for (a) this branch and (b) the roadmap's binding constraints on future work:

- **I. Primary Language (Python)** — 033: N/A (Markdown). Roadmap: every capability is Python-backend. **PASS.**
- **II. UI Delivery Architecture (SDUI)** — 033: N/A. Roadmap: the SDUI mandate is an explicit constraint on every UI/device capability (new renderers/ROTE extensions, primitives unchanged; generative primitives ride grammar+validator+sanitizer, never raw client rendering). **PASS.**
- **III. Testing Standards (≥90% changed-code)** — 033: no code to cover. Roadmap: FR-010/SC-010 carry the ≥90% gate to every follow-on. **PASS.**
- **IV. Code Quality (lint)** — 033: N/A. Roadmap: inherited per follow-on. **PASS.**
- **V. Dependency Management (no new 3rd-party without lead approval)** — 033: zero new deps. Roadmap: "no new third-party runtime libraries" is a first-class filter; out-of-constraint items (realtime voice transport, browser automation, on-device decoding) are explicitly deferred as separate approvals. **PASS.**
- **VI. Documentation** — 033: the corpus is itself documentation; every capability cites sources and an implementation note. **PASS.**
- **VII. Security (Keycloak, RFC 8693, no secrets)** — 033: no secrets, no auth change. Roadmap: the security tier *strengthens* this posture (transaction tokens extend RFC 8693; taint/provenance/policy-engine are additive). **PASS.**
- **VIII. User Experience (astralprims-driven)** — 033: N/A. Roadmap: UI capabilities compose existing primitives; new primitives go through the approval pipeline. **PASS.**
- **IX. Database Migrations (idempotent startup)** — 033: no schema change. Roadmap: every schema delta is an idempotent `_init_db` migration with a rollback note. **PASS.**
- **X. Production Readiness** — 033: a complete, reviewable artifact (no stubs). Roadmap: each follow-on must be production-ready before merge. **PASS.**
- **XI. Continuous Integration** — 033: docs-only change passes lint/build/test/coverage trivially (no changed code lines). Roadmap: the security tier *adds* an AstralDojo adversarial CI job (C-S7). **PASS.**

**Result: PASS — no violations, no Complexity Tracking entries required.** Re-checked post-Phase-1 design (data-model + contracts are artifact schemas, not code): still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/033-frontier-techniques-research/
├── spec.md                         # Feature spec (research + roadmap)
├── plan.md                         # This file
├── research.md                     # Phase 0: method + resolved planning decisions
├── data-model.md                   # Phase 1: research/roadmap entities
├── quickstart.md                   # Phase 1: how to navigate the corpus + spin up a follow-on
├── contracts/
│   └── capability-record.md        # Phase 1: the schema/quality contract for a Finding + Consolidated Capability
├── tasks.md                        # Phase 2 (/speckit-tasks): finalize-corpus + structure-roadmap tasks
└── research/                       # THE DELIVERABLE (already produced)
    ├── SYNTHESIS.md                # Cross-stream dedup, 71 consolidated capabilities, waves, do-not-regress, hype log
    ├── commercial-openai.md        # 17 findings
    ├── commercial-google.md        # 24 findings
    ├── commercial-others.md        # 25 findings (Anthropic/MS/Meta/Amazon/Vercel/startups)
    ├── scholarly-agentic-frameworks.md   # 20 + 8 findings
    ├── scholarly-generative-ui.md        # 21 findings
    ├── scholarly-memory-personalization.md # 18 findings
    ├── scholarly-agentic-security.md     # 19 findings
    └── scholarly-device-adaptation.md    # 20 findings
```

### Source Code (repository root)

**No source-code changes in branch 033.** The existing structure is unchanged; it is reproduced here only to anchor *where the roadmap's future capabilities land* (each in its own follow-on feature branch):

```text
backend/
├── orchestrator/        # future: ui_designer (US2 task-model + scorer), agent_graph/judge/policy-engine (US3/US6), workspace, web_auth
├── agents/              # future: web_research / summarizer / parser hardening (US6 by-construction patterns)
├── rote/                # future: capability negotiation, host-config, VOICE/AOM renderers, model router (US5)
├── webrender/           # future: renderers + chrome surfaces (US2/US4/US5)
├── shared/              # future: database._init_db migrations, external_http (egress), audit
└── <module>/tests/      # future: per-capability unit/integration + AstralDojo CI suite (US6)
```

**Structure Decision**: Branch 033 is documentation-only; all artifacts live under `specs/033-frontier-techniques-research/`. The roadmap maps each capability to an existing backend module (above) so follow-on specs have a clear home, but creates nothing in `backend/` on this branch.

## Phase 0 — Research (already executed)

The research *is* the feature; Phase 0 is complete and recorded in [`research.md`](research.md) and the eight `research/*.md` streams + `research/SYNTHESIS.md`. There are **no open NEEDS CLARIFICATION** items: the four scope/priority clarifications were resolved with the user (see spec Clarifications and `research.md`). Method: eight parallel domain analysts (commercial × 3, scholarly × 5) running web search/fetch against a shared AstralBody baseline + constraint envelope, each emitting a structured findings file; a cross-stream synthesis then deduplicated to 71 consolidated capabilities and sequenced them into waves.

## Phase 1 — Design & Contracts (artifact schemas)

Because the deliverable is a corpus, "design" means the **schema and quality contract** of the corpus, captured in:
- [`data-model.md`](data-model.md) — the entities (Research Stream, Finding, Consolidated Capability, Priority Dimension, Capability Initiative, Wave, Constraint Envelope, Approval Gate) and their fields/relationships.
- [`contracts/capability-record.md`](contracts/capability-record.md) — the required shape of a per-stream Finding record and a Consolidated Capability record (the "interface" every entry in the corpus must satisfy), plus the acceptance checks that map to the spec's Success Criteria.
- [`quickstart.md`](quickstart.md) — how a reviewer navigates the corpus and how a maintainer spins a consolidated capability up into an approved follow-on implementation spec.

Agent context: branch 033 changes no runtime tech, so the auto-generated CLAUDE.md "Active Technologies / Recent Changes" require no new entry; the SPECKIT plan reference (if markered) points here.

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
