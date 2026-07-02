# Implementation Plan: AIP Differential Analysis — "How DAF Differs"

**Branch**: `046-aip-differential-analysis` | **Date**: 2026-07-02 | **Spec**: [spec.md](spec.md)
**Framing source**: [`docs/thesis/thesis-statement-memo.md`](../../docs/thesis/thesis-statement-memo.md) (locked framing, spec 045)

## Summary

Read AIP end-to-end (arXiv paper + `draft-prakash-aip-00` I-D + `agent-identity-protocol` reference implementation), produce source-located reading notes with a "what AIP does not do" list, and distill a 250–350-word "how DAF differs" passage on four axes (transport binding, deployment, provenance, self-extension) plus a claim-map appendix. Verify and pin citation metadata. Surface any framing contradiction into spec 045's lock record. **Documentation/research only — zero product code.**

## Technical Context

**Language/Version**: N/A (Markdown prose + one claim table).
**Primary Dependencies (sources)**: `arXiv:2603.24775`; `draft-prakash-aip-00` (ietf.org); PyPI `agent-identity-protocol` 0.3.0; opportunistic verification of `draft-niyikiza-...-01`. DAF-side artifacts: `orchestrator/delegation.py`, `audit/pii.py`, `audit/repository.py`, `personalization/phi_gate.py`, the 027/035 creation rail.
**Testing**: checklist — every AIP claim traced to a source location; passage within word budget; no unsupported claim; no-strawman rows present; citations resolve.
**Project Type**: Documentation/research.
**Constraints**: passage 250–350 words (cap 400); notes exhaustively source-located.

## Constitution Check

- **V (no new deps)**: PASS — no code.
- **Zero product-code delta**: PASS — diff confined to `docs/thesis/related-work/` + `specs/046-*`.
- **Cross-client parity**: N/A — no wire/UI/primitive change; clients unaffected.
- **Evidence-wins rule (spec FR-008)**: honored — two axes refined against verified evidence; reported to 045.

Gate result: **PASS**.

## Project Structure

```
docs/thesis/related-work/
├── aip-reading-notes.md   # source-located notes, does-not-do list, bibliography (US1, US3)
└── daf-vs-aip.md          # 250–350w passage + claim-map appendix (US2)

specs/046-aip-differential-analysis/
├── spec.md
├── plan.md   # this file
└── tasks.md
```

**Structure Decision**: same `docs/thesis/` area as spec 045; the passage is written to paste into the dissertation related-work chapter with only citation-key edits.

## Phased Approach

**Phase 0 — Read + verify (US1, US3).** Read the I-D in full (primary substance), the arXiv metadata, and the PyPI implementation surface. Pin citation metadata with retrieval dates; note status changes (PyPI 0.1.1→0.3.0; niyikiza 00→01).

**Phase 1 — Notes (US1).** Characterize IBCT construction, chain, both modes, attenuation, provenance, bindings, trust model, evaluation, and impl-vs-spec — each with a source location. Author the evidence-of-absence "does-not-do" list.

**Phase 2 — Differential (US2).** Write the four-axis passage in dissertation register; no claim beyond the notes; acknowledge where AIP is stronger (no-strawman). Build the claim-map appendix binding each DAF claim to a real module.

**Phase 3 — Reconcile with framing (FR-008).** Record amendments A-1 (provenance) and A-2 (self-extension) into the 045 lock record before finalizing.

**Phase 4 — Verify** against SC-001…SC-005.

## Key findings that shaped the work

- Transport-binding and deployed-multi-tenant axes **survived cleanly** (AIP §4 is stateless; AIP claims no multi-tenant real-user deployment).
- Provenance and self-extension axes **required honest refinement** (AIP §6 audit tokens; §5.3 ephemeral grants) — the differential differentiates on *model* and *narrowed scope*, not presence/absence. This is the spec's "evidence wins" clause operating as intended.

## Complexity Tracking

No entries.
