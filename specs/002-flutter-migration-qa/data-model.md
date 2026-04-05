# Data Model: Flutter Migration QA & Feature Parity

**Branch**: `002-flutter-migration-qa` | **Date**: 2026-04-03

## Overview

This feature is primarily a QA and fix effort — it does not introduce new backend data models. The data model below documents the **client-side state entities** that the Flutter app must correctly manage, plus the **existing backend entities** it interacts with. Understanding these is critical for testing parity.

---

## Client-Side Entities (Flutter State)

### AuthState

Managed by `AuthProvider`. Holds the authenticated user session.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `accessToken` | `String?` | Keycloak OIDC / mock `/auth/login` | JWT; stored in `flutter_secure_storage` |
| `refreshToken` | `String?` | Keycloak OIDC / BFF `/auth/token` | Used for silent refresh |
| `tokenExpiry` | `DateTime?` | Decoded from JWT `exp` claim | Triggers refresh before expiry |
| `profile` | `AuthProfile` | Decoded from JWT payload | See AuthProfile below |
| `isAuthenticated` | `bool` | Derived | `accessToken != null && !expired` |
| `isLoading` | `bool` | Internal | True during login/refresh |
| `error` | `String?` | Internal | Last auth error message |

### AuthProfile

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `id` | `String` | JWT `sub` claim | Keycloak user ID |
| `username` | `String` | JWT `preferred_username` | Display name |
| `globalRole` | `String` | JWT `realm_access.roles` | `"admin"` or `"user"` |
| `preferenceId` | `String` | Default `"default"` | User preference bucket |
| `profileTags` | `List<String>` | Optional | Device capability tags |

**Validation Rules**:
- `accessToken` must be a valid JWT with RS256 signature (verified by backend, decoded by client)
- `globalRole` must be one of `["admin", "user"]` — derived from first match in `realm_access.roles`
- Token refresh must occur before `tokenExpiry` — client checks on app resume

---

### SDUITree

Managed by `WebSocketProvider`. The component tree received from the backend.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `components` | `List<Map<String, dynamic>>` | WebSocket `ui_render` | Current SDUI tree |
| `sessionId` | `String?` | WebSocket `session_id` msg | Preserved across reconnects |
| `cachedTree` | `String?` | `SharedPreferences` key `sdui_cached_tree` | JSON-serialized last tree |
| `connectionState` | `enum` | Internal | `disconnected`, `connecting`, `connected`, `reconnecting` |
| `chatMessages` | `List<Map<String, dynamic>>` | WebSocket `ui_append` | Accumulated chat messages |

**State Transitions**:
```
disconnected → connecting → connected
connected → reconnecting → connecting → connected
connected → disconnected (explicit logout)
```

**Validation Rules**:
- Each component must have a `type` field (string)
- Unknown `type` values render `PlaceholderWidget` — never crash
- `cachedTree` loaded on startup; replaced by fresh `ui_render` on connect
- `sessionId` re-sent on reconnect to restore server-side state

---

### DeviceProfile

Managed by `DeviceProfileProvider`. Sent to backend at WebSocket registration.

| Field | Type | Detection | Notes |
|-------|------|-----------|-------|
| `deviceType` | `String` | Viewport width | `mobile` (≤480), `tablet` (481-1024), `tv` (>1024) |
| `screenWidth` | `int` | `MediaQuery.size.width * pixelRatio` | Physical pixels |
| `screenHeight` | `int` | `MediaQuery.size.height * pixelRatio` | Physical pixels |
| `viewportWidth` | `int` | `MediaQuery.size.width` | Logical pixels |
| `viewportHeight` | `int` | `MediaQuery.size.height` | Logical pixels |
| `pixelRatio` | `double` | `MediaQuery.devicePixelRatio` | DPI scaling |
| `hasTouch` | `bool` | `deviceType != "tv"` | Touch input available |
| `hasMicrophone` | `bool` | `deviceType != "tv"` | Voice input available |
| `hasCamera` | `bool` | `deviceType != "tv"` | Camera available |
| `hasGeolocation` | `bool` | `deviceType != "tv"` | GPS available |
| `hasFileSystem` | `bool` | `deviceType != "tv" && != "watch"` | File picker available |
| `inputModality` | `String` | Derived | `touch`, `dpad`, `crown` |

**Validation Rules**:
- `deviceType` determines which capabilities are reported
- Backend ROTE engine uses this to adapt component trees before sending
- TV devices must NOT report touch/microphone/camera/geolocation
- Watch devices must NOT report file system access

---

### SavedComponent

Managed by saved components drawer (to be implemented).

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `id` | `String` | Backend `component_saved` response | Unique component ID |
| `chatId` | `String` | Current chat context | Scoped to chat |
| `type` | `String` | Component `type` field | e.g., `card`, `table`, `metric` |
| `title` | `String?` | Extracted from component props | Display name |
| `data` | `Map<String, dynamic>` | Full component JSON | Serialized for re-rendering |
| `savedAt` | `DateTime` | Client-side timestamp | For ordering |

**State Transitions**:
```
(unsaved) → saved (via save_component WS message)
saved → combined (via combine_components → removed + new component)
saved → condensed (via condense_components → removed + new components)
saved → deleted (via delete_saved_component)
```

---

### AgentPermissions

For the agent permissions modal (to be implemented).

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `agentId` | `String` | Backend `system_config` | Agent identifier |
| `agentName` | `String` | Backend `system_config` | Display name |
| `scopes` | `Map<String, bool>` | Backend | `tools:read`, `tools:write`, `tools:search`, `tools:system` |
| `permissions` | `Map<String, bool>` | Backend | Per-tool overrides |
| `tools` | `List<AgentTool>` | Backend `agent_registered` | Available tools |
| `requiredCredentials` | `List<CredentialSpec>?` | Backend | Credentials the agent needs |

---

## Backend Entities (Reference — no changes)

These entities exist in the backend and are relevant to QA testing. They are documented here for reference; no backend schema changes are planned.

### Chat (PostgreSQL)

| Field | Type | Notes |
|-------|------|-------|
| `id` | `TEXT PK` | UUID |
| `user_id` | `TEXT` | Keycloak sub claim |
| `title` | `TEXT` | Auto-generated or user-set |
| `agent_id` | `TEXT?` | Associated agent |
| `created_at` | `TIMESTAMP` | Creation time |
| `updated_at` | `TIMESTAMP` | Last activity |

### ChatMessage (PostgreSQL)

| Field | Type | Notes |
|-------|------|-------|
| `id` | `TEXT PK` | UUID |
| `chat_id` | `TEXT FK` | Parent chat |
| `role` | `TEXT` | `user` or `assistant` |
| `content` | `TEXT` | Message text |
| `ui_components` | `TEXT?` | JSON SDUI tree |
| `metadata` | `TEXT?` | JSON metadata |
| `created_at` | `TIMESTAMP` | Timestamp |

### SDUI Component (Protocol — not persisted as entity)

| Field | Type | Notes |
|-------|------|-------|
| `type` | `String` | One of 23+ primitive types |
| `id` | `String?` | For targeted updates |
| `content` | `dynamic` | Type-specific content (children, text, rows, datasets, etc.) |
| `style` | `Map?` | Optional styling overrides |
| `action` | `Map?` | Event payload for interactive components |

**23 Registered Types**: container, text, button, input, card, table, list, alert, progress, metric, code, image, grid, tabs, divider, collapsible, bar_chart, line_chart, pie_chart, plotly_chart, color_picker, file_upload, file_download

---

## Entity Relationships

```
AuthState
  └── AuthProfile (1:1, decoded from JWT)

WebSocketProvider
  ├── SDUITree (1:1, current component tree)
  ├── ChatMessages (1:N, accumulated)
  └── SavedComponents (1:N, per chat)

DeviceProfile (1:1 per app instance)
  └── Determines → ROTE adaptation rules (server-side)

AgentPermissions (1:N, one per connected agent)
  ├── Scopes (1:4, the four scope categories)
  ├── Per-tool overrides (1:N)
  └── Required credentials (1:N)

Backend Chat ←→ ChatMessages (1:N)
Backend Chat ←→ SavedComponents (1:N via chat_id)
```
