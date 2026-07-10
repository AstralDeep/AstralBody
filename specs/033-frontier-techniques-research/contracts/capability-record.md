# Contract — Finding & Consolidated-Capability record schema

> The "external interface" of this feature is the research corpus. This contract defines the
> required shape of each record and the acceptance checks that map to the spec's Success Criteria.
> A reviewer (or an automated linter) can verify the corpus against this contract.

## Finding record (per-stream `research/<stream>.md`, entries `F1…Fn`)

Required fields:
- **Source** — at least one citation. Scholarly: primary venue (arXiv id / conference / journal /
  standard / first-party lab page) with a URL. Commercial: official vendor page with a URL and a
  **preview-vs-GA** status. (Maps SC-003.)
- **What it is** — 2–4 concrete sentences (mechanism, not marketing).
- **Frontier evidence** — what it achieves / how deployed, with the metric or result cited; vendor-
  internal or unverifiable numbers labelled as such. (Maps SC-006.)
- **AstralDeep gap** — what is missing and why it matters (or "already at/above frontier — do not
  regress").
- **Priority** — one or more of {Novelty, UX, Device, Security}.
- **How to implement in AstralDeep** — concrete approach that satisfies the Constraint Envelope
  (Python-only, no new third-party runtime libs, SDUI mandate, idempotent migrations, fail-closed).
  (Maps SC-004.)
- **Novelty** 1–5 · **Impact** 1–5 · **Effort** S/M/L. (Maps SC-002.)

## Consolidated Capability record (`research/SYNTHESIS.md` §3 tables, ids `C-<tier><n>`)

Required fields:
- **id** — stable `C-N*/C-U*/C-M*/C-D*/C-S*`.
- **Capability** — one-line description.
- **Sources** — the contributing Finding ids across streams (≥1). (Maps SC-002.)
- **Nov / Imp / Eff** — rolled-up scores.
- **Consensus** — `convergent` (≥3 streams) or stream count. (Maps SC-006.)
- Placement in a Priority-Dimension tier (§3.1–§3.5) and a Wave (§4). (Maps SC-005.)

## Corpus-level required sections (`research/SYNTHESIS.md`)

- **§2 Convergent themes** — the ≥3-stream consensus signals. (SC-006)
- **§3 Prioritized backlog** — all capabilities grouped/ordered by the four Priority Dimensions. (SC-002, SC-005)
- **§4 Recommended sequencing** — waves + rationale + the locked decisions. (SC-005)
- **§5 Do-not-regress** — AstralDeep strengths to protect. (SC-005)
- **§6 Deferred / out-of-constraint** — with portable-now sub-ideas. (SC-004)
- **§7 Hype / caveats** — flagged claims. (SC-006)

## Acceptance checks (verifiable, map to spec Success Criteria)

| Check | Method | Success Criterion |
|-------|--------|-------------------|
| All named vendors + 5 scholarly domains covered | 8 stream files exist + named in SYNTHESIS | SC-001 |
| ≥60 consolidated capabilities, all four tiers | count §3 tables (achieved 71) | SC-002 |
| Every scholarly finding cites a primary venue; zero Medium/listicle | scan scholarly streams' Sources | SC-003 |
| Every retained capability has an in-constraint implementation note; misfits deferred | scan implementation notes + §6 | SC-004 |
| Priority ranking + wave sequencing + do-not-regress + hype log present | inspect §3/§4/§5/§7 | SC-005, SC-006 |
| Convergent (≥3-stream) capabilities identified & front-loaded | inspect §2 + Wave 0/1 | SC-006 |
| Non-specialist can name top moves + first slice from the summary | read SYNTHESIS §1–§4 executive content | SC-007 |
| Each initiative (US2–US6) has an independent test + flag-gated/fail-open/no-dep posture | inspect spec user stories + FR-010 | SC-008 |
| No product behavior changed; no code on 033 | `git diff` touches only `specs/033…` + `.specify/feature.json` | SC-009 |
| Future capabilities: zero new deps, idempotent migration, fail-open, ≥90% coverage | enforced per follow-on PR (not on 033) | SC-010 |

No request/response API contracts apply — this feature exposes documents, not endpoints.
