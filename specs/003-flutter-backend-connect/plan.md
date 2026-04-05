# Implementation Plan: Flutter-Backend SDUI Integration

**Branch**: `003-flutter-backend-connect` | **Date**: 2026-04-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-flutter-backend-connect/spec.md`

## Summary

Connect the Flutter SDUI thin client to the AstralBody backend — fix WebSocket protocol mismatches blocking chat, wire the full save/combine/condense component pipeline, add the UI drawer with auto-condense, implement local persistence for offline resilience, and visually polish all SDUI primitives within the dark navy theme.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Dart 3.x / Flutter 3.x (frontend)  
**Primary Dependencies**: FastAPI + Uvicorn (backend), Provider + web_socket_channel + fl_chart + flutter_secure_storage (frontend)  
**Storage**: SQLite via file-based persistence (backend saved components), SharedPreferences + flutter_secure_storage (frontend caching)  
**Testing**: pytest (backend), flutter_test + mockito + integration_test (frontend)  
**Target Platform**: Windows/macOS/Linux desktop, Android, iOS, Web (Flutter multi-platform)  
**Project Type**: Mobile-app + web-service (SDUI thin client + orchestrator backend)  
**Performance Goals**: SDUI render within 2s of backend response, WebSocket reconnect within 30s  
**Constraints**: Backend is sole UI authority (Constitution VIII), no business logic in Flutter client  
**Scale/Scope**: 16+ SDUI primitive types, 5 user stories, 2 repos (backend + Flutter)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language | PASS | Backend remains Python |
| II. Frontend Client | PASS | Flutter thin client renders SDUI, no business logic |
| III. Testing Standards | PENDING | Must achieve 90% coverage on changed code — test plan needed |
| IV. Code Quality | PENDING | Dart analyzer must pass with no warnings; ruff for Python |
| V. Dependency Management | PASS | No new dependencies required — all packages already in pubspec.yaml |
| VI. Documentation | PENDING | Public Dart members need `///` doc comments; Python needs docstrings |
| VII. Security | PASS | Auth via Keycloak/mock JWT, no secrets in code |
| VIII. SDUI Architecture | PASS | Backend owns all UI composition; Flutter is passive renderer; unknown types degrade to placeholder |

**Gate Result**: PASS — no violations. Pending items are process requirements to satisfy during implementation.

## Project Structure

### Documentation (this feature)

```text
specs/003-flutter-backend-connect/
├── plan.md              # This file
├── research.md          # Phase 0 output — protocol mismatches, connectivity, auth
├── data-model.md        # Phase 1 output — entities, SDUI primitives catalog
├── quickstart.md        # Phase 1 output — dev setup instructions
├── contracts/
│   └── websocket-protocol.md  # Phase 1 output — full WS message contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# AstralBody backend (y:\WORK\MCP\AstralBody\)
backend/
├── orchestrator/
│   ├── orchestrator.py    # WebSocket handler, save/combine/condense actions
│   └── api.py             # REST endpoints for saved components
├── shared/
│   ├── protocol.py        # Message type definitions
│   └── primitives.py      # SDUI component classes (24 types)
├── rote/                  # Device adaptation middleware
└── start.py               # Entry point

# Flutter frontend (y:\WORK\MCP\astralprojection-flutter\)
lib/
├── main.dart
├── app.dart               # MultiProvider root
├── config.dart            # Backend connection config
├── components/
│   ├── dynamic_renderer.dart    # SDUI type→widget mapping
│   ├── chat/
│   │   └── chat_input_bar.dart  # Chat input (payload fix needed)
│   ├── primitives/              # 42 SDUI widget files
│   ├── workspace/
│   │   ├── workspace_layout.dart       # Main content area
│   │   └── saved_components_drawer.dart # UI drawer (exists, needs wiring)
│   ├── common/                  # Shared widgets (glass_card, loading, offline)
│   └── navigation/
├── state/
│   ├── web_socket_provider.dart     # WS lifecycle, SDUI tree, auto-reconnect
│   ├── app_shell_provider.dart      # Shell state, chat history, agents
│   ├── device_profile_provider.dart # Device detection & capabilities
│   ├── project_provider.dart        # Project management
│   ├── theme_provider.dart          # Backend theme application
│   └── token_storage_provider.dart  # Secure token storage
└── platform/                        # TV/Watch specializations

test/
├── unit/
├── widget/
└── integration/
```

**Structure Decision**: Two-repo web-application structure. Backend repo (`AstralBody`) contains the orchestrator, agents, and SDUI primitives. Frontend repo (`astralprojection-flutter`) contains the Flutter thin client. Changes span both repos but are primarily Flutter-side (protocol fixes, UI drawer wiring, visual polish).

## Key Implementation Areas

### Area 1: Protocol Fixes (P0 — blocks all functionality)

Three critical payload mismatches identified in research:

1. **chat_message payload** (`chat_input_bar.dart`): Sends `"text"` key but backend reads `"message"` — all chat silently drops. Fix: rename key to `"message"`.

2. **combine_components payload** (`workspace_layout.dart`): Sends `{"component_ids": [...]}` but backend reads `source_id`/`target_id`. Fix: send `{"source_id": "...", "target_id": "..."}`.

3. **save_component payload**: Verify all call sites send `chat_id`, `component_data`, `component_type`, `title` as required by backend.

### Area 2: Network Connectivity (P0 — blocks mobile/tablet)

- Docker port binding: Change from `127.0.0.1:8001:8001` to `8001:8001` for LAN access
- Flutter `config.dart`: Make backend host runtime-configurable with platform defaults (localhost for desktop, `10.0.2.2` for Android emulator, user-configurable for physical devices)
- CORS: Add LAN IPs to `CORS_ORIGINS` env var

### Area 3: UI Drawer Integration (P2-P3)

The `SavedComponentsDrawer` widget exists with:
- Grid display, drag-and-drop combine, delete, condense all, full-screen inspect

Remaining work:
- Wire "Add to UI" (`+` icon) on every rendered SDUI component
- Connect drawer visibility to `has_saved_components` state (right-edge indicator)
- Full-screen drawer open/dismiss behavior per spec (FR-006)
- Per-chat scoping — drawer shows only active chat's components

### Area 4: Visual Polish (P4)

All 42 primitive widgets exist. Polish tasks:
- Cards: depth/shadow, consistent padding, rounded corners
- Metrics: prominent value typography, theme accent progress bars
- Tables: alternating row backgrounds, distinct headers, horizontal scroll
- Charts: theme-consistent colors, readable labels
- Buttons/inputs: clear press states, focus states
- Overall: dark navy + indigo theme coherence

### Area 5: Local Persistence (P2)

- Serialize SDUI component tree to SharedPreferences on `ui_render`/`ui_update`
- Load cached tree on startup before WebSocket connects
- Serialize saved components list similarly
- Already implemented: tree caching via `loadCachedTree()`/`_persistTree()` — verify it works end-to-end

### Area 6: Auth Flow (P1)

- Verify mock auth token flow works for dev: register → login UI → token issued → stored → re-register
- Option to pre-seed mock token for faster dev iteration
- Ensure `flutter_secure_storage` token survives app restarts

## Complexity Tracking

> No Constitution violations requiring justification.

| Concern | Mitigation |
|---------|-----------|
| Two-repo changes | Protocol fixes are Flutter-only; backend is authoritative and unchanged |
| 42 primitive widgets to polish | Batch by category (layout, content, input, data, chart); theme tokens ensure consistency |
| LLM-powered combine/condense | Backend handles LLM calls; Flutter just sends action and renders result |
