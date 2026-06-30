# Contract: WebSocket Protocol (consumed, not defined)

The Android client conforms to the **existing** orchestrator WS protocol (`/ws`) — the same one the web shell and the Windows client use. This is a consumer contract: the client must not require any new message type or field. Endpoint: `ws(s)://<host>:8001/ws`.

## Outbound (client → orchestrator)

### register_ui (first frame)
```json
{ "type": "register_ui", "token": "<jwt|dev-token>",
  "capabilities": ["render", "stream"], "session_id": "<id>",
  "device": { "device_type": "android", "screen_width": 1080, "screen_height": 2340,
              "viewport_width": 1080, "viewport_height": 2340, "pixel_ratio": 2.75,
              "has_touch": true, "supported_types": ["text","card","table", "..."] },
  "resumed": false }
```

### ui_event (all interactions)
```json
{ "type": "ui_event", "action": "<action>", "session_id": "<chat_id|null>", "payload": { } }
```
Actions used: `chat_message` (`payload.message`, optional `chat_id`/`attachments`), `new_chat`, `load_chat` (`chat_id`), `get_history`, `discover_agents`, `enable_recommended_agents` (`source`, optional `agent_ids`), `set_agent_permissions` (`agent_id`, `scopes`), `stream_subscribe` (`tool_name`, `params`), `stream_unsubscribe` (`stream_id`). Rendered buttons forward their declared `action`+`payload` verbatim.

## Inbound (orchestrator → client)

| `type` | Key fields | Client action |
|--------|-----------|---------------|
| `ui_render` | `target?` (`canvas`/`chat`/`history`), `components[]`, `html?` | Full canvas/chat replace; render `components` (ignore `html`) |
| `ui_upsert` | `chat_id?`, `ops:[{op, component_id, component, html?}]` | In-place upsert/remove by `component_id` |
| `ui_stream_data` | `stream_id`, `session_id`, `seq`, `components[]`, `html?`, `raw?`, `terminal`, `error?` | Render in place keyed by `stream-<stream_id>` (session filter + seq dedupe + terminal + error→alert) |
| `stream_subscribed` | `stream_id`, `tool_name`, `attached`, `max_fps`, `min_fps` | Placeholder for the stream node + status |
| `stream_error` | `request_action`, `session_id`, `payload:{stream_id?, code, message}` | Alert at the stream node, or status line |
| `stream_unsubscribed` / `stream_list` | (legacy poll) | Best-effort cleanup / ignore |
| `chat_created` | `payload.chat_id` | Set active chat |
| `chat_loaded` | `chat:{id, messages[…]}` | Replay transcript + canvas |
| `agent_list` | `agents:[{id,name,description,is_public,scopes}]` | Populate Agents screen |
| `history_list` | `chats:[{id,title,…}]` | Populate History screen |
| `chat_status` | `status` (`thinking`/`executing`/`done`/…), `message?` | Status indicator |
| `chrome_render` | `region` (`modal`/`topbar`), `html`, `mode` | **Acknowledge, do not embed** (native screens instead) |
| `auth_required` | `reason` | Re-fetch session / re-auth, then reconnect |

**Streaming request flow**: client sends `ui_event{action:"stream_subscribe", payload:{tool_name, params}}` → server auto-dispatches and emits `stream_subscribed` then `ui_stream_data` frames → `terminal:true` ends it. `capabilities:["stream"]` is advertised for parity but is not server-gated.
