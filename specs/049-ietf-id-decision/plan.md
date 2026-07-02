# Implementation Plan: IETF Internet-Draft Decision Brief

**Branch**: `049-ietf-id-decision` | **Date**: 2026-07-02 | **Spec**: [spec.md](spec.md)
**Framing source**: [`docs/thesis/thesis-statement-memo.md`](../../docs/thesis/thesis-statement-memo.md). **Fed by**: 046 (verified competitor status) + 048 (mechanism maturity).

## Summary

Produce a ≤2-page **decision brief** (recommendation + case-for/against, venue options, marginal-cost estimate, verified competitor status, 8-month timing) so the advisor can make the go/no-go call in one meeting; a **decision record** capturing the joint outcome; and, conditionally, an **I-D scope outline** (only meaningful on a go). **Documentation/decision only — does not author the draft and changes no product code.**

## Technical Context

**Language/Version**: N/A (Markdown prose).
**Inputs**: spec 046 verified citation block (`draft-prakash-aip-00` individual/Informational/active/expires 2026-09-28; `draft-niyikiza-...-01` OAuth-WG-engaged; WIMSE active); spec 048 mechanism (built + property-tested); the locked framing (spec 045); RFC 8693/9449/9396.
**Testing**: checklist — brief contains recommendation/case-against/venues/marginal-cost/verified-status/horizon; record has outcome/date/deciders/rationale; outline present iff go.
**Constraints**: brief ≤ 2 pages; decision is Sam+advisor (not executed unilaterally); the I-D itself is a separate future effort.

## Constitution Check

- **V (no new deps)** / **zero product-code delta**: PASS — diff confined to `docs/thesis/publication/` + `specs/049-*`.
- **Cross-client parity**: N/A — no wire/UI/primitive change; clients unaffected.
- **Decision-gated (FR-009)**: PASS — does not author the I-D; outline is conditional.
- **Consistent with locked framing (FR-007)**: PASS — an I-D is a positioning move within the spine, not a reframing.

Gate result: **PASS**.

## Project Structure

```
docs/thesis/publication/
├── ietf-id-decision.md          # the brief (US1)
├── ietf-id-decision-record.md   # the joint decision record (US2)
└── id-scope-outline.md          # conditional; contingent on GO ratification (US3)

specs/049-ietf-id-decision/{spec,plan,tasks}.md
```

## Phased Approach

**Phase 0 — Assemble evidence.** Pull verified competitor status from spec 046; confirm spec 048 maturity (mechanism built, property-tested); re-read the locked framing.

**Phase 1 — Brief (US1).** Recommendation (GO), case for + strongest case against, venue table (WIMSE/OAuth/independent), marginal-cost estimate over 046+048, verified status + its effect on timing, the ~8-month horizon with a latest-useful window and cut-losses point.

**Phase 2 — Record (US2).** Pending-ratification record with outcome/date/deciders/rationale fields and the go-details table; consistency-with-framing check.

**Phase 3 — Conditional outline (US3).** Provide the scope outline **marked contingent on a GO ratification** (recommendation is go), citing RFC 8693/9449 and specs 046/048, with explicit out-of-scope items; the record instructs deletion on a no-go/defer (FR-008).

**Phase 4 — Verify** SC-001…SC-005.

## Notes

- The joint decision itself is **externally gated** (requires the advisor meeting); the record is staged in `PENDING` state with a standing GO recommendation. This is the honest state — the deliverable is decision *support* + a durable record, not a fabricated outcome.
- The decision is deliberately the last of the five §8 items and is gated on 046/048 evidence, both of which are complete.

## Complexity Tracking

No entries.
