# Contract: WebSocket Protocol Messages

**Feature**: 001-tool-stream-ui
**Layer**: Wire protocol on `ws://localhost:8001/ws` (browser ↔ orchestrator) and on the existing agent ↔ orchestrator WebSocket.
**Revised**: 2026-04-09 — `error` payload (§A5) extended with `phase`, `attempt`, `next_retry_at_ms` to distinguish reconnecting from failed (FR-021a). Wire format unchanged for the data path; the orchestrator's internal fan-out (FR-009a) requires no new wire messages because it sends the same `ui_stream_data` to multiple websockets.

This document specifies every message added or extended by this feature. All messages are JSON. Existing messages not listed here are unchanged.

---

## A. Browser ↔ Orchestrator

### A1. `stream_subscribe` (extends existing `ui_event` action)

**Direction**: Browser → Orchestrator
**Defined in**: extension to existing `ui_event` action in [backend/orchestrator/orchestrator.py](../../../backend/orchestrator/orchestrator.py) lines ~1012-1027.

```json
{
  "type": "ui_event",
  "action": "stream_subscribe",
  "session_id": "<chat_id>",
  "payload": {
    "tool_name": "weather.live_forecast",
    "agent_id": "weather",
    "params": { "lat": 51.5, "lon": -0.12, "interval_s": 5 },
    "component_hint": "stream-1"
  }
}
```

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | yes | The chat_id this stream belongs to. MUST be the chat the user is currently viewing. |
| `payload.tool_name` | string | yes | A registered streamable tool. |
| `payload.agent_id` | string | yes | The agent that owns the tool. |
| `payload.params` | object | yes | Tool input arguments, validated against the tool's input schema. ≤ 16 KB serialized. |
| `payload.component_hint` | string | no | Optional client-suggested id, ignored by the server (server assigns the canonical `stream_id`). Kept for round-trip debugging only. |

**Server response**: `stream_subscribed` (success) OR `stream_error` (failure). See A3, A6.

**Backwards compatibility note**: this is an *extension* of an existing action; today's polling-based subscribe call site is unchanged. The server distinguishes push from poll by looking up `_streamable_tools[tool_name].kind`.

**Fan-out / dedup behavior** (FR-009a, added 2026-04-09): On the server, the subscription is keyed by `(user_id, chat_id, tool_name, sha256(params)[:16])`. If the user already has an active subscription matching that key (from another tab, another window, or even the same tab having already subscribed), the new request **attaches** the requesting websocket to the existing subscription instead of creating a second one. The server still replies with `stream_subscribed` so the client can begin merging chunks; the `stream_id` returned will be the existing one. From the client's perspective the wire shape is identical whether this was a fresh subscribe or an attach. The per-user concurrency cap (FR-015 = 10 active) counts unique deduplicated subscriptions, not attach calls.

---

### A2. `stream_unsubscribe` (extends existing `ui_event` action)

**Direction**: Browser → Orchestrator

```json
{
  "type": "ui_event",
  "action": "stream_unsubscribe",
  "session_id": "<chat_id>",
  "payload": {
    "stream_id": "stream-7c2a1f"
  }
}
```

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | yes | Chat the stream belongs to. |
| `payload.stream_id` | string | yes | The id returned by `stream_subscribed`. |

**Server side**: validates ownership, removes the requesting websocket from the subscription's `subscribers` list, sends a final `ui_stream_data` chunk with `terminal: true` **to that websocket only**. If `subscribers` becomes empty as a result, the subscription transitions to `DORMANT` (per [data-model.md §3](../data-model.md)). If other tabs of the same user are still subscribed, **they are unaffected** — the stream stays `ACTIVE` for them.

---

### A3. `stream_subscribed` (NEW server-to-client confirmation)

**Direction**: Orchestrator → Browser

```json
{
  "type": "stream_subscribed",
  "stream_id": "stream-7c2a1f",
  "tool_name": "weather.live_forecast",
  "agent_id": "weather",
  "session_id": "<chat_id>",
  "max_fps": 30,
  "min_fps": 5,
  "attached": false
}
```

Sent immediately after a successful `stream_subscribe`. The client uses `stream_id` to associate the upcoming `ui_stream_data` chunks with the right component.

**Field `attached`** (added 2026-04-09 for FR-009a): `true` when the orchestrator attached this websocket to an existing deduplicated subscription (another tab of the same user already had this stream running); `false` when it created a fresh subscription. Purely informational — the client behavior is the same in both cases — but useful for debugging "why is my retry counter not at 0?" scenarios where a new tab attaches to a stream that's mid-`RECONNECTING`. When `attached: true`, the next chunk the client receives may be a reconnecting chunk rather than a fresh data chunk.

---

### A4. `ui_stream_data` (NEW)

**Direction**: Orchestrator → Browser
**This is the core streaming message.**

```json
{
  "type": "ui_stream_data",
  "stream_id": "stream-7c2a1f",
  "session_id": "<chat_id>",
  "seq": 42,
  "components": [
    {
      "type": "metric",
      "id": "stream-7c2a1f",
      "label": "Temperature",
      "value": "12.4°C",
      "delta": "+0.3"
    }
  ],
  "raw": { "temp_c": 12.4, "wind_kph": 8.2, "ts": 1759981234 },
  "terminal": false,
  "error": null
}
```

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `stream_id` | string | yes | Identifies which subscription this chunk belongs to. The frontend uses this to find the component in `uiComponents` to merge into. |
| `session_id` | string | yes | The chat the stream belongs to. The frontend SHOULD drop the chunk if its current chat differs (defense in depth — the server already enforces this). |
| `seq` | int | yes | Per-stream sequence number, monotonically increasing. Frontend uses this to detect out-of-order delivery (drop if `seq <= last_seen`). |
| `components` | array | yes | Either `[component]` or `[]` (empty when this chunk is purely an error/terminal marker). At least one top-level component MUST have `id == stream_id`. |
| `raw` | any | no | Optional raw payload the tool wants the frontend to have access to (e.g., for client-side chart rendering). |
| `terminal` | bool | no | True iff this is the last chunk for this stream. Client should remove the stream from its active subscriptions table on receipt. |
| `error` | object | no | If non-null, the stream has failed. See A5. |

**Frontend merge rule** (from data-model.md §3): walk `uiComponents`, find the component whose `id` matches `stream_id` (recursing into containers), replace it with the new component. If not found, append it to the canvas (this is how the **first** chunk is rendered).

---

### A5. `error` object inside `ui_stream_data`

*Revised 2026-04-09 for FR-021a auto-retry: adds `phase`, `attempt`, `next_retry_at_ms` so the frontend can distinguish "we're trying" from "we gave up".*

```json
// Reconnecting (mid-backoff, system is retrying):
{
  "code": "upstream_unavailable",
  "message": "Upstream weather service is unreachable, retrying…",
  "phase": "reconnecting",
  "attempt": 2,
  "next_retry_at_ms": 1759981239000,
  "retryable": false
}

// Failed (terminal — manual retry required):
{
  "code": "upstream_unavailable",
  "message": "Upstream weather service is unreachable",
  "phase": "failed",
  "retryable": true
}

// Auth failure (immediate, never auto-retried):
{
  "code": "unauthenticated",
  "message": "Your session has expired. Please sign in again.",
  "phase": "failed",
  "retryable": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | One of: `tool_error`, `unauthenticated`, `unauthorized`, `rate_limited`, `upstream_unavailable`, `chunk_too_large`, `cancelled`. |
| `message` | string | yes | Safe-to-display description. MUST NOT include stack traces, file paths, or internal IDs. |
| `phase` | `"reconnecting"` \| `"failed"` | yes | **NEW**. `"reconnecting"` = the orchestrator is in the FR-021a retry loop (1s/5s/15s backoff, max 3 attempts) and the stream may auto-recover. `"failed"` = terminal; the user must take action. |
| `attempt` | int | when `phase == "reconnecting"` | Current retry attempt (1, 2, or 3). Lets the UI render "Reconnecting (2/3)…". |
| `next_retry_at_ms` | int | when `phase == "reconnecting"` | Wall-clock epoch milliseconds of the next scheduled retry attempt. Lets the UI render a countdown if desired. |
| `retryable` | bool | yes | If true AND `phase == "failed"`, the frontend SHOULD render a manual retry button. Always `false` while `phase == "reconnecting"` (no manual button — system is already retrying). Always `false` for codes `unauthenticated`, `unauthorized`, `chunk_too_large`, `cancelled`. |

**Auth carve-out**: codes `unauthenticated` and `unauthorized` MUST go directly to `phase: "failed"` with `retryable: false`. The orchestrator MUST NOT enter the `RECONNECTING` state for these codes (security: never auto-grind through revoked tokens). See [data-model.md §6 classification table](../data-model.md) and research §12.

When `error` is set, `components` MAY contain a single component with the same `id` showing the error state visually (frontend can also generate this from the error alone if no component is provided). For `phase: "reconnecting"` chunks the frontend MUST preserve the existing component's `id` so subsequent reconnect attempts and the eventual recovery chunk merge into the same DOM node.

---

### A6. `stream_error` (NEW server-to-client rejection at subscribe time)

**Direction**: Orchestrator → Browser

```json
{
  "type": "stream_error",
  "request_action": "stream_subscribe",
  "session_id": "<chat_id>",
  "payload": {
    "tool_name": "weather.live_forecast",
    "code": "limit_exceeded",
    "message": "You already have 10 active streams"
  }
}
```

Used when the subscribe call itself fails before any subscription is created. Codes:

| Code | Meaning |
|---|---|
| `limit_exceeded` | Per-user concurrent stream cap reached. |
| `not_streamable` | Tool exists but is not declared streamable. |
| `unauthorized` | User lacks scope or chat ownership. |
| `params_invalid` | `payload.params` failed schema validation. |
| `params_too_large` | `payload.params` exceeds 16 KB. |
| `agent_unavailable` | The agent owning the tool is not connected. |

---

## B. Orchestrator ↔ Agent

### B1. `MCPRequest` with streaming flag (extends existing)

**Direction**: Orchestrator → Agent
**Defined in**: existing [backend/shared/protocol.py](../../../backend/shared/protocol.py) `MCPRequest`.

The orchestrator already sends `MCPRequest` for tool calls. The only change is a new optional metadata field:

```json
{
  "type": "mcp_request",
  "request_id": "req-9af1e2",
  "method": "tools/call",
  "params": {
    "name": "live_forecast",
    "arguments": { "lat": 51.5, "lon": -0.12 },
    "_stream": true,
    "_stream_id": "stream-7c2a1f"
  }
}
```

When `_stream == true`, the agent MUST treat the request as long-lived and use `ToolStreamData` responses (B2) instead of a single `MCPResponse`.

---

### B2. `ToolStreamData` (NEW)

**Direction**: Agent → Orchestrator
**Defined in**: new dataclass added to [backend/shared/protocol.py](../../../backend/shared/protocol.py).

```json
{
  "type": "tool_stream_data",
  "request_id": "req-9af1e2",
  "stream_id": "stream-7c2a1f",
  "agent_id": "weather",
  "tool_name": "live_forecast",
  "seq": 42,
  "components": [ { "type": "metric", "id": "stream-7c2a1f", "label": "Temperature", "value": "12.4°C" } ],
  "raw": { "temp_c": 12.4 },
  "terminal": false,
  "error": null
}
```

**Routing rule** (orchestrator side, revised for fan-out): on receipt, look up the `StreamSubscription` by `(user_id, chat_id, tool_name, params_hash)` (the `request_id` is still used for in-flight tracking but the routing key is now the subscription). For each websocket `ws` in `subscription.subscribers`:

1. Validate the per-subscriber authorization invariant ([data-model.md §8](../data-model.md)).
2. Run `components` through ROTE adaptation **for that ws's device profile** (cached per-ws by ROTE — same call as today's `send_ui_render`, no extra cost in the common case where multiple subscribers share one device profile).
3. Send to that `ws` as `ui_stream_data` (A4), keeping `seq`, `stream_id`, etc.

The send loop is `await asyncio.gather(*sends)` so per-subscriber latency is parallelized; a slow subscriber does not delay fast ones.

**Field cap**: total serialized size ≤ 64 KB (or `max_chunk_bytes` from `StreamableToolMetadata` if overridden). Oversize chunks are dropped at the orchestrator with a `chunk_too_large` error transition (which goes directly to `FAILED`, not `RECONNECTING` — see [data-model.md §6](../data-model.md)).

---

### B3. `ToolStreamCancel` (NEW)

**Direction**: Orchestrator → Agent

```json
{
  "type": "tool_stream_cancel",
  "request_id": "req-9af1e2",
  "stream_id": "stream-7c2a1f"
}
```

Sent when:

- The user navigates away (`load_chat` or disconnect) and the orchestrator wants the agent to stop producing.
- Explicit `stream_unsubscribe`.
- Token revoked.
- TTL expiry on a dormant stream.

Agent obligation: close the underlying async generator (`agen.aclose()`), free upstream subscriptions, optionally send a final `ToolStreamData` with `terminal: true`. SHOULD complete within 1 s.

---

### B4. `ToolStreamEnd` (NEW — natural completion only)

**Direction**: Agent → Orchestrator

```json
{
  "type": "tool_stream_end",
  "request_id": "req-9af1e2",
  "stream_id": "stream-7c2a1f"
}
```

Sent by the agent when the streaming tool's async generator returns naturally (no more data). The orchestrator forwards as a final `ui_stream_data` with `terminal: true` and removes the subscription.

---

### B5. `RegisterAgent.skills[].metadata` (extends existing)

**Direction**: Agent → Orchestrator (at startup)

The existing `AgentSkill.metadata` dict gains optional streaming descriptors:

```json
{
  "name": "live_forecast",
  "id": "weather.live_forecast",
  "description": "Stream live weather updates",
  "input_schema": { "...JSONSchema..." },
  "metadata": {
    "streamable": true,
    "streaming_kind": "push",
    "default_interval_s": 5,
    "max_fps": 30,
    "min_fps": 5,
    "max_chunk_bytes": 65536
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `streamable` | bool | yes | Marks the tool as eligible. |
| `streaming_kind` | `"push" \| "poll"` | yes | Selects which path the orchestrator uses. |
| `default_interval_s` | number | poll only | Default polling cadence. Existing field. |
| `max_fps` / `min_fps` | int | push only | Coalescing bounds. |
| `max_chunk_bytes` | int | push only | Per-stream override of 64 KB cap. |

Tools without `streamable: true` are exactly as today (single response, never streamed). This is the safe default.

---

## C. Wire size and validation summary

| Property | Value | Enforced where |
|---|---|---|
| Max `params` size | 16 KB | Orchestrator at `stream_subscribe` |
| Max chunk size | 64 KB (overridable per tool) | Orchestrator at `ToolStreamData` ingest |
| Max active streams per user | 10 (existing `_MAX_STREAM_SUBSCRIPTIONS`) | Orchestrator at `stream_subscribe` |
| Max dormant streams per user | 50 | Orchestrator dormant table |
| Dormant TTL | 3600 s | Orchestrator background sweeper |
| FPS clamp | 5–30 (overridable per tool) | Orchestrator coalescing buffer |

## D. What this contract intentionally does **not** add

- No new REST endpoints (research §4).
- No new top-level WS message families — `stream_*` and `tool_stream_*` are extensions of the existing `ui_event` and MCP framings, not a new namespace.
- No client capability negotiation — capability is implied by protocol version and feature flag (`FF_TOOL_STREAMING`).
