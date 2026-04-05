# Quickstart: Flutter Migration QA & Feature Parity

**Branch**: `002-flutter-migration-qa` | **Date**: 2026-04-03

## Prerequisites

- **Flutter SDK** 3.x+ with Dart 3.7+
- **Python 3.11+** (for backend)
- **Docker & Docker Compose** (for PostgreSQL)
- **Xcode** (for iOS/watchOS/tvOS simulators)
- **Android Studio** (for Android/Android TV emulators)
- Access to `https://iam.ai.uky.edu` (Keycloak IAM)

---

## 1. Start the Backend

```bash
# From AstralBody repo root
cd c:/Users/sear234/Desktop/Containers/MCP/AstralBody

# Start PostgreSQL
docker compose up -d postgres

# Verify .env exists with credentials
cat .env | grep KEYCLOAK_TEST

# Start the orchestrator + agents
cd backend
python start.py
```

Backend will be running at `http://localhost:8001`. Verify: `curl http://localhost:8001/docs`

---

## 2. Run the Flutter Client

```bash
# From Flutter repo
cd c:/Users/sear234/Desktop/Containers/MCP/astralprojection-flutter

# Get dependencies
flutter pub get

# Run with mock auth (development)
flutter run --dart-define=BACKEND_HOST=localhost \
            --dart-define=BACKEND_PORT=8001 \
            --dart-define=MOCK_AUTH=true

# Run with real Keycloak auth
flutter run --dart-define=BACKEND_HOST=localhost \
            --dart-define=BACKEND_PORT=8001 \
            --dart-define=MOCK_AUTH=false
```

---

## 3. Test on Specific Devices

### iOS Phone (iPhone Simulator)
```bash
flutter run -d "iPhone 15"
```

### Android Phone
```bash
flutter run -d emulator-5554
```

### iPad (Tablet)
```bash
flutter run -d "iPad Pro (12.9-inch)"
```

### Apple TV
```bash
# Requires tvOS simulator in Xcode
flutter run -d "Apple TV"
```

### Android TV
```bash
# Create Android TV emulator in Android Studio (API 34, TV profile)
flutter run -d "Android_TV_1080p"
```

### Apple Watch
```bash
# Requires watchOS simulator in Xcode
# Note: Flutter does not natively target watchOS —
# watch testing uses phone app with simulated watch viewport
flutter run -d "iPhone 15" --dart-define=FORCE_DEVICE_TYPE=watch
```

---

## 4. Run Tests

### Flutter Unit & Widget Tests
```bash
cd c:/Users/sear234/Desktop/Containers/MCP/astralprojection-flutter

# All tests
flutter test

# Specific test categories
flutter test test/unit/
flutter test test/widget/
flutter test test/integration/

# With coverage
flutter test --coverage
```

### Flutter Integration Tests (requires running backend)
```bash
flutter test integration_test/ \
  --dart-define=BACKEND_HOST=localhost \
  --dart-define=BACKEND_PORT=8001 \
  --dart-define=MOCK_AUTH=true
```

### Backend Tests
```bash
cd c:/Users/sear234/Desktop/Containers/MCP/AstralBody/backend
pytest tests/ -v
```

### Dart Analysis
```bash
cd c:/Users/sear234/Desktop/Containers/MCP/astralprojection-flutter
dart analyze
```

---

## 5. Test Authentication with .env Credentials

### Mock Auth Test
```bash
# Login via mock endpoint
curl -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "test_user", "password": "hJ.3w}Hs)agaKmvtk6qps4)z!J~Ae!%)b^7HEBHpDhi-LM.4V@wWoqF:mYp0ZjaiK=d.VR2fJV0+M*pwK}dum890UgdMx14%s6+c"}'
```

### Keycloak OIDC Test
1. Run app with `MOCK_AUTH=false`
2. Tap "Sign in with SSO"
3. Keycloak login page opens in system browser
4. Enter `KEYCLOAK_TEST_USER` / `KEYCLOAK_TEST_PASSWORD`
5. Redirect back to app → dashboard loads

---

## 6. React Reference Comparison

The archived React frontend is at `frontend-archive-react/`. To run it for side-by-side comparison:

```bash
cd c:/Users/sear234/Desktop/Containers/MCP/AstralBody/frontend-archive-react
npm install
npm run dev
```

Opens at `http://localhost:5173`. Compare:
- Login screen layout and styling
- Dashboard sidebar structure
- Chat SDUI component rendering
- Saved component drawer
- Agent permissions modal
- Glass-morphism visual effects

---

## 7. Key Files to Modify

| Area | File | What to Fix |
|------|------|-------------|
| Login UI | `lib/components/auth/login_page.dart` | Show both auth forms |
| OIDC Auth | `lib/state/auth_provider.dart` | Implement flutter_appauth flow |
| Voice Input | `lib/services/voice_input_service.dart` | New — STT streaming |
| Voice Output | `lib/services/voice_output_service.dart` | New — TTS playback |
| Saved Components | `lib/components/workspace/saved_components_drawer.dart` | New — combine/condense DnD |
| Agent Permissions | `lib/components/agents/agent_permissions_sheet.dart` | New — scope/tool management |
| Visual Parity | `lib/components/theme/app_theme.dart` | Match React color scheme |
| Geolocation | `lib/services/geolocation_service.dart` | New — silent capture |

---

## Environment Variables Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `BACKEND_HOST` | `localhost` | Backend server host |
| `BACKEND_PORT` | `8001` | Backend server port |
| `MOCK_AUTH` | `true` | Use mock auth instead of Keycloak |
| `FORCE_DEVICE_TYPE` | *(none)* | Override device detection for testing |
