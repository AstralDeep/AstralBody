# IETF Internet-Draft — Decision Brief

**Question:** Should the recursive-delegation work (Direction A / spec 048) be published as an IETF Internet-Draft that cites and positions against `draft-prakash-aip` and `draft-niyikiza`?
**Decision owners:** Sam + advisor (Bumgardner), jointly. **Prepared:** 2026-07-02. **Framing source:** [`../thesis-statement-memo.md`](../thesis-statement-memo.md). **Evidence:** [`../related-work/aip-reading-notes.md`](../related-work/aip-reading-notes.md) (spec 046), spec 048 mechanism (built + property-tested).

## Recommendation: **GO** — author an individual I-D now, positioned for WIMSE/OAuth-WG feedback

The recommendation from the July analysis survives contact with verified evidence and a working mechanism: the marginal cost is low because the substance already exists (spec 048's mechanism + spec 046's differential), and the committee signal is high for a protocols/security committee (Calvert/Fei). Convergence with an active IETF direction is a credential, not a threat.

## The case for

- **High committee signal.** A published I-D that cites and differentiates from `draft-prakash-aip`/`draft-niyikiza` demonstrates the work is standards-relevant — exactly what Calvert/Fei respect.
- **Low marginal cost.** The draft is largely a repackaging of work already done: spec 048 supplies the mechanism (nested RFC 8693 `act` chains, the monotonic-attenuation / no-escalation / actor-chain-completeness / depth-bound invariants, transport binding, per-hop provenance), and spec 046 supplies the related-work positioning. No new research is required to draft it.
- **Turns the scoop into a credential.** Framing DAF as the *transport-bound, deployed, provenance-integrated* instance of the model the drafts describe converts "aligned with an emerging IETF direction" from a risk into evidence of relevance.
- **The venue is live.** `draft-niyikiza` is active on the OAuth-WG list with a Vienna topic call; WIMSE is an active WG. The door is open now.

## The strongest case against

- **Opportunity cost vs. Direction B.** Drafting competes for time with the evaluation overhaul, which is non-negotiable (§3). B must not slip for an I-D.
- **Spec-vs-implementation divergence risk.** Committing to wire-format text that later diverges from the implementation is a maintenance liability; mitigated by keeping the draft *Informational* and scoped to the mechanism spec 048 actually implements.
- **Traction risk against maturing competitors.** AIP is comparatively mature (PyPI 0.3.0, "under NIST NCCoE evaluation") and `draft-niyikiza` is WG-engaged. An individual competing draft may get limited adoption traction — so the value is primarily *citable credential + positioning*, not winning a standards race (consistent with the framing's "align, don't compete" deprioritization).

## Candidate venues

| Venue | Fit | What adoption/engagement would signal |
|---|---|---|
| **WIMSE WG** | Best charter fit (workload/agent identity). The WIMSE arch text names the exact "derive a narrower token and pass it downstream" gap DAF fills. | Strongest signal; but the draft must fit WIMSE scope (identity/workload), foregrounding the delegation-chain-over-transport angle. |
| **OAuth WG** | Natural home for an RFC 8693/9396 attenuation-chain draft; where `draft-niyikiza` lives. | High signal in the token-exchange community; requires explicit positioning relative to `draft-niyikiza` (complement, not duplicate). |
| **Independent / individual submission** | Lowest barrier, fastest, no WG gating. | Weaker than WG adoption, but sufficient as a citable thesis artifact and a positioning anchor; the recommended **first** step. |

**Recommended path:** individual submission first (fast, citable), written to be adoptable by WIMSE or OAuth if the WG shows interest — position relative to `draft-niyikiza` (OAuth) and the WIMSE agent-identity work.

## Marginal cost over specs 046 + 048

The I-D needs, *beyond what 046/048 already produce*: (1) RFC-style prose for the identity/token/attenuation/depth/provenance sections mapped onto spec 048's mechanism; (2) IETF boilerplate (BCP 14, security considerations, IANA if any); (3) an explicit positioning section against AIP/niyikiza drawn from spec 046. Estimate: **~1–2 weeks of focused writing**, no new research — substantiating the "low marginal cost" claim. (See the scope outline, produced conditionally.)

## Verified competitor status (from spec 046, retrieved 2026-07-02)

- **`draft-prakash-aip-00`** — individual submission, **Informational**, active, **expires 2026-09-28**; **not WG-adopted**. Mature reference impl (PyPI 0.3.0), "under NIST NCCoE evaluation."
- **`draft-niyikiza-oauth-attenuating-agent-tokens`** — now at **-01** (was -00), individual, **OAuth-WG-engaged** (list announcement + Vienna topic call); **not yet WG-adopted**.
- **WIMSE** — active WG (`draft-ietf-wimse-arch`, `draft-ni-wimse-ai-agent-identity`, WPT).
- **Implication:** the space is individual-draft-heavy with **no single adopted standard yet** — a window where a well-positioned, *deployed + transport-bound* draft can differentiate and possibly feed WG discussion. This favors acting sooner rather than later.

## Mapping to the ~8-month horizon

- **Defense ≈ March 2027.** For committee-visible signal, the draft should be submitted and (ideally) have drawn at least list feedback before the defense.
- **Latest-useful submission window:** ~**4–5 months before defense** (≈ Oct–Nov 2026) so it is citable and any WG feedback is visible; note the AIP draft's own 2026-09-28 expiry as a marker of how fast this space moves.
- **Cut-losses point:** if not drafted by ~**2 months before defense**, ship it as an **individual thesis artifact** (submit opportunistically) rather than chasing WG adoption — never let it block Direction B.

## What the advisor is being asked to decide

Ratify **GO / no-go / defer-with-trigger**; if go, confirm the **first venue** (recommended: individual submission), the **submission window**, the **working title**, and the **authoring owner**, on the explicit understanding that **Direction B has priority** and the I-D must not delay it. The recorded outcome lives in [`ietf-id-decision-record.md`](ietf-id-decision-record.md).
