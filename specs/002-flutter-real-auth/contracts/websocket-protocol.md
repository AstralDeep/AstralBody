# WebSocket Protocol Contract

**Version**: 1.0.0
**Compatibility**: Must match backend orchestrator and React frontend

## Connection Establishment

1. **URL**: `ws://{host}:8001/ws` (or `wss://` for production)
2. **Headers**: None (authentication via message payload)
3. **Protocol**: RFC 6455 (standard WebSocket)
4. **Ping/Pong**: 30-second interval, automatic reconnection on failure

## Message Format

All messages are JSON objects with the following structure:

```json
{
  "type": "message_type",
  "data": { ... },
  "timestamp": "2026-02-27T18:38:02.911Z",
  "message_id": "uuid-v4"
}
```

## Message Types

### Client → Server (Flutter → Backend)

#### `register_ui`
Register a UI client with the orchestrator.

```json
{
  "type": "register_ui",
  "data": {
    "user_id": "user-uuid",
    "token": "jwt-access-token",
    "client_type": "flutter",
    "client_version": "1.0.0"
  }
}
```

**Response**: `agent_registered`

#### `ui_event`
Send user interaction or chat message.

```json
{
  "type": "ui_event",
  "data": {
    "session_id": "chat-session-uuid",
    "event_type": "chat_message",
    "payload": {
      "content": "Hello, world!",
      "attachments": [
        {
          "type": "file",
          "id": "file-uuid",
          "name": "data.csv"
        }
      ]
    }
  }
}
```

**Event types**:
- `chat_message`: Text message from user
- `file_upload`: File upload completion
- `component_save`: Save UI component request
- `component_combine`: Combine components request
- `component_condense`: Condense components request
- `agent_selection`: Change active agent

#### `ping`
Keep-alive ping.

```json
{
  "type": "ping",
  "data": {}
}
```

**Response**: `pong` with same timestamp

### Server → Client (Backend → Flutter)

#### `agent_registered`
Confirmation of successful registration.

```json
{
  "type": "agent_registered",
  "data": {
    "agent_id": "agent-uuid",
    "agent_name": "General Assistant",
    "capabilities": ["chat", "file_analysis", "code_generation"]
  }
}
```

#### `chat_response`
Agent response to user message.

```json
{
  "type": "chat_response",
  "data": {
    "session_id": "chat-session-uuid",
    "message_id": "response-uuid",
    "content": "I'll help you analyze that data.",
    "components": [
      {
        "type": "text",
        "id": "component-1",
        "properties": {
          "text": "Analysis complete."
        },
        "style": {
          "color": "#3b82f6",
          "fontSize": 14
        }
      }
    ],
    "status": "completed",
    "thinking_log": ["Step 1: Load data", "Step 2: Analyze"]
  }
}
```

#### `tool_execution`
Tool execution status update.

```json
{
  "type": "tool_execution",
  "data": {
    "tool_name": "python_executor",
    "status": "executing",
    "progress": 0.5,
    "output": "Processing row 500 of 1000..."
  }
}
```

**Status values**: `pending`, `executing`, `completed`, `failed`

#### `error`
Error response.

```json
{
  "type": "error",
  "data": {
    "code": "auth_failed",
    "message": "Authentication token expired",
    "recoverable": true
  }
}
```

#### `pong`
Response to ping.

```json
{
  "type": "pong",
  "data": {
    "timestamp": "2026-02-27T18:38:02.911Z"
  }
}
```

## State Management

### Connection States
1. **connecting**: Establishing WebSocket connection
2. **connected**: Registered with orchestrator
3. **disconnected**: Connection lost, attempting reconnect
4. **error**: Unrecoverable error, user action required

### Reconnection Logic
1. Initial disconnect: Wait 1 second, reconnect
2. Subsequent failures: Exponential backoff (2s, 4s, 8s, 16s, 30s max)
3. After 5 failures: Show error to user, manual retry button

## Authentication

1. Client must have valid JWT access token
2. Token included in `register_ui` message
3. Token expiration: Backend sends `error` with `code: "auth_failed"`
4. Client must refresh token via OIDC and re-register

## Message Ordering

1. Messages are processed in order of receipt
2. Client should maintain local queue for offline messages
3. Server acknowledges receipt with `message_id` in responses

## Error Handling

### Recoverable Errors
- Network timeout
- Token expired
- Rate limit exceeded

### Non-recoverable Errors
- Invalid message format
- Unauthorized access
- Server internal error

## Compatibility with React Frontend

This protocol must be identical to what the React frontend uses. Verify by:
1. Inspecting React's `useWebSocket` hook implementation
2. Comparing message types and data structures
3. Testing with same backend instance

## Testing

### Contract Tests
1. Send `register_ui` with valid token → receive `agent_registered`
2. Send `ui_event` with chat message → receive `chat_response`
3. Verify error responses match schema

### Integration Tests
1. Full chat flow with file upload
2. Reconnection during active session
3. Token refresh flow

---

*This contract defines the WebSocket communication between Flutter frontend and Python backend. Any deviation from this contract will break compatibility with the existing system.*