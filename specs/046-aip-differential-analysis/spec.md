# Feature Specification: AIP Differential Analysis — "How DAF Differs" Related-Work Artifact

**Feature Branch**: `046-aip-differential-analysis`
**Created**: 2026-07-02
**Status**: Draft
**Input**: User description: "Read AIP (2603.24775) end-to-end and write a half-page 'how DAF differs' (transport binding, deployment, provenance, self-extension). This paragraph goes in your related work and de-risks the scoop." (Item 2 of [THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md) §8.)

## Overview

AIP — *Agent Identity Protocol for Verifiable Delegation Across MCP and A2A* (arXiv 2603.24775, IETF `draft-prakash-aip-00`, PyPI `agent-identity-protocol`) — is the closest published competitor to the thesis's primary contribution (DAF). It introduces Invocation-Bound Capability Tokens (IBCTs): identity + attenuated authorization + provenance in an append-only token chain, with a compact JWT single-hop mode and a Biscuit/Datalog chained mode, and Python+Rust reference implementations. The scoop risk is real; the mitigation is a rigorous, evidence-grounded differentiation.

This feature reads AIP **end-to-end** (paper, Internet-Draft, and reference-implementation surface), produces structured reading notes, and distills a **half-page "how DAF differs" passage** — organized on the four surviving-novelty axes (transport binding, deployment, provenance, self-extension) — written to drop verbatim into the dissertation's related-work section. It also verifies the citation metadata, closing the "citation drift" risk flagged in §6/§7 of the thesis-direction document. Documentation/research feature: **no product code changes**. (The arXiv ID was pre-verified on 2026-07-02: 2603.24775 resolves to the expected title.)

## Clarifications

### Session 2026-07-02 (resolved by informed default — confirm or override during `/speckit-clarify`)

- Q: What does "end-to-end" cover — just the paper? → A: Three sources: (1) the arXiv paper in full; (2) `draft-prakash-aip-00` (the I-D is what IETF-track reviewers will compare against); (3) the reference implementation's public surface (README/API of the PyPI package and, if published, the Rust crate) — enough to characterize what is *implemented* vs. *specified*, not a code audit.
- Q: Where do the artifacts live? → A: `docs/thesis/related-work/aip-reading-notes.md` (notes + claim map) and `docs/thesis/related-work/daf-vs-aip.md` (the half-page passage). Same `docs/thesis/` area as spec 045.
- Q: What if reading AIP contradicts the assumed differentiation (e.g., AIP does bind to persistent transports, or does cover dynamically created principals)? → A: Evidence wins. The differential is rewritten from what the paper actually says; any contradicted axis is reported back into the framing memo (spec 045 lock record) before the related-work text is finalized. The deliverable is an honest differential, not a defense of a prior guess.
- Q: Half a page — measured how? → A: 250–350 words for the drop-in passage (hard cap 400), excluding the appendix claim table.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read AIP end-to-end and produce evidence-grounded notes (Priority: P1)

Sam reads the AIP paper, its I-D, and its reference-implementation surface, producing structured notes in which every characterization of AIP carries a location (section/page/figure or I-D section), so later claims about AIP are quotable and defensible under committee questioning.

**Why this priority**: The differential is only as strong as the reading beneath it. A related-work paragraph built on a skim is exactly how a scoop-adjacent thesis gets embarrassed in a defense.

**Independent Test**: Open the reading notes; pick any three characterizations of AIP; each must cite a specific location in the paper/I-D that supports it.

**Acceptance Scenarios**:

1. **Given** the notes, **When** read, **Then** they cover: the IBCT construction; the append-only token chain; JWT single-hop vs. Biscuit/Datalog chained modes; how attenuation is expressed and enforced; how provenance/audit is represented; the MCP and A2A bindings; the trust/verification model (who verifies what, online vs. offline); and the evaluation the paper reports.
2. **Given** the notes, **When** read, **Then** they contain an explicit "what AIP does NOT claim or build" list (each item with the evidence of absence — e.g., "no treatment of stateful/persistent transports; transport section covers only …"), since the thesis's novelty rests on these gaps.
3. **Given** the notes, **When** read, **Then** the reference-implementation section states what the Python/Rust artifacts actually implement (modes, bindings, maturity) as distinct from what the paper specifies.
4. **Given** any assumed differentiator from THESIS-DIRECTION §2.1, **When** the reading contradicts or weakens it, **Then** the notes flag it prominently and the contradiction is carried into Story 2 and reported against spec 045.

---

### User Story 2 - Write the half-page "how DAF differs" passage (Priority: P1)

From the notes, Sam writes a 250–350-word passage, structured on the four axes — transport binding, deployment, provenance, self-extension — that positions AIP as convergent validation and states precisely what DAF contributes beyond it. The passage is written in dissertation register, with citations, ready to paste into the related-work chapter.

**Why this priority**: This paragraph is the named deliverable and the scoop de-risk: once it exists, any reviewer comparison with AIP has a prepared, evidence-grounded answer.

**Independent Test**: Read the passage cold; confirm it (a) fits the word budget, (b) addresses all four axes, (c) contains no claim about AIP that the notes don't support, and (d) could be pasted into a related-work section without edits beyond citation-key formatting.

**Acceptance Scenarios**:

1. **Given** the passage, **When** read, **Then** each of the four axes is present and grounded on both sides: a specific AIP characteristic (from the notes) and a specific Astral artifact — transport binding ↔ per-tool-call attenuation over the persistent WebSocket ReAct loop; deployment ↔ the running multi-tenant UKY sandbox with real users; provenance ↔ the hash-chained audit + `act`-claim chain as tamper-evident completion records; self-extension ↔ DAF-scoped delegation for agents created by the 027/035 rail.
2. **Given** the passage, **When** read, **Then** AIP is treated respectfully as convergent prior art (cited as validation of the model), and any dimension where AIP is *stronger* than DAF (e.g., expressive Datalog policy, cross-protocol breadth) is acknowledged rather than omitted — the no-strawman rule.
3. **Given** the passage, **When** checked against spec 045's locked framing, **Then** the claims are consistent with (or explicitly amend) the framing memo.
4. **Given** the appendix, **When** read, **Then** a claim-by-claim table maps AIP capability ↔ DAF capability ↔ remaining gap/differentiator, as the expandable backing for the prose.

---

### User Story 3 - Verify and pin the citation metadata (Priority: P2)

The exact arXiv ID/version, paper title, author list, I-D name/revision, and package identity are verified against the live sources and recorded, closing the §6 "citation drift" risk for the must-cite competitor.

**Why this priority**: A wrong citation for the *closest competitor* is the most damaging kind of citation error a defense can contain. Cheap to do during the read.

**Independent Test**: The notes' bibliography block contains the verified fields with retrieval dates; each resolves when followed.

**Acceptance Scenarios**:

1. **Given** the bibliography block, **When** checked, **Then** arXiv 2603.24775's title, authors, latest version, and date are recorded as retrieved from arXiv (title pre-confirmed 2026-07-02), and the I-D name `draft-prakash-aip-00` (or its current revision) is confirmed against the IETF datatracker, including its status (individual/adopted, active/expired).
2. **Given** related identifiers named in THESIS-DIRECTION §7 for the delegation cluster (`draft-niyikiza-oauth-attenuating-agent-tokens-00`, WIMSE drafts, arXiv 2604.23280), **When** encountered during the read, **Then** their existence/current revision is opportunistically verified and recorded in the same block (full verification of the rest of §7 remains out of scope).

### Edge Cases

- The paper has been revised since the analysis (v2+ with new claims, e.g., added transport bindings) → the differential targets the **latest** version; deltas from the version the thesis-direction doc assumed are noted.
- The I-D has expired or been adopted by a WG since → record the status change; adoption strengthens the "convergent IETF direction" framing and feeds spec 049.
- Paper access fails from the sandbox (PDF text extraction) → acquire through normal library/arXiv channels; the feature does not depend on tooling, and the notes record which source version was read.
- AIP's evaluation section already includes a deployed system → this collapses the "deployment" axis; the differential re-weights the remaining axes honestly and 045 is notified (framing amendment).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The reading MUST cover the full arXiv paper, the AIP Internet-Draft, and the reference implementation's public surface; the notes MUST state which version/revision of each was read and when.
- **FR-002**: Every characterization of AIP in the notes MUST carry a source location (section, page, figure, or I-D section number).
- **FR-003**: The notes MUST include a "what AIP does not do" list with evidence-of-absence for each item relied on by the thesis framing.
- **FR-004**: The differential passage MUST be 250–350 words (hard cap 400), structured on the four axes (transport binding, deployment, provenance, self-extension), in dissertation-ready prose with citations.
- **FR-005**: The passage MUST NOT contain any claim about AIP unsupported by the notes (traceable note-to-claim mapping), and MUST acknowledge at least the dimensions where AIP exceeds DAF — the no-strawman rule.
- **FR-006**: A claim-by-claim comparison table (AIP ↔ DAF ↔ gap) MUST accompany the passage as an appendix; each DAF-side entry MUST name the concrete system artifact (module, mechanism, or deployment fact) that backs it.
- **FR-007**: Citation metadata for AIP (arXiv + I-D + package) MUST be verified against live sources and recorded with retrieval dates.
- **FR-008**: Any contradiction between the reading and the locked framing (spec 045) MUST be surfaced as an explicit flag in the notes and reported into 045's lock record before the passage is finalized.
- **FR-009**: Artifacts MUST live at `docs/thesis/related-work/aip-reading-notes.md` and `docs/thesis/related-work/daf-vs-aip.md`.
- **FR-010**: The feature MUST NOT change any product code, configuration, schema, or dependency. Documentation only.

### Key Entities

- **Reading notes**: structured, source-located characterization of AIP (paper + I-D + implementation), including the does-not-do list and bibliography block.
- **Differential passage**: the half-page related-work-ready text; the citable output.
- **Claim map**: appendix table tying each differential claim to an AIP source location and an Astral artifact.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The passage exists, is within 250–400 words, covers all four axes, and every AIP-side claim traces to a located note — verifiable by cross-reading the two artifacts.
- **SC-002**: The AIP citation block is complete (arXiv version, authors, I-D revision + status, package identity) with retrieval dates, and each identifier resolves.
- **SC-003**: The passage can be inserted into the related-work chapter without content edits (only citation-key formatting), as judged by the advisor or a committee-adjacent reader.
- **SC-004**: Zero product-code delta (diff confined to `docs/thesis/` and `specs/046-*`).
- **SC-005**: If any framing contradiction was found, it is reflected in 045's lock record; if none, the notes explicitly state that all four axes survived the read.

## Assumptions

- The AIP paper and I-D are publicly accessible; no paywalled dependency.
- The four-axis structure from THESIS-DIRECTION §2.1 is the right skeleton *unless the evidence says otherwise* (FR-008 handles the exception).
- Related-work passages for the other delegation-cluster prior art (niyikiza, WIMSE, Transaction Tokens, Progent) are dissertation-chapter work, out of scope here except for opportunistic citation verification.
- The dissertation's citation style is settled later; the passage uses inline author-year placeholders that any style can absorb.

## Dependencies & Sequencing

- **Fed by**: 045 (the locked framing states what the differential must defend).
- **Feeds**: 048 (the recursive-delegation design should consciously differ from/align with IBCT chaining), 049 (the I-D decision brief leans on this differential), and the dissertation related-work chapter.
