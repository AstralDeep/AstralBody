# Data Model — research & roadmap entities

> This feature produces a corpus, not a database. The "data model" is the logical schema of the
> research artifacts and the roadmap. No PostgreSQL tables are created on branch 033.

## Entities

### Research Stream
One per-domain findings file under `research/`.
- **id** — stream name (e.g. `commercial-openai`, `scholarly-agentic-security`).
- **kind** — `commercial` | `scholarly`.
- **domain** — vendor or scholarly topic surveyed.
- **findings[]** — the Findings it contains.
- **sources[]** — deduped primary-source references.
- *Invariant*: scholarly streams contain only primary-venue sources (no Medium/listicles).

### Finding
A single frontier technique observed in one stream (≈164 total).
- **id** — stream-local (`F1`…`Fn`).
- **title**, **source(s)** (with URL/citation + preview-vs-GA for commercial), **what_it_is**,
  **frontier_evidence**, **astralbody_gap**, **priority** (one or more Priority Dimensions),
  **implementation_note** (must satisfy the Constraint Envelope), **novelty** (1–5),
  **impact** (1–5), **effort** (S/M/L), optional **hype/caveat flag**.

### Consolidated Capability
A deduplicated, cross-stream-merged unit (71 total) — the atomic unit of the roadmap.
- **id** — stable `C-<tier><n>` (e.g. `C-N1`, `C-U2`, `C-M3`, `C-D4`, `C-S2`).
- **tier** — the Priority Dimension it belongs to (Novelty / UX / Device / Security).
- **title**, **sources[]** — the contributing Finding ids (e.g. `GUI-F1, GOO-F1`).
- **novelty / impact / effort** — rolled-up scores.
- **consensus** — count of independent streams (≥3 = convergent / highest confidence).
- **wave** — sequencing bucket (0–5).
- **dependencies[]** — other Capability ids it requires (e.g. C-N5 eval backbone).
- *Relationship*: many Findings → one Consolidated Capability.

### Priority Dimension
The ranking axis, ordered per the user's priority.
- **values (ordered)**: Novelty (paramount) → User Experience → Device Adaptation → Agentic Security.
- Drives **investment depth**; the recommended sequencing reconciles depth with "convergent enablers first".

### Capability Initiative (User Story)
An independently shippable grouping of Consolidated Capabilities mapped to a Priority Dimension.
- **id** — US1…US6.
- **role** — `research-deliverable` (US1, this branch) | `co-flagship follow-on` (US2/US3/US4) |
  `follow-on` (US5/US6).
- **capabilities[]**, **independent_test**, **acceptance_scenarios[]**.

### Wave
A sequencing bucket ordering initiatives by dependency + risk-adjusted leverage.
- **values**: Wave 0 (foundations/quick wins) → Wave 1 (flagship UI) → Wave 2 (agent architecture) →
  Wave 2′ (living memory) → Wave 3 (device) → Wave 4 (security) → Wave 5 (ecosystem).
- *Rule*: a security Capability that guards an autonomy increase ships with/before its dependent
  (FR-011), overriding the tier's lower investment priority.

### Constraint Envelope
The non-negotiable filter every retained Capability's implementation note must satisfy.
- **rules**: Python-only backend · no new third-party runtime libraries · SDUI mandate (astralprims
  defines → orchestrator renders → ROTE adapts) · idempotent guarded startup migrations · fail-closed.
- *Relationship*: a Capability that cannot satisfy the envelope is moved to the **Deferred /
  Out-of-Constraint** list with a portable-now sub-idea routed into an in-constraint Capability.

### Approval Gate
The explicit user go-ahead required before any implementation wave begins.
- **state**: `pending` (current) → `approved-per-wave`.
- *Rule*: branch 033 never transitions any wave to building; it only defines and sequences.

## State / lifecycle

```
Finding (×164)  ──dedup/merge──▶  Consolidated Capability (×71)
        │                                   │
        │                          group by Priority Dimension
        ▼                                   ▼
  Research Stream (×8)            Capability Initiative (US1…US6)
                                            │
                                   sequence into Waves (0…5)
                                            │
                                   Approval Gate (pending)
                                            │
                         (future) approved → follow-on feature branch
```

No persisted DB state, no migration, on branch 033.
