# Thesis Framing — Advisor Memo

**To:** Dr. Bumgardner **From:** Samuel E. Armstrong **Date:** 2026-07-02
**Re:** Locking the thesis framing before the next build cycle · **Verified as of:** 2026-07-02

## The claim I want to defend

> *Astral shows that autonomous, self-extending, multi-device agent systems can be made accountable and safe — by binding every delegated action to an attenuated, provenance-bearing authority token over a persistent transport, and by making the UI, the agent-creation loop, and long-term memory all operate inside that same fail-closed envelope — and it demonstrates this in a deployed, benchmarked system.*

## What changed since the qualifying exam

The standards world moved *toward* our delegation model, not past it. Attenuated, provenance-bearing delegation for agents is now an active IETF item and a published academic protocol with reference code. This is convergence, not a scoop — **if we reposition now.**

**Stop** claiming "a novel delegation protocol." **Start** claiming **"the first implemented, deployed, and evaluated system that binds attenuated, provenance-bearing agent delegation to a persistent transport and to a self-extension loop, and measures its enforcement."** The contribution becomes a *systems* result — exactly what the protocol papers lack.

## Why the claim still stands — four axes of difference

1. **Transport binding.** The competing work is HTTP-request-shaped: one credential per call, presented in a header. Ours re-derives narrowed authority *per tool call over a single long-lived WebSocket*, tied to the reasoning turn. Nobody owns this.
2. **Provenance.** Every action is anchored to the authorizing human through a hash-chained, tamper-evident audit trail — a completion record for the delegation, integrated into a running deployment rather than a portable token artifact.
3. **Deployed, multi-tenant, HIPAA-motivated instantiation.** We measure enforcement on a real system with real users at UKY. A protocol with a reference implementation cannot make the *deployment* claim.
4. **Delegation for agents the system creates itself.** When the orchestrator synthesizes and promotes a new agent, that agent is born under an attenuated, audited delegation only after passing a fail-closed security gate — delegation coupled to a code-generating self-extension loop, not merely a short-lived key for a pre-existing sub-agent.

## Why convergence is a strength

Aligning with an emerging IETF direction (`draft-prakash-aip`, `draft-niyikiza-oauth-attenuating-agent-tokens`, the WIMSE agent-identity work) *validates* that this is the right model. For a systems-and-security committee, building the deployed, measured instance of a model the standards bodies are still drafting is a credential, not a liability. We cite them as convergent prior art and differentiate on the four axes above.

## The shape of the thesis: one spine, three enforced planes

One envelope, three planes that all fail closed and are all measured: **authority** (the delegation framework), **presentation** (server-side semantic device adaptation), and **autonomy** (self-extension and long-term memory). "Advance all three" becomes "three planes of one envelope" — a thesis, not a feature list.

**Direction stack for the ~8 months to defense:**
- **A — primary:** recursive, provenance-bearing delegation over the persistent transport (the defensible core).
- **B — primary, parallel, non-negotiable:** the evaluation overhaul — standard adversarial benchmarks and attack-success-rate reduction, turning the weakest chapter into the strongest.
- **C — rescue the UI contribution:** re-anchor on server-side adaptation (the one thing the UI standards explicitly do not do).
- **D / E — time-boxed supporting evidence:** safe self-extension and gated living memory, one chapter each.

**Explicitly deprioritized:** dynamic agent discovery, net-new generative-UI primitives, and racing anyone on wire-format standardization. We align and interoperate; we do not compete there.

## What I'm asking

1. **Approve the reframing** — the stop/start claim and the four axes as the thesis spine.
2. **Calendar the publication question** — whether the delegation work also goes out as an IETF Internet-Draft. I will bring a short decision brief; that call is deliberately deferred to its own meeting, not made here.
