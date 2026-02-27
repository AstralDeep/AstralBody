# REST API Contract

**Version**: 1.0.0
**Base URL**: `http://localhost:8001` (or configured backend)
**Authentication**: Bearer token (JWT from OIDC)

## Authentication

### `GET /health`
Check backend health.

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-02-27T18:38:02.911Z"
}
```

### `GET /auth/config`
Get OIDC configuration.

**Response**:
```json
{
  "issuer": "https://keycloak.example.com/auth/realms/astralbody",
  "client_id": "astralbody-frontend",
  "scope": "openid profile email",
  "redirect_uri": "astralbody://callback"
}
```

## File Operations

### `POST /upload`
Upload a file for analysis.

**Headers**:
- `Authorization: Bearer {token}`
- `Content-Type: multipart/form-data`

**Form data**:
- `file`: The file to upload
- `session_id`: (optional) Chat session ID

**Response**:
```json
{
  "file_id": "uuid",
  "filename": "data.csv",
  "size": 10240,
  "uploaded_at": "2026-02-27T18:38:02.911Z",
  "analysis_status": "pending"
}
```

### `GET /download/{file_id}`
Download a previously uploaded file.

**Headers**:
- `Authorization: Bearer {token}`

**Response**: File binary with appropriate Content-Type.

## Chat History

### `GET /sessions`
Get user's chat sessions.

**Query parameters**:
- `limit`: Max number of sessions (default: 50)
- `offset`: Pagination offset (default: 0)
- `archived`: Include archived sessions (default: false)

**Response**:
```json
{
  "sessions": [
    {
      "id": "session-uuid",
      "title": "Data analysis session",
      "created_at": "2026-02-27T18:38:02.911Z",
      "updated_at": "2026-02-27T18:38:02.911Z",
      "message_count": 42,
      "is_archived": false
    }
  ],
  "total": 123
}
```

### `GET /sessions/{session_id}/messages`
Get messages for a specific session.

**Query parameters**:
- `limit`: Messages per page (default: 100)
- `before`: Get messages before this timestamp

**Response**:
```json
{
  "session_id": "session-uuid",
  "messages": [
    {
      "id": "message-uuid",
      "role": "user",
      "content": "Hello",
      "timestamp": "2026-02-27T18:38:02.911Z",
      "components": []
    }
  ],
  "has_more": false
}
```

### `DELETE /sessions/{session_id}`
Delete a chat session.

**Response**: 204 No Content

## Saved Components

### `GET /components`
Get user's saved components.

**Response**:
```json
{
  "components": [
    {
      "id": "component-uuid",
      "title": "Sales Dashboard",
      "type": "grid",
      "preview": "base64-image-or-html",
      "saved_at": "2026-02-27T18:38:02.911Z",
      "tags": ["dashboard", "sales"]
    }
  ]
}
```

### `POST /components/combine`
Combine multiple components.

**Request**:
```json
{
  "component_ids": ["id1", "id2"],
  "strategy": "merge"
}
```

**Response**:
```json
{
  "combined_component": {
    "id": "new-component-uuid",
    "title": "Combined Dashboard",
    "type": "grid"
  }
}
```

### `POST /components/condense`
Condense multiple components into fewer.

**Request**:
```json
{
  "component_ids": ["id1", "id2", "id3"],
  "target_count": 2
}
```

## User Management

### `GET /user/profile`
Get current user profile.

**Response**:
```json
{
  "id": "user-uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "roles": ["user"],
  "created_at": "2026-02-27T18:38:02.911Z",
  "last_login": "2026-02-27T18:38:02.911Z"
}
```

### `PUT /user/profile`
Update user profile.

**Request**:
```json
{
  "name": "Updated Name",
  "preferences": {
    "theme": "dark",
    "language": "en"
  }
}
```

## Agent Management

### `GET /agents`
Get available agents.

**Response**:
```json
{
  "agents": [
    {
      "id": "agent-uuid",
      "name": "General Assistant",
      "description": "Handles general queries and tasks",
      "status": "online",
      "capabilities": ["chat", "file_analysis"],
      "average_response_time": 1.2
    }
  ]
}
```

### `POST /agents/{agent_id}/invoke`
Directly invoke an agent (bypassing chat).

**Request**:
```json
{
  "input": "Analyze this CSV file",
  "parameters": {
    "file_id": "file-uuid"
  }
}
```

## Error Responses

All error responses follow this format:
```json
{
  "error": {
    "code": "invalid_token",
    "message": "Authentication token is invalid or expired",
    "details": {},
    "timestamp": "2026-02-27T18:38:02.911Z"
  }
}
```

**Common error codes**:
- `invalid_token`: Authentication failed
- `rate_limited`: Too many requests
- `file_too_large`: File exceeds size limit
- `invalid_file_type`: Unsupported file type
- `not_found`: Resource not found
- `permission_denied`: Insufficient permissions

## Rate Limiting

- 100 requests per minute per user
- 10 file uploads per hour
- WebSocket messages: 50 per second

Headers included in responses:
- `X-RateLimit-Limit`: Total requests allowed
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: UTC epoch seconds until reset

## CORS

- Allowed origins: `http://localhost:*`, `https://*.astralbody.com`
- Allowed methods: GET, POST, PUT, DELETE, OPTIONS
- Allowed headers: Authorization, Content-Type, X-Session-ID

## Compatibility Notes

This API must match exactly what the React frontend uses. Verify by:
1. Comparing with React's API service files
2. Testing endpoints with same requests
3. Ensuring response structures are identical

## Testing

### Contract Tests
1. Health check returns 200
2. Upload endpoint accepts multipart form data
3. Authentication required for protected endpoints
4. Error responses match schema

### Integration Tests
1. Full file upload → analysis → download flow
2. Chat session creation and retrieval
3. Component save and combine operations

---

*This contract defines the REST API between Flutter frontend and Python backend. Any deviation from this contract will break compatibility with the existing system.*