---
description: "Task list for feature 033 — Frontier Capabilities Research & Novel-Technique Roadmap"
---

# Tasks: Frontier Capabilities Research & Novel-Technique Roadmap

**Input**: Design documents from `/specs/033-frontier-techniques-research/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/capability-record.md ✓

**Tests**: No automated test tasks — this branch ships **research + roadmap only, no product code** (spec Clarifications D1). Verification is artifact review against `contracts/capability-record.md` (which maps each Success Criterion to a concrete inspection). Each *future* implementation capability carries its own tests in its own follow-on branch.

**Organization**: Tasks are grouped by user story. US1 (the corpus) is the MVP and is **complete**. US2–US6 are *roadmap-definition* tasks (define each initiative well enough to spin up later) — **not** implementation. Completed work is checked `[x]`; open finalization/handoff work is `[ ]`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1…US6 (user-story phases only)
- Exact file paths included.

## Path Conventions

All deliverables live under `specs/033-frontier-techniques-research/`. No `backend/` paths appear because branch 033 changes no source code.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch, folder, and the constraint brief every research stream depends on.

- [x] T001 Create feature branch `033-frontier-techniques-research` + `research/` folder + spec scaffold via `.specify/scripts/powershell/create-new-feature.ps1`
- [x] T002 Correct `.specify/feature.json` to point at `specs/033-frontier-techniques-research` (it was pinned to 032, which had mis-targeted plan setup) and restore the briefly-clobbered `specs/032-attachment-sdui-verification/plan.md` from git
- [x] T003 [P] Establish the **Constraint Envelope** brief (Python-only · no new third-party runtime libs · SDUI mandate · idempotent migrations · fail-closed) issued to every research stream, recorded in `specs/033-frontier-techniques-research/plan.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The record contract + source rules + baseline that ALL streams must satisfy.

**⚠️ CRITICAL**: No stream findings are valid until these are fixed.

- [x] T004 Define the Finding + Consolidated-Capability **record contract** (Source / What / Evidence / Gap / Priority / in-constraint Impl-note / Novelty·Impact·Effort) in `specs/033-frontier-techniques-research/contracts/capability-record.md`
- [x] T005 [P] Define **source-quality rules** (scholarly = primary venues only, zero Medium/listicles; commercial = official sources + preview-vs-GA) in `contracts/capability-record.md`
- [x] T006 [P] Capture the **AstralDeep baseline + do-not-regress** brief (existing differentiators) shared to all streams, recorded in `research/SYNTHESIS.md` §5

**Checkpoint**: Contract + rules ready — stream research can proceed.

---

## Phase 3: User Story 1 — Vetted, prioritized corpus (Priority: P1) 🎯 MVP

**Goal**: A primary-sourced, deduplicated, prioritized corpus comparing the commercial + scholarly frontier to AstralDeep, ranked by the four priority dimensions, with a recommended wave sequence.

**Independent Test**: Open `research/SYNTHESIS.md` + one stream file; confirm every consolidated capability has a `C-*` id, ≥1 primary-source citation, Novelty/Impact/Effort, a consensus indicator, an in-constraint implementation note, and that do-not-regress + deferred lists exist. (Maps SC-001…SC-007 via `contracts/capability-record.md`.) **Status: complete.**

### Commercial streams

- [x] T007 [P] [US1] OpenAI frontier findings (17) → `research/commercial-openai.md`
- [x] T008 [P] [US1] Google / DeepMind findings (24) → `research/commercial-google.md`
- [x] T009 [P] [US1] Anthropic / Microsoft / Meta / Amazon / Vercel / startups findings (25) → `research/commercial-others.md`

### Scholarly streams

- [x] T010 [P] [US1] Agentic-frameworks & orchestration lit review (20 + 8) → `research/scholarly-agentic-frameworks.md`
- [x] T011 [P] [US1] Generative & adaptive UI lit review (21) → `research/scholarly-generative-ui.md`
- [x] T012 [P] [US1] Agent memory & personalization lit review (18) → `research/scholarly-memory-personalization.md`
- [x] T013 [P] [US1] Agentic security & delegated-authority lit review (19) → `research/scholarly-agentic-security.md`
- [x] T014 [P] [US1] Device adaptation & cross-surface UI lit review (20) → `research/scholarly-device-adaptation.md`

### Synthesis

- [x] T015 [US1] Deduplicate ~164 findings → **71 consolidated capabilities** with stable `C-*` ids, rolled-up scores, and cross-references → `research/SYNTHESIS.md` §3 (depends on T007–T014)
- [x] T016 [US1] Identify **convergent** (≥3-stream) themes as highest-confidence signals → `research/SYNTHESIS.md` §2
- [x] T017 [US1] Rank capabilities by priority dimension + **recommended wave sequencing** with rationale + locked decisions → `research/SYNTHESIS.md` §4
- [x] T018 [US1] Compile **do-not-regress** list (AstralDeep strengths) → `research/SYNTHESIS.md` §5
- [x] T019 [US1] Compile **deferred / out-of-constraint** list with portable-now sub-ideas → `research/SYNTHESIS.md` §6
- [x] T020 [US1] Compile **hype / caveats** log → `research/SYNTHESIS.md` §7
- [ ] T021 [US1] Final QA pass: verify the corpus against the acceptance-check table in `specs/033-frontier-techniques-research/contracts/capability-record.md` (SC-001…SC-007) and fix any gap

**Checkpoint**: US1 is the complete, standalone deliverable — valuable even if no capability is ever built.

---

## Phase 4: User Story 2 — Co-flagship: generative model-grounded UI (Priority: P1)

**Goal (roadmap definition only)**: Fully specify the US2 initiative so it can be spun up as the first follow-on implementation spec.

**Independent Test**: `spec.md` US2 states an independently-testable acceptance + flag-gated/fail-open/no-dep posture, and every mapped capability has an in-constraint note.

- [x] T022 [US2] Map capabilities C-N1, C-N2, C-U1, C-U2, C-U3, C-U6, C-U7, C-N14, C-N15 to the US2 initiative in `specs/033-frontier-techniques-research/spec.md`
- [x] T023 [US2] Write US2 independent test + acceptance scenarios + roadmap note (co-flagship) in `specs/033-frontier-techniques-research/spec.md`
- [ ] T024 [US2] Confirm US2 sits in Wave 1 with its Wave-0 enabler dependencies (C-N14/C-N5) named in `research/SYNTHESIS.md` §4
- [ ] T025 [US2] Verify each US2 capability's implementation note satisfies the Constraint Envelope (no new deps, SDUI mandate, escape-by-default for generative primitives) in the relevant stream files

---

## Phase 5: User Story 3 — Co-flagship: self-improving agent architecture (Priority: P1)

**Goal (roadmap definition only)**: Fully specify the US3 initiative for a follow-on spec.

**Independent Test**: `spec.md` US3 acceptance is independently testable (archive-conditioned creation, surrogate pre-score, trajectory judge, fresh-context fan-out).

- [x] T026 [US3] Map capabilities C-N3, C-N4, C-N5, C-N7, C-N8, C-N9, C-N10, C-N11, C-N12 to US3 in `specs/033-frontier-techniques-research/spec.md`
- [x] T027 [US3] Write US3 independent test + acceptance scenarios + co-flagship roadmap note in `specs/033-frontier-techniques-research/spec.md`
- [ ] T028 [US3] Confirm US3 (Wave 2) depends on the eval backbone (C-N5) and that MAS security defenses (C-S14) are sequenced to co-ship per FR-011 in `research/SYNTHESIS.md` §4
- [ ] T029 [US3] Verify each US3 capability's implementation note satisfies the Constraint Envelope in the relevant stream files

---

## Phase 6: User Story 4 — Co-flagship: living memory & personalization (Priority: P1)

**Goal (roadmap definition only)**: Fully specify the US4 initiative for a follow-on spec.

**Independent Test**: `spec.md` US4 acceptance is independently testable (supersede-not-append, graph/PageRank recall, sleep-time precompute) on Postgres + existing LLM client.

- [x] T030 [US4] Map capabilities C-M1…C-M11, C-N11, C-U8, C-U9 to US4 in `specs/033-frontier-techniques-research/spec.md`
- [x] T031 [US4] Write US4 independent test + acceptance scenarios + co-flagship roadmap note in `specs/033-frontier-techniques-research/spec.md`
- [ ] T032 [US4] Confirm US4 honors the **no-vector-DB / Postgres-only** constraint and that memory-poisoning defense (C-S9) is sequenced to co-ship per FR-011 in `research/SYNTHESIS.md` §4/§6
- [ ] T033 [US4] Verify each US4 capability's implementation note satisfies the Constraint Envelope in `research/scholarly-memory-personalization.md`

---

## Phase 7: User Story 5 — Device adaptation & multimodal reach (Priority: P3)

**Goal (roadmap definition only)**: Specify the US5 follow-on initiative.

**Independent Test**: `spec.md` US5 acceptance is independently testable (fallback ladder, VOICE renderer, model router) and every capability is "add a renderer / extend ROTE" (SDUI-clean).

- [x] T034 [US5] Map capabilities C-D1…C-D11 to US5 in `specs/033-frontier-techniques-research/spec.md`
- [ ] T035 [US5] Confirm US5 capabilities are all "add a target = add a renderer" / ROTE-extension (no primitive change, no new dep) and sit in Wave 3 in `research/SYNTHESIS.md` §4

---

## Phase 8: User Story 6 — Preventive agentic security (Priority: P3)

**Goal (roadmap definition only)**: Specify the US6 follow-on initiative and its timing rule.

**Independent Test**: `spec.md` US6 acceptance is independently testable (injection payload → zero out-of-scope calls/egress/PHI; single pre-action policy decision) and the OWASP ASI matrix is referenced.

- [x] T036 [US6] Map capabilities C-S1…C-S14 to US6 in `specs/033-frontier-techniques-research/spec.md`
- [ ] T037 [US6] Confirm FR-011 timing in `research/SYNTHESIS.md` §4 (guarding controls C-S6/C-S7/C-S9/C-S14 ship with/before the autonomy increases they protect) and that an OWASP ASI01–ASI10 coverage-matrix task (C-S12) is captured for the follow-on

---

## Phase N: Polish & Handoff

**Purpose**: Lock the deliverable, prove no code changed, and reach the Approval Gate.

- [ ] T038 [P] Validate `specs/033-frontier-techniques-research/quickstart.md` navigation end-to-end (every linked section/file resolves)
- [ ] T039 [P] Confirm `git diff main...033` touches **only** `specs/033-frontier-techniques-research/` + `.specify/feature.json` + the CLAUDE.md SPECKIT plan-list line — i.e. zero `backend/` code (SC-009)
- [ ] T040 Run `/speckit-analyze` cross-artifact consistency check (spec ↔ plan ↔ tasks ↔ research) and resolve any finding
- [ ] T041 Produce the stakeholder report and **request approval to open the follow-on implementation specs** (Approval Gate; SC-009) — co-flagship trio US2/US3/US4 first

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)**: the contract + rules gate all stream work.
- **US1 (Phase 3)**: depends on Phase 2; the 8 streams (T007–T014) run in parallel, then synthesis (T015–T021) consolidates them.
- **US2–US6 (Phases 4–8)**: roadmap-definition tasks; depend on US1's synthesis existing. Independent of each other.
- **Polish (Phase N)**: depends on all prior phases.

### User Story Dependencies

- **US1 (P1)** — the MVP; standalone.
- **US2 / US3 / US4 (P1, co-flagship)** — roadmap definitions; each independent; all reference US1's capabilities. (Implementation order later: US2/US3/US4 lead together.)
- **US5 / US6 (P3)** — roadmap definitions; independent; US6 carries the FR-011 timing rule tying specific controls to US3/US4.

### Parallel Opportunities

- T007–T014 (the eight research streams) are fully parallel — and were executed concurrently.
- T038 and T039 (polish checks) are parallel.
- The roadmap-definition QA tasks T024/T025, T028/T029, T032/T033, T035, T037 are parallel across stories.

---

## Parallel Example: User Story 1 (how the corpus was built)

```text
# The eight research streams launched together:
Task: "OpenAI frontier findings → research/commercial-openai.md"
Task: "Google/DeepMind findings → research/commercial-google.md"
Task: "Anthropic/MS/Meta/Amazon/Vercel/startups → research/commercial-others.md"
Task: "Agentic-frameworks lit review → research/scholarly-agentic-frameworks.md"
Task: "Generative/adaptive UI lit review → research/scholarly-generative-ui.md"
Task: "Memory/personalization lit review → research/scholarly-memory-personalization.md"
Task: "Agentic-security lit review → research/scholarly-agentic-security.md"
Task: "Device-adaptation lit review → research/scholarly-device-adaptation.md"
# Then synthesis (T015–T021) deduped to 71 capabilities and sequenced them.
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → Phase 2 Foundational (contract + rules).
2. Phase 3 US1: eight parallel streams → synthesis → QA.
3. **STOP and VALIDATE**: US1 is a complete, standalone competitive-intelligence + roadmap artifact.

### Incremental delivery (this branch)

US1 corpus (done) → US2/US3/US4 roadmap definitions (done) → US5/US6 roadmap definitions (done) → finalization QA (T021, T024–T037) → analyze (T040) → report + Approval Gate (T041).

### After approval (NOT this branch)

Each Consolidated Capability cluster spins up as its own follow-on feature branch via `/speckit-specify`, inheriting the Constraint Envelope + FR-010/FR-011 posture — co-flagship trio (US2/US3/US4) first, novelty-forward.

---

## Notes

- This branch is **research + roadmap only**: no `backend/` code, no schema, no dependency, no product behavior change.
- `[x]` = the corpus + roadmap already produced; `[ ]` = remaining finalization/handoff/QA.
- The Approval Gate (T041) is the user's go/no-go to open the follow-on implementation specs; nothing builds before it.
- Avoid scope creep: implementation tasks belong in the per-capability follow-on branches, not here.
