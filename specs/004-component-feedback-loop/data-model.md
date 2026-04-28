# Data Model: Component Feedback & Tool Auto-Improvement Loop

**Feature**: `004-component-feedback-loop`
**Source spec**: [spec.md](./spec.md) — see Key Entities and FR-001 … FR-032.
**Source research**: [research.md](./research.md)

All four tables are added to `Database._init_db` in [backend/shared/database.py](../../backend/shared/database.py), matching the convention established by feature 003 (raw `psycopg2`, no SQLAlchemy / Alembic). Per-user isolation is enforced at the application (repository) layer — there are no row-level security policies in this codebase.

---

## 1. `component_feedback`

A single feedback submission. Append-only with logical supersession. Lifecycle is enforced by the repository layer, not by triggers.

```sql
CREATE TABLE IF NOT EXISTS component_feedback (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                TEXT NOT NULL,
    conversation_id        TEXT,
    correlation_id         TEXT,                                       -- joins to audit_events.correlation_id; NULL for non-tool-dispatch components
    source_agent           TEXT,
    source_tool            TEXT,
    component_id           TEXT,                                       -- the SDUI component's own id (per-render identifier within a dispatch)
    sentiment              TEXT NOT NULL CHECK (sentiment IN ('positive','negative')),
    category               TEXT NOT NULL CHECK (category IN
                              ('wrong-data','irrelevant','layout-broken','too-slow','other','unspecified'))
                              DEFAULT 'unspecified',
    comment_raw            TEXT,                                       -- length-capped at 2048 chars at API ingress; NULL allowed
    comment_safety         TEXT NOT NULL CHECK (comment_safety IN ('clean','quarantined')) DEFAULT 'clean',
    comment_safety_reason  TEXT,                                       -- e.g. 'jailbreak_phrase','role_override_marker','unicode_control','pre_pass_disagreement'
    lifecycle              TEXT NOT NULL CHECK (lifecycle IN ('active','superseded','retracted')) DEFAULT 'active',
    superseded_by          UUID REFERENCES component_feedback(id),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cf_user_created
    ON component_feedback (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cf_tool_created
    ON component_feedback (source_agent, source_tool, created_at DESC)
    WHERE lifecycle = 'active';
CREATE INDEX IF NOT EXISTS idx_cf_quarantine
    ON component_feedback (comment_safety, created_at DESC)
    WHERE comment_safety = 'quarantined';
CREATE INDEX IF NOT EXISTS idx_cf_dedup_lookup
    ON component_feedback (user_id, correlation_id, component_id, created_at DESC);
```

**Lifecycle states & transitions** (FR-007, FR-009a, FR-028, FR-029):

```
            ┌──────────┐  retract within 24 h    ┌────────────┐
   submit→  │  active  │ ──────────────────────► │ retracted  │
            └─────┬────┘                         └────────────┘
                  │
                  │ amend OR new submission outside 10 s dedup window
                  ▼
            ┌──────────────┐
            │  superseded  │  ← prior row; superseded_by → new row.id
            └──────────────┘
```

- A new submission that arrives **inside** the 10-second dedup window for the same `(user_id, correlation_id, component_id)` does NOT create a new row — it updates the existing `active` row in place and sets `updated_at`. No new audit event written.
- A new submission **outside** the dedup window for the same target marks the prior `active` row `superseded` and inserts a new `active` row. Audit event is written.
- Retract / amend permitted only within 24 h of `created_at`; rejected after with `EDIT_WINDOW_EXPIRED`.

**Cross-user isolation (FR-009, FR-031)**: every repository method takes `actor_user_id` and filters/scopes accordingly. Reads, retracts, amends, and even existence checks return identical "not found" responses for cross-user attempts.

---

## 2. `tool_quality_signal`

Per-(agent, tool) snapshot over a rolling window. One row per evaluation cycle per tool.

```sql
CREATE TABLE IF NOT EXISTS tool_quality_signal (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id                 TEXT NOT NULL,
    tool_name                TEXT NOT NULL,
    window_start             TIMESTAMPTZ NOT NULL,
    window_end               TIMESTAMPTZ NOT NULL,
    dispatch_count           INTEGER NOT NULL,
    failure_count            INTEGER NOT NULL,
    negative_feedback_count  INTEGER NOT NULL,
    failure_rate             REAL NOT NULL,                              -- failure_count / dispatch_count, 0 when dispatch_count=0
    negative_feedback_rate   REAL NOT NULL,                              -- negative_feedback_count / max(dispatch_count, 1)
    status                   TEXT NOT NULL CHECK (status IN
                                 ('healthy','insufficient-data','underperforming')),
    computed_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, tool_name, window_end)
);

CREATE INDEX IF NOT EXISTS idx_tqs_underperforming
    ON tool_quality_signal (computed_at DESC)
    WHERE status = 'underperforming';
```

**Computation** (R-6):
- Windowing: `window_end = now()`, `window_start = now() - interval '14 days'` (operator-configurable per FR-010).
- `status = 'insufficient-data'` when `dispatch_count < 25` (FR-011 default).
- `status = 'underperforming'` when `dispatch_count >= 25 AND (failure_rate >= 0.20 OR negative_feedback_rate >= 0.30)` (FR-012 default).
- Otherwise `status = 'healthy'`.

**Transition detection (FR-012a)**: when comparing the latest snapshot for a (agent, tool) to its prior snapshot, a `healthy|insufficient-data → underperforming` transition emits an audit `tool_flagged` event; the reverse emits `tool_recovered`. Same-status snapshots emit nothing.

---

## 3. `knowledge_update_proposal`

System-generated proposed change to a synthesizer knowledge artifact. Always scoped to one tool. Always targets a path under `backend/knowledge/`.

```sql
CREATE TABLE IF NOT EXISTS knowledge_update_proposal (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id               TEXT NOT NULL,
    tool_name              TEXT NOT NULL,
    artifact_path          TEXT NOT NULL,                                -- relative to backend/knowledge/; rejected at API if it escapes that prefix
    diff_payload           TEXT NOT NULL,                                -- unified diff against the artifact at generation time
    artifact_sha_at_gen    TEXT NOT NULL,                                -- sha256 of artifact contents when proposal was generated
    evidence               JSONB NOT NULL,                               -- {audit_event_ids: [...], component_feedback_ids: [...], window_start, window_end}
    status                 TEXT NOT NULL CHECK (status IN
                              ('pending','accepted','applied','rejected','superseded')) DEFAULT 'pending',
    reviewer_user_id       TEXT,
    reviewed_at            TIMESTAMPTZ,
    reviewer_rationale     TEXT,                                         -- required when status = 'rejected'
    applied_at             TIMESTAMPTZ,
    generated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kup_pending
    ON knowledge_update_proposal (generated_at DESC)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_kup_tool
    ON knowledge_update_proposal (agent_id, tool_name, generated_at DESC);
```

**Lifecycle (FR-016 … FR-019, R-8)**:

```
generated → pending ──accept──► accepted ──apply on accept──► applied
              │                       │
              │                       └─ if file changed since artifact_sha_at_gen → reject acceptance, mark superseded
              │
              └──reject (rationale required)──► rejected
              │
              └──new proposal for same tool with newer evidence──► superseded
```

- `accept` and `apply` are one user action server-side, but two state writes for clarity.
- A `pending` proposal becomes `superseded` automatically when a newer pending proposal arrives for the same `(agent_id, tool_name)`. Only the newest pending per tool is reachable in the admin queue.
- A `rejected` proposal blocks re-proposal of the **same** change for the same evidence (FR-019); a fresh proposal is permitted only if the supporting `evidence` set has materially changed (defined as: the multiset of `audit_event_ids ∪ component_feedback_ids` differs by ≥ 25%).

---

## 4. `quarantine_entry`

A pointer to a `component_feedback` whose text was flagged. One quarantine_entry per feedback record (composite primary key on `feedback_id` enforces this).

```sql
CREATE TABLE IF NOT EXISTS quarantine_entry (
    feedback_id    UUID PRIMARY KEY REFERENCES component_feedback(id) ON DELETE CASCADE,
    reason         TEXT NOT NULL,                                      -- short code matching component_feedback.comment_safety_reason
    detector       TEXT NOT NULL CHECK (detector IN ('inline','loop_pre_pass')),
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status         TEXT NOT NULL CHECK (status IN ('held','released','dismissed')) DEFAULT 'held',
    actor_user_id  TEXT,                                                -- admin who released or dismissed
    actioned_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_qe_held
    ON quarantine_entry (detected_at DESC)
    WHERE status = 'held';
```

**Behaviors (FR-022 … FR-027)**:
- A `release` action sets `status='released'`, records `actor_user_id` and `actioned_at`, AND updates `component_feedback.comment_safety='clean'` so the next synthesizer cycle picks up the now-cleared text.
- A `dismiss` action sets `status='dismissed'`; the feedback's `comment_safety` stays `quarantined` permanently; its sentiment + category still count toward `tool_quality_signal` (FR-024).
- The pre-pass disagreement case (FR-021a) inserts a new `quarantine_entry` with `detector='loop_pre_pass'` and `reason='pre_pass_disagreement'`, replacing any prior `inline`-detector row for the same `feedback_id` (the PK constraint enforces single-row; the bridge code handles the swap atomically).

---

## 5. Audit event extensions

The audit log substrate from feature 003 ([backend/audit/schemas.py](../../backend/audit/schemas.py)) already supports new `event_class` values. This feature adds:

| event_class           | action_type values                                                                 | actor                |
|-----------------------|-------------------------------------------------------------------------------------|----------------------|
| `component_feedback`  | `feedback.submit`, `feedback.retract`, `feedback.amend`                              | submitting user      |
| `tool_quality`        | `tool_flagged`, `tool_recovered`                                                     | system (no user)     |
| `proposal_review`     | `proposal.generated`, `proposal.accept`, `proposal.reject`, `proposal.applied`, `proposal.superseded` | admin or system  |
| `quarantine`          | `quarantine.flag`, `quarantine.release`, `quarantine.dismiss`                        | system or admin      |

`EVENT_CLASSES` in `backend/audit/schemas.py` is extended accordingly (single edit). The hash-chain integrity requirement for audit events (per feature 003) applies to every new entry above.

`outputs_meta` / `inputs_meta` payloads carry the relevant ids (`feedback_id`, `proposal_id`, `tool_name`, `agent_id`, `correlation_id`) for downstream querying.

---

## Field-level requirement traceability

| Spec FR | Where enforced |
|---------|----------------|
| FR-001 (correlation_id on every render) | Orchestrator metadata tagging + protocol DTO |
| FR-002, FR-003, FR-004, FR-005 | `component_feedback` schema |
| FR-006 (≤ 1 s ack) | Inline screen is heuristic-only (R-1) |
| FR-007 (queryability) | Indices on `component_feedback` |
| FR-008 (audit row) | `audit_events.event_class='component_feedback'` |
| FR-009 (cross-user isolation) | Repository layer enforcement + `idx_cf_user_created` |
| FR-009a (dedup window) | `recorder.submit()` app-level dedup logic |
| FR-010, FR-011, FR-012 | `tool_quality_signal` schema + computation |
| FR-012a, FR-012b | Transition-detection in daily quality job + UI badge |
| FR-013 (admin role) | Existing `auth.py` admin-role check on REST routes |
| FR-014 (evidence fields) | `tool_quality_signal` columns + JSONB join in admin GET |
| FR-015, FR-016 | `proposals.py` bridge module + `knowledge_synthesis.py` extension |
| FR-017, FR-018, FR-019 | `knowledge_update_proposal` lifecycle + `proposal_review` audit class |
| FR-020 (degraded mode) | Synthesizer guard + admin queue status field |
| FR-021, FR-021a, FR-022 … FR-027 | `safety.py` + `quarantine_entry` + dual-pass logic |
| FR-028, FR-029 (24 h lock) | `recorder.retract()` / `recorder.amend()` time check |
| FR-030 (audit on every action) | All API and WS handlers emit audit events |
| FR-031 (zero leaks) | `tests/test_isolation.py` |
| FR-032 (retention) | Inherited from existing audit retention; no separate retention job |

---

## Non-goals (data model)

- No object-storage / WORM cold archive for `component_feedback`. Feature 003 already provides that for the parent `audit_events`; the feedback's own audit row inherits that path, and the structured columns (sentiment, category) are not regulatory records.
- No materialized views. The four indices specified above cover every query path the admin and user surfaces need at the assumed scale (R-11).
- No event sourcing / CQRS. The state model is small enough that the table-per-entity layout is the simplest correct choice.
