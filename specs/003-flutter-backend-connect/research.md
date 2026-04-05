# Research: Flutter-Backend SDUI Integration

**Branch**: `003-flutter-backend-connect` | **Date**: 2026-04-05

## 1. Protocol Alignment Between Flutter and Backend

### Decision: Fix three critical payload mismatches in the Flutter client

### Findings

**Mismatch 1 — chat_message payload key**
- Flutter (`chat_input_bar.dart:43`) sends: `payload: {"text": "...", "chat_id": "..."}`
- Backend (`orchestrator.py:505`) reads: `payload.get("message")`
- **Impact**: All chat messages are silently dropped (empty string processed)
- **Fix**: Change Flutter to send `"message"` instead of `"text"`, or add backend fallback to also read `"text"`. Prefer fixing Flutter (single change, matches backend contract).

**Mismatch 2 — combine_components payload structure**
- Flutter (`workspace_layout.dart:73`) sends: `{"component_ids": [...], "target_id": "..."}`
- Backend (`orchestrator.py:679-680`) reads: `payload.get("source_id")`, `payload.get("target_id")`
- **Impact**: Combine always fails — "Both source and target component IDs are required"
- **Fix**: Change Flutter to send `{"source_id": "...", "target_id": "..."}` matching backend contract.

**Mismatch 3 — save_component payload structure**
- Flutter (`workspace_layout.dart:64-68`) passes raw `componentData` dict — caller must ensure correct shape
- Backend (`orchestrator.py:607-645`) expects: `{"chat_id": "...", "component_data": {...}, "component_type": "...", "title": "..."}`
- **Impact**: May work or fail depending on how callers construct the payload
- **Fix**: Verify all save_component call sites pass the expected fields.

### Rationale
Fix Flutter to match backend contracts (not the reverse) because the backend protocol is authoritative per Constitution VIII (backend is sole UI authority). The Flutter client is the thin renderer and must conform.

### Alternatives Considered
- Modifying backend to accept Flutter's format: Rejected — the backend serves multiple clients (React SPA exists), changing its protocol would break compatibility.
- Adding adapter middleware: Rejected — unnecessary complexity for simple field renames.

---

## 2. Network Connectivity: Docker to Flutter Devices

### Decision: Make Docker port binding configurable and Flutter backend host runtime-configurable

### Findings

**Docker port binding** (`docker-compose.yml:27`):
- Currently: `"127.0.0.1:8001:8001"` — only accessible from host machine localhost
- Mobile devices on the same Wi-Fi network cannot reach `127.0.0.1` on the host
- Desktop Flutter app on the same machine CAN connect to `127.0.0.1:8001`

**Uvicorn binding** (`orchestrator.py:3071`):
- Binds to `0.0.0.0:8001` — all interfaces. Docker is the restriction, not the server.

**CORS** (`orchestrator.py:3024`):
- Default: `http://localhost:5173,http://127.0.0.1:5173`
- Configurable via `CORS_ORIGINS` env var
- WebSocket endpoint has NO origin validation — accepts all connections

**Flutter config** (`config.dart`):
- Hardcoded `127.0.0.1:8001` — no runtime override
- This works for desktop but not for mobile/tablet

### Fix Plan

1. **Docker**: Change to `"0.0.0.0:8001:8001"` (or just `"8001:8001"`) to expose on all interfaces
2. **Flutter**: Make `config.dart` support runtime configuration:
   - Use `String.fromEnvironment` for compile-time overrides (desktop builds)
   - Add a settings screen or auto-discovery for mobile (mDNS or manual IP entry)
   - Default to `10.0.2.2:8001` on Android emulator (maps to host localhost)
   - Default to `127.0.0.1:8001` on desktop
3. **CORS**: Add the machine's LAN IP to `CORS_ORIGINS` for mobile testing

### Rationale
The simplest approach that covers all three platforms: desktop uses localhost, Android emulator uses 10.0.2.2, physical mobile devices use host machine's LAN IP. A runtime-configurable host avoids needing different builds per target.

### Alternatives Considered
- Tunneling (ngrok, Tailscale): Rejected — adds external dependency and latency for local dev
- DNS-based discovery (mDNS/Bonjour): Rejected — complex, unreliable across platforms
- Hardcoded LAN IP: Rejected — breaks when IP changes

---

## 3. register_ui Device Capabilities Mapping

### Decision: Verify and align device capability field names

### Findings

**Flutter sends** (`device_profile_provider.dart:75-91`):
```json
{
  "device_type": "mobile|tablet|desktop|tv|watch",
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
}
```

**Backend ROTE expects** (`rote/capabilities.py`):
- Reads `device_type` to determine `DeviceType` enum
- Reads `viewport_width`, `viewport_height` for breakpoint calculations
- Reads `has_touch` and other capability flags
- Maps to internal `DeviceProfile` with `max_grid_columns`, `supports_charts`, etc.

**Status**: The field names align correctly. The ROTE system accepts the device map Flutter sends. However, Flutter sends `device_type` values like `"mobile"`, `"tablet"`, `"desktop"` — the backend ROTE maps these to its enum (`MOBILE`, `TABLET`, `BROWSER` for desktop). Need to verify the `"desktop"` → `BROWSER` mapping exists.

### Fix Plan
- Verify ROTE's device type mapping handles `"desktop"` → `BROWSER` (or add it if missing)
- No other changes needed — the schemas are already aligned

---

## 4. Component Save/Condense Pipeline

### Decision: Wire end-to-end save → list → combine → condense pipeline via WebSocket

### Findings

**Backend supports** (via WebSocket `ui_event` actions):
- `save_component` → responds with `component_saved` message
- `get_saved_components` → responds with `saved_components_list` message
- `delete_saved_component` → responds with updated `saved_components_list`
- `combine_components` → responds with `components_combined` (LLM-powered merge)
- `condense_components` → responds with `components_condensed` (LLM-powered reduce)

**Flutter handles** (`web_socket_provider.dart:172-179`):
- `saved_components_list` → updates `savedComponents` list
- `component_saved` → handled
- `components_combined` / `components_condensed` → updates saved components, removes old, adds new

**Flutter UI** (`saved_components_drawer.dart`):
- Grid display with drag-and-drop combine
- "Condense All" button
- Per-component delete
- Full-screen inspect dialog

**Status**: The pipeline is mostly wired. The main gap is the `combine_components` payload mismatch (covered in finding #1) and verifying the save_component call site passes correct fields.

---

## 5. Streaming and Incremental Updates

### Decision: Verify ui_append handling works for streaming chat responses

### Findings

**Backend sends** (`orchestrator.py`):
- `ui_render` — full component tree replacement
- `ui_update` — replace last component batch (used after ROTE re-adaptation)
- `ui_append` — append data to existing component by target_id (for streaming text)

**Flutter handles** (`web_socket_provider.dart:156-163`):
- `ui_render` → replaces `_components` list entirely
- `ui_update` → replaces `_components` list entirely  
- `ui_append` → finds component by `target_id`, appends `data` to its content

**Status**: The streaming pipeline looks correct. The `ui_append` handler recursively searches the component tree for the target ID and appends data. This should work for streaming text content during chat.

---

## 6. Authentication Flow

### Decision: Use mock auth for development, verify token handling

### Findings

**Backend** (`orchestrator.py:411-475`):
- Reads `msg.token` from `register_ui`
- Validates via Keycloak JWKS (production) or mock validator (dev)
- Mock mode: accepts hardcoded JWT for `dev-user-id`
- If no valid token: sends SDUI login page (OAuth redirect flow)

**Flutter** (`token_storage_provider.dart`):
- Stores tokens in `flutter_secure_storage`
- Loads cached token on startup
- Token sent in `register_ui` message

**Dev flow**: Backend in Docker uses mock auth. Flutter needs to send the mock JWT token. The mock token handling should work if Flutter has a cached token or if the backend's login SDUI flow issues one.

### Fix Plan
- Ensure Flutter can complete the mock auth loop: register → receive login UI → user clicks login → backend issues token via `ui_action` → Flutter stores token → re-register with token
- Or: pre-seed the mock token in Flutter for dev mode

---

## 7. Local Persistence (Offline Support)

### Decision: Use SharedPreferences for component tree cache, flutter_secure_storage for tokens

### Findings

**Current state**:
- `SharedPreferences`: Used for sidebar state persistence (`app_shell_provider.dart:102-114`)
- `flutter_secure_storage`: Used for token storage
- Component tree: NOT persisted locally — lost on app restart

**Spec requirement** (FR-012): Cache SDUI component tree and saved components locally so app displays last-known state on restart.

### Fix Plan
- Serialize `_components` list to SharedPreferences on each `ui_render`/`ui_update`
- Load cached components on startup before WebSocket connects
- Serialize `savedComponents` similarly
- Use JSON encoding (components are already Map<String, dynamic>)

---

## Summary of All Decisions

| # | Decision | Priority |
|---|----------|----------|
| 1 | Fix chat_message payload: `text` → `message` | P0 (blocks all chat) |
| 2 | Fix combine_components payload: `component_ids` → `source_id`/`target_id` | P1 |
| 3 | Make backend host configurable in Flutter | P0 (blocks mobile/tablet) |
| 4 | Change Docker port binding to `0.0.0.0:8001` | P0 (blocks mobile/tablet) |
| 5 | Verify ROTE device type mapping for "desktop" | P1 |
| 6 | Verify save_component call sites pass correct fields | P1 |
| 7 | Add local component tree caching for offline support | P2 |
| 8 | Wire mock auth token for dev mode | P1 |
| 9 | Add CORS origins for LAN access | P1 |
