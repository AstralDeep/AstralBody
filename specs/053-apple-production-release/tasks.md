---
description: "Task list for feature 053 — Apple Clients Production Release"
---

# Tasks: Apple Clients Production Release

**Input**: Design documents from `/specs/053-apple-production-release/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅ (D1–D20), data-model.md ✅, contracts/ ✅ (brand-assets, release-pipeline, build-config, compliance-and-entitlements, deployment-env, client-identity), quickstart.md ✅

**Tests**: This feature is packaging/signing/config/CI/docs — there is little executable product code. Test tasks are included ONLY where Swift/Python logic changes (the `Configuration.swift` bundle-read fallback and the watch endpoint-override resolution logic) and as the AstralCore drift-guard check; the bulk of verification is signed-build validation + per-client on-device evidence (US6), which the constitution (Principle X/XII) requires regardless.

**Organization**: Tasks are grouped by user story (US1–US8 from spec.md, priority order) so each is independently implementable and testable.

**Two structural facts (established from the working tree, per research D18/D19)**: (1) the store topology is **one** Universal Purchase App Store Connect record with **two** archives — iOS (containing the embedded watch app) and macOS — **not** three apps/listings/archives; (2) the XcodeGen generator `apple-clients/project.yml` is **retired/deleted** and the committed `AstralApp.xcodeproj` is the single canonical project (XcodeGen cannot emit the "Embed Watch Content" phase, so regenerating would silently drop the watch app).

**Operator prerequisites (blocking the live upload/submit only — not the build/config work)**: Apple Team ID; an Apple Distribution certificate + **three** App Store provisioning profiles (iOS + macOS for `com.personalailabs.astraldeep`; watchOS for `com.personalailabs.astraldeep.watch`); an App Store Connect API key (issuer id + key id + `.p8`); the single Universal Purchase App Store Connect record; and complete store-listing copy (description, keywords, support/marketing/privacy-policy URLs, age rating). The master icon artwork is **SATISFIED** (operator supplied `android-client/Android Raw Assets/AppIcon.png`, 3000×3000 fully opaque). Screenshots are **operator-assisted**: because the automation environment cannot tap/type a simulator, the operator drives each app to the screens captured in US8. See `operator-prerequisites.md` (T002).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US8; Setup/Foundational/Polish carry no story label
- Every task names an exact file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding both the config-indirection and the release pipeline depend on.

- [ ] T001 [P] Create `apple-clients/Config/Base.xcconfig`, `apple-clients/Config/Debug.xcconfig`, `apple-clients/Config/Release.xcconfig` with `ASTRAL_SERVER_BASE_URL` + `ASTRAL_KEYCLOAK_AUTHORITY` per `contracts/build-config.md` (Debug → `http://localhost:8001`; Release → `https://sandbox.ai.uky.edu` + `https://iam.ai.uky.edu/realms/Astral`), applying the `//`-in-xcconfig URL-escaping caveat.
- [ ] T002 [P] Create `specs/053-apple-production-release/operator-prerequisites.md` listing the operator-supplied inputs and the exact GitHub Actions secret NAMES (`APPLE_TEAM_ID`, `APPLE_DISTRIBUTION_CERT_P12_BASE64`, `APPLE_CERT_PASSWORD`, `APPLE_PROVISION_PROFILE_BASE64` carrying **all three** profiles (iOS, macOS, watchOS), `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8_BASE64`) — names only, never values. Record that the master icon prerequisite is satisfied and screenshots are operator-assisted.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Project wiring every downstream story builds on — including converting the watch from a watch-only app into the embedded companion the one-record store topology (D19) and the runtime override (US2) both require.

**⚠️ CRITICAL**: Complete before US1/US2/US4/US6/US8 build work.

- [ ] T003 Wire the three xcconfig files as `baseConfigurationReference` on every target × configuration in `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` (Base for shared, Debug/Release overlays), so config keys flow to the build settings.
- [ ] T004 Restore the missing shared scheme `apple-clients/AstralApp/AstralApp.xcodeproj/xcshareddata/xcschemes/AstralWatch.xcscheme` (declared shared in `xcschememanagement.plist` but absent) so clean clones and the `apple-ci.yml` `-scheme AstralWatch` leg resolve (D9, FR-014).
- [ ] T005 Convert the watch to an **embedded companion** app: in `apple-clients/AstralApp/WatchInfo.plist` remove `WKWatchOnly`, add `WKCompanionAppBundleIdentifier = com.personalailabs.astraldeep`, keep `WKApplication = YES`, and add `WKRunsIndependentlyOfCompanionApp = YES`; in `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` add an **"Embed Watch Content"** copy-files phase embedding the watch app in the iOS target (D12/D19, FR-011a). This makes the iOS archive carry the watch (SC-001) and preserves standalone install/run + QR device-login.
- [ ] T005a **Platform-filter the embed phase to iOS** (`platformFilters` on the phase's build file in `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj`; in the Xcode UI, uncheck macOS under the embedded content's "Filters"). `AstralApp` is ONE multiplatform target (`SUPPORTED_PLATFORMS = "iphoneos iphonesimulator macosx"`), so an unfiltered phase would embed a watchOS app into the **macOS** archive. Verify by archiving for macOS and confirming the product contains **no** `Watch/` directory (D20, FR-011b).
- [ ] T006 Set `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` on the **AstralWatch** target's Debug/Release build configs in `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` (currently set only on the AstralApp target), wiring the newly-created watch asset catalog so the embedded watch archive carries its own icon (D15, FR-004a).

**Checkpoint**: xcconfig plumbing present, `AstralWatch` scheme restored, the watch is an embedded companion with its icon wired — story work can begin.

---

## Phase 3: User Story 1 — App-Store-submittable signed builds (Priority: P1) 🎯 MVP

**Goal**: The **two** archives — iOS (with the embedded watch app) and macOS — each archive and pass App Store Connect upload validation with zero signing/compliance errors.

**Independent Test**: `xcodebuild archive` → `-exportArchive` (app-store) → `xcrun altool --validate-app` for each of the two archives reports no missing-icon / missing-privacy-manifest / ATS / entitlement / signing errors, no icon carries an alpha channel (ITMS-90717) while the macOS slots retain their gutter, and a unique build number is present (SC-001, SC-005a).

- [x] T007 [US1] Committed `apple-clients/Scripts/generate_app_icons.py` — stdlib Python + Apple `sips`, **zero new dependencies** (Constitution V), deriving every Apple icon from `android-client/Android Raw Assets/AppIcon.png`, with a `--check` mode asserting slot sizes, iOS/watch opacity, and macOS gutter retention (D15, FR-004/FR-030). **DONE.**
- [x] T008 [US1] Emitted the iOS/watch App Store icons and the macOS slots into `apple-clients/AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/`: `AppIcon-1024.png` + `AppIcon-1024-dark.png` (1024×1024, **no alpha**) and the ten macOS rounded-rect "squircle" slots `mac-{16,32,128,256,512}x…@{1,2}x.png` (824/1024 body, ~185.4px radius, transparent gutter — RGBA is correct here) (D15, FR-004). **DONE.**
- [x] T009 [US1] Created the new AstralWatch asset catalog `apple-clients/AstralWatch/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` + `Contents.json` (the watch target previously had **no** asset catalog at all) (D15, FR-004a). **DONE.**
- [x] T010 [US1] Rewrote `apple-clients/AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/Contents.json`. **Build-verified**: `sips` reports `hasAlpha=no` on the three 1024 icons and `hasAlpha=yes` on the macOS slots; `xcodebuild -scheme AstralApp -destination 'generic/platform=iOS Simulator' -configuration Debug` **BUILD SUCCEEDED**; `actool` emitted `AppIcon60x60@2x.png` and `AppIcon76x76@2x~ipad.png`; `Assets.car` carries phone+pad renditions in default and dark appearances (D15, FR-004). **DONE.**
- [ ] T011 [P] [US1] Create `apple-clients/AstralApp/AstralApp.entitlements` (keychain-access-groups; macOS: `com.apple.security.app-sandbox`, `com.apple.security.network.client`) per `contracts/compliance-and-entitlements.md` / D7.
- [ ] T012 [P] [US1] Create `apple-clients/AstralApp/AstralWatch.entitlements` (keychain-access-groups; **no** `com.apple.security.application-groups` — D7 excludes the App Group) per the same contract.
- [ ] T013 [US1] In `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj`: set `DEVELOPMENT_TEAM` (from CI/xcconfig, not committed), manual Apple Distribution signing for Release with **three** App Store provisioning profiles (iOS + macOS for `com.personalailabs.astraldeep`; watchOS for `…​.watch`), `CODE_SIGN_ENTITLEMENTS` per target, and (macOS) `ENABLE_APP_SANDBOX=YES` + `ENABLE_HARDENED_RUNTIME=YES` (D1/D7, FR-001/002/003).
- [ ] T014 [P] [US1] Add `apple-clients/AstralApp/PrivacyInfo.xcprivacy` — `NSPrivacyTracking=false`, honest `NSPrivacyCollectedDataTypes`, audited `NSPrivacyAccessedAPITypes` required-reason entries (D4, FR-005).
- [ ] T014a [P] [US1] Add `apple-clients/AstralWatch/PrivacyInfo.xcprivacy` and wire it into the AstralWatch target's Copy-Bundle-Resources. The embedded watch ships as its **own** `.app` bundle, so the iOS manifest does not cover it; it MUST declare the `UserDefaults` required-reason category (`CA92.1`) used to persist the endpoint override (D4/D12, FR-005).
- [ ] T015 [US1] Add watch voice usage strings (`NSSpeechRecognitionUsageDescription`, `NSMicrophoneUsageDescription`) to `apple-clients/AstralApp/WatchInfo.plist` where the dictation path exists (D4, FR-005).
- [ ] T016 [US1] Add `ITSAppUsesNonExemptEncryption=false` to `apple-clients/AstralApp/WatchInfo.plist` (already present in `Info.plist`) — export compliance consistent with the companion phone target (D4, FR-007).
- [ ] T017 [US1] Remove the unconditional `NSAllowsArbitraryLoads` from `apple-clients/AstralApp/Info.plist` and `apple-clients/AstralApp/WatchInfo.plist` so Release is ATS-clean; move the localhost exception to a Debug-only `NSAllowsLocalNetworking` (D3, FR-006). *(SC-003 is verified in US2.)*
- [ ] T018 [US1] Set `MARKETING_VERSION` (human-set release version) in `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` and confirm the archive picks up a build number (CI-run-derived stamping lands in US4) (D5, FR-008).
- [ ] T019 [US1] Run `python3 apple-clients/Scripts/generate_app_icons.py --check` to mechanically assert every slot size, iOS/watch opacity (no alpha), and macOS gutter retention before submission; record the pass in `specs/053-apple-production-release/verification/us1-icons.md` (D15, FR-004/FR-030, SC-005a).
- [ ] T020 [US1] Validate: archive the **two** targets — iOS (containing the embedded watch app) and macOS — and run `xcrun altool --validate-app` (or App Store Connect API validation) for each; record zero-error output in `specs/053-apple-production-release/verification/us1-validation.md` (SC-001). *(Live account gates the real upload; validation runs against a distribution profile.)*

**Checkpoint**: Both archives validate for App Store upload — MVP reached.

---

## Phase 4: User Story 2 — Build-time endpoint configuration (Priority: P2)

**Goal**: Release resolves the backend URL + realm from build config (default sandbox), repointable without a code edit; the watch has an **opportunistic** companion-delivered runtime override that never blocks; no dev endpoint in Release.

**Independent Test**: Inspect a Release build's resolved endpoint (from Info.plist), flip the xcconfig and rebuild to repoint, exercise the watch override with and without a companion installed (`isCompanionAppInstalled`), and `grep` Release-reachable source for `localhost`/`127.0.0.1` (expect none) (SC-003).

- [ ] T021 [US2] Surface `ASTRALServerBaseURL` + `ASTRALKeycloakAuthority` into `apple-clients/AstralApp/Info.plist` and `apple-clients/AstralApp/WatchInfo.plist` via `$(ASTRAL_SERVER_BASE_URL)` / `$(ASTRAL_KEYCLOAK_AUTHORITY)` substitution (D2, FR-009).
- [ ] T022 [US2] Rewrite `apple-clients/AstralCore/Sources/AstralCore/Configuration.swift` `serverBaseURL`/`keycloakAuthority` to read `Bundle.main.object(forInfoDictionaryKey:)` with a `sandbox.ai.uky.edu`/realm fallback (so no-bundle unit tests resolve), dropping the `#if DEBUG` hardcode (D2, FR-009/010).
- [ ] T023 [US2] Implement the watch endpoint override as an **opportunistic** WatchConnectivity path in `apple-clients/AstralWatch/WatchModel.swift` (+ a companion sender in `apple-clients/AstralApp/AstralApp/AppModel.swift`), syncing into the watch's **own** `UserDefaults` — **not** a shared App Group. The resolver MUST consult `WCSession.isCompanionAppInstalled` and fall back to the build-time (xcconfig) default when no companion is installed; it MUST NEVER block the watch (D12, FR-011).
- [ ] T024 [P] [US2] Add an AstralCore unit test in `apple-clients/AstralCore/Tests/AstralCoreTests/` asserting the `Configuration` bundle-read + sandbox fallback behavior (Constitution III for the changed Swift logic).
- [ ] T025 [P] [US2] Add a unit test for the watch override **resolution logic** — companion-installed + override present → override wins; companion absent (`isCompanionAppInstalled == false`) or no override → build-time default — in `apple-clients/AstralWatch/` (or its test target), exercising a pure resolver seam so no live `WCSession` is required (Constitution III, FR-011).
- [ ] T026 [US2] Verify no hardcoded dev endpoint is reachable in a Release build: `grep`/`strings` the Release-configured sources/binary for `localhost`/`127.0.0.1` (expect none); record in `verification/us2-endpoint.md` (SC-003).

**Checkpoint**: US1 + US2 both hold — signed builds point at the configured production endpoint; the watch falls back cleanly with no companion.

---

## Phase 5: User Story 3 — One canonical project and consistent client identity (Priority: P2)

**Goal**: Exactly one canonical Xcode project whose bundle ids, URL scheme, OAuth client ids, and shared schemes agree with the README and realm docs; no project generator remains to drift.

**Independent Test**: On a clean checkout, build every shared scheme by name (including `AstralWatch`); confirm `apple-clients/project.yml` no longer exists, the README names the committed `.xcodeproj` as canonical, and the realm docs name the code's client ids (SC-004/005).

- [ ] T027 [US3] Confirm `apple-clients/project.yml` is retired (already deleted, D18) and document the committed `apple-clients/AstralApp/AstralApp.xcodeproj` as the **single canonical project** in `apple-clients/README.md`, fixing README steps 4/6 (URL scheme + bundle id) to the shipped `com.personalailabs.astraldeep` values and removing any instruction to run `xcodegen` (FR-012/028, D18). *(The old "regenerate and diff" step is gone — there is no generator to regenerate.)*
- [ ] T028 [P] [US3] Resolve the client-id conflict in `docs/keycloak-realm-settings.md` §051 — replace `astral-ios`/`astral-macos` with the shipped `astral-mobile`/`astral-desktop`/`astral-watch`, and document that the Apple redirect `com.personalailabs.astraldeep:/oauth2redirect` is registered on the SHARED `astral-mobile` (iOS+Android) and `astral-desktop` (macOS+Windows) clients (FR-013/019).
- [ ] T029 [US3] Verify: on a clean checkout, `xcodebuild -scheme {AstralApp(iOS),AstralApp(macOS),AstralWatch}` builds each with no manual fix-up; confirm no project generator remains (`apple-clients/project.yml` absent) and the README names the committed project canonical; confirm the realm docs name the code's client ids and the watch bundle id is a strict prefix-extension of the iOS id (`…​astraldeep` → `…​astraldeep.watch`); record in `verification/us3-identity.md` (SC-004/005).

**Checkpoint**: One canonical project; every scheme builds clean; docs match code.

---

## Phase 6: User Story 8 — Store-ready brand assets and a complete listing (Priority: P2)

**Goal**: The record carries a correct icon on every platform (done in US1) and a native screenshot set for every required device class, with every supplied brand asset's reuse status recorded, so the version can actually be submitted.

**Independent Test**: The icon self-check passes (US1 T019); a screenshot set exists at exactly one accepted pixel size per required class (iPhone 6.9", iPad 13", Mac, Apple Watch), each showing the real Apple app **in use** (Guideline 2.3.3); the reuse status of every supplied asset is recorded; and the App Store Connect listing is complete (SC-005b, FR-031/032/015a).

- [ ] T030 [US8] Record the brand-asset reuse mapping (usable / reference-only / not transferable) in `specs/053-apple-production-release/verification/us8-brand-assets.md` per research D17 — `AppIcon.png` usable (icon master); `feature-graphic.png` **not transferable** (Google-Play-only, no App Store analogue); the `*x*.png` desktop renders and `phone-*`/`tablet*-*` renders **reference-only** (wrong aspect ratio for every Apple class) — so no asset is silently ignored or wrongly shipped (FR-032).
- [ ] T031 [P] [US8] Capture iPhone 6.9" screenshots (operator-assisted, via `xcrun simctl io <device> screenshot`) at exactly one accepted size (1260×2736 | 1290×2796 | 1320×2868; landscape swaps W/H), depicting the app in use, then composite AstralDeep brand/caption overlays; store under `specs/053-apple-production-release/screenshots/iphone-6.9/` (FR-031, SC-005b).
- [ ] T032 [P] [US8] Capture iPad 13" screenshots at one accepted size (2048×2732 | 2064×2752), app in use, + overlays; store under `specs/053-apple-production-release/screenshots/ipad-13/` (FR-031, SC-005b).
- [ ] T033 [P] [US8] Capture Mac screenshots (window capture) at one accepted 16:10 size (1280×800 | 1440×900 | 2560×1600 | 2880×1800), app in use, + overlays; store under `specs/053-apple-production-release/screenshots/mac/` (FR-031, SC-005b).
- [ ] T034 [P] [US8] Capture Apple Watch screenshots at exactly one accepted size (422×514 | 416×496 | 410×502 | 396×484 | 368×448 | 312×390) — the **same** size across all localizations — app in use, + overlays; store under `specs/053-apple-production-release/screenshots/watch/` (FR-031, SC-005b).
- [ ] T035 [US8] Assemble the complete App Store Connect listing for the single Universal Purchase record from operator metadata — app name, description, keywords, support/marketing URLs, the screenshots for each required class (T031–T034), privacy-policy URL, age rating, and export-compliance answer — and record listing completeness in `specs/053-apple-production-release/verification/us8-listing.md` (FR-015a).

**Checkpoint**: Icons validated, native screenshots captured per class, listing complete — the record can be submitted.

---

## Phase 7: User Story 4 — Signed release pipeline that submits to review (Priority: P2)

**Goal**: A tag push archives, exports, uploads the **two** platform builds into the **single** Universal Purchase record, and submits the version **once** for review via CI secrets, without disturbing existing gates.

**Independent Test**: Tag-push (or `workflow_dispatch`) runs the workflow through archive→export→validate→upload (both builds)→submit-once (validate/dry-run where creds absent); the six backend gates + `apple-ci.yml` stay green; gitleaks finds no secret (SC-006).

- [ ] T036 [US4] Create `.github/workflows/apple-release.yml` per `contracts/release-pipeline.md`: `on: push tags ['apple-v*']` (the non-`v` prefix keeps `release-windows.yml`'s `v*` filter from double-firing) + `workflow_dispatch`, `runs-on: macos-15`, ordered steps (checkout → select Xcode → import cert + **all three** App Store profiles (iOS, macOS, watchOS) into a temp keychain → archive the **two** targets [iOS-with-embedded-watch, macOS] → `-exportArchive` app-store → `altool --validate-app` → `--upload-app` **both** builds into the single record → **one** submit-for-review → always-cleanup), **no `notarytool` step**, failing clearly (without an unsigned artifact or leaked secret) on missing signing material (D6/D14/D19, FR-015/017).
- [ ] T037 [P] [US4] Add per-platform export options — `apple-clients/ExportOptions-ios.plist` and `apple-clients/ExportOptions-macos.plist` (`method = app-store`, team id, manual signing, the App Store profiles for the relevant bundle ids) — referenced by `-exportArchive` (FR-015).
- [ ] T038 [US4] Add the tag-vs-`MARKETING_VERSION` guard step to `.github/workflows/apple-release.yml` (mirroring `release-windows.yml`'s tag-vs-`__version__` check) so a mislabeled tag fails fast (D5/D14).
- [ ] T039 [US4] Implement CI-run-derived build-number stamping in `.github/workflows/apple-release.yml` (`agvtool new-version -all "$GITHUB_RUN_NUMBER"` or archive-time override) so successive archives never collide (D5, FR-008).
- [ ] T040 [US4] Verify additivity: confirm `ci.yml` (six gates) and `apple-ci.yml` are unchanged and green, release/verification failures are distinguishable, and gitleaks passes (no secret committed); record in `verification/us4-pipeline.md` (FR-016/017, SC-006).

**Checkpoint**: Reproducible signed release wired — two builds into one record, submitted once; existing CI intact.

---

## Phase 8: User Story 5 — Verified backend & `.env` production posture (Priority: P3)

**Goal**: The backend the clients target is production-correct and fail-closed.

**Independent Test**: `.env` passes the production checklist; realm well-known advertises the device endpoint; production-posture boot exits 78 on a placeholder secret; drift guard 47/35/67 matches the baked astralprims (SC per US5).

- [ ] T041 [P] [US5] Fix the `.env.example` `KEYCLOAK_ALLOWED_AZP` comment (lines ~149–153) to name `astral-mobile`/`astral-desktop`/`astral-watch` (not `astral-ios`/`astral-macos`), matching shipped code (D8/D10, FR-018).
- [ ] T042 [US5] Add an Apple-production `.env` + realm checklist to `docs/production-deployment.md` per `contracts/deployment-env.md` (ASTRAL_ENV, USE_MOCK_AUTH=false, AZP set, KEYCLOAK_DEVICE_CLIENTS, FF_DEVICE_LOGIN/FF_LLM_STREAMING, secrets set, FORWARDED_ALLOW_IPS, DB_POOL_MAX×processes < max_connections) (FR-018/028).
- [ ] T043 [US5] Verify the deployment `.env` against the checklist (secrets set to real high-entropy values, pool sizing within Postgres limits) and that a production-posture boot with a placeholder secret exits 78; record in `verification/us5-env.md` (no secret values) (FR-021).
- [ ] T044 [P] [US5] Confirm (operator/realm) the realm well-known advertises `device_authorization_endpoint`, `astral-watch` has the device grant enabled, and `com.personalailabs.astraldeep:/oauth2redirect` is a Valid Redirect URI on `astral-mobile` + `astral-desktop`; record status in `verification/us5-realm.md` (FR-019).
- [ ] T045 [US5] Confirm the production image's resolved `astralprims` wheel yields the 35 component types the drift guard asserts (47/35/67); pin `backend/requirements.txt` explicitly only if the resolved wheel differs (D11, FR-020/025).

**Checkpoint**: Backend posture verified; watch QR + streaming preconditions confirmed.

---

## Phase 9: User Story 6 — End-to-end verification on signed builds (Priority: P3)

**Goal**: Evidence that every signed client works on its device family and stays consistent with the other clients.

**Independent Test**: Install signed builds; capture PKCE sign-in, keychain persistence across reinstall, watch QR device-login, live `FF_LLM_STREAMING` narrative render on iOS/macOS/watch, and the watch no-companion override fallback; complete 051 T046/T041 (SC-002/007/008/009).

- [ ] T046 [US6] Verify signed iOS + macOS builds: PKCE sign-in succeeds and the session persists across an app reinstall; capture in `specs/053-apple-production-release/verification/us6-signin.md` (SC-002/009).
- [ ] T047 [US6] Verify a signed watch build: QR device-login completes end-to-end; capture in `verification/us6-watch-qr.md` (SC-008).
- [ ] T048 [US6] Verify live narrative streaming (`FF_LLM_STREAMING=true`) renders coherently on iOS, macOS, and watchOS and is superseded by the final render, and matches web/Windows/Android; capture in `verification/us6-streaming.md` (D13, FR-023, SC-007). *(Fix + add a regression test if a defect surfaces.)*
- [ ] T049 [P] [US6] Complete the outstanding 051 evidence — round-trip p95 timing (051 T046, inheriting the 051 target) and the browser short-code device-login path (051 T041); capture in `verification/us6-051-evidence.md` (FR-024).
- [ ] T050 [US6] Verify the watch server-override on-device against the live backend: with the iPhone companion installed, set an override and confirm the watch retargets **without a rebuild**; with **no** companion installed (`isCompanionAppInstalled == false`), confirm the watch falls back to the sandbox default and stays fully usable via QR device-login; capture in `verification/us6-watch-override.md` (FR-011, US2 acceptance #3/#4, Constitution X — a UI change must be exercised on every affected client, not just grepped).
- [ ] T051 [P] [US6] Confirm the AstralCore drift guard (`ManifestDriftTests.swift`, 47/35/67) is green (`swift test --package-path apple-clients/AstralCore`) — extended, not forked (FR-025).

**Checkpoint**: All clients verified on signed builds and consistent.

---

## Phase 10: User Story 7 — Updated knowledge base (Priority: P3)

**Goal**: The Obsidian vault + repo docs record the shipped release process with all doc-vs-code conflicts resolved.

**Independent Test**: Vault lint passes; the release-pipeline page exists; affected pages revised; anchor commit bumped; README/realm-doc match code (SC-010).

- [ ] T052 [US7] Create `../obsidian-vault/wiki/entities/Apple Release Pipeline.md` (signing, xcconfig endpoint config, icon generator + `--check`, embedded-companion watch, one-record store topology, App Store submission flow, `apple-release.yml`, secrets) per the vault CLAUDE.md schema (frontmatter, lead, `## Sources` → `[[astralbody-repo]]`, wikilinks) (FR-029).
- [ ] T053 [P] [US7] Revise `../obsidian-vault/wiki/entities/Apple Clients.md` (retire "legacy keychain until real signing exists"; add signed/MAS/entitlements/privacy-manifest/embedded-companion-watch state) and clear the client-id `> Conflicts with` block on `../obsidian-vault/wiki/entities/Keycloak Realm Astral.md` (FR-029).
- [ ] T054 [P] [US7] Revise `../obsidian-vault/wiki/concepts/CI Gates.md` (add `apple-release.yml`), `Feature Flags.md` (reconcile `FF_DEVICE_LOGIN` state), `Feature Timeline.md` (add 053), and fix the stale `../obsidian-vault/wiki/entities/AstralBody.md` hub "Current state" commit (FR-029).
- [ ] T055 [US7] Bump `../obsidian-vault/wiki/sources/astralbody-repo.md` reviewed_commit to the 053 merge commit; append a `## [2026-07-08] update | 053 apple production release` entry to `../obsidian-vault/log.md`; update `../obsidian-vault/index.md`; run the vault LINT (SC-010).
- [ ] T056 [US7] Update `apple-clients/README.md` (signing + release runbook) and retire the KNOWN-ISSUES #2 "legacy keychain" note in `apple-clients/KNOWN-ISSUES.md` now that signing is real (FR-028).

**Checkpoint**: Knowledge captured; no unresolved doc-vs-code conflict.

---

## Phase 11: Polish & Cross-Cutting Concerns

- [ ] T057 Run the full `quickstart.md` validation runbook end-to-end and reconcile any gaps.
- [ ] T058 [P] Add a step to `.github/workflows/apple-ci.yml` running `python3 apple-clients/Scripts/generate_app_icons.py --check` so an icon regression (wrong slot size, iOS/watch alpha, lost macOS gutter) fails CI before submission (FR-004/FR-030, SC-005a).
- [ ] T059 [P] Confirm zero new third-party runtime deps (Swift package graph unchanged; `generate_app_icons.py` is stdlib + `sips`; `backend/requirements.txt` no additions) and note it in the PR (Constitution V, FR-026, SC-011).
- [ ] T060 [P] Final Constitution compliance pass (I–XIII), emphasizing X (no hardcoded endpoint, per-client verification incl. the watch no-companion fallback), XI (release workflow additive), XII (drift guard green, parity) — record in the PR description.
- [ ] T061 Confirm no schema change shipped (data-model.md "no migration"); if any arose, verify it is an idempotent guarded `_init_db` delta with rollback (Constitution IX, FR-027).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately.
- **Foundational (Phase 2)**: after Setup; T003 (xcconfig wiring) blocks US1 versioning + US2 endpoint; T004 (watch scheme) blocks any watch build; T005 (embedded-companion conversion) blocks the iOS-with-embedded-watch archive (US1/US4) and the companion override (US2); T006 (watch appicon setting) blocks the watch icon in the archive (US1).
- **US1 (Phase 3, P1)**: after Foundational — the MVP. Icon generation (T007–T010) is already **done**; remaining tasks are entitlements/signing/compliance/validation.
- **US2 (Phase 4, P2)**: after Foundational (T003 endpoint wiring, T005 companion conversion); largely independent of US1 build work.
- **US3 (Phase 5, P2)**: after Foundational; independent of US1/US2 (docs + verification only — the generator is already retired).
- **US8 (Phase 6, P2)**: icon half depends on US1 (T019 self-check); screenshots need a runnable app (dev/simulator builds suffice) + the icon; the listing (T035) feeds US4's submission.
- **US4 (Phase 7, P2)**: after US1 signing (T013) and the US8 listing (T035) exist; ExportOptions/guard/build-number are internal to the workflow.
- **US5 (Phase 8, P3)**: independent (backend/docs) — can start anytime after Setup.
- **US6 (Phase 9, P3)**: after US1 (signed builds) + US2 (endpoint + companion override) + US5 (backend posture) so on-device flows work.
- **US7 (Phase 10, P3)**: after the work it documents (US1–US6, US8) is substantially done.
- **Polish (Phase 11)**: after all desired stories.

### Parallel Opportunities

- Setup T001 ∥ T002.
- Within US1: T011 ∥ T012 ∥ T014 (different files) around T013; T015–T019 after their plists/assets exist.
- Within US2: T024 ∥ T025 (different test files).
- US2, US3, US5 can run concurrently once Foundational is done (different file sets: Swift/plist vs README/realm docs vs .env/backend).
- Within US8: T031 ∥ T032 ∥ T033 ∥ T034 (different screenshot classes/directories) before T035.
- Within US4: T037 (ExportOptions plists) ∥ the workflow authoring (T038/T039 are sequential edits to the one workflow file).
- US5 T041 ∥ T044 (`.env.example` vs realm verification file).
- US7 revisions T053 ∥ T054 (different vault pages).
- Polish T058 ∥ T059 ∥ T060.

### MVP Scope

**US1 only** (Phases 1–3): the **two** signed archives — iOS (with the embedded watch app) and macOS — that pass App Store upload validation, with opaque iOS/watch icons and gutter-retaining macOS slots. Stop-and-validate at T020 before proceeding.

---

## Implementation Strategy

1. **MVP**: Setup → Foundational (incl. the embedded-companion conversion) → US1 → validate the two archives (T020). Demonstrable: submittable signed builds.
2. **Correctness & reproducibility**: add US2 (config indirection + opportunistic watch override) + US3 (one canonical project, identity/doc alignment) so the signed build points at prod and clean clones stay working.
3. **Brand assets & listing**: US8 records the reuse mapping, captures native screenshots per required class, and assembles the complete store listing.
4. **Automation**: US4 wires the signed release — two builds into one Universal Purchase record, submitted once.
5. **Backend + verification**: US5 verifies `.env`/realm posture; US6 proves every client on-device (including the watch no-companion fallback) and consistent.
6. **Knowledge**: US7 records it all and resolves the doc-vs-code conflicts.
7. **Live submission** (operator-gated): once Team ID, certs + **three** App Store profiles (iOS, macOS, watchOS), the ASC record + API key, and store metadata are in hand, tag `apple-v*` to run the pipeline through the real upload of both builds + one submit-for-review.

## Notes

- `[P]` = different files, no incomplete-task dependency.
- No DB schema change (data-model.md); rollback = revert the PR (config/CI/docs only).
- Zero new third-party runtime dependencies (Swift or backend) — Constitution V; `generate_app_icons.py` is stdlib Python + the Apple `sips` tool.
- Verification evidence lives under `specs/053-apple-production-release/verification/`; screenshots under `specs/053-apple-production-release/screenshots/`, mirroring 051.
- Never commit signing secrets; they are CI-injected at runtime (gitleaks gate).
