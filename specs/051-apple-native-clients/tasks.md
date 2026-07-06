---
description: "Task list for 051-apple-native-clients"
---

# Tasks: Native Apple Clients (iOS, macOS, watchOS SDUI Targets)

**Input**: Design documents from `specs/051-apple-native-clients/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution III (test-first for backend logic; ≥90% changed-line
coverage) and FR-038 (Swift drift guards). Backend unit tests are DB-free where the logic is
pure; suite-integrated tests run in the `astralbody` container.

**Organization**: Setup → Foundational (blocking) → US1..US6 → Polish. Paths per plan.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1–US6 (setup/foundational/polish unlabeled)

---

## Phase 1: Setup

- [X] T001 Scaffold `apple-clients/` (README.md with canonical manual-Xcode setup + optional
      XcodeGen note, `project.yml`, directory layout per plan.md).
- [X] T002 [P] `apple-clients/AstralCore/Package.swift` — SPM package, platforms iOS 17 /
      macOS 14 / watchOS 10, zero dependencies, test target.
- [X] T003 [P] `.github/workflows/apple-ci.yml` — macOS runner, `swift test` for AstralCore
      (app-build job added in T052).
- [X] T004 [P] `.env.example` — `FF_DEVICE_LOGIN`, extended `KEYCLOAK_ALLOWED_AZP` sample
      (`astral-ios,astral-macos,astral-watch`).
- [X] T005 [P] `docs/keycloak-realm-settings.md` — device-grant enablement on `astral-watch`,
      new public clients + redirect URIs, azp allow-list, 365-day session-max mapping (D7).

## Phase 2: Foundational (Blocking Prerequisites)

**Backend**

- [X] T006 [P] Tests first: `backend/tests/test_apple_profiles.py` — `ios`/`macos` named
      profiles derive full-capability (no viewport downgrade), `supported_types` negotiation,
      watch profile unchanged.
- [X] T007 `backend/rote/capabilities.py` — `DeviceType.IOS`/`MACOS` + host-config entries
      (041 `android` pattern). Green T006.
- [X] T008 [P] Tests first: `backend/tests/test_qr.py` — known-answer matrices (frozen from
      reference-encoder cross-check), structural invariants (size, finder/timing/format info),
      PNG validity (header/IHDR/CRC), payload range V1–V10.
- [X] T009 `backend/shared/qr.py` — first-party QR Model 2 byte-mode encoder (ECC M, GF(256)
      Reed–Solomon, standard format-info table) + stdlib PNG writer + `qr_matrix()` accessor.
      Green T008.
- [X] T010 [P] Tests first: `backend/tests/test_device_login.py` — broker state machine with
      injected fake IdP: start (payload shape, unknown client, flag off, IdP missing
      device endpoint ⇒ 503), poll (pending/slow_down local enforcement/approved-once/denied/
      expired/invalid handle), role gate (roleless ⇒ denied_no_access + revocation call),
      rate limiting, handle single-use + TTL, no token logging.
- [X] T011 `backend/orchestrator/device_login.py` — RFC 8628 broker per
      contracts/device-login.md (`FF_DEVICE_LOGIN` fail-closed, well-known discovery, Fernet
      handle over web-session key, in-memory rate buckets, audit events). Green T010.
- [X] T012 Route wiring: `POST /api/auth/device/{start,poll,refresh}` registered alongside the
      existing `/api/auth/logout` (`backend/orchestrator/web_auth.py` / api router), audit
      `auth.device_login_*` actions emitted.
- [X] T013 [P] Tests first: `backend/tests/test_watch_speech.py` — `speech` attachment helper:
      SSML + text from adapted components via the `voice` target, absent when unspeakable,
      bounds respected; send-path predicate (watch-profile sockets only).
- [X] T014 Speech helper (`backend/orchestrator/watch_speech.py` or colocated in webrender):
      `build_speech(components) -> {"ssml","text"} | None`. Green T013 (helper portion).
- [ ] T015 Orchestrator send-path: attach `speech` to `ui_render`/`ui_upsert` for
      watch-profile sockets (per-socket adaptation point), per
      contracts/spoken-rendition.md; full container suite green.

**AstralCore (Swift)**

- [X] T016 [P] `Sources/AstralCore/Protocol/` — `Frames.swift` (47 push types: typed decode
      for handled frames, `.unknown` passthrough), `Components.swift` (35-type component
      model + fallback), `Manifest.swift`; `Tests/AstralCoreTests/ManifestDriftTests.swift`
      reading `backend/shared/ui_protocol.json` (FR-038).
- [X] T017 [P] `Sources/AstralCore/Transport/WSClient.swift` — URLSession WebSocket,
      register_ui device payloads, backoff 1 s ×2 → 30 s cap, 64-frame bounded FIFO queue
      with drop signal; unit tests for queue/backoff math.
- [X] T018 [P] `Sources/AstralCore/Auth/PKCE.swift` — verifier/challenge (S256, CryptoKit),
      authorize-URL builder, token exchange/refresh via URLSession; unit tests (RFC 7636
      test vector).
- [X] T019 [P] `Sources/AstralCore/Auth/DeviceLogin.swift` — start/poll/refresh client with
      state machine mirroring the contract (interval + slow_down honoring); unit tests
      against a stubbed transport.
- [X] T020 [P] `Sources/AstralCore/Auth/TokenStore.swift` + `Session.swift` — Keychain-backed
      store (protocol-abstracted for tests), silent refresh, `auth_required` handling hooks.
- [X] T021 [P] `Sources/AstralCore/API/Rest.swift` — chats list/detail, new chat, logout
      (`client_id` attribution), attachment upload.

**Checkpoint**: backend units green in container; `swift test` green; no story work before
this line.

## Phase 3: US1 — iOS daily chat loop (P1)

- [X] T022 [US1] `AstralApp/` app entry + navigation shell (SwiftUI multiplatform; iOS
      presentation) with server-address config + sign-in screen
      (ASWebAuthenticationSession + PKCE, `astral-ios`).
- [X] T023 [US1] Chat list screen (REST paginated, open/delete, pull-to-refresh).
- [X] T024 [US1] Chat canvas: transcript rendering, `ui_stream_data` terminal semantics,
      progress signals, `user_message_acked`.
- [ ] T025 [US1] Component renderer dispatch (all 35 types: native views for the core set,
      documented fallback view for the rest — parity dispositions recorded as implemented).
- [ ] T026 [US1] `ui_upsert` op application preserving scroll; `component_action` round trip
      (table pagination).
- [ ] T027 [P] [US1] Attachments: document/photo pickers, staged chips, upload,
      `parser_status` surfacing.
- [ ] T028 [P] [US1] Chrome menu (agents/settings/theme), agent permission toggles.
- [ ] T029 [P] [US1] Error/`stream_error` banners; reconnect status UI; `resumed` register
      flag; sign-out → logout endpoint + keychain wipe.
- [ ] T030 [US1] iPad adaptivity (viewport reporting via device-update on size change).

## Phase 4: US2 — macOS desktop twin (P2 ordering; P1 priority)

- [X] T031 [US2] macOS window anatomy: top bar (identity/status/new-chat/search), chat rail,
      canvas (reuses US1 renderer).
- [X] T032 [US2] PKCE via ASWebAuthenticationSession (`astral-macos`); session persistence
      across restarts.
- [ ] T033 [P] [US2] Attachments via file dialog + drag-and-drop with `parser_status` chips.
- [ ] T034 [P] [US2] Table pagination; live theme restyle without restart.
- [ ] T035 [P] [US2] Image rendering; chart-family rendering (raster acceptable).
- [ ] T036 [US2] Transcript/workspace re-hydration parity with Windows (`load_chat`).

## Phase 5: US3 — watch QR sign-in (P2)

- [X] T037 [US3] `AstralWatch/` app entry; signed-out screen: QR (backend PNG; matrix
      re-render optional), short code, expiry countdown.
- [X] T038 [US3] Poll loop honoring interval/slow_down; auto-rotate before expiry; approved ⇒
      token store + signed-in transition.
- [X] T039 [P] [US3] Failure states: denied / denied_no_access / expired / 503 unavailable —
      friendly retry UI, no partial sessions.
- [X] T040 [P] [US3] Signed-in identity display + one-tap sign-out (logout endpoint,
      `client_id=astral-watch`, wipe, return to QR).
- [ ] T041 [US3] Live demo evidence: phone-camera scan path + browser short-code path
      (quickstart § watch sign-in).

## Phase 6: US4 — watch conversation, voice in, speech out (P2)

- [X] T042 [US4] Watch home: one-tap new conversation; bounded recents list.
- [X] T043 [US4] Dictation-first input (TextFieldLink; scribble/keyboard fallback) with
      confirm-before-send.
- [X] T044 [US4] Watch chat view: crown-scrollable adapted components + narrative.
- [X] T045 [US4] `Speaker` (AVSpeechSynthesizer): speak `speech.ssml`→`text` fallback on
      arrival, stop/replay controls, stop-on-navigate, silent/DND respect, never re-speak a
      turn (last-spoken tracking).
- [ ] T046 [US4] Round-trip timing check vs SC-005/SC-006.

## Phase 7: US5 — degradation guarantees (P2)

- [X] T047 [US5] Backend sweep test: all 35 component types (+ nested layouts) through a
      watch-profile socket ⇒ non-empty bounded visual output + non-empty `speech` where
      speakable, zero errors (extends test_watch_speech.py or new test_watch_sweep.py).
- [X] T048 [P] [US5] Watch fallback UX: read-only summary + "continue on another device"
      affordance for over-budget interactivity; text-cap notice.
- [ ] T049 [P] [US5] Attachment name-chips (read-only) on watch turns.

## Phase 8: US6 — evidence & drift guards (P3)

- [ ] T050 [US6] Extend `specs/044-native-client-parity/parity-matrix.md` with iOS/macOS/watch
      columns (every push type + component type dispositioned).
- [ ] T051 [US6] Verification bundle under `specs/051-apple-native-clients/verification/`
      (legible captures: iOS sim, macOS app, watch sim; 044 conventions).
- [ ] T052 [US6] `apple-ci.yml` app-build job (xcodebuild for the three targets) once the
      project file exists on runners.

## Phase 9: Polish

- [ ] T053 [P] Accessibility: VoiceOver labels (iOS/macOS), watch Dynamic Type within profile
      bounds (FR-041).
- [ ] T054 [P] `docs/production-deployment.md` — Apple client + device-login operational
      notes.
- [X] T055 [P] `apple-clients/KNOWN-ISSUES.md` (041 convention).
- [ ] T056 Full container suite + ruff green; diff-cover ≥90% on changed lines; Constitution V
      toolchain approval recorded in PR notes.

## Dependencies

- Phase 2 blocks all stories. T007←T006, T009←T008, T011←T010, T014/T015←T013, T012←T011,
  T015←T014.
- US1 renderer (T025) is reused by US2 (T031) and informs watch fallbacks (T048).
- US3 blocks US4 runtime testing (needs a signed-in watch).
- T052 depends on the Xcode project existing (T001 canonical steps executed on the Mac).
