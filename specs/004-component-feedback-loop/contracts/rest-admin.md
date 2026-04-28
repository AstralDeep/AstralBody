# REST API: Admin Surfaces

**Feature**: `004-component-feedback-loop`
**Substrate**: existing FastAPI app — see [backend/orchestrator/api.py](../../../backend/orchestrator/api.py).

All routes below require Keycloak JWT with `admin` role (per Constitution Principle VII and the existing pattern in [backend/orchestrator/auth.py:254](../../../backend/orchestrator/auth.py)). Non-admin callers receive `403 FORBIDDEN`. All endpoints emit audit-log entries on every state-changing action.

Mounted under `/api/admin/feedback/`. Auto-documented via FastAPI's `/docs` Swagger UI (Constitution Principle VI).

---

## 1. Tool quality (flagged tools)

### `GET /api/admin/feedback/quality/flagged`

List tools currently in `underperforming` state — i.e., the latest `tool_quality_signal` row per `(agent_id, tool_name)` has `status='underperforming'`.

**Query params**: `cursor` (opaque string, optional), `limit` (1–100, default 50).

**Response 200**:
```jsonc
{
  "items": [
    {
      "agent_id":               "string",
      "tool_name":              "string",
      "window_start":           "iso8601",
      "window_end":             "iso8601",
      "dispatch_count":         123,
      "failure_count":          27,
      "negative_feedback_count": 41,
      "failure_rate":           0.22,
      "negative_feedback_rate": 0.33,
      "category_breakdown":     { "wrong-data": 18, "irrelevant": 12, "layout-broken": 4, "too-slow": 5, "other": 2, "unspecified": 0 },
      "flagged_at":             "iso8601",       // first transition into underperforming on or after window_start
      "pending_proposal_id":    "uuid | null"     // if a pending KnowledgeUpdateProposal exists
    }
  ],
  "next_cursor": "string | null"
}
```

### `GET /api/admin/feedback/quality/flagged/{agent_id}/{tool_name}/evidence`

Return the supporting evidence per FR-014: dispatch and feedback ids inside the current window.

**Response 200**:
```jsonc
{
  "agent_id": "string",
  "tool_name": "string",
  "window_start": "iso8601",
  "window_end":   "iso8601",
  "audit_event_ids":         ["uuid", "..."],     // capped at 500 most-recent
  "component_feedback_ids":  ["uuid", "..."],     // capped at 500 most-recent
  "category_breakdown":      { ... }
}
```

---

## 2. Knowledge update proposals

### `GET /api/admin/feedback/proposals`

List proposals.

**Query params**: `status` (`pending` | `accepted` | `applied` | `rejected` | `superseded`, default `pending`), `agent_id`, `tool_name`, `cursor`, `limit` (1–100, default 50).

**Response 200**: list of proposals matching `KnowledgeUpdateProposal` columns + an inlined evidence summary count.

### `GET /api/admin/feedback/proposals/{proposal_id}`

Full proposal including the `diff_payload` and the resolved evidence references.

**Response 200**:
```jsonc
{
  "id": "uuid",
  "agent_id": "string",
  "tool_name": "string",
  "artifact_path": "string",                    // always under backend/knowledge/
  "diff_payload": "string",                     // unified diff
  "artifact_sha_at_gen": "hex sha256",
  "current_artifact_sha": "hex sha256",         // computed at request time
  "is_current": true,                           // false if file changed since generation
  "evidence": {
    "audit_event_ids": ["uuid", "..."],
    "component_feedback_ids": ["uuid", "..."],
    "window_start": "iso8601",
    "window_end":   "iso8601"
  },
  "status": "pending | accepted | applied | rejected | superseded",
  "reviewer_user_id": "string | null",
  "reviewed_at": "iso8601 | null",
  "reviewer_rationale": "string | null",
  "applied_at": "iso8601 | null",
  "generated_at": "iso8601"
}
```

### `POST /api/admin/feedback/proposals/{proposal_id}/accept`

Accept (and apply, in one server-side transaction).

**Request body**:
```jsonc
{
  "edited_diff": "string | null"                 // optional; admin may modify the proposed diff before accepting
}
```

**Behavior**:
1. Validate proposal is `pending`.
2. Validate `proposal.artifact_path` resolves under `backend/knowledge/` (server-side; reject any escape attempt with `400 INVALID_PATH`).
3. Validate `current_artifact_sha == artifact_sha_at_gen`. If not, return `409 STALE_PROPOSAL` with the refreshed evidence and a hint to re-review (matches Edge Case "An admin attempts to accept a proposal that is no longer current").
4. Apply the diff (or `edited_diff`) to the artifact file atomically (write-then-rename).
5. Set `status='applied'`, `reviewer_user_id`, `reviewed_at`, `applied_at`.
6. Emit `proposal_review.proposal.accept` and `proposal_review.proposal.applied` audit events.

**Response 200**: the updated proposal record.

### `POST /api/admin/feedback/proposals/{proposal_id}/reject`

**Request body**:
```jsonc
{ "rationale": "string"  /* required, length-capped at 2048 chars */ }
```

**Behavior**: validate proposal is `pending`, set `status='rejected'`, store rationale, set reviewer fields, emit `proposal_review.proposal.reject` audit event.

**Response 200**: the updated proposal record.

---

## 3. Quarantine review

### `GET /api/admin/feedback/quarantine`

List quarantined feedback items in `held` status by default.

**Query params**: `status` (`held` | `released` | `dismissed`, default `held`), `cursor`, `limit` (1–100, default 50).

**Response 200**:
```jsonc
{
  "items": [
    {
      "feedback_id": "uuid",
      "user_id":     "string",                 // admin can see this for review purposes; non-admins never see it
      "source_agent": "string | null",
      "source_tool":  "string | null",
      "comment_raw":  "string | null",         // raw text shown ONLY in the admin quarantine surface, with explicit "untrusted text" framing in the UI
      "reason":       "string",
      "detector":     "inline | loop_pre_pass",
      "detected_at":  "iso8601",
      "status":       "held | released | dismissed"
    }
  ],
  "next_cursor": "string | null"
}
```

### `POST /api/admin/feedback/quarantine/{feedback_id}/release`

Returns the feedback's text to the synthesizer input pool (FR-026).

**Behavior**: set `quarantine_entry.status='released'`; set `component_feedback.comment_safety='clean'`; emit `quarantine.release` audit event.

**Response 200**: `{ "feedback_id": "uuid", "status": "released" }`.

### `POST /api/admin/feedback/quarantine/{feedback_id}/dismiss`

Keeps text quarantined permanently (sentiment+category still count per FR-024).

**Behavior**: set `quarantine_entry.status='dismissed'`; emit `quarantine.dismiss` audit event.

**Response 200**: `{ "feedback_id": "uuid", "status": "dismissed" }`.

---

## 4. Error responses

All endpoints use the existing FastAPI HTTPException convention. Unique status codes introduced by this feature:

| Code  | Meaning                                                                                          |
|-------|---------------------------------------------------------------------------------------------------|
| `403` | Caller lacks `admin` role.                                                                       |
| `404` | Proposal or feedback not found, OR found but cross-user (FR-009 — admins still see all, this case applies to user-side endpoints in [rest-user.md](./rest-user.md)). |
| `409 STALE_PROPOSAL` | Acceptance attempted on a proposal whose source artifact has changed since generation. |
| `400 INVALID_PATH`    | Proposal targets a path outside `backend/knowledge/`. Should never occur from system-generated proposals; defends against tampering. |
| `400 INVALID_INPUT`   | Field validation (length cap, missing required field, bad enum). |
