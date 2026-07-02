# Feature Specification: IETF Internet-Draft Decision Brief for the Delegation Work

**Feature Branch**: `049-ietf-id-decision`
**Created**: 2026-07-02
**Status**: Draft
**Input**: User description: "Decide with your advisor whether the delegation work goes out as an IETF I-D (recommended — high committee signal, low marginal cost)." (Item 5 of [THESIS-DIRECTION-2026-07.md](../../THESIS-DIRECTION-2026-07.md) §8; §5 publication mapping.)

## Overview

The thesis-direction analysis recommends publishing the recursive-delegation work as an **IETF Internet-Draft** that cites and positions against `draft-prakash-aip` and `draft-niyikiza`: high signal for a systems/security committee (Calvert/Fei), low marginal cost because the work is being done anyway, and it converts "aligned with an emerging IETF direction" from a scoop risk into a credential. This is a **decision that belongs to Sam and the advisor**, not something to execute unilaterally — so this feature produces the **decision brief** that makes the call crisp, records the decision, and (only if the decision is go) defines the minimal I-D scope. It is a documentation/decision feature: **no product code changes**, and it explicitly does not write the draft.

## Clarifications

### Session 2026-07-02 (resolved by informed default — confirm or override during `/speckit-clarify`)

- Q: Does this feature write the Internet-Draft? → A: **No.** It produces the decision brief and, conditionally, an I-D *scope outline* + effort/timeline estimate. Authoring the actual `.xml`/`.md` draft is a follow-on only triggered if the decision is go; keeping it separate avoids sinking effort before the advisor agrees.
- Q: Who decides? → A: **Sam + advisor jointly.** The brief is decision support; the recorded outcome captures their joint call (go / no-go / defer-with-trigger) with rationale and, if go, target venue (WIMSE WG vs. OAuth WG vs. independent submission) and timeline against the ~8-month horizon.
- Q: Where does it live? → A: `docs/thesis/publication/ietf-id-decision.md` (brief + decision record); a conditional `docs/thesis/publication/id-scope-outline.md` only if go. Same `docs/thesis/` area as specs 045/046.
- Q: What makes the recommendation credible rather than a restatement of the thesis doc? → A: It must reflect the **actual state** of the competing drafts (verified in spec 046 — are they individual or WG-adopted, active or expired?) and of the recursive-delegation build (spec 048 — how much is real), because both change the cost/benefit materially.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce the go/no-go decision brief (Priority: P1)

Sam writes a one-to-two-page brief laying out the case for and against submitting an I-D, grounded in the verified state of AIP/niyikiza/WIMSE and the actual maturity of the recursive-delegation work, so the advisor can make the call in one meeting.

**Why this priority**: The decision, made deliberately with the advisor, unblocks (or closes) a publication track with outsized committee signal. A vague "we should maybe do an I-D" is not a decision; the brief forces it.

**Independent Test**: Read the brief; it states the recommendation, the strongest case against, the target venue options, the marginal cost over work already planned, and exactly what the advisor is being asked to decide.

**Acceptance Scenarios**:

1. **Given** the brief, **When** read, **Then** it states the recommendation (go, per the thesis-direction analysis) and the honest case against (IETF process overhead, review load, the risk of committing to a wire spec that later diverges from the implementation).
2. **Given** the brief, **When** read, **Then** it identifies candidate venues (WIMSE WG, OAuth WG, or independent/individual submission) with one line each on fit and what adoption there would signal.
3. **Given** the brief, **When** read, **Then** it quantifies **marginal** cost — what an I-D needs beyond what specs 046/048 already produce (differential, mechanism, invariants) — to substantiate "low marginal cost."
4. **Given** the brief, **When** read, **Then** it reflects the **verified** status of `draft-prakash-aip` and `draft-niyikiza` (from spec 046) — individual vs. adopted, active vs. expired — because that status changes both the opportunity and the timing.
5. **Given** the brief, **When** read, **Then** it maps the decision to the ~8-month horizon: latest submission date that still yields committee-visible signal before the defense, and the cut-losses point.

---

### User Story 2 - Record the joint decision (Priority: P1)

After the advisor discussion, the outcome — go, no-go, or defer-with-explicit-trigger — is recorded with rationale, date, and (if go) venue and timeline, so the decision is a durable, checkable fact.

**Why this priority**: The named deliverable is a *decision*, not a brief. Without a recorded outcome the item stays perpetually open.

**Independent Test**: Inspect the decision record; it states the outcome, the date, both deciders, the rationale, and any conditions/triggers.

**Acceptance Scenarios**:

1. **Given** a go decision, **When** recorded, **Then** it names target venue, target submission window, the draft's working title, and who owns authoring.
2. **Given** a no-go or defer, **When** recorded, **Then** it states the rationale and, for defer, the explicit trigger that would reopen it (e.g., "revisit if niyikiza is WG-adopted" or "if 048 lands its enforcement tests by <date>").
3. **Given** the decision, **When** made, **Then** it is consistent with the locked framing (spec 045) — an I-D is a positioning move within that framing, not a reframing.

---

### User Story 3 - Conditionally outline the I-D scope (Priority: P3)

Only if the decision is go, a short scope outline defines what the draft would and would not specify — leaning on spec 048's mechanism (nested `act` chains, attenuation invariants, depth bound, transport binding) and spec 046's positioning — so authoring can start from an agreed skeleton, not a blank page.

**Why this priority**: De-risks the follow-on authoring effort and makes "low marginal cost" real, but only matters conditional on go. P3 and gated.

**Independent Test**: If go, the outline exists and lists the draft's sections, its normative scope (what it specifies vs. describes), and its relationship to RFC 8693/9449 and to AIP; if no-go/defer, the outline is intentionally absent and the decision record says so.

**Acceptance Scenarios**:

1. **Given** a go decision, **When** the outline is written, **Then** it enumerates intended sections and states normative vs. informative scope, explicitly citing RFC 8693/9449 as the base it extends.
2. **Given** the outline, **When** read, **Then** it names what is out of scope for the I-D (e.g., Astral-specific deployment, ROTE, memory) so the draft stays a focused protocol document.
3. **Given** a no-go/defer, **When** checked, **Then** no scope outline is produced and the absence is deliberate and recorded.

### Edge Cases

- Advisor says go but the venue's submission window doesn't fit the 8-month horizon → the brief's timeline analysis surfaces this; the decision may become "author the draft as a thesis artifact, submit opportunistically" rather than committing to a specific IETF meeting.
- Spec 046 reveals AIP/niyikiza have been WG-adopted and substantially overlap the intended draft → the brief re-weighs toward "contribute to/position against the adopted work" vs. a competing individual draft; the recommendation is updated from evidence, not assumed.
- Spec 048 slips and the mechanism isn't real by decision time → the brief flags that an I-D asserting an unimplemented mechanism is weaker; the decision may defer with a trigger tied to 048's completion.
- Decision is go but authoring competes with the evaluation overhaul (Direction B) for time → the brief states the opportunity cost explicitly so the advisor trades off with eyes open (B is non-negotiable per §3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The brief MUST present a clear recommendation with both the case for and the strongest case against submitting an I-D.
- **FR-002**: The brief MUST identify candidate venues (WIMSE WG, OAuth WG, independent submission) with a one-line fit assessment and signal value for each.
- **FR-003**: The brief MUST quantify the **marginal** cost of the I-D over work already scoped in specs 046 and 048, substantiating the "low marginal cost" claim.
- **FR-004**: The brief MUST reflect the **verified** status of `draft-prakash-aip` and `draft-niyikiza` (adoption + active/expired) as established by spec 046, and MUST state how that status affects the recommendation.
- **FR-005**: The brief MUST map the decision onto the ~8-month defense horizon, giving a latest-useful submission window and a cut-losses point.
- **FR-006**: A decision record MUST capture the joint outcome (go / no-go / defer-with-trigger), date, both deciders, and rationale; a go MUST additionally record venue, submission window, working title, and authoring owner.
- **FR-007**: The decision MUST be consistent with the locked framing (spec 045); any tension MUST be surfaced, not buried.
- **FR-008**: A conditional I-D scope outline MUST be produced **iff** the decision is go, citing RFC 8693/9449 as the extended base and specs 046/048 as the substance, and stating explicit out-of-scope items; on no-go/defer it MUST be deliberately absent and that noted.
- **FR-009**: This feature MUST NOT author the Internet-Draft itself and MUST NOT change any product code, configuration, schema, or dependency. Documentation/decision only.

### Key Entities

- **Decision brief**: the advisor-facing for/against + venue + cost + timing analysis; decision support.
- **Decision record**: the durable joint outcome with rationale and (if go) venue/timeline/owner.
- **I-D scope outline** (conditional): the agreed skeleton for a future draft; exists only on a go decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The brief exists, is ≤ 2 pages, and contains recommendation, case-against, venue options, marginal-cost estimate, verified-competitor status, and the horizon/timing analysis.
- **SC-002**: A decision record exists with an explicit outcome, date, both deciders, and rationale (and venue/timeline/owner if go).
- **SC-003**: If go, an I-D scope outline exists and is traceable to specs 046/048 and RFC 8693/9449; if no-go/defer, it is absent by design and the record says so.
- **SC-004**: The decision is consistent with spec 045's locked framing (cross-checked).
- **SC-005**: Zero product-code delta (diff confined to `docs/thesis/` and `specs/049-*`).

## Assumptions

- Spec 046 has verified the competing drafts' status before this decision is finalized; if 046 is not yet done, the brief is drafted but the decision is explicitly held pending that verification (a stated dependency, not a guess).
- Spec 048's maturity is known at decision time (even if partial); the brief reflects reality rather than the plan.
- The advisor relationship and the ~8-month horizon are as stated in THESIS-DIRECTION-2026-07.md.
- Actually authoring and submitting the I-D, if chosen, is a separate follow-on effort (its own future spec), not part of this feature.

## Dependencies & Sequencing

- **Fed by**: 045 (locked framing), 046 (verified competitor status + differential), 048 (the mechanism an I-D would specify and its maturity).
- **Feeds**: potentially a future "author IETF I-D" spec (only if the decision is go); the publication-mapping section of the thesis.
- **Note**: This is the last of the five §8 items and is deliberately decision-gated on the other four — it should be revisited once 046 and 048 have produced their evidence.
