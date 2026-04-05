# WebSocket Protocol Contract: Flutter ↔ AstralBody Backend

**Version**: 1.0 | **Date**: 2026-04-05 | **Transport**: WebSocket over TCP

## Connection

- **Endpoint**: `ws://{host}:{port}/ws`
- **Stream endpoint**: `ws://{host}:{port}/ws/stream/mcp:{projectId}` (project-scoped)
- **Default port**: 8001
- **Encoding**: JSON text frames (no binary)

## Client → Server Messages

### register_ui (Connection Registration)

Sent immediately after WebSocket opens. Must be first message. Backend blocks all other message processing until registration completes.

```json
{
  "type": "register_ui",
  "token": "<jwt-string | null>",
  "capabilities": ["container", "text", "button", "card", "..."],
  "device": {
    "device_type": "mobile | tablet | desktop | tv | watch",
    "screen_width": 1080,
    "screen_height": 1920,
    "viewport_width": 360,
    "viewport_height": 640,
    "pixel_ratio": 3.0,
    "has_touch": true,
    "has_geolocation": true,
    "has_microphone": true,
    "has_camera": true,
    "has_file_system": true,
    "connection_type": "wifi",
    "user_agent": "AstralBody-Flutter/1.0"
  },
  "session_id": "<string | null>"
}
```

### ui_event (All User Actions)

Wrapper for all user-initiated actions. The `action` field determines the operation.

```json
{
  "type": "ui_event",
  "action": "<action-name>",
  "payload": { },
  "session_id": "<string | null>"
}
```

#### Action: chat_message

```json
{
  "type": "ui_event",
  "action": "chat_message",
  "payload": {
    "message": "<user text>",
    "chat_id": "<chat-id | null>"
  }
}
```

**NOTE**: The payload field is `"message"`, NOT `"text"`. This is a known mismatch in the current Flutter code that must be fixed.

#### Action: save_component

```json
{
  "type": "ui_event",
  "action": "save_component",
  "payload": {
    "chat_id": "<chat-id>",
    "component_data": { "<full SDUI component tree>" },
    "component_type": "<top-level type>",
    "title": "<display title>"
  }
}
```

#### Action: get_saved_components

```json
{
  "type": "ui_event",
  "action": "get_saved_components",
  "payload": {}
}
```

#### Action: delete_saved_component

```json
{
  "type": "ui_event",
  "action": "delete_saved_component",
  "payload": {
    "component_id": "<saved-component-id>"
  }
}
```

#### Action: combine_components

Merges exactly two saved components into one (LLM-powered).

```json
{
  "type": "ui_event",
  "action": "combine_components",
  "payload": {
    "source_id": "<saved-component-id>",
    "target_id": "<saved-component-id>"
  }
}
```

**NOTE**: The payload uses `"source_id"` and `"target_id"`, NOT `"component_ids"`. This is a known mismatch in the current Flutter code that must be fixed.

#### Action: condense_components

Reduces multiple saved components into fewer combined ones (LLM-powered).

```json
{
  "type": "ui_event",
  "action": "condense_components",
  "payload": {
    "component_ids": ["<id1>", "<id2>", "<id3>", "..."]
  }
}
```

#### Action: new_chat

```json
{
  "type": "ui_event",
  "action": "new_chat",
  "payload": {}
}
```

#### Action: update_device

Sent when device capabilities change (e.g., screen rotation).

```json
{
  "type": "ui_event",
  "action": "update_device",
  "payload": {
    "device_type": "tablet",
    "viewport_width": 1024,
    "viewport_height": 768,
    "...": "..."
  }
}
```

#### Action: table_paginate

```json
{
  "type": "ui_event",
  "action": "table_paginate",
  "payload": {
    "component_id": "<table-component-id>",
    "page_offset": 20,
    "page_size": 10
  }
}
```

#### Generic Button/Input Actions

Buttons and inputs dispatch their `action` field value as the ui_event action:

```json
{
  "type": "ui_event",
  "action": "<button.action value>",
  "payload": { "<button.payload or form values>" }
}
```

## Server → Client Messages

### ui_render (Full Component Tree)

Replaces the entire SDUI component tree. Components are ROTE-adapted for the device.

```json
{
  "type": "ui_render",
  "components": [
    {
      "type": "card",
      "id": "card-1",
      "title": "Hello",
      "content": [
        { "type": "text", "content": "World", "variant": "body" }
      ]
    }
  ]
}
```

### ui_update (Replace Last Components)

Same structure as ui_render. Used when device profile changes trigger re-adaptation.

```json
{
  "type": "ui_update",
  "components": [ ]
}
```

### ui_append (Streaming Content)

Appends data to an existing component by ID (used for streaming chat text).

```json
{
  "type": "ui_append",
  "target_id": "<component-id>",
  "data": "<text to append>"
}
```

### chat_status (Processing Status)

```json
{
  "type": "chat_status",
  "status": "thinking | executing | fixing | done",
  "message": "<human-readable status>"
}
```

### session_id (Session Token)

Sent after successful registration. Client should store and send in subsequent messages.

```json
{
  "type": "session_id",
  "session_id": "<uuid>"
}
```

### system_config (Agent Configuration)

Sent after registration. Contains available agents and their tools.

```json
{
  "type": "system_config",
  "config": {
    "agents": [
      {
        "id": "<agent-id>",
        "name": "<name>",
        "description": "<desc>",
        "tools": ["tool1", "tool2"],
        "scopes": { "tools:read": true },
        "permissions": { "tool1": true },
        "status": "connected"
      }
    ],
    "total_tools": 42
  }
}
```

### history_list (Chat History)

```json
{
  "type": "history_list",
  "history": [
    {
      "chat_id": "<id>",
      "title": "<first message preview>",
      "created_at": 1234567890000,
      "message_count": 5
    }
  ]
}
```

### rote_config (Device Profile Confirmation)

Sent after registration. Confirms the device profile the backend assigned.

```json
{
  "type": "rote_config",
  "device_profile": {
    "device_type": "mobile",
    "max_grid_columns": 1,
    "supports_charts": true,
    "supports_tables": true,
    "supports_code": false,
    "supports_file_io": true,
    "supports_tabs": true,
    "max_text_chars": 0,
    "max_table_rows": 20,
    "max_table_cols": 4
  },
  "speech_server_available": false
}
```

### saved_components_list

```json
{
  "type": "saved_components_list",
  "components": [
    {
      "id": "<saved-id>",
      "chat_id": "<chat-id>",
      "component_data": { },
      "component_type": "card",
      "title": "My Component",
      "created_at": 1234567890000
    }
  ]
}
```

### component_saved

```json
{
  "type": "component_saved",
  "component": {
    "id": "<saved-id>",
    "chat_id": "<chat-id>",
    "component_data": { },
    "component_type": "card",
    "title": "My Component",
    "created_at": 1234567890000
  }
}
```

### components_combined / components_condensed

```json
{
  "type": "components_combined",
  "removed_ids": ["<id1>", "<id2>"],
  "new_components": [
    {
      "id": "<new-saved-id>",
      "chat_id": "<chat-id>",
      "component_data": { },
      "component_type": "grid",
      "title": "Combined Component",
      "created_at": 1234567890000
    }
  ]
}
```

### combine_status

```json
{
  "type": "combine_status",
  "status": "combining | condensing",
  "message": "<human-readable>"
}
```

### combine_error

```json
{
  "type": "combine_error",
  "error": "<error message>"
}
```

### ui_action (Backend Commands)

Backend instructs the client to perform an action.

```json
{
  "type": "ui_action",
  "action": "open_url | store_token | clear_token",
  "payload": {
    "url": "https://...",
    "token": "<jwt>"
  }
}
```

### theme (Theme Configuration)

```json
{
  "type": "theme",
  "config": {
    "colors": {
      "primary": "#6366F1",
      "secondary": "#8B5CF6",
      "background": "#0F1221"
    },
    "typography": { },
    "spacing": { }
  }
}
```

### agent_registered

```json
{
  "type": "agent_registered",
  "agent_id": "<id>",
  "name": "<name>",
  "description": "<desc>",
  "tools": ["tool1"],
  "permissions": { "tool1": true },
  "scopes": { "tools:read": true }
}
```

## Connection Lifecycle

```
Client                              Server
  |                                    |
  |--- WebSocket Open --------------->|
  |--- register_ui (token, device) -->|
  |                                    |-- validate token
  |                                    |-- register ROTE device
  |<-- session_id --------------------|
  |<-- rote_config -------------------|
  |<-- system_config -----------------|
  |<-- history_list ------------------|
  |<-- ui_render (dashboard) ---------|
  |                                    |
  |--- ui_event (chat_message) ------>|
  |<-- chat_status (thinking) --------|
  |<-- chat_status (executing) -------|
  |<-- ui_render (result) ------------|
  |<-- ui_append (streaming) ---------|
  |<-- chat_status (done) ------------|
  |                                    |
  |--- ui_event (save_component) ---->|
  |<-- component_saved ---------------|
  |                                    |
  |--- WebSocket Close --------------->|
```

## Error Handling

- Unknown message types are silently ignored by the backend
- Invalid JSON produces a WebSocket close
- Token validation failure triggers SDUI login page response (not a close)
- Component operations that fail send `combine_error` messages
- WebSocket disconnection should trigger client auto-reconnect with exponential backoff (1s → 30s cap)
