# Contract: SDUI WebSocket Protocol

**Version**: 1.0 | **Date**: 2026-04-03

## Overview

The Flutter client communicates with the AstralBody backend via a persistent WebSocket connection. The backend sends Server-Driven UI (SDUI) component trees; the client renders them. All messages are JSON-encoded.

---

## Connection

**Endpoint**: `ws://{BACKEND_HOST}:{BACKEND_PORT}/ws?token={JWT}`

Alternative (project-scoped): `ws://{BACKEND_HOST}:{BACKEND_PORT}/ws/stream/mcp:{projectId}?token={JWT}`

### Connection Lifecycle
```
Client                              Server
  │                                   │
  │ 1. WebSocket connect              │
  │──────────────────────────────────>│
  │                                   │
  │ 2. register_ui                    │
  │──────────────────────────────────>│
  │                                   │
  │ 3. session_id                     │
  │<──────────────────────────────────│
  │                                   │
  │ 4. system_config                  │
  │<──────────────────────────────────│
  │                                   │
  │ 5. ui_render (initial tree)       │
  │<──────────────────────────────────│
  │                                   │
  │     ... bidirectional messages ... │
```

---

## Client → Server Messages

### register_ui
Sent immediately after WebSocket connects. Declares client capabilities and device profile.

```json
{
  "type": "register_ui",
  "token": "<JWT>",
  "capabilities": ["text", "button", "input", "card", "table", "list", "alert", "progress", "metric", "code", "image", "grid", "tabs", "divider", "collapsible", "bar_chart", "line_chart", "pie_chart", "plotly_chart", "color_picker", "file_upload", "file_download", "container"],
  "session_id": "preserved-session-id-or-null",
  "device": { /* DeviceProfile map — see device-profile.md */ }
}
```

### chat_message
Send a user message to the active chat.

```json
{
  "type": "chat_message",
  "message": "What is the weather?",
  "chat_id": "chat-uuid-or-null",
  "display_message": "What is the weather?"
}
```

### ui_event
User interaction with a SDUI component (button click, input submit, etc.).

```json
{
  "type": "ui_event",
  "action": "button_click",
  "payload": {
    "component_id": "btn-123",
    "value": "submit"
  }
}
```

### Chat & Component Management

| Type | Payload | Purpose |
|------|---------|---------|
| `new_chat` | `{}` | Create new chat session |
| `load_chat` | `{ "chat_id": "uuid" }` | Load existing chat |
| `get_history` | `{}` | Request recent chat list |
| `get_dashboard` | `{}` | Request system config |
| `discover_agents` | `{}` | List connected agents |
| `save_component` | `{ "chat_id", "component_data", "component_type", "title?" }` | Save UI component |
| `get_saved_components` | `{ "chat_id?" }` | Fetch saved components |
| `delete_saved_component` | `{ "component_id" }` | Delete saved component |
| `combine_components` | `{ "source_id", "target_id" }` | Merge two components via LLM |
| `condense_components` | `{ "component_ids": [] }` | Consolidate multiple components |

---

## Server → Client Messages

### ui_render
Full SDUI component tree replacement. Replaces all current components.

```json
{
  "type": "ui_render",
  "components": [
    {
      "type": "card",
      "id": "card-1",
      "title": "Weather",
      "content": [
        { "type": "text", "text": "Sunny, 72°F" },
        { "type": "metric", "title": "Humidity", "value": "45%", "icon": "💧" }
      ]
    }
  ]
}
```

### ui_update
Replace specific components by ID within the existing tree.

```json
{
  "type": "ui_update",
  "components": [
    { "type": "metric", "id": "metric-1", "title": "Temperature", "value": "75°F" }
  ]
}
```

### ui_append
Append data to an existing component (used for streaming chat responses).

```json
{
  "type": "ui_append",
  "target_id": "chat-stream",
  "data": {
    "type": "text",
    "text": " additional streamed text"
  }
}
```

### Status & Configuration

| Type | Payload | Purpose |
|------|---------|---------|
| `session_id` | `{ "session_id": "uuid" }` | Session ID for reconnect |
| `system_config` | `{ "config": { "agents": [], "total_tools": N } }` | Dashboard data |
| `agent_registered` | `{ "agent_id", "name", "tools": [] }` | New agent connected |
| `chat_status` | `{ "status": "thinking\|executing\|done", "message?" }` | Processing state |
| `chat_created` | `{ "payload": { "chat_id": "uuid" } }` | New chat confirmation |
| `chat_loaded` | `{ "chat": { ... } }` | Chat data loaded |
| `history_list` | `{ "chats": [] }` | Recent chat list |
| `heartbeat` | `{ "timestamp": N }` | Keep-alive (every 5s during ops) |
| `theme` | `{ "colors": {}, "typography": {} }` | Dynamic theme override |
| `rote_config` | `{ "capabilities": {} }` | Device capability confirmation |
| `saved_components_list` | `{ "components": [] }` | Saved component list |
| `component_saved` | `{ "component": {} }` | Save confirmation |
| `components_combined` | `{ "removed_ids": [], "new_components": [] }` | Combine result |
| `components_condensed` | `{ "removed_ids": [], "new_components": [] }` | Condense result |

---

## SDUI Component Types (23 registered)

| Type | Category | Key Fields | Interactive |
|------|----------|------------|-------------|
| `container` | Layout | `children`, `direction`, `gap` | No |
| `grid` | Layout | `children`, `columns` | No |
| `tabs` | Layout | `tabs: [{label, content}]` | Yes (tab switching) |
| `collapsible` | Layout | `title`, `content`, `expanded` | Yes (expand/collapse) |
| `divider` | Layout | `style?` | No |
| `text` | Content | `text`, `variant` (h1/h2/h3/body/caption) | No |
| `card` | Content | `title`, `content` (children) | No |
| `alert` | Content | `message`, `severity` (info/success/warning/error) | No |
| `image` | Content | `url`, `alt`, `width?`, `height?` | No |
| `button` | Input | `label`, `action`, `variant` | Yes (click → ui_event) |
| `input` | Input | `placeholder`, `value`, `id` | Yes (submit → ui_event) |
| `color_picker` | Input | `value`, `id` | Yes (change → ui_event) |
| `file_upload` | Input | `accept?`, `multiple?` | Yes (file select → upload) |
| `file_download` | Action | `url`, `filename` | Yes (click → download) |
| `table` | Data | `headers`, `rows`, `total_rows?`, `page_size?` | Pagination |
| `list` | Data | `items`, `ordered?` | No |
| `metric` | Data | `title`, `value`, `icon?`, `progress?` | No |
| `progress` | Data | `value` (0-1), `label?` | No |
| `code` | Data | `code`, `language?`, `line_numbers?` | No |
| `bar_chart` | Chart | `title`, `labels`, `datasets` | No |
| `line_chart` | Chart | `title`, `labels`, `datasets` | No |
| `pie_chart` | Chart | `title`, `labels`, `values` | No |
| `plotly_chart` | Chart | `data`, `layout` (Plotly.js spec) | Yes (interactive) |

---

## Reconnection Protocol

1. Connection drops → state = `reconnecting`
2. Display offline indicator
3. Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (max)
4. On reconnect: send `register_ui` with preserved `session_id`
5. Server restores session state → sends fresh `ui_render`
6. While reconnecting: display cached SDUI tree from `SharedPreferences`

---

## Error Handling

| Scenario | Client Behavior |
|----------|----------------|
| Invalid JSON from server | Log warning, ignore message |
| Unknown message type | Log warning, ignore |
| Unknown component type | Render `PlaceholderWidget` |
| WebSocket close (1000) | Clean disconnect, no reconnect |
| WebSocket close (other) | Start reconnection loop |
| Auth token expired | Refresh token → reconnect with new token |
| Refresh fails | Redirect to login screen |
