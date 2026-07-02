# Tasks: AIP Differential Analysis — "How DAF Differs"

**Feature**: 046-aip-differential-analysis | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
Documentation/research feature. "Verification" = checklist + citation-resolution pass.

## Phase 0 — Read & verify sources (US1 P1, US3 P2)

- [X] T001 Resolve & read `draft-prakash-aip-00` in full (ietf.org) — primary substance source; capture §1–§9.
- [X] T002 Resolve arXiv:2603.24775 metadata (title, author, submit date); note PDF body not sandbox-extractable, substance taken from the accompanying I-D.
- [X] T003 Read PyPI `agent-identity-protocol` surface (0.3.0): sub-packages, modes, adapters, benchmarks; record impl-vs-spec.
- [X] T004 Opportunistically verify `draft-niyikiza-...` (found **-01**, OAuth-WG) and note WIMSE characterization; record status changes for spec 049.
- [X] T005 Write the bibliography block with verified fields + retrieval dates (FR-007); confirm each identifier resolves (SC-002).

## Phase 1 — Reading notes (US1 P1)

- [X] T006 `docs/thesis/related-work/aip-reading-notes.md`: cover IBCT construction, append-only chain, JWT vs Biscuit/Datalog modes, attenuation expression+enforcement, provenance/audit, MCP+A2A bindings, trust/verification model, reported evaluation (FR-002, US1-AS1) — each source-located.
- [X] T007 Add the reference-implementation "implemented vs specified" section (US1-AS3).
- [X] T008 Author the "what AIP does NOT do" list with evidence-of-absence per item (FR-003, US1-AS2).

## Phase 2 — Differential passage (US2 P1)

- [X] T009 `docs/thesis/related-work/daf-vs-aip.md`: 250–350w four-axis passage, dissertation register, citations (FR-004). **Measured: 261 words.**
- [X] T010 Enforce no-strawman: acknowledge AIP's stronger dimensions (Datalog policy, MCP/A2A/HTTP breadth, portable audit tokens) (FR-005, US2-AS2).
- [X] T011 Build the claim-map appendix (AIP ↔ DAF ↔ gap); every DAF cell names a real module (FR-006, US2-AS4).
- [X] T012 Cross-check every passage claim against the notes (no claim beyond evidence) (SC-001).

## Phase 3 — Reconcile with locked framing (FR-008)

- [X] T013 Record Amendment A-1 (provenance) and A-2 (self-extension) into `docs/thesis/framing-lock-record.md` before finalizing the passage (US2-AS3, SC-005).
- [X] T014 State explicitly in the notes that transport + deployment axes survived the read unchanged (SC-005 "if none…").

## Phase 4 — Verification

- [X] T015 SC-001: passage 250–400 words, all four axes, every AIP claim traces to a located note.
- [X] T016 SC-002: citation block complete + resolves (arXiv, I-D revision+status, package identity).
- [X] T017 SC-004: zero product-code delta (diff confined to `docs/thesis/` + `specs/046-*`).

## Dependencies

- Fed by: 045 (locked framing states what the differential must defend).
- Feeds: 048 (nested-`act`-vs-IBCT rationale), 049 (verified competitor status + differential), dissertation related-work chapter.
