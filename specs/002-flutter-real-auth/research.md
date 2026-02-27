# Research: Flutter Real Authentication Implementation

**Date**: 2026-02-27  
**Branch**: `002-flutter-real-auth`  
**Purpose**: Resolve technical unknowns and establish best practices for implementing React frontend parity in Flutter with real OIDC authentication.

## Research Methodology

1. **Analyze React frontend implementation** to extract styling values, component structure, and API interactions
2. **Evaluate Flutter ecosystem libraries** for OIDC, WebSocket, file upload, and chart rendering
3. **Test compatibility** with existing backend (port 8001) WebSocket protocol and API endpoints
4. **Benchmark performance** of alternative approaches to match React frontend experience

## Research Topics & Findings

### 1. OIDC/Keycloak Authentication Library for Flutter

**Decision**: Use `flutter_appauth` package with `oauth2` for token management

**Rationale**:
- `flutter_appauth` provides native platform integration (ASWebAuthenticationSession on iOS, Chrome Custom Tabs on Android) for secure OIDC flows
- Supports PKCE (Proof Key for Code Exchange) required by modern OIDC providers like Keycloak
- Actively maintained (1.2k stars, recent updates)
- Integrates well with `shared_preferences` for token storage
- Backend compatibility: The React frontend uses `oidc-client-ts` which follows same OIDC standards

**Alternatives considered**:
- `oauth2` pure Dart package: Lower-level, requires manual platform integration for authentication flows
- `keycloak_flutter`: Keycloak-specific but less flexible for other OIDC providers
- Custom implementation: Too much risk and maintenance burden

**Implementation notes**:
- Configure with same issuer, client ID, scopes as React frontend
- Token refresh handled automatically by `flutter_appauth`
- Store tokens in secure storage (`flutter_secure_storage` for sensitive data)

### 2. WebSocket Implementation for Real-time Chat

**Decision**: Use `web_socket_channel` package with custom protocol layer

**Rationale**:
- Official Flutter team package, well-maintained
- Supports both `dart:io` WebSocket and browser WebSocket
- Compatible with backend's `websockets` Python library (RFC 6455)
- Provides `Stream` interface for reactive programming with Riverpod

**Alternatives considered**:
- `socket_io_client`: Socket.IO protocol but backend uses plain WebSocket
- Custom `dart:io` WebSocket: More boilerplate, less error handling
- `stream_channel`: Lower-level, unnecessary complexity

**Protocol compatibility**:
- Backend message format: JSON with `type` and `data` fields
- React frontend uses `useWebSocket` hook with same format
- Flutter implementation will mirror message parsing logic

### 3. File Upload for Mobile Platforms

**Decision**: Use `file_picker` for file selection + `dio` for multipart upload

**Rationale**:
- `file_picker` provides consistent cross-platform file selection (iOS/Android/Web)
- Supports multiple file types (CSV, text, JSON, MD) matching React frontend
- `dio` supports multipart/form-data with progress tracking
- Backend expects same `/upload` endpoint as React frontend

**Alternatives considered**:
- `image_picker`: Limited to images/videos
- `cross_file`: Lower-level, requires more platform-specific code
- Native platform channels: Too complex for simple file upload

**Drag-and-drop on mobile**:
- Mobile platforms don't support true drag-and-drop from filesystem
- Implement "browse" button with file picker as primary method
- On web target, implement HTML5 drag-and-drop using `dart:html`

### 4. UI Component Rendering for Complex Charts

**Decision**: Use `fl_chart` for basic charts, `webview_flutter` for Plotly

**Rationale**:
- `fl_chart` provides high-performance native Flutter rendering for bar, line, pie charts
- Matches React's `recharts` library visual output
- `webview_flutter` can render Plotly.js charts (same as React frontend)
- Backend generates Plotly JSON spec that can be passed to WebView

**Alternatives considered**:
- `charts_flutter`: Google's library but less customization
- `syncfusion_flutter_charts`: Commercial, licensing issues
- `plotly_dart`: Incomplete, not maintained

**Performance consideration**:
- WebView has higher memory footprint but necessary for Plotly compatibility
- Cache rendered charts to improve performance

### 5. State Management Architecture

**Decision**: Use Riverpod with `StateNotifier` for complex state, `StateProvider` for simple state

**Rationale**:
- Riverpod is compile-safe, testable, and scales well
- Similar mental model to React's hooks (Provider vs useContext)
- Supports async state, dependency injection, and scoped providers
- Active community and good documentation

**Alternatives considered**:
- Provider: Older, less type-safe
- Bloc: More boilerplate for simple state
- GetX: Opinionated, less predictable
- Redux: Too much boilerplate for this project

### 6. Local Storage for Saved Components

**Decision**: Use `hive` for local database with JSON serialization

**Rationale**:
- `hive` is fast, NoSQL database with zero dependencies
- Supports complex object storage with type adapters
- Better performance than `shared_preferences` for larger datasets
- React frontend uses IndexedDB; Hive provides similar capabilities

**Alternatives considered**:
- `shared_preferences`: Key-value only, not suitable for complex objects
- `sqflite`: SQLite, overkill for simple component storage
- `isar`: More features but newer, less mature

### 7. Performance Optimization Strategies

**Decision**: Implement virtual scrolling for chat, image caching, and WebSocket message batching

**Rationale**:
- Chat history can grow large; `ListView.builder` with `itemExtent` for virtual scrolling
- `cached_network_image` for efficient image loading
- Batch WebSocket messages during high-frequency updates
- Use `compute()` for expensive UI component rendering

**Benchmark targets**:
- 60fps during chat scrolling
- <200ms message delivery (matching React)
- <3s authentication flow
- <30s file upload (10MB)

## Integration Points with Backend

### WebSocket Protocol
```json
{
  "type": "register_ui",
  "data": {
    "user_id": "...",
    "token": "..."
  }
}
```
- Same format as React frontend
- Connection URL: `ws://localhost:8001/ws` (configurable)
- Reconnection logic: Exponential backoff (5s, 10s, 20s)

### Authentication Flow
1. User clicks "Login with Keycloak"
2. `flutter_appauth` opens OIDC provider
3. Receives authorization code, exchanges for tokens
4. Tokens stored in secure storage
5. WebSocket connects with token in `register_ui` message

### File Upload Endpoint
- `POST /upload` with `multipart/form-data`
- Same as React frontend
- Progress events via `dio` interceptors

## Open Questions Resolved

1. **How to handle platform-specific UI differences?**
   - Use responsive design with `LayoutBuilder` and `MediaQuery`
   - Maintain same component hierarchy but adapt layout for mobile screens

2. **How to ensure pixel-perfect matching with React?**
   - Extract CSS values from React components (padding, margin, colors, fonts)
   - Create Flutter theme with exact values
   - Use screenshot comparison during development

3. **How to handle backend API changes?**
   - Monitor React frontend network calls as reference
   - Backend is immutable; API should remain stable
   - If changes occur, update Flutter to match React implementation

## Next Steps

1. **Phase 1 Design**: Create data models based on research decisions
2. **Implementation**: Begin with foundational OIDC authentication
3. **Testing**: Verify connectivity with backend on port 8001
4. **Validation**: Compare with React frontend for visual and functional parity

---

*This research document resolves all NEEDS CLARIFICATION items from the Technical Context. All technology choices are justified with alternatives considered. Implementation can proceed to Phase 1.*