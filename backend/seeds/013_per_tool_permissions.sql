-- Feature 013 — Agent Visibility, Active-Agent Clarity, Per-Tool Permissions, and In-Chat Tool Picker
--
-- This file documents the schema delta. The project's actual schema is
-- managed by `backend/shared/database.py::Database._init_db()`, which uses
-- idempotent `CREATE TABLE IF NOT EXISTS` and `_column_exists`-guarded
-- ALTERs and runs on every backend startup. The statements below mirror
-- exactly what `_init_db()` applies for this feature; they are kept here
-- as a portable reference and as a documented down path.
--
-- Forward (applied by _init_db on next backend start):
--
-- 1. Bind a chat session to its active agent (Story 2 / FR-006, FR-009).
ALTER TABLE chats ADD COLUMN IF NOT EXISTS agent_id TEXT NULL;

-- 2. Per-tool, per-permission-kind permission rows (Story 3 / FR-010).
--    `permission_kind` is one of 'tools:read', 'tools:write',
--    'tools:search', 'tools:system', or NULL (legacy tool-wide
--    semantics). The unique key includes COALESCE so legacy NULL rows
--    coexist with new per-kind rows.
ALTER TABLE tool_overrides ADD COLUMN IF NOT EXISTS permission_kind TEXT NULL;
ALTER TABLE tool_overrides DROP CONSTRAINT IF EXISTS tool_overrides_user_id_agent_id_tool_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS tool_overrides_user_agent_tool_kind_uniq
    ON tool_overrides (user_id, agent_id, tool_name, COALESCE(permission_kind, ''));

-- 3. Idempotent backfill from agent_scopes -> tool_overrides (FR-015).
--    For every (user, agent, scope) row in agent_scopes with enabled=true,
--    insert one tool_overrides row per tool whose required scope equals
--    that scope. Guarded by NOT EXISTS so re-runs are no-ops.
--    Note: the join against the agent's tool->scope map is materialised
--    by application code at first read (see backend/orchestrator/
--    tool_permissions.py::ToolPermissionManager.backfill_per_tool_rows)
--    rather than in pure SQL because the map is not stored as a table —
--    it is constructed at runtime when each agent registers its tools.
--
-- Down path (rollback):
--   ALTER TABLE tool_overrides DROP COLUMN IF EXISTS permission_kind;
--   DROP INDEX IF EXISTS tool_overrides_user_agent_tool_kind_uniq;
--   ALTER TABLE chats DROP COLUMN IF EXISTS agent_id;
-- The pre-feature `agent_scopes` rows are preserved untouched, so reverting
-- falls back to scope-only enforcement with no data loss.
