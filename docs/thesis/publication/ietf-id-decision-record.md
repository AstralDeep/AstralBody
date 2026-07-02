# IETF I-D — Decision Record

Companion to [`ietf-id-decision.md`](ietf-id-decision.md). The decision is a **joint** call (Sam + advisor). This record is the durable outcome; until it carries a ratified outcome + date, the decision is **pending**.

## Current status

| Field | Value |
|---|---|
| **Status** | **PENDING joint ratification** |
| **Standing recommendation** | **GO** — individual I-D first, positioned for WIMSE/OAuth-WG feedback |
| Deciders | Samuel E. Armstrong + Dr. Bumgardner |
| Date prepared | 2026-07-02 |
| Date decided | — |
| Outcome | — (go / no-go / defer-with-trigger) |

> **How to finalize:** at the advisor meeting, set *Outcome* and *Date decided*. If **go**, fill the Go-details table and the scope outline ([`id-scope-outline.md`](id-scope-outline.md)) becomes active. If **no-go/defer**, delete/So-mark the scope outline (FR-008 requires it absent on no-go/defer) and record the trigger.

## If GO — details to record

| Field | Value (fill on ratification) |
|---|---|
| Target venue (first) | recommended: **individual submission**, written for WIMSE/OAuth adoptability |
| Target submission window | recommended: **Oct–Nov 2026** (≥4–5 months pre-defense) |
| Working title | e.g. *"Transport-Bound Attenuating Delegation Chains for Agent Systems"* |
| Authoring owner | Sam (draft), advisor review |
| Priority constraint | **Direction B (evaluation) has priority; the I-D must not delay it** |

## If NO-GO or DEFER — record

| Field | Value (fill on ratification) |
|---|---|
| Rationale | — |
| Defer trigger (if defer) | e.g. "revisit if `draft-niyikiza` is WG-adopted" or "if spec 048 lands its flag-on integration by <date>" |
| Scope outline | must be **absent** (FR-008) — delete `id-scope-outline.md` and note here |

## Consistency check (FR-007)

The decision is a **positioning move within** the locked framing (spec 045), not a reframing. An I-D specifies the delegation *mechanism* (spec 048); it does **not** restate the thesis spine, and it stays within the "align/interoperate, don't compete on wire formats" deprioritization. No tension with the locked framing was found. Any tension surfaced later must be recorded here, not buried.

## Dependencies honored

- **Fed by spec 046** — the verified competitor status (AIP individual/Informational/active/expires 2026-09-28; niyikiza -01/OAuth-WG-engaged; WIMSE active) is reflected in the brief; the decision is **not** finalized on unverified citations.
- **Fed by spec 048** — the mechanism is real (built + property-tested green), so the brief reflects maturity rather than plan. The flag-on integration (048 T014) is the one open piece; if it is a decision input, note it in the trigger.

## Decision history

| Attempt | Date | Outcome | Notes |
|---|---|---|---|
| 1 | 2026-07-02 | Pending (recommendation: GO) | Brief prepared on verified 046 evidence + working 048 mechanism; awaiting joint ratification. |
