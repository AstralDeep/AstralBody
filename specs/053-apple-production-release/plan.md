# Implementation Plan: Apple Clients Production Release

**Branch**: `053-apple-production-release` | **Date**: 2026-07-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/053-apple-production-release/spec.md`

## Summary

Take the feature-051 Apple clients (iOS, macOS, watchOS) from dev-verified/unsigned to a real **public App Store submission**, consistent across all clients. The work is almost entirely Xcode project configuration, App Store compliance artifacts, build-time endpoint indirection, cross-client identity reconciliation, a signed release workflow, a verified backend `.env`/realm posture, on-device verification, and knowledge capture — with **zero product-code stubs** and **zero new runtime dependencies**. The backend server→client contract is byte-identical since 051 (drift guard 47/35/67), so no wire/schema change is required; the only client-observable backend change (`FF_LLM_STREAMING` narrative frames) is already dispositioned and must be verified rendering on-device.

Two structural facts (verified against the working tree) shape the packaging. **(1) Store topology is one record, not three.** The iOS and macOS targets share bundle id `com.personalailabs.astraldeep`, so they must be a single Universal Purchase App Store Connect record with two platform versions; the watch app is converted from a watch-only app into an **embedded companion** shipped inside the iOS build. Net: **one record, one listing, two archives** (iOS-with-embedded-watch, macOS), two uploads, one submission. **(2) Brand assets are supplied and already generated.** The operator supplied `android-client/Android Raw Assets/`; its 3000×3000 opaque `AppIcon.png` is the master from which every Apple icon is derived by the committed, dependency-free `apple-clients/Scripts/generate_app_icons.py` (stdlib Python + Apple `sips`) — the emitted catalogs are on disk and build-verified. No Android screenshot transfers (each mismatches Apple's aspect ratios; Guideline 2.3.3 requires the real app in use), so screenshots are captured natively with brand overlays.

Approach, per the 2026-07-08 clarifications: distribution = **public App Store** (macOS via the **Mac App Store**, so App Sandbox + Hardened Runtime); endpoint = **build-time xcconfig indirection** defaulting to `sandbox.ai.uky.edu`; identities = **keep shipped** `astral-mobile`/`astral-desktop`/`astral-watch` + bundle `com.personalailabs.astraldeep`. The XcodeGen generator (`apple-clients/project.yml`) is **retired** — it had drifted and cannot emit the "Embed Watch Content" phase the companion watch app requires, so the committed `.xcodeproj` becomes the single canonical project (documented in the README). A tag-triggered **`apple-release.yml`** mirroring `release-windows.yml` performs archive→export(app-store)→upload→submit via `xcrun` tooling + an App Store Connect API key (no fastlane); `FF_DEVICE_LOGIN` and `FF_LLM_STREAMING` stay ON. The live upload/submit step is gated on operator-supplied signing material (distribution cert + three App Store profiles — iOS + macOS (`com.personalailabs.astraldeep`) and watchOS (`…​.watch`)), the App Store Connect record + API key, and store-listing metadata + native screenshot capture (blocking prerequisites); the icon-artwork prerequisite is now **satisfied**, and all other work proceeds in parallel.

## Technical Context

**Language/Version**: Swift 5.9+ (client, iOS 17 / macOS 14 / watchOS 10 targets; Xcode 16+, project objectVersion 77); Python 3.11 (backend, no expected code change); YAML (GitHub Actions); Markdown (docs + vault). Static config: `.xcconfig`, `Info.plist`, `.entitlements`, `PrivacyInfo.xcprivacy`, `.env`.

**Primary Dependencies**: Existing only — the zero-third-party-dep `AstralCore`/`AstralPrims` SwiftPM package; Apple toolchain (`xcodebuild`, `xcrun altool`/Transporter, `sips` + stdlib Python for `Scripts/generate_app_icons.py`, `xcrun simctl io … screenshot` for native captures, `codesign`, `actool`, `security`); existing backend (FastAPI, Keycloak, `astralprims`). The committed icon generator is **stdlib Python + Apple `sips` only — zero new dependencies** (Constitution V). **No new third-party runtime library**; no fastlane; no `notarytool` (App Store distribution, not Developer-ID).

**Storage**: N/A — no database schema change. Client token storage is the existing Keychain. Signing material lives only in CI secrets at runtime.

**Testing**: `swift test` (AstralCore incl. the `ui_protocol.json` drift guard, plus a new test for the opportunistic `WatchConnectivity`/`isCompanionAppInstalled` fallback); `generate_app_icons.py --check` (slot sizes, iOS/watch opacity, macOS gutter); **two** archives — iOS (with the embedded watch app) and macOS — each `xcodebuild` archive + `xcrun altool --validate-app` (or App Store Connect API validation), uploaded into the **single** Universal Purchase record; existing backend `pytest` suites (unchanged); manual, operator-assisted on-device verification per client incl. the no-companion fallback (Constitution X/XII); the six backend CI gates untouched.

**Target Platform**: iOS 17+ (with embedded watchOS 10+ companion), macOS 14+ (Mac App Store); one Universal Purchase App Store Connect record, two platform builds; backend at `sandbox.ai.uky.edu` (realm `iam.ai.uky.edu/realms/Astral`).

**Project Type**: Native multi-platform Apple client (SwiftUI SDUI) + additive CI/CD + config/docs; server-driven UI backend unchanged.

**Performance Goals**: No new runtime performance target. US6 inherits the 051 round-trip p95 target for the timing evidence. Signed archives must validate and upload within the release workflow's `timeout-minutes` budget.

**Constraints**: Zero new runtime dependencies (Swift + backend); Keycloak-only auth; fail-closed feature flags; no hardcoded endpoints reachable in Release; secrets never committed or baked into an image; cross-client SDUI parity preserved (manifest + drift guards green, extended not forked); idempotent guarded `_init_db` migration IF any schema change arises (none anticipated).

**Scale/Scope**: 3 Apple apps (iOS + embedded watchOS companion, macOS) from one canonical Xcode project + one SwiftPM package, shipping as **one** App Store Connect record via **two** archives; ~1 new CI workflow; edits to `Configuration.swift`, `Info.plist`, `WatchInfo.plist` (watch-only→companion conversion), `project.pbxproj` (Embed Watch Content phase, watch app-icon name, signing/versioning), new `.xcconfig`/`.entitlements`/`PrivacyInfo.xcprivacy`, a new watch asset catalog, the already-generated icon PNGs, README, the watch `WatchConnectivity` server-override path; the retirement (deletion) of `project.yml`; `.env.example` + `docs/keycloak-realm-settings.md` + `docs/production-deployment.md`; ~7 obsidian-vault pages. **Icon artwork prerequisite satisfied** (operator-supplied master, icons generated + build-verified). Operator still provides: Apple Team ID + distribution cert + three App Store profiles (iOS, macOS, watchOS) + App Store Connect record + API key, store-listing metadata, and driving the simulators for native screenshot capture.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I (Python backend)**: ✅ No backend language change; backend edits (if any) stay Python. Client is Swift, already sanctioned by feature 051 under Principle XII (native ROTE-target clients).
- **II (SDUI: astralprims defines → orchestrator renders → ROTE adapts)**: ✅ Unchanged. Apple clients remain thin consumers of the server-driven contract; no primitive/renderer change; the `AstralPrims` Swift mirror stays a consumer of the published vocabulary.
- **III (Testing ≥90% changed-code)**: ✅ Changed *code* is minimal (Swift config + the watch `WatchConnectivity`/`isCompanionAppInstalled` override-and-fallback path + optional backend touch). The new override logic is changed Swift logic and carries a unit test asserting it consults `isCompanionAppInstalled` and falls back to the build-time default when no companion is present. Config/plist/entitlements/pbxproj/icon-PNGs/CI-YAML/docs are not executable coverage lines; any other changed Swift/Python logic carries tests. Backend diff-cover gate honored if backend is touched.
- **IV (Code quality/lint)**: ✅ Swift follows existing style; any backend edit passes ruff-from-root; YAML validated.
- **V (No new third-party deps)**: ✅ **Zero** new runtime deps. Signing/upload uses the Apple toolchain (`xcrun`), not fastlane; the committed icon generator (`Scripts/generate_app_icons.py`) is **stdlib Python + Apple `sips` only**, adding no dependency; icons/manifests/entitlements are config/assets, not deps. Documented in PR.
- **VI (Documentation)**: ✅ New xcconfig keys, entitlements, privacy manifest, and the release process are documented (README + docs + vault); no undocumented public API.
- **VII (Security: Keycloak-only, fail-closed, secrets)**: ✅ Auth stays Keycloak PKCE + RFC 8628 device grant; `FF_DEVICE_LOGIN` fail-closed default preserved; **all signing secrets are CI-injected at runtime, never committed** (gitleaks gate enforces); no new auth provider.
- **VIII (UX/design language)**: ✅ No new primitives; consistent design language preserved across clients.
- **IX (DB migrations)**: ✅ **No schema change anticipated.** If one arises it ships as an idempotent guarded `_init_db` delta with documented rollback (none expected — see data-model.md).
- **X (Production readiness: no stubs, no hardcoded localhost, per-client verification)**: ✅ This feature *removes* the hardcoded endpoint smell (FR-009/010), and verifies every client end-to-end on signed builds (FR-022/023, US6) against the live backend — including the watch's **no-companion fallback** (the override is opportunistic, never a dependency; the watch stays fully usable via QR device-login with no phone app installed) — exactly Principle X's bar. No stub/TODO-without-issue.
- **XI (CI six gates + additive release publish)**: ✅ `apple-release.yml` is **additive** (mirrors `release-windows.yml` / `android-ci.yml` precedent); the six backend gates in `ci.yml` are **untouched**; `apple-ci.yml` gains exactly one additive step (`generate_app_icons.py --check`) and its existing compile matrix is unchanged. Release-workflow failures are distinguishable from verification gates (FR-016).
- **XII (Cross-client consistency incl. theme + layout parity, manifest + drift guards)**: ✅ The `ui_protocol.json` drift guard (47/35/67) stays green and is *extended not forked* if vocabulary ever changes (FR-025); no client forks palette/layout; the Apple family stays a faithful ROTE target. Streaming parity across web/Windows/Android/Apple is explicitly verified (SC-007).
- **XIII (Docs/research integrity)**: ✅ The vault + docs updates trace claims to the code as merged (client-id reconciliation resolves a real doc-vs-code conflict rather than asserting an unverified one).

**Result**: PASS. No violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/053-apple-production-release/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — signing, xcconfig, ATS, privacy manifest, App-Store-vs-notarize, build-number, .env, astralprims, watch override
├── data-model.md        # Phase 1 — config/asset "entities" (no DB schema); explicit "no migration" record
├── quickstart.md        # Phase 1 — per-story validation runbook (archive→validate; clean-clone build; endpoint check; streaming on-device; watch QR; vault lint)
├── contracts/           # Phase 1 — release-pipeline, build-config, compliance-entitlements, deployment-env, client-identity
│   ├── release-pipeline.md
│   ├── build-config.md
│   ├── compliance-and-entitlements.md
│   ├── deployment-env.md
│   └── client-identity.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
apple-clients/
├── AstralApp/
│   ├── AstralApp.xcodeproj/
│   │   ├── project.pbxproj                      # EDIT: DEVELOPMENT_TEAM, CODE_SIGN_STYLE, CODE_SIGN_ENTITLEMENTS, sandbox/hardened-runtime (macOS), xcconfig wiring, versioning; "Embed Watch Content" copy-files phase on the iOS target, PLATFORM-FILTERED to iOS (FR-011a/FR-011b); ASSETCATALOG_COMPILER_APPICON_NAME=AppIcon on AstralWatch (FR-004a)
│   │   └── xcshareddata/xcschemes/
│   │       ├── AstralApp.xcscheme
│   │       └── AstralWatch.xcscheme            # ADD: restore missing shared scheme (FR-014)
│   ├── Info.plist                               # EDIT: DEBUG-scope/remove NSAllowsArbitraryLoads (FR-006); usage strings
│   ├── WatchInfo.plist                          # EDIT: watch-only→companion — remove WKWatchOnly, add WKCompanionAppBundleIdentifier=com.personalailabs.astraldeep + WKRunsIndependentlyOfCompanionApp=YES, keep WKApplication (FR-011a); ATS + ITSAppUsesNonExemptEncryption (FR-007)
│   ├── AstralApp/Assets.xcassets/AppIcon.appiconset/   # DONE: generated PNGs — AppIcon-1024.png + AppIcon-1024-dark.png (no alpha) + ten macOS mac-*x*@Nx.png (gutter) + rewritten Contents.json (FR-004)
│   ├── PrivacyInfo.xcprivacy                     # ADD: privacy manifest for the iOS/macOS app (FR-005)
│   ├── AstralApp.entitlements                    # ADD: keychain; (macOS) App Sandbox
│   └── AstralWatch.entitlements                  # ADD: keychain (watch)
├── AstralWatch/Assets.xcassets/AppIcon.appiconset/  # DONE: NEW watch asset catalog (target had none) — AppIcon-1024.png + Contents.json (FR-004a)
├── AstralWatch/PrivacyInfo.xcprivacy                # ADD: the embedded watch is its own .app -> its own manifest (FR-005)
├── Scripts/
│   └── generate_app_icons.py                     # DONE: stdlib Python + sips, zero deps; derives all Apple icons from the master + `--check` mode (FR-004/FR-030)
├── Config/                                       # ADD: xcconfig endpoint/realm indirection (FR-009)
│   ├── Base.xcconfig
│   ├── Debug.xcconfig                            # localhost:8001 (ATS localhost scoped to Debug)
│   └── Release.xcconfig                          # sandbox.ai.uky.edu + realm (default)
├── AstralCore/Sources/AstralCore/Configuration.swift  # EDIT: read endpoint/realm from build settings, drop #if DEBUG hardcode (FR-009/010)
├── AstralWatch/WatchModel.swift                  # EDIT: consume config; opportunistic WatchConnectivity server-override — check isCompanionAppInstalled, fall back to build-time default (FR-011)
├── ExportOptions-ios.plist                       # ADD: method=app-store (iOS .ipa; maps app + embedded-watch profiles)
├── ExportOptions-macos.plist                     # ADD: method=app-store (macOS .pkg; maps the macOS profile)
├── project.yml                                   # DELETE: retire XcodeGen generator (drifted + cannot emit Embed Watch Content); committed .xcodeproj is canonical (FR-012)
├── README.md                                     # EDIT: document the committed .xcodeproj as the single canonical project; signing+release+icon generation (FR-012/FR-028)
└── KNOWN-ISSUES.md                               # EDIT: retire the "legacy keychain until real signing" note once signed

.github/workflows/
└── apple-release.yml                             # ADD: tag-triggered (apple-v*) archive→export→upload→submit (FR-015/016/017)

.env.example                                      # EDIT: correct KEYCLOAK_ALLOWED_AZP comment to astral-mobile/astral-desktop/astral-watch (FR-018)
docs/
├── keycloak-realm-settings.md                    # EDIT: resolve §051 client-id conflict; document Apple redirect on shared clients (FR-013/019)
└── production-deployment.md                      # EDIT: Apple release + .env posture checklist (FR-018/028)

# Obsidian vault (additional working dir; per its CLAUDE.md rules) — FR-029 / US7
../obsidian-vault/wiki/entities/Apple Release Pipeline.md   # NEW
../obsidian-vault/wiki/entities/{Apple Clients,Keycloak Realm Astral,AstralBody}.md  # REVISE
../obsidian-vault/wiki/concepts/{CI Gates,Feature Flags,Feature Timeline}.md          # REVISE
../obsidian-vault/wiki/sources/astralbody-repo.md          # REVISE (reviewed_commit bump)
../obsidian-vault/{index.md,log.md}                        # UPDATE
```

**Structure Decision**: This is a native-Apple-client + CI/CD + config/docs feature. The overwhelming majority of edits land under `apple-clients/` (Xcode project settings incl. the iOS-target "Embed Watch Content" phase, new `Config/*.xcconfig`, entitlements, privacy manifest, the already-generated icon assets + their generator under `Scripts/`, the new watch asset catalog, `Configuration.swift`, the opportunistic-`WatchConnectivity` watch override, the `WatchInfo.plist` watch-only→companion conversion, README) plus the **deletion** of `project.yml` (the retired generator), plus one additive `.github/workflows/apple-release.yml`, plus `.env.example` + two `docs/` files, plus the obsidian vault. The committed `.xcodeproj` is the single canonical project — no generator remains, so there is no second source of project truth to drift. No backend `src/` module structure is introduced; the backend is verified, not modified (US5), unless the astralprims-version check (FR-020) reveals a `requirements.txt` pin adjustment — an additive, dependency-neutral edit. No new test tree beyond extending AstralCore tests where Swift logic changes (the watch companion-fallback test) and per-client manual verification evidence under `specs/053-.../verification/` mirroring 051.

## Complexity Tracking

No Constitution violations — table intentionally omitted. Two nuances worth flagging, both resolved in research.md:

- **Terminology ("notarize")**: for App Store distribution the pipeline does archive→export(app-store)→upload→submit; developer notarization via `notarytool` is an App-Store-*independent* path used only for Developer-ID direct distribution, which this feature does not produce. The spec's FR wording "notarize" is interpreted as Apple's server-side processing of the submitted build. The release tag namespace stays `apple-v*` (a `v`-prefixed tag would also match `release-windows.yml`'s `v*` filter and double-fire it).
- **Store topology is one record, not three**: iOS and macOS share bundle id `com.personalailabs.astraldeep`, so they form **one** Universal Purchase App Store Connect record with two platform versions, and the watch ships as an embedded companion inside the iOS build — one record, one listing, two archives (D19), not the three apps/listings/archives earlier text assumed.

## Phase 0 — Outline & Research

See [research.md](research.md). Resolves the concrete "how" decisions with no NEEDS CLARIFICATION remaining: distribution signing style (manual App Store distribution certs + three platform profiles imported into a temp CI keychain vs automatic), the one-record Universal Purchase store topology (D19), the xcconfig endpoint/realm indirection mechanism and how `Configuration.swift` reads it, ATS scoping (Debug-only localhost exception; Release clean), the privacy-manifest + usage-string content set (watch speech/dictation, required-reason APIs), export-compliance declaration, build-number automation (CI-run-derived), the App-Store-upload-vs-notarization flow correction, the `.env`/realm production checklist (including adding the Apple redirect to the shared `astral-mobile`/`astral-desktop` clients), the baked `astralprims` version confirmation, the **watch-only→embedded-companion conversion** and its opportunistic-`WatchConnectivity` server-override with build-time fallback (D12), the icon generation from the supplied master (D15) and brand-asset reuse mapping (D16/D17), and the retirement of the XcodeGen generator (D18).

## Phase 1 — Design & Contracts

See [data-model.md](data-model.md) (config/asset entities; explicit no-DB-migration record), [contracts/](contracts/) (release-pipeline, build-config, compliance-and-entitlements, deployment-env, client-identity), and [quickstart.md](quickstart.md) (the per-user-story validation runbook). Agent context is refreshed via `.specify/scripts/bash/update-agent-context.sh` after Phase 1.

**Post-Design Constitution re-check**: PASS — the design introduces no new dependency, no schema change, no wire change, no client-parity divergence; it strengthens Principle X (removes the hardcoded endpoint, adds per-client signed verification) and stays additive on Principle XI.
