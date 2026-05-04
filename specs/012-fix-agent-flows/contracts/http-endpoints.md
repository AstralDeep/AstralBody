# Contract: HTTP Endpoints Touched

**Feature**: 012-fix-agent-flows
**Date**: 2026-05-01

This feature does not introduce new HTTP routes. It clarifies and stabilizes the response shapes of existing draft-lifecycle routes so the frontend can deterministically advance the user through the create-test-approve loop.

All routes are already secured by Keycloak and live under the orchestrator FastAPI app at [`backend/orchestrator/api.py`](../../../backend/orchestrator/api.py). Authorization rules are unchanged.

---

## POST `/api/agents/drafts`

Create a new draft from the wizard's Step 1–2 input. **Unchanged** in this feature.

---

## POST `/api/agents/drafts/{draft_id}/generate`

Trigger LLM-based code generation for the draft. **Behavior unchanged**, but consumers (the wizard) now expect:

- On success, the draft's `status` reaches `generated` (not `testing`).
- The frontend opens the Test WebSocket on Step 4 entry; the WS handshake — not this endpoint — is what flips the draft to `testing`.

No request/response shape change.

---

## GET `/api/agents/drafts/{draft_id}`

Fetch the current draft state (used by `CreateAgentModal`'s resume path). **Unchanged**, but the frontend now keys its WS-connection effect on the union of `generated` / `testing` (Story 1 fix) instead of `testing` alone.

---

## POST `/api/agents/drafts/{draft_id}/approve`

User-initiated approval. **Behavior change** — the response now reflects the deterministic outcome described in Clarification Q2 and FR-010:

### Request
```json
{}
```
(unchanged — body is empty)

### Response — auto-promoted to live (200 OK)
```json
{
  "status": "live",
  "agent_id": "string",
  "draft_id": "string"
}
```

### Response — rejected by automated security checks (200 OK)
```json
{
  "status": "rejected",
  "draft_id": "string",
  "failures": [
    { "check": "string", "severity": "low|medium|high|critical", "message": "string" }
  ]
}
```

### Response — already live, idempotent no-op (200 OK)
```json
{
  "status": "live",
  "agent_id": "string",
  "draft_id": "string",
  "idempotent": true
}
```

### Response — invalid precondition (409)
The draft is not in a state that can be approved (e.g., `generating`, or already `rejected` without re-submission). Body:
```json
{ "error": "string", "current_status": "string" }
```

There is **no** `pending_review` outcome (per spec Clarification Q2).

### Side effects on auto-promotion
1. `draft_agents.status` ← `live`
2. `.draft` marker file removed
3. `set_agent_ownership(agent_id, owner_email, is_public=false)` re-asserted
4. Live agent registered in `orchestrator.agent_cards`
5. `agent_list` event broadcast over the owner's WebSocket (see contracts/websocket-events.md)

---

## DELETE `/api/agents/drafts/{draft_id}`

Owner-initiated draft deletion (FR-017). **Already exists** at [`api.py:1014`](../../../backend/orchestrator/api.py#L1014). **Unchanged** in this feature.

### Authorization
The route already verifies the caller's email matches `draft_agents.user_id`'s email. No change.

### Response (200 OK)
```json
{ "deleted": true, "draft_id": "string" }
```

### Side effects
- `draft_agents` row removed.
- `agent_ownership` row removed (cascade in `delete_draft_agent`).
- If the draft has a running subprocess, it is stopped before the row is removed.
- A live agent (status=`live`) **cannot** be deleted via this endpoint — this endpoint serves the drafts list only. Removing a live agent uses the existing live-agent management path and is out of scope here.

---

## GET `/api/agents`

Live agents list (already used by the dashboard). **Unchanged** in this feature, but the frontend now invalidates and re-fetches it whenever an `agent_list` event is received over the WS — which closes the gap that previously required a manual page reload to see a newly promoted agent.

---

## Compatibility

No breaking changes. Every change above is either a side-effect addition (ownership re-assertion, broadcast) or a clarification of an existing response shape that older clients already accepted.
