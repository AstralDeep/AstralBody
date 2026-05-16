# Spec 021: Async Queries (US-20)

**Status:** In Progress
**Branch:** `020-async-queries`
**User Story:** As a user, I want to submit queries and have them run asynchronously, so I can navigate away from the session and get a notification when it is finished.

## Current State

Query processing is fully synchronous via WebSocket:
1. Frontend sends `chat_message` over WS
2. Backend `handle_chat_message()` processes inline — LLM calls, tool execution, response streaming
3. Results stream back to the same WS connection in real-time
4. If the user closes the browser tab or navigates away, the WS drops and the query is orphaned

The orchestrator already has per-WebSocket serialized dispatch (`_serialized_chat`) and cancellation support (`cancel_task`), but no background task infrastructure.

## Problem

1. **Blocking UX:** User must watch the query process — can't start another query or navigate away
2. **No persistence:** If the WS drops mid-query, results are lost
3. **No notifications:** No way to know when a long-running query completes
4. **Single-threaded:** Only one query at a time per WebSocket session

## Proposed Changes

### 1. Background Task Queue
- New `_background_tasks` dict: `{task_id: asyncio.Task}`
- `chat_message` handler accepts optional `async_mode: true` in payload
- When async: creates background asyncio task, returns `{"type": "task_started", "task_id": "..."}`
- Background task runs existing `handle_chat_message` logic with a **virtual WebSocket** that captures all outputs

### 2. Virtual WebSocket (Output Capture)
- Create a `VirtualWebSocket` class that implements `.send_text()` / `.send_json()`
- Captures all `send_ui_render`, `chat_status`, `component_stream` messages into a results buffer
- On completion, persists results to chat history and sends `task_completed` notification

### 3. Task Status Endpoint
- `GET /api/tasks/{task_id}` — returns `{status, progress, chat_id, started_at}`
- `GET /api/tasks` — lists user's active and recent tasks
- Task statuses: `queued`, `running`, `completed`, `failed`, `cancelled`

### 4. WebSocket Notification Channel
- Subscribe to task updates: `{"action": "watch_task", "payload": {"task_id": "..."}}`
- Backend sends `task_completed` / `task_failed` messages to any watching client
- Frontend can re-subscribe on reconnect

### 5. Frontend Changes
- Optional "Run in background" toggle on chat input
- Task progress indicator showing active background tasks
- Notification when background task completes
- Results load automatically when user opens the chat

## Files to Touch

1. **`backend/orchestrator/orchestrator.py`** — Background task dispatch, VirtualWebSocket, task status management
2. **`backend/orchestrator/api.py`** — New task status endpoints
3. **`backend/orchestrator/schemas.py`** — Task status response models
4. **`frontend/src/hooks/useWebSocket.ts`** — Handle task_started / task_completed messages, watch_task action
5. **`frontend/src/components/ChatInterface.tsx`** — "Run in background" toggle, task progress UI

## Constitution Compliance

| Principle | Assessment |
|-----------|-----------|
| I — No New Dependencies | ✅ Pure asyncio, no new packages |
| II — HIPAA | ✅ Task data stored in same audit-compliant DB |
| III — Audit Trail | ✅ All background task execution logged via existing audit recorder |
| IV — Agent Autonomy | ✅ Agents unchanged; orchestration layer only |
| V — No Third-Party Libs | ✅ |
| VI — Accessibility | ✅ Task status UI uses ARIA live regions |
| VII — Extensibility | ✅ Task queue pattern is reusable for any background work |
| VIII — Performance | ✅ Background tasks don't block the WS event loop |
| IX — Database Schema | ✅ New `background_tasks` table for persistence |
| X — Testing | ✅ Test async submission, completion, failure, cancellation |

## Success Criteria

1. User can submit a query and receive an immediate task ID
2. Query runs in background while user navigates away
3. Results appear when user returns to the chat
4. Task status endpoint returns current progress
5. WebSocket `task_completed` notification fires on completion
6. Cancellation works for background tasks
7. All existing synchronous queries still work (backward compatible)
8. Tests cover async submission, completion, failure, and cancellation
