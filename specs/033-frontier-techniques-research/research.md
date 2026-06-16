# Phase 0 Research — method & resolved decisions

> For a research-led feature, Phase 0 *is* the deliverable. This file records the **method** that
> produced the corpus and the **resolved planning decisions** (in decision / rationale / alternatives
> form). The findings themselves live in `research/` (eight streams + `SYNTHESIS.md`).

## Method

- **Eight parallel domain analysts.** Three commercial streams (OpenAI; Google/DeepMind;
  Anthropic+Microsoft+Meta+Amazon+Vercel+startups) and five scholarly streams (agentic frameworks;
  generative/adaptive UI; memory/personalization; agentic security; device adaptation), each run
  with the same AstralBody baseline brief and the same hard constraint envelope.
- **Source discipline.** Scholarly streams restricted to primary venues (arXiv, CHI/UIST/IUI,
  NeurIPS/ICML/ICLR, ACL, IEEE S&P/USENIX/CCS/NDSS, IETF, OWASP) — no Medium/listicles. Commercial
  streams restricted to official vendor sources with preview-vs-GA flags and hype call-outs.
- **Per-finding contract.** Every finding carries Source, What-it-is, Frontier-evidence,
  AstralBody-gap, Priority, an in-constraint "how to implement", and Novelty/Impact/Effort scores
  (see `contracts/capability-record.md`).
- **Cross-stream synthesis.** ~164 raw findings deduplicated to 71 consolidated capabilities with a
  consensus indicator (≥3 streams = convergent = highest confidence), grouped by the four priority
  dimensions and sequenced into waves; plus a "do not regress" list and an out-of-constraint list.

## Resolved decisions (NEEDS CLARIFICATION → resolved with user, 2026-06-16)

### D1 — Scope of branch 033
- **Decision**: Research + roadmap only; **no product/implementation code** on this branch.
- **Rationale**: Matches the explicit ask ("much more research than implementation this time") and
  keeps every future capability behind its own production-ready, ≥90%-coverage follow-on PR rather
  than an unreviewably large change.
- **Alternatives considered**: (a) research + Wave-0 quick wins here; (b) research + Wave-0 + the
  flagship UI core here. Both rejected for this branch to preserve the research-first intent; they
  remain the recommended *first follow-on* work.

### D2 — Lead implementation initiative(s)
- **Decision**: Co-flagship **trio** — generative model-grounded UI (US2) + self-improving agent
  architecture (US3) + living memory & personalization (US4) — lead together as the first follow-on
  specs.
- **Rationale**: These are the three highest-novelty/UX clusters; "novelty is of the utmost
  importance" argues for leading with the boldest bets, and the trio jointly exercises the Wave-0
  enablers (structured output, eval backbone, context engineering) so those land early.
- **Alternatives considered**: UI-only lead (too narrow for "novelty above all"); enablers-first
  (safer but defers the differentiating work); single-flagship (under-uses the convergent enablers
  that all three need anyway).

### D3 — Selection bias within the backlog
- **Decision**: **Novelty-forward** — lead with the boldest structural bets (task-model-first UI,
  generative primitives, optimizable agent graph, evolutionary auto-create, sleep-time memory, the
  VOICE renderer), each paired with the cheap convergent enabler it depends on.
- **Rationale**: Directly honors the stated priority while the paired enabler keeps each bold bet
  measurable (eval backbone) and reliable (structured output, taint), so novelty isn't built on sand.
- **Alternatives considered**: confidence-first (safer, slower differentiation); balanced (chosen
  partially — the "paired enabler" is the balance, but novelty leads).

### D4 — Corpus completeness
- **Decision**: **Locked as sufficient** — 71 capabilities across 8 primary-sourced streams.
- **Rationale**: Coverage spans all named vendors + five scholarly domains with convergence signals;
  further breadth has diminishing returns vs starting the roadmap.
- **Alternatives considered**: expand the agent-startup long tail; deepen one dimension. Both
  deferred — re-openable if a follow-on spec surfaces a specific gap.

## Open items

None. No NEEDS CLARIFICATION remain; the roadmap's *future* per-capability design questions are
intentionally deferred to each capability's own follow-on spec (that is the point of the gating).
