# Phase 1 — Data Model

This document captures the schema deltas and the in-memory shapes used by the feature. All schema changes ship with an idempotent, auto-running migration script (Constitution IX).

---

## 1. `chats` (existing — additive change)

```sql
ALTER TABLE chats
  ADD COLUMN IF NOT EXISTS agent_id TEXT NULL;
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | TEXT | PK (existing) | unchanged |
| `user_id` | TEXT | NOT NULL (existing) | unchanged |
| `title` | TEXT | (existing) | unchanged |
| `agent_id` | **TEXT** | **NULL** | **NEW**. The agent the chat is bound to. NULL is allowed for backward compat with chats created before the migration; the frontend renders an "Unknown agent" / "Pick an agent" state in that case. |
| `created_at`, `updated_at` | (existing) | | unchanged |

**Helpers added to `backend/shared/database.py`**:

- `get_chat_agent(chat_id: str) -> Optional[str]`
- `set_chat_agent(chat_id: str, agent_id: str) -> None` — called when a chat is created or when the user explicitly switches the agent in an existing chat.

**Lifecycle**: set once at chat creation; updated only when the user explicitly switches the agent on the chat. Never silently re-routed (FR-009).

---

## 2. `tool_overrides` (existing — extended for per-tool permissions)

```sql
ALTER TABLE tool_overrides
  ADD COLUMN IF NOT EXISTS permission_kind TEXT NULL;

-- Drop and re-create the unique key to include permission_kind
ALTER TABLE tool_overrides
  DROP CONSTRAINT IF EXISTS tool_overrides_user_agent_tool_uniq;

CREATE UNIQUE INDEX IF NOT EXISTS tool_overrides_user_agent_tool_kind_uniq
  ON tool_overrides (user_id, agent_id, tool_name, COALESCE(permission_kind, ''));
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `user_id` | TEXT | NOT NULL (existing) | |
| `agent_id` | TEXT | NOT NULL (existing) | |
| `tool_name` | TEXT | NOT NULL (existing) | |
| `permission_kind` | **TEXT** | **NULL** | **NEW**. One of `tools:read`, `tools:write`, `tools:search`, `tools:system`. NULL preserves the legacy "tool-wide override" semantics for any pre-existing rows. |
| `enabled` | BOOLEAN | NOT NULL (existing) | |
| `updated_at` | (existing) | | |

**Backfill (idempotent)**: For every `(user_id, agent_id, scope)` row in `agent_scopes` with `enabled=true`, insert one `tool_overrides` row per tool whose required scope equals that scope, with `permission_kind=scope` and `enabled=true`, guarded by `WHERE NOT EXISTS`. Implements FR-015 (1:1 carry-forward, never widens).

**Helpers added/modified in `backend/orchestrator/tool_permissions.py`**:

- `get_effective_tool_permissions(user_id, agent_id) -> Dict[str, Dict[str, bool]]` — returns `{tool_name: {permission_kind: enabled}}` for every tool the agent exposes, falling back to `agent_scopes` for any (tool, kind) pair without an explicit row.
- `set_tool_permission(user_id, agent_id, tool_name, permission_kind, enabled) -> None` — writes a single per-tool, per-kind row.
- Modified `is_tool_allowed(user_id, agent_id, tool_name)` — now resolves the tool's required permission kind(s) via `get_tool_scope` and checks the per-tool row in `tool_overrides` first; if no per-tool row exists, falls back to the existing `agent_scopes` check (preserving legacy behavior for tools that have not been per-tool-configured yet).

`agent_scopes` is **not dropped**. It remains as the fallback layer and as the down-migration path.

---

## 3. `user_preferences` (existing — JSON key added under existing column)

No DDL change. The existing `preferences TEXT (JSON)` column gains a new top-level key:

```json
{
  "tool_selection": {
    "<agent_id_a>": ["tool_name_x", "tool_name_y"],
    "<agent_id_b>": ["tool_name_z"]
  }
}
```

- Each map value is the user's selected subset of tools for that specific agent. Tools not present in the array are treated as deselected for that agent (FR-024).
- Absence of an `<agent_id>` key means "no narrowing — use the agent's full permission-allowed set" (FR-019).
- "Reset to default" deletes the `<agent_id>` key (FR-025).

**Helpers added to `backend/shared/database.py`**:

- `get_user_tool_selection(user_id: str, agent_id: str) -> Optional[List[str]]`
- `set_user_tool_selection(user_id: str, agent_id: str, tool_names: List[str]) -> None`
- `clear_user_tool_selection(user_id: str, agent_id: str) -> None` — implements reset.

These wrap the existing `get_user_preferences` / `set_user_preferences` helpers so the JSON shape is encapsulated in one place.

---

## 4. Frontend in-memory shapes

### `Agent` (existing — fields used)

```ts
interface Agent {
  id: string;
  name: string;
  description?: string;
  tools: AgentTool[];
  status: string;
  owner_email?: string;
  is_public: boolean;
  permissions?: Record<string, boolean>;       // legacy scope flags
  per_tool_permissions?: PerToolPermissions;   // NEW: see below
  scopes?: Record<string, boolean>;            // legacy scope flags
}
```

### `PerToolPermissions` (new)

```ts
type PermissionKind = "tools:read" | "tools:write" | "tools:search" | "tools:system";

type PerToolPermissions = {
  [toolName: string]: {
    [kind in PermissionKind]?: boolean;  // only the kinds applicable to that tool appear
  };
};
```

### `ChatSession` (new field)

```ts
interface ChatSession {
  id: string;
  title: string;
  agent_id: string | null;   // NEW — null only for legacy chats
  // ...existing fields
}
```

### `ToolSelection` (new — per-user preference)

```ts
type ToolSelection = {
  [agentId: string]: string[];   // selected tool names; absence = "use full default"
};
```

---

## 5. WS / API message-payload deltas

### Chat WebSocket message (existing — field added)

```json
{
  "type": "ui_event",
  "action": "chat_message",
  "session_id": "...",
  "payload": {
    "message": "...",
    "chat_id": "...",
    "display_message": "...",
    "selected_tools": ["tool_a", "tool_b"]   // NEW — optional; absent ≡ no narrowing
  }
}
```

- The orchestrator MUST treat an absent or empty `selected_tools` array (when no saved preference exists for that agent) as "no narrowing — use the agent's full permitted set."
- An explicitly empty `selected_tools=[]` after the user has interactively deselected every tool is **prevented at the UI layer** (FR-021 blocks send), so the backend does not need to define behavior for that case beyond defensive logging.

The frontend reads the per-user pref via the new `getUserToolSelection(agentId)` helper before send and includes the array in the payload.

---

## 6. Migration script outline

File: `backend/seeds/013_per_tool_permissions.sql` (or equivalent under the project's migration framework).

```sql
-- 1. chats.agent_id
ALTER TABLE chats ADD COLUMN IF NOT EXISTS agent_id TEXT NULL;

-- 2. tool_overrides.permission_kind + new unique index
ALTER TABLE tool_overrides ADD COLUMN IF NOT EXISTS permission_kind TEXT NULL;
ALTER TABLE tool_overrides DROP CONSTRAINT IF EXISTS tool_overrides_user_agent_tool_uniq;
CREATE UNIQUE INDEX IF NOT EXISTS tool_overrides_user_agent_tool_kind_uniq
  ON tool_overrides (user_id, agent_id, tool_name, COALESCE(permission_kind, ''));

-- 3. Idempotent backfill from agent_scopes -> tool_overrides
-- (Pseudo-SQL — actual implementation joins agent's tool->scope map at runtime.)
INSERT INTO tool_overrides (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
SELECT s.user_id, s.agent_id, t.tool_name, s.scope, TRUE, NOW()
FROM agent_scopes s
JOIN agent_tool_scope_map t
  ON t.agent_id = s.agent_id AND t.required_scope = s.scope
WHERE s.enabled = TRUE
  AND NOT EXISTS (
    SELECT 1 FROM tool_overrides o
    WHERE o.user_id = s.user_id
      AND o.agent_id = s.agent_id
      AND o.tool_name = t.tool_name
      AND COALESCE(o.permission_kind, '') = COALESCE(s.scope, '')
  );
```

Idempotent. Down path: drop `tool_overrides.permission_kind`, drop `chats.agent_id`. `agent_scopes` rows are preserved untouched, so reverting falls back to scope-only enforcement.

---

## 7. Validation rules summary (cross-references to spec FRs)

| Rule | Source FR |
|---|---|
| Owned agents (any lifecycle state) appear under "My Agents" | FR-001, FR-002 |
| Owned-and-public agents appear in both tabs | FR-003 |
| Chat header shows active agent name persistently | FR-006 |
| Send blocked + banner when active agent unavailable | FR-009 |
| Per-tool permissions resolved per (user, agent, tool, kind) | FR-010, FR-013 |
| (i) info reachable while toggle is OFF | FR-011 |
| Migration is 1:1 from agent_scopes to per-tool rows | FR-015 |
| Selection narrows but never widens | FR-018, FR-020 |
| Zero selection blocks send (UI gate) | FR-021 |
| Selection logged with reason="user_selection" | FR-023 |
| Selection persists per-user, per-agent | FR-024 |
| Reset action clears the per-agent entry | FR-025 |
