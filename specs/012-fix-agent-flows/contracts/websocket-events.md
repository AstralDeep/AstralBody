# Contract: WebSocket Events Touched

**Feature**: 012-fix-agent-flows
**Date**: 2026-05-01

This feature touches two WebSocket channels: the **test channel** used inside `CreateAgentModal` Step 4, and the **dashboard channel** used by the rest of the UI. No new channels are introduced. Message shapes below describe only the events this feature relies on or adds.

All WS connections inherit existing Keycloak-derived auth (token in the `Authorization` header during handshake). No change to authorization.

---

## Test channel — `/ws/test/{draft_id}` (or equivalent existing route)

Used by `CreateAgentModal` to chat with the draft under test.

### Server → client: `draft_status`

Sent immediately after handshake and on every status transition while the channel is open.

```json
{
  "type": "draft_status",
  "draft_id": "string",
  "status": "generated|testing|analyzing|rejected|live|error",
  "error_message": "string|null",
  "missing_credentials": ["string"]
}
```

Story 1 fix uses this event to drive the Test screen's status badge. Story 2 fix uses `error_message` and `missing_credentials` to render actionable failure / credential-missing states (FR-005, FR-006a, FR-006b).

### Client → server: `chat_message` (existing `ui_event`)

Existing shape — unchanged:
```json
{
  "type": "ui_event",
  "action": "chat_message",
  "session_id": "string|null",
  "payload": {
    "message": "string",
    "chat_id": "string|null",
    "draft_agent_id": "string"
  }
}
```

### Server → client: `chat_message` / `chat_chunk`

Existing message-streaming shapes — unchanged. Story 2 ensures these are emitted; today they can be silently dropped if the draft subprocess never registered.

### Server → client: `draft_runtime_error` *(new event in this feature)*

Emitted instead of silently dropping a message when the draft subprocess is not running or failed to bind a port.

```json
{
  "type": "draft_runtime_error",
  "draft_id": "string",
  "reason": "subprocess_failed_to_start|port_discovery_timeout|crashed_during_turn|missing_credentials",
  "detail": "string",
  "retryable": true
}
```

Frontend behavior on receipt: show the failure inline in the test chat with a `Retry` action that re-sends the user's message (which re-enters `start_draft_agent`). Required by FR-005 acceptance scenario 2.3.

### Server → client: `draft_promoted` *(new event in this feature)*

Emitted after auto-approval succeeds, before the dashboard `agent_list` broadcast. Lets the Test screen show a "now live" success state without listening to the broader dashboard channel.

```json
{
  "type": "draft_promoted",
  "draft_id": "string",
  "agent_id": "string"
}
```

---

## Dashboard channel — existing user-scoped WS

Used by `DashboardLayout` and the agents-modal for live-agent state.

### Server → client: `agent_list` (existing)

Existing event — see [`useWebSocket.ts:327–340`](../../../frontend/src/hooks/useWebSocket.ts#L327-L340). **Now also broadcast** as a side effect of `approve_agent` succeeding (Story 3 fix). The frontend's existing handler is unchanged; the change is purely server-side timing.

```json
{
  "type": "agent_list",
  "agents": [ /* AgentCard[] */ ]
}
```

### Server → client: `dashboard` (existing)

Existing periodic broadcast. **Unchanged**, but the test for `_is_draft_agent` continues to filter drafts so newly-live agents (no longer drafts) start appearing in this broadcast naturally.

---

## Sequencing — happy path

```
T+0   user clicks Approve in CreateAgentModal Step 4
T+0   POST /api/agents/drafts/{id}/approve  (server: status=analyzing, run security checks)
T+~s  server: status=live + .draft removed + ownership re-asserted + agent_cards register
T+~s  WS test channel ──▶ {type: "draft_promoted"}
T+~s  WS dashboard ──────▶ {type: "agent_list", agents:[…now includes new live agent…]}
T+~s  HTTP response 200 with {status: "live", agent_id, draft_id}
T+~s  CreateAgentModal shows "Now live" success state; dashboard re-renders live agents list
```

The HTTP response and WS broadcast are not strictly ordered — the frontend treats either as confirmation. SC-003's 10-second budget covers the entire sequence.

---

## Compatibility

`draft_runtime_error` and `draft_promoted` are new event types. Existing frontend code ignores unknown WS event types (per the `useWebSocket` reducer's default case), so older clients receiving these events would silently no-op — backward-compatible.
