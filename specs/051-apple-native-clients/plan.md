# Implementation Plan: Native Apple Clients (iOS, macOS, watchOS SDUI Targets)

**Branch**: `051-apple-native-clients` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/051-apple-native-clients/spec.md`

## Summary

Add the Apple family as three first-party SDUI targets consuming the existing WS + REST
contract unchanged: iOS (twin of the Android client), macOS (twin of the Windows client), and
watchOS (smallest target; backend-brokered RFC 8628 QR sign-in, voice dictation in, on-device
TTS speaking the server's `voice`-target rendition, hard ROTE degradation guarantees). Backend
deltas are additive and dependency-free: named `ios`/`macos` device profiles, a first-party
stdlib QR encoder, `/api/auth/device/*` broker endpoints (`FF_DEVICE_LOGIN`, fail-closed), and
an additive `speech` field on watch-bound deliveries.

## Technical Context

**Language/Version**: Swift 5.9+ (SwiftUI; iOS/iPadOS 17, macOS 14, watchOS 10) for clients;
Python 3.11+ (production image; local `.venv` 3.13) for backend deltas.

**Primary Dependencies**: Clients — Apple frameworks only (URLSession WebSocket,
ASWebAuthenticationSession, Codable, CryptoKit for PKCE S256, AVFoundation/AVSpeechSynthesizer,
CoreImage). **Zero third-party Swift packages** (Constitution V; toolchain approval recorded in
PR). Backend — existing only: FastAPI, websockets, `python-jose`, `cryptography` (Fernet),
`shared.external_http`, `webrender` voice target. **Zero new backend runtime deps**; QR encoder
is first-party stdlib (`zlib`/`struct`).

**Storage**: None new. Device-login state is stateless — the watch holds an opaque
Fernet-encrypted poll handle; RFC 8628 state lives at Keycloak. (Constitution IX: if planning
is wrong about this, any persistence ships as a guarded idempotent `_init_db` delta.)

**Testing**: pytest (backend; DB-free units for QR/profiles/broker logic + suite-integrated
tests run in the `astralbody` container); XCTest via `swift test` for AstralCore (manifest
drift guard, PKCE, queue/backoff, device-login state machine); Xcode for app targets.

**Target Platform**: iPhone/iPad, Mac, Apple Watch (independent watch app) against the
existing orchestrator (`:8001`) + Keycloak realm.

**Project Type**: Native mobile/desktop/wearable clients + small server deltas.

**Performance Goals**: SC-001 (QR sign-in < 60 s), SC-005 (TTS starts ≤ 2 s after final
frame, p95), SC-006 (≤ 2 taps beyond speech per voice round trip).

**Constraints**: Additive-only wire changes; `ui_protocol.json` remains the vocabulary source;
shared reconnect contract (1 s ×2 → 30 s cap; 64-frame bounded queue); watch never receives
unadapted payloads; fail-closed auth posture throughout.

**Scale/Scope**: 3 app targets + 1 shared Swift package; 47 push frames / 67 actions / 35
component types dispositioned per client; ~4 backend modules touched, ~3 added.

## Constitution Check

- **I (Primary Language)**: Backend deltas pure Python 3.11. Clients are a sanctioned native
  client stack (041/044 precedent). ✅
- **II/XII (SDUI + Cross-Client)**: astralprims defines → orchestrator renders → ROTE adapts;
  new named profiles `ios`/`macos` follow the 041 `android` pattern; watch reuses the existing
  profile; manifest + per-client drift guards extended, never forked. ✅
- **III (Testing)**: Test-first for backend logic (QR known-answer + invariants, broker state
  machine, profile derivation); AstralCore ships with XCTest incl. the drift guard; ≥90%
  changed-line coverage via existing gates. ✅
- **V (Dependencies)**: Zero new backend runtime deps; zero third-party Swift deps. XcodeGen
  is an optional dev-machine convenience only (never a runtime or CI-required dep; manual
  Xcode target setup documented as the canonical path). ✅
- **VII (Security)**: Auth stays IdP-native (RFC 8628 at Keycloak, brokered); egress to the
  IdP via existing verified-TLS paths; codes single-use/TTL/rate-limited; `FF_DEVICE_LOGIN`
  fail-closed; audit `auth` class events; tokens never logged. ✅
- **IX (Migrations)**: No schema change anticipated. ✅
- **XI (CI)**: Additive `apple-ci` workflow (macOS runner: `swift test` for AstralCore now;
  app builds when project generation lands); all existing gates untouched. ✅

## Project Structure

### Documentation (this feature)

```text
specs/051-apple-native-clients/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── tasks.md
├── checklists/requirements.md
└── contracts/
    ├── device-login.md        # /api/auth/device/* REST contract
    └── spoken-rendition.md    # additive `speech` field on watch-bound frames
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── device_login.py        # NEW: RFC 8628 broker (start/poll/refresh, flag, rate limit)
│   ├── web_auth.py            # touch: route registration for /api/auth/device/*
│   └── orchestrator.py        # touch: attach spoken rendition on watch-profile sends
├── rote/capabilities.py       # touch: DeviceType.IOS/MACOS + host-config entries
├── shared/qr.py               # NEW: first-party QR Model 2 encoder + stdlib PNG writer
├── webrender/voice.py         # reused unchanged (spoken rendition source)
└── tests/
    ├── test_apple_profiles.py # NEW
    ├── test_qr.py             # NEW
    ├── test_device_login.py   # NEW
    └── test_watch_speech.py   # NEW

apple-clients/
├── README.md                  # build/run; manual Xcode setup is canonical
├── project.yml                # optional XcodeGen convenience (dev-machine only)
├── AstralCore/                # shared Swift package (SPM), zero third-party deps
│   ├── Package.swift
│   ├── Sources/AstralCore/
│   │   ├── Protocol/          # Frames.swift, Components.swift, Manifest.swift
│   │   ├── Transport/         # WSClient.swift (backoff + 64-frame bounded queue)
│   │   ├── Auth/              # PKCE.swift, TokenStore.swift, DeviceLogin.swift, Session.swift
│   │   └── API/               # Rest.swift (chats list/detail, logout, device endpoints)
│   └── Tests/AstralCoreTests/ # ManifestDriftTests + unit tests
├── AstralApp/                 # iOS + macOS multiplatform SwiftUI target sources
└── AstralWatch/               # watchOS app sources (QR login, chat, TTS)

.github/workflows/apple-ci.yml # NEW: macOS runner, swift test (drift guard)
```

**Structure Decision**: One `apple-clients/` root (mirrors `windows-client/`,
`android-client/`) holding a single shared SPM package consumed by three app targets; app
targets are thin — protocol, transport, auth, and models live in AstralCore where `swift test`
covers them without Xcode.

## Complexity Tracking

| Risk | Mitigation |
|---|---|
| Hand-rolled QR correctness | Known-answer tests frozen from a matrix cross-checked against a reference encoder at dev time; structural invariant tests (finder/timing/format) in CI |
| RFC 8628 availability on the realm | Startup/first-use discovery of `device_authorization_endpoint` from realm well-known; fail-closed 503 with actionable message; realm-settings doc updated |
| Orchestrator send-path touch (speech field) | Additive field, watch-profile sockets only, helper unit-tested standalone; full container suite must stay green before merge |
| App targets need Xcode to build | AstralCore is CI-testable headlessly; canonical manual target setup documented; XcodeGen optional |

## Phase 0 / Phase 1 outputs

- [research.md](research.md) — decisions + alternatives (broker vs. direct IdP, QR in-house,
  per-platform client ids, speech field shape, SPM/XcodeGen posture, CI runner).
- [data-model.md](data-model.md) — DeviceLoginRequest lifecycle; no schema.
- [contracts/](contracts/) — device-login REST contract; spoken-rendition wire contract.
- [quickstart.md](quickstart.md) — realm setup, backend flags, running the three targets.
- [tasks.md](tasks.md) — phased task list grouped by user story.
