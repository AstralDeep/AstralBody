# Phase 1 Data Model: Native Android Client

The client is a **renderer**, not a data owner: it decodes the orchestrator's wire into in-memory models and renders them. The only persisted datum is the encrypted OIDC refresh token. All models below live in `:core` (pure Kotlin, JVM-tested) except where noted.

## Wire models (decoded from the existing protocol)

### Component (the SDUI unit)
```
Component(
  type: String,                 // primitive type, e.g. "table", "card", "alert"
  id: String?,                  // component_id (or id); identity for in-place upsert
  attributes: JsonObject,       // dynamic per-primitive fields (title, rows, variant, …)
  children: List<Component>     // from `content`/`children`
)
```
- Decoding is tolerant (`ignoreUnknownKeys`, missing fields default). Identity = `component_id` ?: `id`.
- Rendering = registry lookup by `type`; unknown → placeholder.

### Canvas operation (in-place update)
```
CanvasOp(op: "upsert" | "remove", componentId: String, component: Component?)
```
- Produced from `ui_upsert.ops` and from the streaming consumer; applied to the keyed canvas state.

### Inbound message (sealed union on `type`)
`ui_render` · `ui_upsert` · `ui_stream_data` · `stream_subscribed` · `stream_error` · `stream_unsubscribed` · `stream_list` · `chat_created` · `chat_loaded` · `agent_list` · `history_list` · `chat_status` · `chrome_render` · `auth_required`. Field shapes per [contracts/ws-protocol.md](contracts/ws-protocol.md).

### Outbound message
`register_ui` · `ui_event` (incl. `chat_message`, `stream_subscribe`/`stream_unsubscribe`, `discover_agents`, `set_agent_permissions`, `enable_recommended_agents`, `get_history`, `load_chat`, `new_chat`). Per [contracts/ws-protocol.md](contracts/ws-protocol.md).

### DeviceCapabilities (reported in `register_ui.device`)
```
device_type = "android"
screen_width / screen_height / viewport_width / viewport_height   // px
pixel_ratio, has_touch = true
supported_types: List<String>   // the primitive types this client renders natively
```
Maps to the server `DeviceCapabilities`/`DeviceProfile` (`backend/rote/capabilities.py`); `supported_types` drives ROTE substitution.

## Streaming state (`:core/streaming`)
```
seqState: MutableMap<String, Int>   // stream-key -> last seq (monotonic dedupe)
```
- `streamFrameToOps(frame, activeChat, seqState) -> List<CanvasOp>` — session filter + seq dedupe + terminal forget + error→alert + components (ignore `html`). Reset on chat switch. (Direct port of the Windows logic.)

## Domain entities (rendered, not owned)

### Conversation
- `id`, ordered `messages` (role/content), current canvas (`List<Component>` keyed by id). Reopened via `load_chat` → `chat_loaded`. Listed via `history_list`.

### Agent / Tool Permission
- `id`, `name`, `description`, `isPublic`, `scopes: Map<String, Boolean>` (e.g. `tools:read/write/execute`). From `agent_list`; mutated via `set_agent_permissions` / `enable_recommended_agents`.

### Audit Entry (REST DTO — see [contracts/rest-endpoints.md](contracts/rest-endpoints.md))
- `event_id`, `recorded_at`, `event_class`, `action_type`, `outcome`, `description`, plus detail fields (`correlation_id`, `inputs_meta`, `outputs_meta`, `started_at`, `completed_at`, …). Paged via `next_cursor`; filtered by `event_class`/`outcome`/`q`.

## Persisted state (`:app`, encrypted)
- **Refresh token** only (AndroidX Security/DataStore). Access token is in-memory. No conversation/audit data is persisted (offline is out of scope v1).

## Validation rules
- Unknown `type` → placeholder (never throw). Malformed component → render error chip, never crash the canvas (mirrors the Windows renderer's per-component try/catch).
- Stream frames: drop when `session_id` ≠ active chat, or `seq` ≤ last seen.
- Audit view is server-scoped to the user; the client sends no user id and rejects any attempt to (none in the UI).
