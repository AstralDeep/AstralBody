# Implementation Plan: Lock the Thesis Framing — One-Page Advisor Memo

**Branch**: `045-thesis-framing-memo` | **Date**: 2026-07-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/045-thesis-framing-memo/spec.md`

## Summary

Produce a one-page, advisor-facing thesis-statement memo that quotes the §0 spine verbatim, states the §2.1 stop/start reframing rule, enumerates the four surviving novelty axes, cites the convergent IETF/academic work as validation, presents the one-spine/three-planes structure and the A–E direction stack, and closes with explicit asks. Capture the advisor's decision in a dated framing-lock record that binds the decision to a specific memo revision. **Documentation only — zero product code.**

## Technical Context

**Language/Version**: N/A (Markdown prose).
**Primary Dependencies**: Source of truth = `THESIS-DIRECTION-2026-07.md` (§0, §2.1, §3, §5, §8). Verified reading list = spec 046 citation block.
**Storage**: In-repo Markdown under `docs/thesis/`.
**Testing**: Manual/checkable — word-count budget, element checklist (FR-001…FR-007), standalone-readability, zero-code-delta grep.
**Target Platform**: Repo docs; an exported copy (PDF or the `.md`) goes to the advisor.
**Project Type**: Documentation/decision.
**Performance/Constraints**: ≤1 printed page; 450–650 words body, hard cap 700.
**Scale/Scope**: Two artifacts (memo + lock record).

## Constitution Check

- **V (no new deps)**: PASS — no code, no dependencies touched.
- **Zero product-code delta**: PASS — diff confined to `docs/thesis/` and `specs/045-*`.
- **No schema/config/flag changes**: PASS — none.
- **Cross-client parity**: N/A — no wire-protocol, primitive, or UI surface touched; web/Windows/Android clients unaffected. Confirmed in spec 044's UI-protocol manifest terms (no change).

Gate result: **PASS** (no violations; Complexity Tracking empty).

## Project Structure

### Documentation (this feature)

```
specs/045-thesis-framing-memo/
├── spec.md         # authored
├── plan.md         # this file
└── tasks.md        # task breakdown

docs/thesis/
├── thesis-statement-memo.md   # the one-page memo (FR-001…FR-007)
└── framing-lock-record.md     # the dated decision record (FR-008)
```

**Structure Decision**: New `docs/thesis/` area holds all defense-track artifacts so specs 046–049 cite one canonical location. No `backend/`, `windows-client/`, or `android-client/` paths are touched.

## Phased Approach

**Phase 0 — Source extraction (research).** Pull the §0 spine (verbatim), the §2.1 stop/start rule, the four axes, the A–E stack, and the deprioritized list from `THESIS-DIRECTION-2026-07.md`. Fold in the spec-046 pre-verification amendments (A-1 provenance, A-2 self-extension) so the memo never overclaims relative to verified evidence (FR-010).

**Phase 1 — Author the memo.** Write to the word budget in advisor register: no code, no spec jargon, no internal file paths. Make the spine visually prominent; keep each axis ≤2 sentences.

**Phase 2 — Author the lock record.** Create the record in `PROPOSED` state with the per-element table, evidence log, decision-history table, and downstream-impact checklist, ready to flip to `LOCKED` after the advisor meeting.

**Phase 3 — Verify.** Word count in range; all seven content elements present; standalone-readable; `git diff` touches only `docs/thesis/` + `specs/045-*`.

## Complexity Tracking

No entries — no constitution deviations.
