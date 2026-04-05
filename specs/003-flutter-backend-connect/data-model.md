# Data Model: Flutter-Backend SDUI Integration

**Branch**: `003-flutter-backend-connect` | **Date**: 2026-04-05

## Entities

### 1. SDUI Component (rendered in Flutter)

The fundamental unit of server-driven UI. Backend produces these; Flutter renders them.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | String | Yes | Component type identifier (e.g., `"card"`, `"text"`, `"table"`) |
| `id` | String | No | Unique component ID (used for `ui_append` targeting) |
| `style` | Map | No | CSS-like style overrides (padding, margin, background, etc.) |
| `children` | List<Component> | No | Nested child components (for containers, cards, grids, tabs) |
| *(type-specific)* | varies | varies | Each type has its own fields (see primitives catalog below) |

**Validation**: `type` must be one of the 41 registered primitives. Unknown types render as placeholder.

**State Transitions**: None — components are immutable snapshots from the backend. Updates arrive as full tree replacements (`ui_render`) or targeted appends (`ui_append`).

### 2. Saved Component (persisted in UI drawer)

A user-curated component stored in the backend's file-based persistence.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | String | Yes | Unique saved component ID (backend-generated) |
| `chat_id` | String | Yes | Chat session that produced this component |
| `component_data` | Map | Yes | The full SDUI component tree (serialized) |
| `component_type` | String | Yes | Top-level component type |
| `title` | String | No | User-facing title (extracted or user-provided) |
| `created_at` | int (ms epoch) | Yes | Timestamp of save |

**State Transitions**:
- Created: `save_component` action → backend persists → `component_saved` response
- Listed: `get_saved_components` → `saved_components_list` response
- Deleted: `delete_saved_component` action → backend removes → updated list sent
- Combined: `combine_components` action → LLM merges two → `components_combined` (replaces source+target with result)
- Condensed: `condense_components` action → LLM reduces many → `components_condensed` (replaces all with fewer)

### 3. Chat Session

A conversation thread between user and orchestrator.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chat_id` | String | Yes | Unique chat identifier |
| `session_id` | String | No | WebSocket session persistence token |
| `messages` | List<ChatMessage> | Yes | Ordered message history |
| `created_at` | int (ms epoch) | Yes | Creation timestamp |

**State Transitions**:
- Created: `new_chat` action or first `chat_message` in a session
- Active: Receives messages, produces SDUI renders
- Listed: `history_list` message sent on registration

### 4. Device Profile (ROTE adaptation)

Capabilities of the connecting device, used to adapt SDUI output.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `device_type` | Enum | Yes | `BROWSER`, `TABLET`, `MOBILE`, `WATCH`, `TV`, `VOICE` |
| `viewport_width` | int | Yes | Logical pixel width |
| `viewport_height` | int | Yes | Logical pixel height |
| `pixel_ratio` | double | No | Device pixel ratio |
| `has_touch` | bool | No | Touch input available |
| `has_geolocation` | bool | No | GPS available |
| `has_microphone` | bool | No | Mic available |
| `has_camera` | bool | No | Camera available |
| `has_file_system` | bool | No | File I/O available |
| `connection_type` | String | No | Network type (wifi, cellular) |

**Derived Properties** (computed by ROTE from device_type):
- `max_grid_columns`: 1 (mobile/watch) to 6 (browser)
- `supports_charts`: false for watch/voice
- `supports_tables`: false for watch/voice
- `supports_code`: false for mobile/watch/voice
- `supports_file_io`: false for watch/TV/voice
- `max_text_chars`: 120 (watch), 300 (voice), 0=unlimited (others)

### 5. Connection Config (Flutter runtime)

Runtime configuration for backend connectivity.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `backendHost` | String | Yes | Backend hostname or IP |
| `backendPort` | int | Yes | Backend port (default 8001) |
| `apiBaseUrl` | String | Derived | `http://{host}:{port}/api` |
| `wsBaseUrl` | String | Derived | `ws://{host}:{port}/ws` |

**Platform defaults**:
- Desktop: `127.0.0.1:8001`
- Android emulator: `10.0.2.2:8001`
- Physical device: User-configurable (LAN IP)

## SDUI Primitives Catalog

All 41 component types with their type-specific fields:

| Type | Key Fields | Category |
|------|-----------|----------|
| `container` | `children` | Layout |
| `stack_layout` | `children` | Layout |
| `grid` | `columns`, `gap`, `children` | Layout |
| `tabs` | `tabs[].label`, `tabs[].content` | Layout |
| `card` | `title`, `content`, `variant` | Layout |
| `collapsible` | `title`, `content`, `default_open` | Layout |
| `text` | `content`, `variant` (h1-h3, body, caption) | Content |
| `code` | `code`, `language`, `show_line_numbers` | Content |
| `image` | `url`, `alt`, `width`, `height` | Content |
| `html_view` | *(html content)* | Content |
| `button` | `label`, `action`, `payload`, `variant` | Input |
| `input` | `placeholder`, `name`, `value`, `input_type` | Input |
| `checkbox` | *(toggle state)* | Input |
| `color_picker` | `label`, `color_key`, `value` | Input |
| `file_upload` | `label`, `accept`, `action` | Input |
| `file_download` | `label`, `url`, `filename` | Input |
| `table` | `headers`, `rows`, `total_rows`, `page_size` | Data |
| `list` | `items`, `ordered`, `variant` | Data |
| `metric` | `title`, `value`, `subtitle`, `icon`, `progress` | Data |
| `progress` | `value`, `label`, `show_percentage` | Data |
| `bar_chart` | `title`, `labels`, `datasets` | Chart |
| `line_chart` | `title`, `labels`, `datasets` | Chart |
| `pie_chart` | `title`, `labels`, `data`, `colors` | Chart |
| `plotly_chart` | `title`, `data`, `layout`, `config` | Chart |
| `alert` | `message`, `title`, `variant` (info/success/warning/error) | Feedback |
| `divider` | `variant` (solid) | Feedback |
| `webview` | `url`, `intercept_url`, `intercept_action` | Embed |

## Relationships

```
ChatSession 1──* ChatMessage
ChatSession 1──* SavedComponent (via chat_id)
SavedComponent 1──1 SDUI Component (component_data contains full tree)
DeviceProfile 1──1 WebSocket Connection (registered per connection)
SDUI Component *──* SDUI Component (parent-child via children/content fields)
```
