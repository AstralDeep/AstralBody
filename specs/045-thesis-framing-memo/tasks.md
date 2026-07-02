# Tasks: Lock the Thesis Framing — One-Page Advisor Memo

**Feature**: 045-thesis-framing-memo | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
Documentation-only feature. No code, no tests-as-code; "verification" is a checklist pass.

## Phase 0 — Setup & source extraction

- [X] T001 Create `docs/thesis/` (and `related-work/`, `publication/` for sibling specs).
- [X] T002 Extract from `THESIS-DIRECTION-2026-07.md`: §0 spine verbatim; §2.1 stop/start rule; the four axes; the A–E direction stack; the deprioritized list. (Research phase.)
- [X] T003 Fold in spec-046 pre-verification amendments (A-1 provenance, A-2 self-extension) so no memo claim overshoots verified evidence (FR-010).

## Phase 1 — Author the memo (US1, P1)

- [X] T004 Write `docs/thesis/thesis-statement-memo.md`: spine blockquote (FR-001), stop/start rule (FR-002), four axes ≤2 sentences each (FR-003).
- [X] T005 Add convergent-validation paragraph citing AIP / `draft-niyikiza` / WIMSE and why alignment is a committee strength (FR-004).
- [X] T006 Add one-spine/three-planes structure, the A–E direction stack with time-boxing, and the explicit deprioritized list (FR-005).
- [X] T007 Close with the two asks (approve reframing; calendar the I-D decision) and the ~8-month horizon (FR-007).
- [X] T008 Trim to budget: 450–650 words body, ≤700 hard cap; advisor register, no code/jargon/paths (FR-006). **Measured: 592 words.**

## Phase 2 — Lock record (US2, P2)

- [X] T009 Write `docs/thesis/framing-lock-record.md` in `PROPOSED` state with decision/date/decider/memo-revision fields (FR-008).
- [X] T010 Add per-element status table (partial-lock support) and the evidence log capturing amendments A-1/A-2.
- [X] T011 Add decision-history table + downstream-impact checklist (US2 scenarios 2–3; edge cases).

## Phase 3 — Make citable by downstream (US3, P3)

- [X] T012 Confirm specs 046–049 reference the locked-framing path (added in each sibling spec's plan; grep at final verification, SC-005).

## Phase 4 — Verification

- [X] T013 Verify SC-001: memo ≤700 words body and contains all seven elements (checklist pass).
- [X] T014 Verify SC-004: `git diff` for this feature touches only `docs/thesis/` and `specs/045-*` (zero product-code delta).
- [ ] T015 **[BLOCKED ON ADVISOR]** Verify SC-002: advisor-ready copy delivered and lock record carries an explicit decision + date. *Cannot be completed in-repo without the advisor meeting; record is staged in `PROPOSED` state (SC-003 standalone-readability already met).*

## Dependencies

- Feeds specs 046, 047, 048, 049 (each cites the locked framing).
- Fed by: none — deliberately first, precedes code.
- T015 is the only open item and is externally gated (advisor decision), by design of US2.
