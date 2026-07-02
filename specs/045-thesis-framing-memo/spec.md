# Feature Specification: Lock the Thesis Framing — One-Page Advisor Memo

**Feature Branch**: `045-thesis-framing-memo`
**Created**: 2026-07-02
**Status**: Draft
**Input**: User description: "Lock the framing (§0 spine + §2.1 reframing rule). Write it as a 1-page thesis-statement memo for your advisor before touching code — the repositioning is the highest-value decision here." (Item 1 of [THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md) §8.)

## Overview

The novelty-gap analysis ([THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md)) concludes that the thesis's defensible core has shifted: the claim is no longer "a novel delegation protocol" (now contested by AIP, `draft-niyikiza`, and WIMSE) but **the first implemented, deployed, evaluated system that binds attenuated, provenance-bearing agent delegation to a persistent transport and to a self-extension loop, and measures its enforcement**. Every subsequent work item (specs 046–049, Directions A–E) inherits this framing, so locking it with the advisor is the highest-value action and must precede code.

This feature produces a **one-page thesis-statement memo** addressed to the advisor (Bumgardner), captures the advisor's decision, and records the locked framing as the canonical reference the rest of the work cites. It is a documentation/decision feature: **no product code changes**.

## Clarifications

### Session 2026-07-02 (resolved by informed default — confirm or override during `/speckit-clarify`)

- Q: Where does the memo live? → A: In-repo at `docs/thesis/thesis-statement-memo.md` (new `docs/thesis/` area for defense-track artifacts), so it is version-controlled and citable by later specs. An exported copy (PDF or the md itself) is what actually goes to the advisor.
- Q: What counts as "locked"? → A: A dated **framing-lock record** appended to the memo (or a sibling `decision.md`) stating the advisor's response: approved / approved-with-edits (edits captured) / rejected (rationale captured, memo revised, cycle repeats). Until that record exists the framing is proposed, not locked.
- Q: One page — measured how? → A: ≤ 1 printed page: target 450–650 words of body text (excluding title/metadata), never more than 700. Density is the point; the advisor should absorb it in under five minutes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Author the one-page framing memo (Priority: P1)

Sam writes a single-page memo that states the thesis spine verbatim, states the repositioning rule (what we stop claiming, what we now claim), names the convergent external work as validation rather than threat, and lays out the 8-month direction stack — so the advisor can approve a defense-shaped thesis framing in one reading.

**Why this priority**: Every other item in the 30-day plan (AIP differential, benchmark harness, recursive delegation, IETF I-D decision) is scoped by this framing. Written first, it prevents building the wrong thesis.

**Independent Test**: Open `docs/thesis/thesis-statement-memo.md`; verify it fits one page, contains the required elements (FR-001…FR-007), and reads standalone — a committee member with no context on the July analysis could understand the claim and the plan.

**Acceptance Scenarios**:

1. **Given** the memo, **When** read, **Then** it contains the one-sentence thesis spine from §0 of the thesis-direction document, quoted verbatim and visually prominent.
2. **Given** the memo, **When** read, **Then** it states the §2.1 reframing rule explicitly in stop/start form: STOP claiming "a novel delegation protocol"; START claiming "the first implemented and evaluated system that binds attenuated, provenance-bearing agent delegation to a persistent transport and to a self-extension loop, and measures its enforcement."
3. **Given** the memo, **When** read, **Then** the four surviving novelty axes are named: (1) transport binding (attenuated delegation over a persistent, stateful WebSocket with mid-session re-derivation), (2) provenance-aware completion records (hash-chained audit + `act`-claim chain), (3) deployed multi-tenant HIPAA-motivated instantiation with measured enforcement, (4) delegation for dynamically created agents.
4. **Given** the memo, **When** read, **Then** AIP (arXiv 2603.24775), `draft-niyikiza-oauth-attenuating-agent-tokens`, and IETF WIMSE are cited as **convergent validation** of the model, with one sentence on why alignment with an emerging IETF direction strengthens a systems thesis.
5. **Given** the memo, **When** read, **Then** it presents the "one spine, three enforced planes" structure (authority = DAF, presentation = ROTE, autonomy = self-extension + memory, all fail-closed, all measured) and the direction stack: A primary, B parallel/non-negotiable, C rescues the UI contribution, D/E time-boxed supporting evidence.
6. **Given** the memo, **When** read, **Then** it ends with explicit asks: approve the reframing, and calendar the IETF I-D question (deferred to its own decision, spec 049).

---

### User Story 2 - Capture the advisor's decision as a framing-lock record (Priority: P2)

After the advisor reads the memo, their response — approval, requested edits, or rejection with rationale — is recorded in the repo with a date, so "the framing is locked" is a checkable fact rather than a recollection.

**Why this priority**: The lock, not the prose, is the deliverable; downstream specs need a stable framing to cite. P2 only because the memo must exist first.

**Independent Test**: Inspect the framing-lock record; it names the decision, the date, the advisor, and (if edited) exactly what changed in the memo.

**Acceptance Scenarios**:

1. **Given** advisor approval, **When** the lock record is written, **Then** it states the decision, date, and the memo revision (content hash or git ref) approved.
2. **Given** advisor edits, **When** incorporated, **Then** the memo is updated, the lock record notes each change, and the spine/reframing elements (FR-001…FR-003) still hold or the change is escalated as a framing change, not silently absorbed.
3. **Given** rejection, **When** recorded, **Then** the rationale is captured and a revised memo cycle starts; the record shows the history of attempts.

---

### User Story 3 - Make the locked framing citable by downstream work (Priority: P3)

Specs 046–049 and future thesis chapters reference one canonical framing location instead of restating it, so a later framing edit propagates from a single source.

**Why this priority**: Traceability hygiene; valuable but trivial once Stories 1–2 exist.

**Independent Test**: Grep specs 046–049 for a reference to the memo path; confirm each states its dependency on the locked framing.

**Acceptance Scenarios**:

1. **Given** the locked memo, **When** downstream specs are read, **Then** each cites `docs/thesis/thesis-statement-memo.md` as its framing source.
2. **Given** a post-lock framing change, **When** it occurs, **Then** the memo is revised with a new lock record and downstream specs are reviewed for impact (a checklist note in the lock record).

### Edge Cases

- Advisor approves the spine but rejects a novelty axis (e.g., considers the self-extension tie-in weak) → partial lock is recorded per element; downstream specs touching the rejected element (048 P-promotion binding, 049) are flagged before work starts.
- New prior art surfaces between memo writing and the advisor meeting (the area is hot) → memo carries a "verified as of" date; a material scoop reopens Story 1 rather than being penciled into the meeting.
- The AIP differential (spec 046) later contradicts a memo claim (e.g., AIP does address persistent transports) → the lock record is amended and the memo corrected; the memo must never overclaim relative to verified evidence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The memo MUST quote the §0 one-sentence thesis spine verbatim from [THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md).
- **FR-002**: The memo MUST state the §2.1 reframing rule in explicit stop/start form (stop: "a novel delegation protocol"; start: implemented + deployed + transport-bound + provenance-bearing + self-extension-coupled + measured).
- **FR-003**: The memo MUST enumerate the four surviving novelty axes (transport binding; provenance-aware completion records; deployed multi-tenant HIPAA-motivated instantiation + evaluation; delegation for dynamically created agents), each in at most two sentences.
- **FR-004**: The memo MUST cite AIP, `draft-niyikiza-oauth-attenuating-agent-tokens`, and WIMSE as convergent validation, not competition, and say why that is a strength for this committee.
- **FR-005**: The memo MUST present the one-spine/three-planes structure and the prioritized direction stack (A, B, C, D/E with time-boxing), and MUST state what is explicitly deprioritized (dynamic discovery, net-new generative-UI primitives, wire-format standardization race).
- **FR-006**: The memo MUST fit one printed page (450–650 words body, hard cap 700) and be written in advisor-facing prose — no code, no spec jargon, no internal file paths.
- **FR-007**: The memo MUST close with the explicit asks (approve reframing; schedule the I-D decision) and identify the ~8-month defense horizon.
- **FR-008**: The memo MUST live at `docs/thesis/thesis-statement-memo.md`; the framing-lock record MUST live with it and carry decision, date, decider, and memo revision.
- **FR-009**: The feature MUST NOT change any product code, configuration, schema, or dependency. Documentation only.
- **FR-010**: Any factual claim in the memo about external work MUST match the verified reading list (§7 of the thesis-direction document) and MUST be revisited when spec 046's verification pass lands.

### Key Entities

- **Thesis-statement memo**: the one-page advisor-facing document; the single canonical statement of the reframed thesis.
- **Framing-lock record**: dated decision record binding an advisor decision to a specific memo revision; the definition of "locked."

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The memo exists at the canonical path, is ≤ 1 page (≤ 700 words body), and contains all seven content elements (FR-001…FR-007) — checkable by reading it against the list.
- **SC-002**: An advisor-ready copy was delivered and a framing-lock record exists with an explicit decision and date.
- **SC-003**: A reader with no exposure to the July analysis can state, after one reading, (a) the thesis claim and (b) the next two work items — the memo stands alone.
- **SC-004**: `git diff` for this feature touches only `docs/thesis/` and `specs/045-*` — zero product-code delta.
- **SC-005**: Specs 046–049 each carry a reference to the locked framing (verified by grep once those specs merge).

## Assumptions

- The advisor meeting happens within the 30-day window; the memo is written to be sent asynchronously if scheduling slips.
- The §0 spine and §2.1 rule in THESIS-DIRECTION-2026-07.md are the intended framing to lock; if the advisor materially rewrites the spine, that is a new framing decision recorded in the lock record, and THESIS-DIRECTION is annotated rather than silently diverging.
- The qualifying-exam document (`main.pdf`, 2026-04-01) remains the committee-visible baseline the memo repositions against; no committee re-approval of scope is needed for a framing memo.
- Spec 049 (IETF I-D decision) is intentionally **not** decided in this memo — the memo only tees it up.

## Dependencies & Sequencing

- **Feeds**: 046 (differential must match the locked claim), 047/048 (evaluation and build priorities follow the direction stack), 049 (decision brief cites the locked framing).
- **Fed by**: none — this is deliberately first; it must precede code per the thesis-direction plan.
