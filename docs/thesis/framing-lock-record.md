# Framing-Lock Record

Companion to [`thesis-statement-memo.md`](thesis-statement-memo.md). The framing is **locked** only when this record carries an explicit advisor decision bound to a specific memo revision. Until then the framing is **proposed**.

## Current status

| Field | Value |
|---|---|
| **Status** | **PROPOSED — awaiting advisor decision** |
| Memo revision under review | `docs/thesis/thesis-statement-memo.md` @ initial commit (spec 045) |
| Decider | Dr. Bumgardner (advisor) |
| Author | Samuel E. Armstrong |
| Date proposed | 2026-07-02 |
| Date decided | — |
| Decision | — (approved / approved-with-edits / rejected) |

> **How to lock:** after the advisor meeting, fill the *Decision*, *Date decided*, and (if edited) the *Edits incorporated* rows below, and record the approved memo's git ref or content hash. A partial lock (spine approved, one axis contested) is recorded per element in the *Per-element status* table so downstream specs touching a contested element are flagged before work starts.

## Per-element status (for partial locks)

| Element | Memo section | Status | Notes |
|---|---|---|---|
| FR-001 Thesis spine (§0 verbatim) | "The claim I want to defend" | Proposed | — |
| FR-002 Stop/start reframing (§2.1) | "What changed…" | Proposed | — |
| FR-003 Axis 1 — transport binding | Axis 1 | Proposed | Survived 046 pre-read strongly (AIP bindings are stateless HTTP headers). |
| FR-003 Axis 2 — provenance | Axis 2 | Proposed | **Refined** — see Amendment A-1. |
| FR-003 Axis 3 — deployed multi-tenant HIPAA | Axis 3 | Proposed | AIP reports benchmarks/NIST evaluation but no multi-tenant real-user deployment; axis holds, stated carefully. |
| FR-003 Axis 4 — delegation for self-created agents | Axis 4 | Proposed | **Refined** — see Amendment A-2. |
| FR-005 One-spine/three-planes + direction stack | "The shape of the thesis" | Proposed | — |

## Evidence log & amendments

The 046 citation/verification pass was run on 2026-07-02 *before* the advisor meeting (the AIP paper, its Internet-Draft, and the reference implementation were read from live sources). Two axes were sharpened to stay honest against what AIP actually specifies. Neither breaks the framing; both make it defensible under committee questioning.

- **Amendment A-1 (provenance axis).** AIP §6 specifies *completion blocks*, three verification trust levels, and self-contained, offline-verifiable "audit tokens." Provenance is therefore **not** clean white space. The memo does not claim AIP lacks provenance; it differentiates on *model*: DAF's provenance is a deployment-integrated, server-side **hash-chained audit** (`audit/pii.py::chain_hmac`, `repository.py::verify_chain`) anchoring each action to the authorizing human across a running multi-tenant system, complementary to AIP's portable per-token artifact. The memo wording ("integrated into a running deployment rather than a portable token artifact") already reflects this.
- **Amendment A-2 (self-extension axis).** AIP §5.3 specifies *ephemeral agent grants* — a parent mints a short-lived key + delegation block for a sub-agent. So "delegation for dynamically created principals" is partially covered. The memo therefore sharpens the axis to **delegation bound to a code-generating, security-gated agent-synthesis loop** (the 027/035 create → self-test → admin-approve → DAF-scoped promotion rail), which is distinct from issuing a credential to a sub-agent that already exists. Memo axis 4 already carries this wording.

These amendments are the substance of spec 046 and must be presented to the advisor alongside the memo. If the advisor rejects a refined axis, the impacted downstream specs are 048 (self-extension binding, Story 5) and 049 (I-D positioning); flag them before starting.

## Decision history

| Attempt | Date | Outcome | Rationale / edits | Memo ref |
|---|---|---|---|---|
| 1 | 2026-07-02 | Proposed | Initial memo authored; 046 pre-read amendments A-1/A-2 folded in. | spec 045 initial |

## Downstream-impact checklist (run on any post-lock framing change)

- [ ] 046 differential still consistent with the locked axes (re-read `daf-vs-aip.md`).
- [ ] 048 Story 5 (self-extension binding) unaffected by any change to axis 4.
- [ ] 049 decision brief positioning still consistent with the locked spine.
- [ ] `THESIS-DIRECTION-2026-07.md` annotated if the advisor materially rewrote the §0 spine.
