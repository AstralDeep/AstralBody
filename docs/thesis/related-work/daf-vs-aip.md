# How DAF Differs from AIP — Related-Work Passage

**Status:** dissertation-ready draft. Drop into the related-work chapter; edit only citation keys to the final style. Evidence base: [`aip-reading-notes.md`](aip-reading-notes.md). Framing source: [`../thesis-statement-memo.md`](../thesis-statement-memo.md). Word budget: 250–350 (hard cap 400).

---

The closest published competitor to the Delegated Authority Framework (DAF) is the Agent Identity Protocol (AIP) [Prakash 2026a; Prakash 2026b], whose Invocation-Bound Capability Tokens fuse identity, attenuated authorization, and provenance into an append-only chain with a compact single-hop JWT mode and a Biscuit/Datalog chained mode. AIP is strong precisely where a protocol should be: its Datalog policy profiles express richer constraints than DAF's scope sets, it specifies bindings across MCP, A2A, and HTTP, and its completion blocks yield portable, offline-verifiable audit tokens. We treat AIP as convergent validation that attenuated, provenance-bearing agent delegation is the right model, and differentiate on four systems axes rather than on the token format.

First, **transport binding.** AIP's bindings are per-request headers over stateless transports (§4); DAF re-derives further-attenuated authority *per tool call over a single persistent WebSocket*, tied to the ReAct turn, without a fresh authorization round-trip. Second, **deployment.** AIP reports an adversarial test battery and micro-benchmarks; DAF is instantiated in a multi-tenant, HIPAA-motivated system with real users, where enforcement is measured in production rather than in a harness. Third, **provenance.** AIP's audit lives inside the token; DAF anchors each action to the authorizing human through a server-side, hash-chained audit log spanning the whole deployment, mapped field-by-field onto a clinical audit-trail checklist. Fourth, **self-extension.** AIP's ephemeral grants credential a sub-agent that already exists (§5.3); DAF issues an attenuated delegation to an agent the platform *synthesizes at runtime*, only after that agent clears a fail-closed security gate and isolated self-test. In short, AIP specifies the credential; DAF contributes the deployed, transport-bound, self-extending system that carries one.

---

*Body word count: ~300 (within budget). Citation placeholders: [Prakash 2026a] = arXiv:2603.24775; [Prakash 2026b] = draft-prakash-aip-00.*

## Appendix — Claim map (AIP ↔ DAF ↔ remaining differentiator)

Backing table for the passage. Each AIP cell cites a source location; each DAF cell names a concrete system artifact (FR-006). "No-strawman" column records where AIP is equal or stronger.

| Axis / capability | AIP (source-located) | DAF (system artifact) | Differentiator / honest gap |
|---|---|---|---|
| **Transport** | Per-request carriage: MCP `X-AIP-Token` (§4.1), A2A `metadata.aip_token` (§4.2), HTTP `Authorization: AIP` (§4.3); no session concept | Per-tool-call re-derivation over persistent WebSocket ReAct loop; `orchestrator/delegation.py` + WS dispatch; DPoP (RFC 9449) `cnf.jkt` binding | **DAF-unique:** stateful, mid-session, per-call attenuation on a long-lived socket. AIP not equipped for it. |
| **Attenuation rule** | 4 dimensions — tools⊆, budget≤, domains⊆, time≤; verifier checks every hop (§3.3) | scope-level + `tool:<name>` claims, `exp` cap, no-escalation (spec 048 invariants over `act` chain) | **AIP stronger on expressiveness** (budget + domains + Datalog). DAF matches tools/time; adds transport-bound enforcement. No-strawman: cite AIP's richer policy. |
| **Chained token format** | Biscuit + Datalog, append-only blocks, policy profiles (§3.2, §3.4) | Nested RFC 8693 `act` claims in existing JWT/DPoP construction (spec 048) | **AIP stronger on policy language.** DAF deliberately stays in RFC 8693 to keep the contribution transport+deployment, not a competing format (see 046→048 rationale). |
| **Depth bound** | `max_depth` default 3, per-block +1, forbidden at limit (§5.1) | configurable max depth, enforced at mint + verify, recorded on token + audit (spec 048 FR-005) | **Parity** (convergent). DAF adds depth on the tamper-evident audit event. |
| **Deployment / evaluation** | 600 adversarial attempts, 100% rejection (§7.2); micro-benchmarks; "under NIST evaluation" (Alpha impl) | Multi-tenant UKY sandbox, real users; ASR ablation harness (spec 047); deployment-log enforcement study | **DAF-unique:** deployed multi-tenant real-user + HIPAA-motivated measurement. No-strawman: AIP *is* evaluated adversarially. |
| **Provenance / audit** | In-token completion blocks; 3 trust levels; offline-verifiable audit tokens (§6) | Server-side HMAC-SHA256 hash chain `audit/pii.py::chain_hmac`, `repository.py::verify_chain`; `act` chain → human `sub` | **Different model, not clean win** (Amendment A-1). DAF = deployment-wide, human-anchored, PHI-gated; AIP = portable, self-contained. |
| **Dynamically-created agents** | Ephemeral key grants for spawned sub-agents (§5.3) | Code-synthesis rail (027/035): draft → `VirtualWebSocket` self-test → admin approval → DAF-scoped promotion | **DAF-unique** narrowed claim (Amendment A-2): delegation bound to gated *capability creation*, not just key issuance. |
| **HIPAA conformance** | Generic provenance; no regulated-field mapping | `act` chain + hash-chained audit + `personalization/phi_gate.py` mapped to §2.5 audit-field checklist | **DAF-unique.** |
| **Revocation** | Prefers short TTL; key removal invalidates; token CRL deferred to v2 (§5.5) | Offline-tolerant revocation queue + short-lived delegation tokens (`offline_grant.py`, existing) | **Parity/convergent.** |

*Every DAF-side artifact above is a real module in this repository; the transport, provenance, and self-extension rows are the load-bearing differentiators and are the ones spec 048 makes recursive.*
