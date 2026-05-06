# Contract — Per-Tool Agent Permissions API

Replaces the four-scope `PUT /api/agents/.../permissions` payload with per-tool, per-permission-kind toggles. The legacy scope-only payload remains accepted for one release as a fallback for clients that have not been updated, but the spec calls for replacement.

## Endpoints

### `GET /api/agents/{agent_id}/permissions`

Returns the resolved per-tool permissions for the current user for this agent.

**Response 200**:

```json
{
  "agent_id": "agent_123",
  "permissions": {
    "search_web": {
      "tools:read": true,
      "tools:search": true
    },
    "send_email": {
      "tools:write": false
    }
  },
  "legacy_scopes": {
    "tools:read": true,
    "tools:write": false,
    "tools:search": true,
    "tools:system": false
  }
}
```

- `permissions[tool][kind]` is the effective per-tool, per-kind boolean. Only the kinds that **apply to that tool** are present (FR-014).
- `legacy_scopes` is included as a read-only echo for any client still surfacing the old four-scope view; the user-facing UI does not edit it post-migration.

---

### `PUT /api/agents/{agent_id}/permissions`

Persists a per-tool permission update.

**Request body** (preferred — per-tool):

```json
{
  "permissions": {
    "search_web": { "tools:read": true, "tools:search": true },
    "send_email": { "tools:write": false }
  }
}
```

- The body MAY be a partial update — only the tools/kinds present are written; others are left untouched.
- The server MUST reject any (tool, kind) pair where the kind does not apply to that tool (FR-014) with 400.
- The server MUST NOT widen permissions silently. Any setting that flips a permission ON for the first time is acceptable (the user is consenting); the server simply persists the row. The UI is responsible for surfacing the (i) info pre-toggle (FR-011).
- A successful PUT updates `tool_overrides` rows keyed by `(user_id, agent_id, tool_name, permission_kind)`.

**Request body** (legacy fallback — accepted for one release):

```json
{
  "scopes": { "tools:read": true, "tools:write": false }
}
```

When this shape is received, the server treats it as a scope-level update against `agent_scopes` and additionally writes the corresponding per-tool rows so the new model stays in sync. Logged at WARN with `legacy_scope_update=true` for migration tracking.

**Response 200**: same shape as GET.

**Errors**: 400 invalid (kind not applicable to tool); 401 unauthorized; 403 not the agent owner / not permitted to modify; 404 unknown agent.

---

## Migration semantics (FR-015)

The first read of this endpoint after the migration ships triggers a one-time backfill check via `get_effective_tool_permissions`: any tool/kind pair without an explicit `tool_overrides` row inherits its boolean from `agent_scopes` (1:1 carry-forward). The backfill is idempotent — see [research.md R7](../research.md).

## Observability

Every PUT emits a structured log line: `user_id`, `agent_id`, `tools_changed_count`, `kinds_changed`, `legacy_payload=bool`. A metric counter `agent_permission_updates_total{shape="per_tool"|"legacy_scope"}` is incremented for migration tracking.
