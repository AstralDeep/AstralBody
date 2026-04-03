# Data Model: Flutter SDUI Thin Client

**Branch**: `001-flutter-sdui-client` | **Date**: 2026-04-03

## Overview

The Flutter client is a stateless renderer — it does not own any persistent data models. All entities below describe the **client-side representations** of data produced by the backend. The backend `primitives.py` and `protocol.py` remain the source of truth.

---

## Entity: DeviceProfile (Client-Side)

Represents the client device's capabilities, reported to the backend on WebSocket registration.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| device_type | String | `"mobile"`, `"tablet"`, `"watch"`, `"tv"` | Must be valid DeviceType enum value |
| screen_width | int | Physical screen width in pixels | > 0 |
| screen_height | int | Physical screen height in pixels | > 0 |
| viewport_width | int | Usable viewport width (may differ from screen) | > 0 |
| viewport_height | int | Usable viewport height | > 0 |
| pixel_ratio | double | Device pixel ratio | > 0 |
| has_touch | bool | Supports touch input | — |
| has_geolocation | bool | GPS available | — |
| has_microphone | bool | Mic available | — |
| has_camera | bool | Camera available | — |
| has_file_system | bool | Can read/write local files | — |
| connection_type | String | `"wifi"`, `"4g"`, `"3g"`, etc. | — |
| input_modality | String | `"touch"`, `"dpad"`, `"crown"` | — |

**Source**: `backend/rote/capabilities.py:DeviceCapabilities`

**Detection logic** (Flutter client):
- `device_type`: Detected via `defaultTargetPlatform` + `MediaQuery.of(context).size`
  - watchOS → `"watch"`
  - Android TV / tvOS → `"tv"`
  - Width ≤ 480px → `"mobile"`
  - Width ≤ 1024px → `"tablet"`
  - Else → `"mobile"` (phones report as mobile)
- `has_touch`: True for phones/tablets, false for TV/watch
- `input_modality`: `"touch"` for mobile/tablet, `"dpad"` for TV, `"crown"` for watch

---

## Entity: SDUIComponentTree (Client-Side)

Received from backend via `ui_render` messages. The client renders this tree recursively.

| Field | Type | Description |
|-------|------|-------------|
| components | List<Map> | Top-level list of component dicts |

Each component dict follows the structure from `backend/shared/primitives.py`:

| Field | Type | Description | Present On |
|-------|------|-------------|------------|
| type | String | Component type identifier (snake_case) | All |
| id | String? | Unique component identifier | All |
| style | Map? | CSS-like style overrides | All |
| children | List<Map>? | Child components | container, grid |
| content | dynamic | Component-specific content | text, card, collapsible, tabs |

**State transitions**: The client does not manage component state transitions. It receives complete or partial trees and renders them. The backend manages all state.

---

## Entity: ActionBinding (Client-Side)

Describes a user interaction that the client sends to the backend.

| Field | Type | Description |
|-------|------|-------------|
| action | String | Action identifier (e.g., `"chat_message"`, `"button_click"`) |
| payload | Map | Action-specific data |
| payload.component_id | String? | ID of the component that triggered the action |
| payload.value | dynamic | User-provided value (text input, selection, etc.) |

**Sent as**: `ui_event` message via WebSocket.

---

## Entity: Session (Client-Side)

Represents the authenticated connection between Flutter client and backend.

| Field | Type | Description | Persistence |
|-------|------|-------------|-------------|
| token | String | JWT from Keycloak (via BFF proxy) | Secure storage |
| session_id | String? | Backend-assigned session identifier | Memory |
| profile | AuthProfile | User identity (id, username, role) | SharedPreferences |
| device_profile | DeviceProfile | Device capabilities | Computed at runtime |
| websocket_url | String | Backend WebSocket endpoint | Config |
| connected | bool | WebSocket connection status | Memory |

**Lifecycle**:
1. `DISCONNECTED` → User opens app
2. `AUTHENTICATING` → Keycloak OIDC flow in progress
3. `AUTHENTICATED` → JWT obtained, stored
4. `CONNECTING` → WebSocket connecting, `register_ui` sent
5. `CONNECTED` → Backend acknowledged, initial `ui_render` received
6. `RECONNECTING` → Connection lost, auto-reconnect in progress
7. `DISCONNECTED` → User logs out or app closed

---

## Entity: Primitive Widget Contract

Each Flutter widget that renders a backend primitive MUST:

1. Accept a `Map<String, dynamic>` representing the component dict
2. Handle missing/null fields gracefully (use defaults)
3. Recursively render `children` or `content` via `DynamicRenderer`
4. Forward user interactions as `ui_event` messages
5. Display a placeholder for unknown child component types

**No entity creates, updates, or deletes data in the backend.** All mutations are initiated by the backend via updated component trees.

---

## Relationships

```
Session 1──1 DeviceProfile       (one device profile per session)
Session 1──* SDUIComponentTree   (receives many renders over time)
SDUIComponentTree 1──* Component (tree of nested components)
Component 0──* ActionBinding     (interactive components have actions)
```

---

## Backend Entities (Unchanged — Reference Only)

These entities exist in the backend and are NOT modified by this feature:

| Entity | Location | Notes |
|--------|----------|-------|
| Component (and subclasses) | `backend/shared/primitives.py` | Source of truth for SDUI types |
| DeviceCapabilities | `backend/rote/capabilities.py` | Backend's raw device model |
| DeviceProfile | `backend/rote/capabilities.py` | Backend's derived rendering constraints |
| Message types | `backend/shared/protocol.py` | WebSocket protocol definitions |
| chats, messages | `backend/shared/database.py` | Chat persistence |
| saved_components | `backend/shared/database.py` | Component save/combine |
