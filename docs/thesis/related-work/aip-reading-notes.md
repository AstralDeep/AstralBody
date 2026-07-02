# AIP — Structured Reading Notes

**Purpose:** evidence base for the "how DAF differs" related-work passage ([`daf-vs-aip.md`](daf-vs-aip.md)) and the citation record for the closest competitor. Every characterization below carries a source location. Framing source: [`../thesis-statement-memo.md`](../thesis-statement-memo.md) (spec 045).

## Sources read (and versions)

| Source | Identifier / version | Read from | Retrieved | Notes |
|---|---|---|---|---|
| arXiv paper | `arXiv:2603.24775`, "AIP: Agent Identity Protocol for Verifiable Delegation Across MCP and A2A", S. Prakash | arxiv.org abstract + metadata | 2026-07-02 | Submitted 27 Mar 2026. Abstract/companion referenced by the I-D as `[AIP-PAPER]`. PDF body not machine-extractable from sandbox; protocol substance read from the I-D (below), which the paper accompanies. |
| IETF Internet-Draft | `draft-prakash-aip-00` | ietf.org full HTML | 2026-07-02 | Individual Submission, Intended status **Informational**, published 27 Mar 2026, **expires 28 Sep 2026**. Full §1–§9 read. Primary substance source. |
| Reference implementation | PyPI `agent-identity-protocol` **0.3.0** (2026-05-09; also 0.1.0/0.1.1/0.2.0) | pypi.org project page | 2026-07-02 | Dev status **3-Alpha**, Apache-2.0. Sub-packages `aip_core`, `aip_token`, `aip_mcp`, `aip_a2a`; Rust impl in `rust/`; framework adapters via `aip-agents` (CrewAI/ADK/LangChain); TS SDK `aip-node`. "Under NIST NCCoE evaluation." |

> The thesis-direction doc assumed PyPI 0.1.1; the live package is **0.3.0** with a broader ecosystem (gateway, node SDK, OpenClaw/Claude-Code plugins). AIP is more mature and more actively developed than the July analysis assumed — material for the 049 timing analysis.

## What AIP is (source-located)

- **Problem statement.** MCP has no built-in auth; A2A uses self-declared identities with no attestation; OAuth 2.1 on MCP is single-hop only and "does not address multi-hop delegation chains" — "the delegation chain that led to the tool invocation is lost" (I-D §1). Motivating survey: ~2,000 MCP servers, all lacked authentication (I-D Abstract, §1).
- **IBCT — the core primitive.** Invocation-Bound Capability Tokens bind *identity, authorization, scope constraints, and provenance* into a single cryptographic artifact answering four questions per action: who authorized, through which chain, with what constraints at each hop, and what was the outcome (I-D §1, Abstract).
- **Identity scheme.** Two identifier types: DNS-based `aip:web:<domain>/<path>` with a signed identity document at `/.well-known/aip/<path>.json` (I-D §2.1, §2.3), and self-certifying `aip:key:ed25519:<multibase-pubkey>` for ephemeral agents (I-D §2.2). Ed25519 only; JCS canonicalization for document verification (I-D §2.3, §7.3).
- **Two token modes.**
  - *Compact* — a JWT (`typ: aip+jwt`, EdDSA/Ed25519) for **single-hop** only; REQUIRED claims include `scope`, `budget_usd`, `max_depth`, `exp`; TTL SHOULD be < 1 hour (I-D §3.1).
  - *Chained* — a **Biscuit** token of append-only blocks with **Datalog** policy evaluation for **multi-hop** (I-D §3.2). Block 0 = authority (root identity, capabilities, budget, max_depth, expiry); Blocks 1..N-1 = delegation (each narrows scope, signed by the delegator, mandatory non-empty `context`); Block N = optional completion block (I-D §3.2, §5.2, §6.1).
- **Attenuation (expressed + enforced).** "Scope can only narrow or remain equal, never widen," across **four dimensions**: tools (child ⊆ parent), budget (child ≤ parent), domains (child ⊆ parent), time (child `exp` ≤ parent `exp`). "Verifiers MUST check attenuation at every hop." Wildcard→specific allowed; specific→wildcard forbidden (I-D §3.3).
- **Policy profiles.** Simple (templated Datalog), Standard (curated, no recursion, bounded), Advanced (full Datalog, ≤1000 iterations, opt-in) (I-D §3.4).
- **Depth bounding.** `max_depth` default **3**, declared in Block 0; each delegation block +1; at depth == max_depth further delegation forbidden; compact `max_depth: 0` ⇒ no further delegation (I-D §5.1). Threat "delegation depth violation" is one of two AIP-unique detections (I-D §7.2).
- **Ephemeral agent grants.** For short-lived sub-agents a parent generates an Ed25519 keypair, forms an `aip:key:` identity, and appends a delegation block with scoped caps + short TTL (5 min RECOMMENDED); a parent MAY disable via `delegation.allow_ephemeral_grants=false` (I-D §5.3). **← directly relevant to DAF axis 4; see Contradiction Flags.**
- **Provenance / audit.** Completion block (signed by executor) carries `status`, `result_hash` (SHA-256), `verification_status` ∈ {self_reported, tool_verified, peer_verified, human_verified}, optional cost/tokens/duration, optional `ldp_provenance_id` (I-D §6.1). Three trust levels: self-reported / counter-signed / third-party attested (I-D §6.2). A completed chained token **is** a self-contained "audit token": tamper-evident, non-repudiable, **offline-verifiable** from identity-document public keys, answering the four questions without an external DB (I-D §6.3). **← relevant to DAF axis 2; see Contradiction Flags.**
- **Protocol bindings (transport).** All request-scoped headers/fields: MCP `X-AIP-Token:` header (or `X-AIP-Token-Ref:` by-reference >4KB) (I-D §4.1); A2A `metadata.aip_token` field, with the caller appending a delegation block before send and the receiver verifying the final block delegates to its own id (I-D §4.2); generic HTTP `Authorization: AIP <token>` (I-D §4.3). **No stateful/persistent-transport or session-bound re-derivation is specified** — bindings are per-request. (I-D §4 in full.)
- **Trust/verification model.** MCP verification is a 5-step per-request check (extract → verify signatures against issuer identity doc → check tool ∈ scope → validate chain constraints → inject identity) (I-D §4.1); A2A adds a 6th delegation-append/audience step (I-D §4.2). Verification is **offline** against cached identity-document public keys (5-min cache TTL; I-D §5.4). Revocation is de-emphasized in favor of short TTLs; key removal invalidates tokens; token-level CRLs deferred to v2 (I-D §5.5).
- **Evaluation reported.** I-D §7.2: "600 adversarial attempts in six attack categories, 100% rejection." Two categories (depth violation, empty-context audit evasion) "uniquely addressed by AIP's chained token structure." Reference-impl benchmarks (PyPI page): compact verify 0.189 ms Py / 0.049 ms Rust; chained +340–388 B/hop; 5-hop verify 0.447 ms Py; "~2.3 ms vs OAuth ~20 ms" for a 2-hop delegation; "100% rejection across 100 attack scenarios; 129 tests passing." Paper reports "0.086% of total latency" overhead in a "real multi-agent deployment."

## Reference-implementation surface — implemented vs specified

- **Implemented (per PyPI 0.3.0):** compact + chained tokens (`aip_token`), Ed25519 crypto + identity (`aip_core`), MCP binding + auth proxy `aip-proxy` (`aip_mcp`), A2A middleware + chain verification + delegation helpers (`aip_a2a`); Rust port; CrewAI/ADK/LangChain adapters; TS SDK. Delegation example shows `ChainedToken.create_authority(...).delegate(scopes⊆, budget≤, context=...)` and `authorize(tool, root_pubkey)` raising on out-of-scope (PyPI "Multi-agent delegation").
- **Specified but lighter in impl:** Datalog "Advanced" profile, IANA registrations (§8), token-by-reference SSRF specifics (§4.3/§7.4) are spec-level; maturity is **Alpha**, so treat impl as demonstrative, not production-hardened.
- **Distinct from the paper:** the I-D specifies the wire protocol; the paper `[AIP-PAPER]` reports the adversarial evaluation and deployment latency. The 600-attempt / 100%-rejection result is an I-D summary of the paper's experiment.

## What AIP does NOT claim or build (evidence-of-absence)

Each item is what the thesis novelty rests on; absence is sourced.

1. **No persistent/stateful transport binding.** §4 specifies only per-request header/field carriage over MCP/A2A/HTTP; there is no long-lived-session concept and no mid-session, per-tool-call re-derivation tied to a reasoning turn. (Absence across all of §4; §5.5 even prefers statelessness via short TTLs.)
2. **No deployed multi-tenant, real-user system.** Evaluation is an adversarial test battery + micro-benchmarks + "under NIST evaluation" (§7.2; PyPI). No multi-tenant production deployment with real users or a regulated-domain instantiation is claimed.
3. **No coupling to a code-generating self-extension loop.** §5.3 ephemeral grants credential a sub-agent the parent *spawns*; there is no notion of the platform *synthesizing an agent's code at runtime* and gating it (security analysis + isolated self-test + human approval) before it is born under delegation. (Absence in §5; the lifecycle is key/scope issuance, not capability creation.)
4. **No HIPAA/clinical audit-field conformance.** Provenance is generic (status/result_hash/verification_status); there is no mapping to a regulated audit-trail field checklist (§6 has no PHI/authorizer-of-record/policy-context-for-compliance framing).
5. **No PHI / data-plane authority gate.** Nothing governs what may enter long-term memory or leave a data boundary (out of scope entirely).

## Contradiction / refinement flags (feed spec 045 lock record)

- **FLAG A-1 (provenance).** AIP §6 is a genuine, sophisticated provenance mechanism (offline-verifiable audit tokens, 3 trust levels). The assumed "provenance is open white space" framing **overshoots**. Refinement: differentiate on *model* (DAF = deployment-integrated server-side hash-chained audit anchored to the human principal; AIP = portable per-token artifact), **not** on presence/absence. Recorded as Amendment A-1 in the 045 lock record.
- **FLAG A-2 (self-extension / dynamically-created agents).** AIP §5.3 ephemeral grants partially cover "delegation for dynamically created principals." Refinement: sharpen DAF axis 4 to "delegation bound to a *security-gated agent-synthesis loop*," not the broad "self-created principals." Recorded as Amendment A-2.
- **Axes that survived cleanly:** transport binding (§4 is stateless) and deployed-multi-tenant-HIPAA (no such AIP claim). No amendment needed; stated carefully (AIP is *evaluated*, just not *deployed multi-tenant*).

## Bibliography block (verified 2026-07-02)

- **[AIP-paper]** Prakash, S. "AIP: Agent Identity Protocol for Verifiable Delegation Across MCP and A2A." arXiv:2603.24775, submitted 27 Mar 2026. `https://arxiv.org/abs/2603.24775`. *Resolved.*
- **[AIP-ID]** Prakash, S. "Agent Identity Protocol (AIP): Verifiable Delegation for AI Agent Systems." `draft-prakash-aip-00`, IETF, Individual Submission, Informational, 27 Mar 2026, expires 28 Sep 2026. `https://datatracker.ietf.org/doc/draft-prakash-aip/`. *Resolved; status = individual (not WG-adopted), active (not expired) as of retrieval.*
- **[AIP-impl]** `agent-identity-protocol` 0.3.0, PyPI, Apache-2.0, 2026-05-09. `https://pypi.org/project/agent-identity-protocol/`. *Resolved.*
- **[niyikiza]** "Attenuating Authorization Tokens for Agentic Delegation Chains." `draft-niyikiza-oauth-attenuating-agent-tokens` — **now at -01** (thesis-direction doc cited -00); associated with the IETF **OAuth WG** mailing list (new-I-D announcement + Vienna topic call). AATs = RFC 9396 `authorization_details` profile, offline child-token derivation (no AS round-trip), monotonic attenuation over capability/depth/lifetime, cryptographic parent→child linkage to a root anchor, PoP at invocation. `https://datatracker.ietf.org/doc/draft-niyikiza-oauth-attenuating-agent-tokens/`. *Resolved; individual draft, active; status change 00→01 noted for spec 049.*
- **[WIMSE]** IETF WIMSE WG — `draft-ietf-wimse-arch`, `draft-ni-wimse-ai-agent-identity`, Workload Proof Token. Per AIP's own comparison table, WIMSE is characterized as two-party (no multi-hop A→B→C). *Existence corroborated via AIP I-D references and niyikiza's "complements WIMSE" positioning; full per-draft revision verification deferred to dissertation related-work (out of scope here, per spec 046 Assumptions).*
- **[related, opportunistic]** AIP "trust stack" siblings surfaced on the PyPI page: LDP (arXiv 2603.08852), Provenance Paradox (2603.18043), DCI (2603.11781) — noted, not verified; not required by the differential.

*Not independently re-verified here (thesis-direction §7 leads, out of scope per spec 046): arXiv 2604.23280, Progent, and the AIP trust-stack siblings.*
