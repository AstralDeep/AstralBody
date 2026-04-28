# Contract: WebSocket Audit Events

**Branch**: `003-agent-audit-log`
**Channel**: existing user-scoped WebSocket served by `backend/orchestrator/orchestrator.py` at `ws://<host>/ws`.
**Direction added by this feature**: server → client only. There is no client → server audit message.

## Subscription model

A client receives `audit_append` events implicitly once it has completed `register_ui` on a connection authenticated to user `U`. There is no separate "subscribe to audit" message — every authenticated WS connection automatically receives `audit_append` events whose `actor_user_id == U`. The audit-log route on the frontend is the consumer; other routes on the same connection MAY ignore the event but MUST NOT see other users' events under any circumstances (FR-007 / FR-019, enforced server-side).

## Server → client message: `audit_append`

```jsonc
{
  "type": "audit_append",
  "event": { /* AuditEvent DTO — see data-model.md and rest-audit-api.md */ }
}
```

Sent exactly once per `audit_events` row insert that satisfies `actor_user_id == connection.user_id`. Ordering is best-effort recent-first as observed by the client; the manual refresh control (FR-010) is the canonical recovery path for any gap.

## Server-side filtering invariant

The publisher in `backend/audit/ws_publisher.py` MUST iterate only the connections whose `user_id == event.actor_user_id`. The publisher MUST NOT receive a "broadcast all" event and trust clients to filter. Tests (`backend/tests/integration/audit/test_ws_live_push.py`) MUST cover the case where two users are simultaneously connected to the same orchestrator process.

## Behavior under disconnect

The server does NOT buffer missed `audit_append` events for a disconnected client. On reconnect, the client re-renders the route and the manual refresh path (`GET /api/audit`) covers the gap. Buffering would multiply storage and complicate FR-019 (a buffered event must still be filterable per-user across reconnect). The simpler "live while connected, refresh on demand" model satisfies SC-001's 5 s freshness target while connected, and the refresh button restores correctness after a gap.

## What is NOT sent over WS

- Internal AU-9 fields (`prev_hash`, `entry_hash`, `key_id`).
- Bulk historical events. Historical lookup goes through the REST endpoint, not the WS channel.
- Other users' events — under any condition.

## Test obligations

Contract / integration tests MUST cover:

1. A user connected on connection A receives every audit event for which `actor_user_id == A.user_id`.
2. A second user connected on connection B in the same process never receives any event for connection A's user.
3. Disconnect-then-reconnect produces no `audit_append` for events that occurred during the gap; the manual refresh REST call surfaces them.
4. The DTO sent over WS is byte-equivalent to the DTO returned by `GET /api/audit/{event_id}` for the same row.
