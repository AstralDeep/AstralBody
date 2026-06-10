# Data Model: 027 Agentic Creation & Top-Bar Settings Menu

## Schema delta (idempotent, in `Database._init_db()` — Constitution IX)

Only `draft_agents` changes. All columns nullable or defaulted; applied via
`ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS ...` on startup.

| Column | Type | Default | Purpose |
|---|---|---|---|
| `origin` | TEXT NOT NULL | `'manual'` | `manual` \| `auto_chat` \| `revision` — entry point provenance (spec Key Entities) |
| `source_chat_id` | TEXT | NULL | chat that triggered auto-creation (dedup scope + audit linkage) |
| `gap_fingerprint` | TEXT | NULL | normalized hash of requested capability (name + tool names); FR-007 dedup key |
| `revises_agent_id` | TEXT | NULL | live agent id this draft revises (origin=`revision` only) |
| `self_test` | TEXT (JSON) | NULL | `{status: "passed"\|"failed"\|"timeout", summary, tools_called[], evidence, tested_at}` |

Index: `CREATE INDEX IF NOT EXISTS idx_draft_gap ON draft_agents (user_id, source_chat_id, gap_fingerprint)`.

**Rollback path**: columns are additive and ignored by all pre-027 code; rollback = redeploy
prior image (columns remain, harmless). Destructive removal (not required): `ALTER TABLE
draft_agents DROP COLUMN ...` documented here per Constitution IX.

## Entities (runtime / conceptual)

### CapabilityGap (not persisted as its own table — lives on the draft row)
- Identified by `(user_id, source_chat_id, gap_fingerprint)`.
- States: *unresolved* (no draft) → *staged* (draft exists, non-terminal) → *resolved*
  (approved → live) | *discarded* (declined → row deleted).
- Invariant (FR-007): at most one non-terminal draft per key; repeat `create_capability` calls
  with a matching fingerprint return the existing draft instead of creating.

### Draft Agent (existing, extended)
- Existing statuses unchanged: `pending → generating → generated → testing → analyzing →
  approved/pending_review/rejected/validating → live → error`.
- `origin=revision` drafts additionally carry `revises_agent_id`; their approval path is
  `apply_revision` (gate → swap → restart, rollback on failure) instead of promotion.
- Decline/discard (FR-002): `delete_draft` (existing) — process stopped, directory removed,
  row deleted.

### Revision swap state machine (origin=`revision`)
```
staged(clone tested) --user approves--> gating(stop live, backup, install, analyze+compile+validate)
   gating --pass--> applied(restart live, delete clone+row, audit lifecycle.revision_applied)
   gating --fail--> rolled_back(restore backup, restart live, draft stays rejected-editable,
                                audit lifecycle.revision_rolled_back)
```
Invariant (FR-006): the live agent's on-disk code is changed only inside `gating`, and every
failure path restores the backup before restart.

### SettingsMenuEntry (not persisted)
Computed per request at shell render: `(group: Account|Help|Admin tools|Session, key, label,
surface, visible: role/availability-filtered)`. FR-014/FR-019: admin entries simply absent from
the rendered HTML for non-admins; unavailable entries omitted; empty groups hide their heading.

### Audit additions (event_class `agent_lifecycle`)
One `correlation_id` per gap, paired in_progress→terminal events:
`lifecycle.gap_detected`, `lifecycle.auto_created`, `lifecycle.self_test`, `lifecycle.refined`,
`lifecycle.approved`, `lifecycle.rejected`, `lifecycle.discarded`, `lifecycle.revision_applied`,
`lifecycle.revision_rolled_back`. `inputs_meta` carries `{gap_fingerprint, draft_id,
revises_agent_id?}` (≤32 keys / 4KB — existing schema bounds). Settings surfaces reuse existing
classes (`settings`, `personalization`, `memory`, `skill`, `schedule`, `dreaming`, `audit_view`).

### user_preferences (existing, no change)
`theme` continues to be the persistence home for the Theme surface (`save_theme` semantics).
