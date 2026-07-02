# Tasks: IETF Internet-Draft Decision Brief

**Feature**: 049-ietf-id-decision | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
Documentation/decision feature. "Verification" = checklist. Decision itself is advisor-gated.

## Phase 0 — Evidence

- [X] T001 Pull verified competitor status from spec 046 (AIP individual/Informational/active/expires 2026-09-28; niyikiza -01/OAuth-WG; WIMSE active).
- [X] T002 Confirm spec 048 maturity (mechanism built + property-tested green) so the brief reflects reality, not plan.
- [X] T003 Re-read the locked framing (spec 045) for the FR-007 consistency check.

## Phase 1 — Decision brief (US1, P1)

- [X] T004 `docs/thesis/publication/ietf-id-decision.md`: recommendation (GO) + case-for + **strongest case-against** (process overhead, spec/impl divergence, traction vs. maturing competitors) (FR-001).
- [X] T005 Venue table — WIMSE WG / OAuth WG / independent, each with fit + signal (FR-002).
- [X] T006 Marginal-cost estimate over specs 046+048 (~1–2 weeks writing, no new research) (FR-003).
- [X] T007 Verified competitor status + how it affects the recommendation/timing (FR-004).
- [X] T008 8-month horizon: latest-useful submission window (~Oct–Nov 2026) + cut-losses point (FR-005).

## Phase 2 — Decision record (US2, P1)

- [X] T009 `ietf-id-decision-record.md`: PENDING joint ratification; outcome/date/deciders/rationale fields; go-details + no-go/defer tables (FR-006).
- [X] T010 FR-007 consistency check recorded (I-D is positioning within the spine, not a reframing).

## Phase 3 — Conditional scope outline (US3, P3)

- [X] T011 `id-scope-outline.md` marked **contingent on GO ratification**; cites RFC 8693/9449 as the extended base + specs 046/048 as substance; explicit out-of-scope (Astral deployment, ROTE, memory, competing token format, discovery) (FR-008).
- [X] T012 Record instructs deletion of the outline on a no-go/defer ratification (FR-008 "absent on no-go/defer").

## Phase 4 — Verification

- [X] T013 SC-001: brief ≤ 2 pages and contains all six required elements (checklist).
- [X] T014 SC-004: decision consistent with spec 045 locked framing (cross-checked).
- [X] T015 SC-005: zero product-code delta (diff confined to `docs/thesis/` + `specs/049-*`).
- [ ] T016 **[BLOCKED ON ADVISOR]** SC-002: record carries an explicit ratified outcome + date. Staged in PENDING; finalized at the joint meeting (by design of US2).

## Dependencies

- Fed by: 045 (locked framing), 046 (verified status + differential), 048 (mechanism maturity).
- Feeds: a future "author IETF I-D" spec (only if go); the publication-mapping section of the thesis.
- Note: last of the five §8 items; decision-gated on 046 + 048, both complete.
