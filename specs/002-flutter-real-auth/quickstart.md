# Quickstart: Flutter Real Authentication Implementation

**Date**: 2026-02-27  
**Target**: Developers implementing the Flutter frontend  
**Prerequisites**: Flutter 3.22+, Dart 3.4+, running backend on port 8001

## Overview

This quickstart guide helps you set up and run the Flutter frontend with real OIDC authentication, connecting to the existing Python backend.

## 1. Environment Setup

### Clone and Navigate
```bash
git clone <repository-url>
cd AstralBody/flutter
```

### Install Dependencies
```bash
flutter pub get
```

### Configure Environment
Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
```env
# Backend configuration
VITE_WS_URL=ws://localhost:8001/ws
VITE_API_URL=http://localhost:8001

# OIDC/Keycloak configuration
VITE_OIDC_ISSUER=https://keycloak.example.com/auth/realms/astralbody
VITE_OIDC_CLIENT_ID=astralbody-frontend
VITE_OIDC_REDIRECT_URI=astralbody://callback

# Feature flags
VITE_ENABLE_MOCK_AUTH=false
VITE_ENABLE_FILE_UPLOAD=true
```

## 2. Backend Preparation

Ensure the Python backend is running:
```bash
# From repository root
cd backend
python start.py
# Or using Docker
docker-compose up
```

Verify backend health:
```bash
curl http://localhost:8001/health
# Should return {"status": "healthy"}
```

## 3. Authentication Setup

### Keycloak/OIDC Provider
1. Set up a Keycloak instance (or use existing)
2. Create a realm "astralbody"
3. Create a client with:
   - Client ID: `astralbody-frontend`
   - Access Type: `public`
   - Valid Redirect URIs: `astralbody://callback`
   - Web Origins: `*`

### Alternative: Mock Authentication
For development without Keycloak, enable mock auth:
```env
VITE_ENABLE_MOCK_AUTH=true
```

## 4. Running the App

### Development Mode
```bash
flutter run
```

### Platform Specific
```bash
# Android
flutter run -d android

# iOS
flutter run -d ios

# Web
flutter run -d chrome
```

### Build for Production
```bash
# Android APK
flutter build apk --release

# iOS
flutter build ios --release

# Web
flutter build web --release
```

## 5. First-Time Usage

1. **Launch the app** - You'll see the login screen
2. **Authenticate** - Click "Login with Keycloak" (or use mock credentials if enabled)
3. **Connect to backend** - App automatically connects to WebSocket
4. **Start chatting** - Send a message to test the connection

## 6. Testing Connectivity

### Manual Test
1. Check connection status in dashboard sidebar
2. Send test message: "Hello, world!"
3. Verify response contains UI components

### Automated Test
Run the test suite:
```bash
flutter test
```

Run integration tests:
```bash
flutter test integration_test/
```

## 7. Development Workflow

### File Structure
```
flutter/lib/
├── core/           # Configuration, themes, utilities
├── data/           # Models, datasources, repositories
├── presentation/   # UI components, pages, providers
└── main.dart       # App entry point
```

### Key Files to Modify
- **Authentication**: `lib/data/datasources/oidc_auth_datasource.dart`
- **WebSocket**: `lib/data/datasources/websocket_service.dart`
- **UI Components**: `lib/presentation/widgets/dynamic_renderer.dart`
- **Theme**: `lib/core/theme/app_theme.dart`

### Hot Reload
Flutter supports hot reload during development:
```bash
flutter run --hot-reload
```

## 8. Debugging

### Common Issues

#### "Cannot connect to WebSocket"
1. Verify backend is running: `curl http://localhost:8001/health`
2. Check WebSocket URL in `.env`
3. Ensure no firewall blocking port 8001

#### "Authentication failed"
1. Verify OIDC configuration in `.env`
2. Check Keycloak server is accessible
3. Try mock authentication for testing

#### "UI components not rendering"
1. Check WebSocket messages in browser DevTools
2. Verify `DynamicRenderer` handles component type
3. Compare with React frontend rendering

### Logging
Enable verbose logging:
```dart
// In main.dart
import 'package:flutter/foundation.dart';

void main() {
  debugPrint = (String? message, {int? wrapWidth}) {
    if (kDebugMode) {
      print(message);
    }
  };
  runApp(MyApp());
}
```

## 9. Integration with Existing System

### Backend Compatibility
- Uses same WebSocket protocol as React frontend
- Same REST API endpoints
- Same authentication tokens

### Data Migration
No data migration needed - Flutter app uses same backend data as React.

### Coexistence with React
Both frontends can run simultaneously, connecting to same backend.

## 10. Next Steps

### After Successful Connection
1. Implement file upload functionality
2. Add saved components drawer
3. Enhance UI component rendering
4. Optimize performance

### Production Deployment
1. Set up CI/CD pipeline
2. Configure production OIDC provider
3. Enable analytics and monitoring
4. Set up error reporting (Sentry, Firebase)

## Appendix

### Environment Variables Reference
| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_WS_URL` | WebSocket URL | `ws://localhost:8001/ws` |
| `VITE_API_URL` | REST API URL | `http://localhost:8001` |
| `VITE_OIDC_ISSUER` | OIDC issuer URL | - |
| `VITE_OIDC_CLIENT_ID` | OIDC client ID | - |
| `VITE_OIDC_REDIRECT_URI` | OIDC redirect URI | `astralbody://callback` |
| `VITE_ENABLE_MOCK_AUTH` | Enable mock authentication | `false` |
| `VITE_ENABLE_FILE_UPLOAD` | Enable file upload | `true` |

### Useful Commands
```bash
# Code generation for models
flutter pub run build_runner build --delete-conflicting-outputs

# Analyze code for issues
flutter analyze

# Format code
flutter format .

# Generate icons
flutter pub run flutter_launcher_icons
```

### Support
- Backend API documentation: `backend/README.md`
- React reference implementation: `frontend/`
- Issue tracking: Project issue tracker

---

*This quickstart gets you from zero to a working Flutter frontend connected to the AstralBody backend. For detailed implementation, refer to the spec and plan documents.*
