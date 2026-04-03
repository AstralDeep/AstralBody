# Quickstart: Flutter SDUI Thin Client

**Branch**: `001-flutter-sdui-client` | **Date**: 2026-04-03

## Prerequisites

- Flutter SDK 3.x+ (Dart 3.7+)
- Xcode (for iOS/watchOS builds)
- Android Studio (for Android/TV builds)
- Docker + Docker Compose (for AstralBody backend)
- Keycloak instance (or `MOCK_AUTH=true` for local dev)

## 1. Start the Backend

```bash
cd AstralBody/
cp .env.example .env
# Edit .env: set DB credentials, VITE_USE_MOCK_AUTH=true for dev
docker-compose up -d
```

Backend will be available at:
- WebSocket: `ws://localhost:8001/ws`
- REST API: `http://localhost:8001`

## 2. Set Up the Flutter Client

```bash
cd astralprojection-flutter/
flutter pub get
```

### Configure Backend Connection

Edit `lib/config.dart`:
```dart
class AppConfig {
  static const String backendHost = 'localhost';
  static const int backendPort = 8001;
  // ...
}
```

Or pass via environment:
```bash
flutter run --dart-define=BACKEND_HOST=localhost --dart-define=BACKEND_PORT=8001
```

## 3. Run on Phone/Tablet

### iOS Simulator
```bash
flutter run -d "iPhone 16 Pro"
```

### Android Emulator
```bash
flutter run -d emulator-5554
```

### Physical Device
```bash
flutter run -d <device-id>
```

## 4. Run on TV

### Android TV Emulator
1. In Android Studio: Create AVD → TV → Android TV (1080p)
2. Start the emulator
```bash
flutter run -d <tv-emulator-id>
```

### Key behaviors to verify:
- D-pad/arrow key navigation works
- Focus indicators visible on interactive elements
- Text is large enough for 10-foot viewing
- File upload/download components are hidden

## 5. Run on Apple Watch

The watch app is a native watchOS companion (SwiftUI). It is NOT built via Flutter.

```bash
cd astralprojection-flutter/ios/
open Runner.xcworkspace
# Select the WatchOS target in Xcode
# Build and run on watch simulator
```

### Key behaviors to verify:
- Only text, metric, alert, card, button render
- Charts degrade to metric cards
- Tables degrade to lists
- Compact layout fits 40mm watch face

## 6. Run Tests

### Unit + Widget Tests
```bash
cd astralprojection-flutter/
flutter test
```

### Integration Tests (requires emulator/device)
```bash
# Phone
flutter test integration_test/phone_rendering_test.dart -d "iPhone 16 Pro"

# Tablet
flutter test integration_test/tablet_rendering_test.dart -d "iPad Pro"

# TV
flutter test integration_test/tv_rendering_test.dart -d <tv-emulator-id>

# Watch
# Run from Xcode with watch simulator
```

### Coverage
```bash
flutter test --coverage
genhtml coverage/lcov.info -o coverage/html
open coverage/html/index.html
```

Target: 90%+ line coverage per constitution.

## 7. Run Backend Tests

```bash
cd AstralBody/backend/
pytest
```

## 8. Development Workflow

1. Start backend: `docker-compose up -d`
2. Run Flutter app: `flutter run`
3. Make changes to Flutter code — hot reload (`r`) applies instantly
4. Backend changes require `docker-compose restart astralbody`
5. Run `flutter test` before committing
6. Run `dart analyze` to check for lint errors

## 9. Mock Auth Mode

For local development without Keycloak:
1. Set `VITE_USE_MOCK_AUTH=true` in backend `.env`
2. Flutter app will use username/password login against `/auth/login`
3. Default test user: `public_user`

## 9b. Keycloak Test Auth

For integration/E2E testing against a real Keycloak instance:
1. Set `VITE_USE_MOCK_AUTH=false` in backend `.env`
2. Ensure `KEYCLOAK_TEST_USER` and `KEYCLOAK_TEST_PASSWORD` are set in `.env`
3. The Flutter integration tests read these env vars to authenticate via the Keycloak OIDC flow
4. These credentials are never committed to source — they live only in `.env` (gitignored)

## 10. Architecture Quick Reference

```
┌──────────────────────────────────────────────┐
│                Flutter Client                 │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Auth     │  │ Device   │  │ WebSocket  │ │
│  │ Provider │  │ Profile  │  │ Provider   │ │
│  └────┬─────┘  └────┬─────┘  └──────┬─────┘ │
│       │              │               │        │
│       └──────────────┼───────────────┘        │
│                      │                        │
│              ┌───────┴───────┐                │
│              │ Dynamic       │                │
│              │ Renderer      │                │
│              └───────┬───────┘                │
│                      │                        │
│     ┌───────┬────────┼────────┬──────────┐    │
│     │text   │button  │table   │chart ... │    │
│     │widget │widget  │widget  │widget    │    │
│     └───────┴────────┴────────┴──────────┘    │
└──────────────────────────────────────────────┘
                       │ WebSocket
                       ▼
┌──────────────────────────────────────────────┐
│              AstralBody Backend               │
│  ┌──────────┐  ┌──────┐  ┌───────────────┐  │
│  │ Keycloak │  │ ROTE │  │ Orchestrator  │  │
│  │ Auth     │  │      │  │ + Agents      │  │
│  └──────────┘  └──────┘  └───────────────┘  │
└──────────────────────────────────────────────┘
```
