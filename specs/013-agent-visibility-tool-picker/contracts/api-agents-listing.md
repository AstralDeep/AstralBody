# Contract — Agents Listing API (no shape change)

The existing `GET /api/agents` endpoint already returns every field needed for the new "My Agents" / "Public Agents" filter behavior — `owner_email`, `is_public`, and `status`. **No backend contract change is required for Story 1.** The fix is entirely in the frontend tab filters.

## Endpoint (existing, documented here for clarity)

### `GET /api/agents`

Returns all live agents visible to the requesting user.

**Response 200** (existing shape from [`backend/orchestrator/api.py:379-402`](../../backend/orchestrator/api.py#L379-L402)):

```json
{
  "agents": [
    {
      "id": "agent_123",
      "name": "Grants Helper",
      "description": "...",
      "tools": [ /* AgentTool[] */ ],
      "status": "connected",
      "owner_email": "alice@example.com",
      "is_public": true,
      "permissions": { /* legacy scopes */ },
      "security_flags": { /* ... */ },
      "scopes": { /* legacy scopes */ }
    }
  ]
}
```

## Frontend filter changes (DashboardLayout.tsx)

Today at [`frontend/src/components/DashboardLayout.tsx:343-344`](../../frontend/src/components/DashboardLayout.tsx#L343-L344):

```ts
// CURRENT
const myAgents = agents.filter(a => a.owner_email === userEmail || !a.owner_email);
const publicAgents = agents.filter(a => a.is_public);
```

Becomes:

```ts
// NEW — owned-and-public agents intentionally appear in BOTH lists (Q4 clarification, FR-003)
const myAgents = agents.filter(a => a.owner_email === userEmail);
const publicAgents = agents.filter(a => a.is_public);
```

Notes:

- The `|| !a.owner_email` clause is removed: an agent with no owner is by definition not the user's, so it should not appear under "My Agents." (Pre-feature, this clause was masking the bug.)
- Drafts that are owned by the user but not yet published also need to surface under "My Agents" (FR-001 — every agent the user owns, regardless of lifecycle state). The drafts listing — fetched separately from `/api/agents/drafts` ([`api.py:929`](../../backend/orchestrator/api.py#L929)) — is merged into the same `myAgents` view by the frontend, with the draft's lifecycle state rendered as a badge (FR-002). Drafts continue to also be reachable from the existing "Drafts" tab; this is a non-exclusive merge.

## Status badge (FR-002)

Each entry under "My Agents" renders a small badge derived from the agent's `status` (live / draft / testing / pending_review / etc.) using the existing status-pill styling already used for the connection dot at [`DashboardLayout.tsx:566-576`](../../frontend/src/components/DashboardLayout.tsx#L566-L576).

## Auto-refresh on create (FR-005)

The agent listing already refreshes via WebSocket events on agent state change. The frontend ensures that after a successful create-agent call, it dispatches whatever existing event triggers the listing's re-render — no new mechanism required.
