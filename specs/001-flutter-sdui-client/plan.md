# Implementation Plan: Flutter SDUI Thin Client

**Branch**: `001-flutter-sdui-client` | **Date**: 2026-04-03 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-flutter-sdui-client/spec.md`

## Summary

Replace the React/TypeScript frontend with a Flutter-based device-agnostic SDUI thin client. The Flutter app (sourced from the `astralprojection-flutter` codebase) will be adapted to AstralBody's backend protocol, rendering SDUI component trees produced by the backend on phones, tablets, Apple Watch, and TV. The React frontend will be archived. The backend remains unchanged except for one minor fix: re-enabling primary buttons on TV in the ROTE adapter.

## Technical Context

**Language/Version**: Dart 3.7+ / Flutter 3.x (client), Python 3.11+ (backend — unchanged)  
**Primary Dependencies**: Flutter SDK, Provider, web_socket_channel, flutter_markdown, fl_chart (charts), shared_preferences, flutter_appauth (Keycloak OIDC)  
**Storage**: SharedPreferences (client session), PostgreSQL (backend — unchanged)  
**Testing**: flutter_test (unit/widget), integration_test (device integration), pytest (backend — existing)  
**Target Platforms**: iOS (iPhone, iPad), Android (phone, tablet), watchOS (Apple Watch — companion), tvOS/Android TV  
**Project Type**: Multi-platform mobile/watch/TV app (SDUI thin client)  
**Performance Goals**: Dashboard interactive within 5s (phone/tablet/TV), 3s (watch); SDUI updates visible within 1s of dispatch  
**Constraints**: Single codebase for phone/tablet/TV; watch as a companion target; no business logic in client  
**Scale/Scope**: 25+ SDUI primitive renderers, 5 form factors, WebSocket real-time, Keycloak OIDC

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python backend) | PASS | Backend unchanged. Client is Dart per constitution. |
| II. Frontend Client (Flutter SDUI) | PASS | Migrating to Flutter as constitution mandates. Passive renderer, no business logic. |
| III. Testing Standards (90% coverage) | PASS | Plan includes comprehensive test suite across all device targets. |
| IV. Code Quality (Dart analyzer) | PASS | `dart analyze` + flutter_lints enforced. |
| V. Dependency Management | PASS | All new Flutter dependencies documented with rationale in this plan. |
| VI. Documentation (Dart doc comments) | PASS | All public Dart members will have `///` doc comments. |
| VII. Security (Keycloak) | PASS | Migrating from basic auth to Keycloak OIDC. No secrets in source. |
| VIII. SDUI Architecture | PASS | Client renders backend-produced trees. No hard-coded screens. |

**Post-Phase 1 Re-check**: All gates still pass. No violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/001-flutter-sdui-client/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── sdui-component-contract.md
│   └── websocket-protocol-contract.md
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/                          # UNCHANGED — Python backend
├── shared/
│   ├── primitives.py             # SDUI component definitions (source of truth)
│   └── protocol.py               # WebSocket message types
├── rote/                         # Device profile adaptation (supports mobile/watch/TV)
│   ├── capabilities.py
│   ├── adapter.py
│   └── rote.py
├── orchestrator/
│   ├── orchestrator.py           # WebSocket server, ROTE integration
│   ├── api.py                    # REST endpoints
│   └── auth.py                   # Keycloak BFF proxy
├── agents/                       # Specialist agents (unchanged)
└── tests/                        # Backend tests (update where frontend-coupled)

frontend-archive-react/           # ARCHIVED from frontend/
├── src/                          # Historical reference only
└── ...

astralprojection-flutter/         # Flutter client (MODIFIED IN-PLACE)
├── lib/
│   ├── main.dart                 # Entry point
│   ├── app.dart                  # MaterialApp + providers
│   ├── config.dart               # Backend host/port configuration
│   ├── state/                    # State management
│   │   ├── auth_provider.dart    # REWRITE: Keycloak OIDC
│   │   ├── web_socket_provider.dart  # REWRITE: AstralBody protocol
│   │   ├── project_provider.dart     # UPDATE: project selection
│   │   └── device_profile_provider.dart  # NEW: device capability reporting
│   ├── components/
│   │   ├── dynamic_renderer.dart     # REWRITE: map AstralBody primitives
│   │   ├── auth/
│   │   │   └── login_page.dart       # UPDATE: Keycloak login
│   │   ├── navigation/
│   │   │   └── nav_bar.dart          # UPDATE: responsive nav
│   │   ├── workspace/
│   │   │   ├── workspace_layout.dart # UPDATE: protocol integration
│   │   │   └── project_dropdown.dart
│   │   ├── theme/
│   │   │   └── app_theme.dart        # UPDATE: TV/watch themes
│   │   ├── common/
│   │   │   ├── placeholder_widget.dart  # NEW: unknown component placeholder
│   │   │   └── offline_indicator.dart   # NEW: connection status
│   │   └── primitives/              # SDUI renderers
│   │       ├── container_widget.dart    # NEW (backend: container)
│   │       ├── text_widget.dart         # RENAME+UPDATE (backend: text)
│   │       ├── button_widget.dart       # UPDATE (backend: button)
│   │       ├── input_widget.dart        # UPDATE (backend: input)
│   │       ├── card_widget.dart         # UPDATE (backend: card)
│   │       ├── table_widget.dart        # NEW (backend: table + pagination)
│   │       ├── list_widget.dart         # NEW (backend: list)
│   │       ├── alert_widget.dart        # NEW (backend: alert)
│   │       ├── progress_widget.dart     # NEW (backend: progress)
│   │       ├── metric_widget.dart       # NEW (backend: metric)
│   │       ├── code_widget.dart         # RENAME+UPDATE (backend: code)
│   │       ├── image_widget.dart        # NEW (backend: image)
│   │       ├── grid_widget.dart         # NEW (backend: grid)
│   │       ├── tabs_widget.dart         # NEW (backend: tabs)
│   │       ├── divider_widget.dart      # NEW (backend: divider)
│   │       ├── collapsible_widget.dart  # NEW (backend: collapsible)
│   │       ├── bar_chart_widget.dart    # NEW (backend: bar_chart)
│   │       ├── line_chart_widget.dart   # NEW (backend: line_chart)
│   │       ├── pie_chart_widget.dart    # NEW (backend: pie_chart)
│   │       ├── plotly_chart_widget.dart  # NEW (backend: plotly_chart)
│   │       ├── color_picker_widget.dart  # NEW (backend: color_picker)
│   │       ├── file_upload_widget.dart   # RENAME+UPDATE (backend: file_upload)
│   │       └── file_download_widget.dart # NEW (backend: file_download)
│   └── platform/                     # NEW: platform-specific adaptations
│       ├── tv/
│       │   ├── tv_focus_manager.dart     # D-pad/remote focus navigation
│       │   └── tv_theme.dart             # Large text, generous spacing
│       └── watch/
│           ├── watch_renderer.dart        # Subset component renderer
│           └── watch_theme.dart            # Glanceable, compact layout
├── test/                             # Flutter tests
│   ├── unit/
│   │   ├── dynamic_renderer_test.dart
│   │   ├── web_socket_provider_test.dart
│   │   ├── auth_provider_test.dart
│   │   └── device_profile_test.dart
│   ├── widget/
│   │   ├── primitives/               # One test per primitive widget
│   │   │   ├── text_widget_test.dart
│   │   │   ├── button_widget_test.dart
│   │   │   ├── table_widget_test.dart
│   │   │   ├── chart_widget_test.dart
│   │   │   └── ... (all 25+ primitives)
│   │   ├── placeholder_test.dart
│   │   └── offline_indicator_test.dart
│   └── integration/
│       ├── phone_rendering_test.dart
│       ├── tablet_rendering_test.dart
│       ├── tv_rendering_test.dart
│       ├── watch_rendering_test.dart
│       └── websocket_flow_test.dart
├── android/                          # Android phone/tablet/TV
├── ios/                              # iOS iPhone/iPad
├── macos/                            # macOS (secondary)
└── pubspec.yaml                      # Dependencies
```

**Structure Decision**: The Flutter client lives in the `astralprojection-flutter/` directory (modified in-place as requested). The React frontend moves to `frontend-archive-react/` for reference. Backend stays at `backend/`. This preserves the existing mono-repo layout while swapping the frontend technology.

## Key Protocol Gaps

### Critical: Protocol Mismatch

The AstralProjection Flutter client and AstralBody backend use **different WebSocket protocols**:

| Concern | AstralBody Backend (current) | Flutter Client (current) |
|---------|------------------------------|--------------------------|
| Registration | `register_ui` (capabilities, device, token) | `register_capabilities` (primitives list) |
| User action | `ui_event` (action, payload) | `ui_action` (actionId, arguments) |
| Full render | `ui_render` (components list) | `initial_ui_state` (rootElement tree) |
| Partial update | `ui_update` / `ui_append` | `primitive_content_update` |
| Component types | snake_case (text, bar_chart) | PascalCase (TextView, StackLayout) |

**Resolution**: The Flutter client will be rewritten to speak the AstralBody backend protocol. The backend protocol is the source of truth and remains unchanged.

### Critical: Primitive Coverage Gap

| Backend Primitive | Flutter Equivalent | Action |
|---|---|---|
| container | StackLayout (partial) | Rewrite as `container_widget.dart` |
| text | TextView | Rename + adapt to backend schema |
| button | Button | Adapt to backend schema |
| input | InputField | Rename + adapt |
| card | Card | Adapt to backend schema (content[] vs children[]) |
| table | HtmlView (inadequate) | New widget with pagination |
| list | — | New widget |
| alert | — | New widget |
| progress | — | New widget |
| metric | — | New widget |
| code | CodeView | Rename + adapt |
| image | ImageUpload (different) | New display widget |
| grid | — | New widget |
| tabs | — | New widget |
| divider | — | New widget |
| collapsible | — | New widget |
| bar_chart | — | New widget (fl_chart) |
| line_chart | — | New widget (fl_chart) |
| pie_chart | — | New widget (fl_chart) |
| plotly_chart | — | New widget (WebView/static) |
| color_picker | — | New widget |
| file_upload | FileUploadField | Rename + adapt |
| file_download | — | New widget |

**14 new widgets** needed, **9 existing widgets** to adapt/rename.

### Auth Gap

Flutter currently uses basic username/password auth against `/auth/login`. Needs Keycloak OIDC code flow through backend BFF proxy at `/auth/token`.

### Device Profile Gap

Flutter has no device profile reporting. Backend ROTE system expects `device` dict in `register_ui` with: device_type, screen_width/height, viewport_width/height, pixel_ratio, has_touch, etc.

## Dependency Rationale

| Package | Purpose | Why This Package |
|---------|---------|------------------|
| `fl_chart` | Bar, line, pie chart rendering | Most popular pure-Dart chart lib, 60fps, no platform channels |
| `flutter_appauth` | Keycloak OIDC auth | Wraps native AppAuth SDK, supports PKCE, system browser |
| `flutter_inappwebview` | Plotly chart rendering | Required for JavaScript-based Plotly on mobile |
| `flutter_secure_storage` | JWT storage | Keychain/Keystore backed, more secure than SharedPreferences for tokens |
| `connectivity_plus` | Network status detection | Auto-reconnect trigger, offline indicator |
| `provider` | State management | Already in use, proven pattern |
| `web_socket_channel` | WebSocket communication | Already in use, standard Flutter WebSocket |
| `file_picker` | File upload | Already in use, cross-platform |
| `flutter_color_picker` | Color picker widget | Lightweight, matches backend color_picker primitive |

## Complexity Tracking

> No constitution violations detected. No justifications needed.

| Area | Complexity | Mitigation |
|------|------------|------------|
| Apple Watch | High — watchOS has limited Flutter support | Native watchOS companion app (SwiftUI) sharing WebSocket protocol |
| TV D-pad navigation | Medium — Flutter FocusTraversalGroup needed | Dedicated TV focus manager widget |
| Plotly charts | Medium — no native Dart Plotly | WebView on phone/tablet; metric fallback on watch/TV |
| Protocol rewrite | Medium — complete WebSocket provider rewrite | Follow backend protocol.py as spec |

## Backend Changes (Minimal)

Only **one** backend change is needed:

**File**: `backend/rote/adapter.py`, method `_adapt_button`

**Current behavior**: Removes ALL buttons on TV (`DeviceType.TV` returns `None`).  
**Problem**: TV users can select items with remote/D-pad — primary buttons should remain.  
**Fix**: Allow primary buttons on TV, remove only secondary/tertiary buttons.

```python
# Current (line 248):
if profile.device_type in (DeviceType.TV, DeviceType.VOICE):
    return None

# Proposed:
if profile.device_type == DeviceType.VOICE:
    return None
if profile.device_type == DeviceType.TV:
    if comp.get("variant", "primary") != "primary":
        return None
```

No other backend changes required.
