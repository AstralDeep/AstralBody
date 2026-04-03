# WebSocket Protocol Contract

**Version**: 1.0.0 | **Source of Truth**: `backend/shared/protocol.py`

## Overview

The Flutter client communicates with the AstralBody orchestrator via a persistent WebSocket connection. This contract defines all message types exchanged between client and server.

## Connection

**Endpoint**: `ws://{host}:{port}/ws`  
**Authentication**: JWT token passed as query parameter: `?token={jwt}`

## Client → Server Messages

### `register_ui`

Sent immediately after WebSocket connection is established. Registers the client and its device capabilities.

```json
{
  "type": "register_ui",
  "capabilities": ["text", "button", "card", "table", "..."],
  "session_id": "optional-session-id",
  "token": "jwt-token",
  "device": {
    "device_type": "mobile",
    "screen_width": 1170,
    "screen_height": 2532,
    "viewport_width": 390,
    "viewport_height": 844,
    "pixel_ratio": 3.0,
    "has_touch": true,
    "has_geolocation": true,
    "has_microphone": true,
    "has_camera": true,
    "has_file_system": true,
    "connection_type": "wifi",
    "user_agent": "AstralBody-Flutter/1.0 iOS"
  }
}
```

**Fields**:
- `capabilities`: List of SDUI component types the client can render
- `session_id`: Optional session ID for reconnection
- `token`: JWT from Keycloak auth
- `device`: Device capabilities dict (consumed by ROTE)

**Device type values**: `"mobile"`, `"tablet"`, `"watch"`, `"tv"`, `"browser"`

### `ui_event`

Sent when the user interacts with a rendered component.

```json
{
  "type": "ui_event",
  "action": "chat_message",
  "payload": {
    "text": "Hello, show me the dashboard",
    "chat_id": "chat-uuid"
  },
  "session_id": "optional-session-id"
}
```

**Common actions**:
- `chat_message` — User sends a chat message. Payload: `{ text, chat_id }`
- `button_click` — User clicks a button. Payload: `{ action, component_id, value }`
- `form_submit` — User submits form data. Payload: `{ fields: { name: value } }`
- `page_change` — Table pagination. Payload: `{ source_tool, source_agent, source_params, page_offset, page_size }`
- `save_component` — User saves a component. Payload: `{ component_id, title }`
- `combine_components` — User combines components. Payload: `{ component_ids }`

### `mcp_request`

Low-level tool call (rarely used by client directly).

```json
{
  "type": "mcp_request",
  "request_id": "req-uuid",
  "method": "tool_name",
  "params": {}
}
```

## Server → Client Messages

### `ui_render`

Full component tree render. Replaces the entire UI.

```json
{
  "type": "ui_render",
  "components": [
    {
      "type": "container",
      "id": "main-container",
      "children": [
        { "type": "text", "content": "Dashboard", "variant": "h1" },
        {
          "type": "grid",
          "columns": 2,
          "children": [
            { "type": "metric", "title": "Revenue", "value": "$1M" },
            { "type": "metric", "title": "Users", "value": "5K" }
          ]
        }
      ]
    }
  ]
}
```

**Client behavior**: Replace the current component tree entirely. Render all components recursively.

### `ui_update`

Partial update. Replaces specific components in the existing tree (matched by `id`).

```json
{
  "type": "ui_update",
  "components": [
    { "type": "text", "id": "status-text", "content": "Updated!", "variant": "body" }
  ]
}
```

**Client behavior**: For each component in the list, find the component with matching `id` in the current tree and replace it.

### `ui_append`

Append data to a specific component.

```json
{
  "type": "ui_append",
  "target_id": "chat-messages",
  "data": {
    "role": "assistant",
    "content": "Here are the results...",
    "components": [/* optional inline SDUI */]
  }
}
```

**Client behavior**: Find the component with `target_id` and append `data` to its content/children.

### `mcp_response`

Response to an `mcp_request`.

```json
{
  "type": "mcp_response",
  "request_id": "req-uuid",
  "result": { "data": "..." },
  "error": null,
  "ui_components": [/* optional SDUI components */]
}
```

### `agent_creation_progress`

Progress update during agent creation workflows.

```json
{
  "type": "agent_creation_progress",
  "draft_id": "draft-uuid",
  "step": "generating_tools",
  "message": "Creating agent tools...",
  "status": "generating",
  "detail": {}
}
```

## Connection Lifecycle

```
Client                                    Server
  |                                          |
  |--- WebSocket connect (?token=jwt) ------>|
  |                                          |
  |--- register_ui (device, capabilities) -->|
  |                                          |
  |<--- ui_render (initial dashboard) -------|
  |                                          |
  |--- ui_event (chat_message) ------------->|
  |                                          |
  |<--- ui_render (agent response + SDUI) ---|
  |                                          |
  |--- ui_event (button_click) ------------->|
  |                                          |
  |<--- ui_update (partial update) ----------|
  |                                          |
  |     [connection drops]                   |
  |                                          |
  |--- WebSocket reconnect (?token=jwt) ---->|
  |--- register_ui (same device + session) ->|
  |                                          |
  |<--- ui_render (restored state) ----------|
```

## Error Handling

### Connection Loss
1. Client detects WebSocket close/error
2. Display offline indicator overlay
3. Retain last rendered UI (do not clear)
4. Attempt reconnect with exponential backoff: 1s, 2s, 4s, 8s, max 30s
5. On reconnect, send `register_ui` with same `session_id`
6. Server responds with current state via `ui_render`

### Unknown Message Type
- Log warning with message type
- Do not crash
- Ignore the message

### Malformed JSON
- Log error
- Do not crash
- Ignore the message

## Device Profile Reporting on Viewport Change

When the device orientation changes or the window is resized:
1. Client sends a new `register_ui` with updated `device` dimensions
2. Server re-runs ROTE adaptation on cached components
3. Server sends `ui_render` with re-adapted components (if profile changed meaningfully)
4. Client does NOT re-fetch — just renders the new tree

This avoids the client needing to re-adapt layouts locally. The backend remains the sole layout authority per constitution principle VIII.
