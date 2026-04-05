# Quickstart: Flutter-Backend SDUI Integration

**Branch**: `003-flutter-backend-connect` | **Date**: 2026-04-05

## Prerequisites

- Docker + Docker Compose installed
- Flutter SDK 3.x installed (`flutter doctor` passes)
- Backend repo: `y:\WORK\MCP\AstralBody\`
- Frontend repo: `y:\WORK\MCP\astralprojection-flutter\`
- Both repos cloned and on correct branches

## 1. Start the Backend (Docker)

```bash
cd y:/WORK/MCP/AstralBody
docker compose up -d
```

Verify it's running:
```bash
curl http://127.0.0.1:8001/api/health
# or check WebSocket:
# wscat -c ws://127.0.0.1:8001/ws
```

**For mobile/tablet testing**, change `docker-compose.yml` port binding:
```yaml
# Before (localhost only):
ports:
  - "127.0.0.1:8001:8001"

# After (all interfaces):
ports:
  - "8001:8001"
```

Then restart: `docker compose down && docker compose up -d`

## 2. Configure the Flutter App

Edit `lib/config.dart` to point to your backend:

**Desktop (same machine):**
```dart
static const String backendHost = '127.0.0.1';
```

**Android Emulator:**
```dart
static const String backendHost = '10.0.2.2';
```

**Physical Device (mobile/tablet on same Wi-Fi):**
```dart
static const String backendHost = '192.168.x.x'; // Your machine's LAN IP
```

Find your LAN IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)

## 3. Run the Flutter App

```bash
cd y:/WORK/MCP/astralprojection-flutter

# Desktop (Windows)
flutter run -d windows

# Desktop (macOS)
flutter run -d macos

# Android (emulator or device)
flutter run -d android

# iOS (simulator or device)
flutter run -d ios

# Chrome (web)
flutter run -d chrome
```

## 4. Verify Connection

1. App launches → should see the dark navy UI shell
2. Bottom status bar should show "Connected" (green indicator)
3. If disconnected: check backend is running, check config.dart host, check network access

## 5. Test End-to-End Chat

1. Type "hello" in the chat input bar at the bottom
2. You should see:
   - Status indicator: "thinking..." then "executing..."
   - SDUI components render in the main content area
3. If no response: check the protocol fixes are applied (see research.md)

## 6. Test Saved Components

1. Send a chat message that produces SDUI components
2. Tap/click on a component → "Add to UI" action should appear
3. Save a component → open the UI drawer (toggle button in navbar)
4. Verify saved components appear as cards in the drawer
5. Test "Condense All" with 3+ saved components

## Key Files to Watch

| Purpose | File |
|---------|------|
| Backend connection config | `lib/config.dart` |
| WebSocket protocol | `lib/state/web_socket_provider.dart` |
| SDUI renderer | `lib/components/dynamic_renderer.dart` |
| Chat input | `lib/components/chat/chat_input_bar.dart` |
| Saved components | `lib/components/workspace/saved_components_drawer.dart` |
| Device detection | `lib/state/device_profile_provider.dart` |
| Docker config | `docker-compose.yml` (backend repo) |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Connection refused" | Backend not running or wrong host/port in config.dart |
| Connected but chat doesn't work | Check chat_message payload fix (must send `"message"` not `"text"`) |
| Mobile can't connect | Docker port binding must be `"8001:8001"` not `"127.0.0.1:8001:8001"` |
| Components don't render | Check browser console/Flutter logs for JSON parse errors |
| "Add to UI" doesn't work | Verify save_component payload has `chat_id`, `component_data`, `component_type`, `title` |
| Combine fails | Verify combine_components sends `source_id`/`target_id` not `component_ids` |
