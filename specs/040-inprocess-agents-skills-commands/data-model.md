# Data Model & Migrations: 040-inprocess-agents-skills-commands

Phase 1 output. All schema changes ship as idempotent, guarded deltas inside `shared/database.py::_init_db()` (Constitution IX). No ad-hoc SQL. Rollback documented per delta.

## New table: `agent_trust`

Records the owner-approved "safe" status per agent. Distinct from `agent_ownership.is_public` (visibility), keyed uniquely by `agent_id`.

| Column | Type | Notes |
|--------|------|-------|
| `agent_id` | TEXT PRIMARY KEY | The agent's stable id (e.g. `weather-1`). |
| `is_safe` | BOOLEAN NOT NULL DEFAULT FALSE | Whether the agent is owner-approved safe. |
| `marked_by` | TEXT | Acting principal (admin/owner email or `system` for the boot seed). |
| `marked_at` | TIMESTAMPTZ | When the current state was set. |
| `prior_state` | BOOLEAN | The `is_safe` value before the most recent transition (audit aid). |
| `revised_reset_at` | TIMESTAMPTZ NULL | Set when a revision reset the marker (re-approval pending). |

**Guarded creation**: `CREATE TABLE IF NOT EXISTS agent_trust (...)`. Idempotent; safe to re-run.

**Boot seed (idempotent)**: for each of the nine bundled first-party agent ids, `INSERT ... ON CONFLICT (agent_id) DO NOTHING` a row with `is_safe=TRUE, marked_by='system', marked_at=now(), prior_state=FALSE`, and emit one `agent_lifecycle`/`marked_safe` audit event per newly-seeded agent (skip if the row already existed). Re-running performs no inserts and emits no events.

**Read path**: `is_tool_allowed` consults `is_safe` (cached per request) only when `FF_SAFE_AGENTS` is on. With the flag off, `agent_trust` is ignored and the legacy default-deny applies.

**Rollback**: `DROP TABLE IF EXISTS agent_trust;` restores the prior behavior (with `FF_SAFE_AGENTS` off, the table is inert anyway). No data in other tables depends on it (no FK), so the drop is non-destructive to chats/permissions.

## Explicit user opt-out representation (no schema change)

The "explicit opt-out wins over the safe default" rule reuses existing structures:

- A user disabling a **scope** for a safe agent is recorded as an explicit negative in the existing `agent_scopes` / `tool_overrides` surface (an override with a deny `permission_kind`, or a scope row marked disabled) rather than mere absence.
- `is_tool_allowed` distinguishes *absence* (→ safe default allow) from an *explicit negative record* (→ deny, opt-out wins). This requires no new column: it requires the permission writer to persist a disable as an explicit row, which the existing `set_skill_enabled` / override path already supports.

**Validation rule**: for a safe agent, `allow` iff (no explicit per-(tool,kind) deny) AND (no explicit scope-disabled record) AND (tool not hard-blocked by a security flag).

## One-time guarded cleanup: retire `etf-tracker-1-1`

Mirrors the proven 029 `_migrate_agent_catalog` pattern. Guarded so it runs once and is a no-op thereafter (e.g. a marker row in an existing migrations-applied table, or existence checks before each delete).

Steps (all idempotent):

1. `DELETE FROM agent_scopes WHERE agent_id = 'etf-tracker-1-1';`
2. `DELETE FROM tool_overrides WHERE agent_id = 'etf-tracker-1-1';`
3. Delete any stored credentials for `etf-tracker-1-1` (per the credential store's delete helper).
4. `DELETE FROM agent_ownership WHERE agent_id = 'etf-tracker-1-1';`
5. Retire/reassign conversations: rows in `chats` (and any per-chat agent binding) referencing `agent_id = 'etf-tracker-1-1'` are cleared/retired so they route through the retired-agent handling rather than dangling.
6. `DELETE FROM agent_trust WHERE agent_id = 'etf-tracker-1-1';` (in case a prior boot seeded it).

**Why guarded, not pure idempotent deletes**: the deletes are themselves idempotent (no-ops once rows are gone), but the conversation retirement is wrapped in an existence/marker guard so it does not repeatedly touch chat rows on every boot.

**Rollback**: removal is intentionally destructive of the retired agent's rows (the agent no longer exists). No down-migration restores it; recovery is via database backup if ever needed. This is the sanctioned exception under Principle IX (intentional destruction) and is documented here for the PR review.

## Code-constant deltas (not schema)

- `shared/database.py` `_FIRST_PARTY_PUBLIC_AGENT_IDS`: remove `'etf-tracker-1-1'`.
- `orchestrator/orchestrator.py` `RETIRED_AGENT_IDS`: add `'etf-tracker-1-1'`.
- `orchestrator/history_surface.py` `_AGENT_ICONS`: remove the `etf_tracker_1` entry.

## No schema for skills or commands

- **Skill packs** are committed files under `backend/knowledge_packs/` — no table.
- **Slash commands** are a curated in-code registry — no table. (User-definable per-user macros, which would need a table, are out of scope per Assumptions.)

## Migration testing (Principle IX)

- Test idempotency: run `_init_db` twice against a representative dataset that includes pre-existing `etf-tracker-1-1` ownership/scope/override/chat rows; assert the rows are gone after the first run and the second run is a no-op (no errors, no duplicate audit events for the safe seed).
- Test the safe seed emits exactly one `marked_safe` event per agent on first run and zero on re-run.
