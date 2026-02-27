# Implementation Plan: Flutter Real Authentication Implementation

**Branch**: `002-flutter-real-auth` | **Date**: 2026-02-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-flutter-real-auth/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Copy design and functionality from the React frontend (`frontend/`) to the Flutter project (`flutter/`), implementing real OIDC/Keycloak authentication and ensuring connectivity to the Python backend on port 8001. The implementation must achieve visual parity, logic mirroring, and API integrity with the React frontend while only modifying files within the `flutter/` directory.

## Technical Context

**Language/Version**: Dart 3.4 / Flutter 3.22  
**Primary Dependencies**: Riverpod (state management), Dio (HTTP client), web_socket_channel (WebSocket), flutter_appauth (OIDC), shared_preferences (local storage)  
**Storage**: Local: shared_preferences for tokens, Hive/Isar for saved components. Remote: Backend PostgreSQL via API.  
**Testing**: flutter_test (unit/widget), integration_test, mockito for mocking  
**Target Platform**: iOS, Android, Web (Chrome) - primary focus mobile  
**Project Type**: Mobile application with real-time WebSocket communication  
**Performance Goals**: 60fps UI rendering, <200ms chat message delivery, <3s authentication flow, <30s file upload (10MB)  
**Constraints**: Must match React frontend pixel-perfect, only modify `flutter/` directory, maintain backend compatibility, support offline cached components  
**Scale/Scope**: 5 user stories, 48 tasks, ~50 screens/components, 10k+ lines of Flutter code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Gates from Constitution:
1. **Visual Parity Law**: ✅ Compliant - All styling will be replicated from React CSS to Flutter widgets
2. **Logic Mirror Law**: ✅ Compliant - Business logic copied verbatim from React components
3. **API Integrity Law**: ✅ Compliant - Same endpoints, headers, tokens as React
4. **Asset Law**: ✅ Compliant - Assets copied from `frontend/public` to `flutter/assets`
5. **Execution Protocol**: ✅ Compliant - Follow 4-step migration sequence
6. **Target Directory Constraint**: ✅ Compliant - Only `flutter/` directory modifications
7. **Immutable Backend**: ✅ Compliant - Backend remains READ-ONLY

**Result**: All gates PASS. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-flutter-real-auth/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/                    # Python FastAPI orchestrator (READ-ONLY)
├── orchestrator/
│   ├── auth.py            # Authentication logic
│   ├── orchestrator.py    # WebSocket server
│   └── history.py         # Chat history
├── shared/
│   ├── database.py        # PostgreSQL connection
│   └── protocol.py        # WebSocket message formats
└── tests/

frontend/                   # React reference implementation (READ-ONLY)
├── src/
│   ├── components/        # UI components to replicate
│   ├── hooks/             # Custom hooks (useWebSocket, useAuth)
│   ├── services/          # API services
│   └── styles/            # CSS/Tailwind styling
└── public/                # Static assets

flutter/                    # Target implementation directory
├── lib/
│   ├── core/
│   │   ├── config/        # App configuration
│   │   ├── errors/        # Exception handling
│   │   ├── theme/         # App theme matching React
│   │   └── utils/         # Utilities
│   ├── data/
│   │   ├── datasources/   # OIDC, WebSocket, file upload services
│   │   ├── models/        # Data models (User, ChatSession, etc.)
│   │   └── repositories/  # Repository pattern
│   ├── presentation/
│   │   ├── pages/         # Screens (login, dashboard, chat)
│   │   ├── widgets/       # Reusable widgets
│   │   ├── providers/     # Riverpod providers
│   │   └── router/        # Navigation
│   └── main.dart          # App entry point
├── assets/                # Copied from frontend/public
│   ├── fonts/             # Inter, JetBrains Mono
│   └── images/            # Logos, icons
└── test/                  # Flutter tests
```

**Structure Decision**: Mobile + API structure (Option 3) with `backend/` as immutable API and `flutter/` as mobile client. The React `frontend/` serves as reference implementation for styling and logic.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations - all constitution gates pass.
