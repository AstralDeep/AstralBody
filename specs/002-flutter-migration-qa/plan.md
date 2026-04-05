# Implementation Plan: Flutter Migration QA & Feature Parity

**Branch**: `002-flutter-migration-qa` | **Date**: 2026-04-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-flutter-migration-qa/spec.md`

## Summary

Validate and fix the Flutter SDUI thin client (`astralprojection-flutter/`) to achieve full feature parity with the archived React frontend (`frontend-archive-react/`). The backend produces all UI via Server-Driven UI over WebSocket; the Flutter client must faithfully render it across phone, tablet, TV, and watch form factors. Key work areas: complete Keycloak OIDC authentication (currently TODO), fix login screen to show both username/password + SSO, validate all 23 SDUI primitives, implement missing features (voice I/O, geolocation, drag-and-drop combine, LaTeX math), and run QA across all target devices using test credentials from the project `.env` file.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Dart 3.7+ / Flutter 3.x (client)
**Primary Dependencies**: FastAPI + websockets (backend); Provider, web_socket_channel, fl_chart, flutter_appauth, flutter_secure_storage, shared_preferences, flutter_markdown, file_picker, just_audio, connectivity_plus (client)
**Storage**: PostgreSQL (backend); SharedPreferences + flutter_secure_storage (client)
**Testing**: pytest + pytest-asyncio (backend, 25 test files); flutter_test + integration_test + mockito (client, 35+ test files)
**Target Platform**: iOS phone, Android phone, iOS tablet, Android tablet, Apple TV/Android TV, Apple Watch
**Project Type**: Multi-platform mobile/TV/watch app (client) + web service (backend)
**Performance Goals**: Login < 5s (phone/tablet), SSO login < 10s, SDUI updates < 1s, watch dashboard < 3s, reconnect < 10s
**Constraints**: Flutter client must be a passive SDUI renderer (no embedded business logic or layout decisions); backend is sole UI authority
**Scale/Scope**: 23+ SDUI primitive types, 5 target form factors, 20 functional requirements (FR-001 through FR-020)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language | PASS | Backend remains Python 3.11+; no changes to backend language |
| II. Frontend Client | PASS | Flutter SDUI thin client; client is passive renderer; backend is sole UI authority |
| III. Testing Standards | GATE | Must achieve 90% coverage on changed code. Current test suite has 35+ files but gaps exist (auth_provider_test.dart missing, OIDC flow untested). New tests required for all fixes. |
| IV. Code Quality | PASS | Dart analyzer + flutter_lints enforced; Python uses ruff/PEP 8 |
| V. Dependency Management | GATE | Any new dependencies (e.g., flutter_math_fork for LaTeX) must be documented and justified in PR |
| VI. Documentation | PASS | Public APIs documented; SDUI contract documented in backend primitives.py |
| VII. Security | PASS | Keycloak auth; KEYCLOAK_CLIENT_SECRET stays server-side via BFF proxy; no secrets in client |
| VIII. SDUI Architecture | PASS | Client renders backend-produced trees; no hard-coded screens; unknown types degrade gracefully |

**Gate Resolution**: Testing (III) will be addressed by writing tests for every fix. Dependencies (V) will be documented in the tasks and PR description.

### Post-Design Re-Check (after Phase 1)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language | PASS | No backend language changes in design |
| II. Frontend Client | PASS | All design artifacts confirm Flutter as passive SDUI renderer. New features (voice, geolocation, saved components, agent permissions) are client-side UI only — no business logic added to client |
| III. Testing Standards | PASS (planned) | Test matrix defined in research.md R8. Each task will include test requirements. auth_provider_test.dart gap identified and will be addressed |
| IV. Code Quality | PASS | dart analyze enforced; no new lint exceptions |
| V. Dependency Management | GATE (1 new dep) | Audio recording package needed for STT (research.md R4). Will be documented in PR with rationale. All other features use existing deps |
| VI. Documentation | PASS | Contracts documented (auth-flow.md, sdui-protocol.md, device-profile.md). SDUI component types fully cataloged |
| VII. Security | PASS | Client secret stays server-side via BFF. Test credentials via --dart-define, not in source. No secrets in Flutter code |
| VIII. SDUI Architecture | PASS | All new UI driven by backend component trees. Agent permissions modal reads backend-provided scope data. Saved components managed server-side |

## Project Structure

### Documentation (this feature)

```text
specs/002-flutter-migration-qa/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── auth-flow.md     # Authentication contract (OIDC + password)
│   ├── sdui-protocol.md # WebSocket SDUI message protocol
│   └── device-profile.md# Device profile registration contract
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (AstralBody repo — QA-only, minimal changes expected)
src/
├── backend/
│   ├── orchestrator/
│   │   ├── auth.py              # BFF token proxy + JWT validation
│   │   ├── api.py               # REST endpoints
│   │   ├── orchestrator.py      # WebSocket SDUI server
│   │   └── models.py            # Message types
│   ├── shared/
│   │   ├── primitives.py        # 23+ SDUI component definitions
│   │   └── protocol.py          # Message protocol
│   ├── rote/
│   │   ├── rote.py              # Device adaptation engine
│   │   ├── capabilities.py      # Device type constraints
│   │   └── adapter.py           # Component transformer
│   └── tests/                   # 25 backend test files
├── .env                         # Keycloak credentials + test user creds
└── frontend-archive-react/      # Reference React implementation

# Flutter Client (sibling repo: astralprojection-flutter/)
astralprojection-flutter/
├── lib/
│   ├── main.dart                # Entry point
│   ├── app.dart                 # Root widget + providers
│   ├── config.dart              # Environment configuration
│   ├── state/
│   │   ├── auth_provider.dart   # Auth (OIDC + mock) — NEEDS FIX
│   │   ├── web_socket_provider.dart  # WebSocket + SDUI tree
│   │   ├── device_profile_provider.dart # Device detection
│   │   ├── project_provider.dart     # Project switching
│   │   └── theme_provider.dart       # Backend theme
│   ├── components/
│   │   ├── auth/
│   │   │   └── login_page.dart  # Login UI — NEEDS FIX (show both forms)
│   │   ├── primitives/          # 23 SDUI widget implementations
│   │   ├── dynamic_renderer.dart # Component registry
│   │   ├── workspace/           # Main SDUI rendering area
│   │   ├── navigation/          # Top bar + project selector
│   │   ├── common/              # Loading, offline, placeholder
│   │   └── platform/
│   │       ├── tv/              # TV focus + theme
│   │       └── watch/           # Watch renderer + theme
│   └── (missing features)
│       # voice_input_service.dart  — MISSING
│       # voice_output_service.dart — MISSING
│       # geolocation_service.dart  — MISSING
│       # saved_components/         — MISSING (combine/condense DnD)
│       # agent_permissions_modal   — MISSING
├── test/
│   ├── unit/                    # 7 test files
│   ├── widget/                  # 26 widget test files
│   └── integration/             # 5 integration test files
└── pubspec.yaml                 # Dependencies
```

**Structure Decision**: Existing dual-repo structure is correct per spec 001. Backend repo contains the SDUI server + archived React reference. Flutter client is in sibling repo. QA work primarily targets the Flutter client with reference comparisons against the React archive.

## Complexity Tracking

> No constitution violations requiring justification. All gates pass or have clear resolution paths.
