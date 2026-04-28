# REST API: User Surfaces

**Feature**: `004-component-feedback-loop`
**Substrate**: existing FastAPI app — see [backend/orchestrator/api.py](../../../backend/orchestrator/api.py).

These endpoints are the REST counterparts of the WebSocket actions in [ws-protocol.md](./ws-protocol.md). They exist for cases where REST is more natural than WS (listing the user's own feedback, programmatic clients, retry semantics on flaky connections per FR-005). The submit path is also exposed via REST for resilience but the dashboard's primary path is the WS action.

All routes require Keycloak JWT (any authenticated user). All routes are strictly per-user — the `actor_user_id` is derived from the JWT `sub` claim and applied to every query (FR-009, FR-031). Mounted under `/api/feedback/`. Auto-documented via `/docs`.

---

## 1. List my feedback

### `GET /api/feedback`

**Query params**: `cursor` (opaque), `limit` (1–100, default 50), `lifecycle` (`active` | `superseded` | `retracted`, default `active`), `source_tool`, `source_agent`, `start`, `end` (iso8601).

**Response 200**:
```jsonc
{
  "items": [
    {
      "id":               "uuid",
      "conversation_id":  "string | null",
      "correlation_id":   "string | null",
      "source_agent":     "string | null",
      "source_tool":      "string | null",
      "component_id":     "string | null",
      "sentiment":        "positive | negative",
      "category":         "wrong-data | irrelevant | layout-broken | too-slow | other | unspecified",
      "comment":          "string | null",        // user always sees their own comment, regardless of safety status
      "comment_safety":   "clean | quarantined",  // surfaced so the user knows when their text is held back from the system's improvement loop
      "lifecycle":        "active | superseded | retracted",
      "created_at":       "iso8601",
      "updated_at":       "iso8601"
    }
  ],
  "next_cursor": "string | null"
}
```

**Cross-user behavior**: queries are scoped to the JWT `sub`. A user requesting another user's records by guessing ids cannot succeed; existence and not-found are indistinguishable.

---

## 2. Get a single feedback record

### `GET /api/feedback/{feedback_id}`

Returns the user's own record, or `404 NOT_FOUND` if the id does not exist OR belongs to another user (indistinguishable per FR-009).

---

## 3. Submit feedback (REST alternative to WS)

### `POST /api/feedback`

Request body matches the WS `component_feedback` payload (see [ws-protocol.md §2.1](./ws-protocol.md)).

```jsonc
{
  "correlation_id": "string | null",
  "component_id":   "string | null",
  "source_agent":   "string | null",
  "source_tool":    "string | null",
  "sentiment":      "positive | negative",
  "category":       "wrong-data | irrelevant | layout-broken | too-slow | other | unspecified",
  "comment":        "string | null"
}
```

Server behavior is identical to the WS action: validate, length-cap comment at 2048 chars, run inline safety screen, apply 10s dedup window, write audit event on out-of-window submissions.

**Response 200**:
```jsonc
{
  "feedback_id": "uuid",
  "status":      "recorded | quarantined",
  "deduped":     false                       // true when the submission collapsed into an in-window prior submission
}
```

**Response 400** (`INVALID_INPUT`): malformed payload.

---

## 4. Retract own feedback

### `POST /api/feedback/{feedback_id}/retract`

**Server behavior**:
1. Resolve `feedback_id` scoped to the JWT subject. Cross-user → `404 NOT_FOUND`.
2. If `now() - created_at > 24 h` → `409 EDIT_WINDOW_EXPIRED`.
3. Set `lifecycle='retracted'`, emit `feedback.retract` audit event.

**Response 200**: `{ "feedback_id": "uuid", "lifecycle": "retracted" }`.

---

## 5. Amend own feedback

### `PATCH /api/feedback/{feedback_id}`

**Request body**: subset of submit fields (sentiment, category, comment); fields omitted are inherited from the prior version.

**Server behavior**:
1. Resolve scoped to JWT subject. Cross-user → `404 NOT_FOUND`.
2. If `now() - created_at > 24 h` → `409 EDIT_WINDOW_EXPIRED`.
3. Mark target `superseded`. Insert new `active` row with `superseded_by` chain pointing back. Re-run inline safety screen on the new comment. Emit `feedback.amend` audit event.

**Response 200**:
```jsonc
{
  "prior_id": "uuid",
  "feedback_id": "uuid",                     // the new active row
  "lifecycle": "active",
  "comment_safety": "clean | quarantined"
}
```

---

## 6. Status / error codes summary

| Status | Code                  | Reason                                                                 |
|--------|-----------------------|------------------------------------------------------------------------|
| 200    | —                     | Success.                                                               |
| 400    | `INVALID_INPUT`       | Field validation (enum, length, missing required).                     |
| 401    | `UNAUTHENTICATED`     | Missing or invalid JWT.                                                |
| 404    | `NOT_FOUND`           | Resource does not exist OR belongs to another user (indistinguishable).|
| 409    | `EDIT_WINDOW_EXPIRED` | Retract / amend attempted after 24 h.                                  |
