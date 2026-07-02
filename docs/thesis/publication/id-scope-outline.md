# I-D Scope Outline — **CONTINGENT on a GO ratification**

> **Status: provisional.** This outline exists because the standing recommendation is **GO** and it de-risks the follow-on authoring (spec 049 US3). It is **not** an authorization to author. Per FR-008 it becomes active only when [`ietf-id-decision-record.md`](ietf-id-decision-record.md) records a **go**; on a **no-go/defer** ratification this file MUST be deleted and its absence noted in the record.

**Base extended:** RFC 8693 (OAuth 2.0 Token Exchange, the `act`-claim delegation semantics) and RFC 9449 (DPoP, proof-of-possession). **Substance:** spec 048 (mechanism) + spec 046 (positioning). **This outline does not author the draft.**

## Working title

*Transport-Bound Attenuating Delegation Chains for Agent Systems* (placeholder).

## Intended sections

1. **Introduction & motivation** — multi-hop agent delegation over persistent transports; the gap OAuth/WIMSE name (derive-a-narrower-token-and-pass-downstream). *Informative.*
2. **Terminology** — BCP 14; principal, actor, delegation chain, attenuation, depth. *Normative definitions.*
3. **Nested `act` delegation token** — extending RFC 8693 §4.1 `act` to a nested chain terminating at the human `sub`; claim set (`delegation_depth`, `max_delegation_depth`); DPoP (RFC 9449) binding carried per hop. *Normative.*
4. **Attenuation invariants** — monotonic scope narrowing (child ⊆ parent), no-escalation (no scope/tool/audience/flag absent from parent), expiry cap (child `exp` ≤ parent), depth bound; verifier obligations at every hop. *Normative — the core.*
5. **Transport binding** — per-tool-call re-derivation over a persistent (stateful) session; per-call fail-closed denial without session teardown. *Normative + informative (the differentiator vs. AIP's per-request headers).*
6. **Provenance / completion records** — a per-hop record linking parent→child into a tamper-evident chain; the audit fields (acting agent, human authorizer, operation, scope/policy context, timestamp). *Informative → maps to deployment audit; normative field set.*
7. **Security considerations** — threat model (scope widening, escalation, over-depth, replay, forged chain), chain-of-custody (child cannot outlive/exceed/survive-revocation-of parent). *Normative.*
8. **Relationship to prior/parallel work** — position vs. `draft-prakash-aip` (IBCT/Biscuit) and `draft-niyikiza` (AATs/RFC 9396); convergent model, differentiated on transport binding + deployment. *Informative (from spec 046).*
9. **IANA considerations** — claim registrations if any. *Normative-if-needed.*

## Normative vs informative scope

- **Normative:** the nested-`act` token structure, the four attenuation invariants + verifier obligations, the depth bound, the per-hop provenance field set, chain-of-custody rules.
- **Informative:** the persistent-transport binding rationale, deployment/audit mapping, and the positioning section.

## Explicitly OUT of scope for the I-D

- Astral-specific deployment details, the orchestrator, and the UKY instantiation.
- **ROTE** (device/UI adaptation) and **living memory** — different thesis planes, not protocol.
- A competing token *format*: the draft stays within RFC 8693 `act` + RFC 9449 DPoP and does **not** specify a Biscuit/Datalog policy language (that is AIP's lane; see spec 046).
- Discovery / registry mechanisms (deprioritized in the framing).

## Traceability

- Mechanism → spec 048 (`orchestrator/delegation.py`: `mint_child_delegation`, `verify_delegation_chain`, `authorize_chained_tool_call`, `delegation_chain_audit_record`; property tests green).
- Positioning → spec 046 (`daf-vs-aip.md` + reading notes).
- Base RFCs → 8693 (token exchange / `act`), 9449 (DPoP), and 9396 (RAR, as `draft-niyikiza` uses) referenced for comparison.
