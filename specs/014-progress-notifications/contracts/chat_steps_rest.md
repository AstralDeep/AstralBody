# Contract: `GET /chats/{chat_id}/steps` — load persisted step entries

REST endpoint exposed by [`backend/orchestrator/api.py`](../../../backend/orchestrator/api.py). Used by the frontend on initial chat load and on WebSocket reconnect (see R9) to rehydrate the step trail for prior turns.

## Endpoint

```text
GET /chats/{chat_id}/steps
```

## Authentication / authorization

- Same Keycloak-bearer auth as every other `/chats/*` endpoint (Constitution VII).
- Authorization: requesting user MUST own `chat_id` (matches the `user_id` scope check used by `get_chat`, `add_message`, etc. — see [`history.py:105`](../../../backend/orchestrator/history.py#L105) for the existing pattern).
- 403 if the chat exists but belongs to a different user.
- 404 if the chat does not exist (under the requesting user's scope).

## Query parameters

None. The endpoint always returns the chat's full step history in chronological order. Future paging can be added without breaking this contract by introducing optional `?after_started_at=` / `?limit=` parameters.

## Response shape

```json
{
  "chat_id": "<uuid>",
  "steps": [
    {
      "id": "<uuid>",
      "chat_id": "<uuid>",
      "turn_message_id": 12345,
      "kind": "tool_call",
      "name": "search_grants",
      "status": "completed",
      "args_truncated": "{\"query\": \"NSF biomedical 2026\"}",
      "args_was_truncated": false,
      "result_summary": "Found 17 matching grants; top match: NSF-2026-XYZ ...",
      "result_was_truncated": true,
      "error_message": null,
      "started_at": 1746489600000,
      "ended_at": 1746489603450
    }
  ]
}
```

- `steps` is sorted ascending by `started_at`. Stable sort preserves insertion order for ties.
- Each `step` object matches the `ChatStep` shape in [`data-model.md`](../data-model.md) and the per-event shape in `chat_step_event.md` exactly.

## Read-time healing (FR-021 reconnect path)

Before serializing, the endpoint:

1. Fetches all `chat_steps` rows for the chat.
2. For any row where `status = 'in_progress'` AND `(now - started_at) > 30_000` ms AND there is no active task on the chat (i.e., `TaskManager.get_active_task(chat_id) is None`), the row is treated as `interrupted` for the response. The healing is **not** persisted to the DB on this read — only stamped on the response — so a still-running step on a slow turn isn't prematurely flipped if the read raced with a backend hiccup. A separate housekeeping path (cleanup on next turn start) flushes truly-orphaned rows.

## PHI guarantees

The endpoint applies `phi_redactor.redact(...)` defensively to `args_truncated`, `result_summary`, and `error_message` on every read, providing the second enforcement point described in R4. This is a no-op on rows that were redacted at write time but protects against rows from any future code path that bypassed the recorder.

## Errors

| HTTP | Body | When |
|---|---|---|
| 200 | full response | success |
| 401 | standard auth error | missing/invalid token |
| 403 | `{ "detail": "Chat not owned by user" }` | chat exists under another user |
| 404 | `{ "detail": "Chat not found" }` | no such chat for this user |
| 500 | `{ "detail": "Failed to load steps" }` | unexpected; structured-logged |

## Caching

`Cache-Control: no-store` — step status mutates while a turn is in flight; clients MUST refetch on every chat load and on reconnect.
