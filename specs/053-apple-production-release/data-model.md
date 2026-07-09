# Data Model: Apple Clients Production Release (053)

**Database schema changes: none.** This feature is client packaging / signing /
configuration + additive CI + docs. The backend server→client manifest is
**byte-identical since 051** (drift guard 47 push / 35 component / 67 accept types),
and the only client-observable backend change — narrative prose streaming over the
already-dispositioned `ui_stream_data` frame — is verified on-device, not schema.
Per Constitution IX, *if* a schema change ever proved necessary (FR-027) it would ship
as an idempotent, guarded `_init_db` delta with a documented rollback — **none is
needed here** (see [Migrations](#migrations)).

The feature's "entities" are therefore **version-controlled configuration and asset
artifacts** plus **runtime-injected secrets** and **verification evidence files** — not
tables. Each is documented below as an entity: its shape/fields, where it lives (real
repo-relative path), its validation rules (traced to the FRs), and its lifecycle.

---

## A. Build configuration (D2 · FR-009/FR-010/FR-011)

The version-controlled source that supplies the backend endpoint and Keycloak realm to a
build, resolved by indirection so **no dev endpoint is reachable in a Release build**.

**Shape** — three-layer resolution:

1. **xcconfig keys** (`apple-clients/Config/{Base,Debug,Release}.xcconfig`)
   - `ASTRAL_SERVER_BASE_URL` — Debug `http://localhost:8001`; Release `https://sandbox.ai.uky.edu`
   - `ASTRAL_KEYCLOAK_AUTHORITY` — Release `https://iam.ai.uky.edu/realms/Astral`
2. **Info.plist keys** (`AstralApp/Info.plist`, `AstralApp/WatchInfo.plist`) — custom keys
   `ASTRALServerBaseURL` / `ASTRALKeycloakAuthority` populated via `$(ASTRAL_SERVER_BASE_URL)`
   build-setting substitution.
3. **Swift read** (`apple-clients/AstralCore/Sources/AstralCore/Configuration.swift`) —
   `AstralConfig.serverBaseURL` / `keycloakAuthority` read
   `Bundle.main.object(forInfoDictionaryKey:)`, falling back to the sandbox default when no
   bundle is present (so `AstralCore` unit tests resolve). The `#if DEBUG` hardcode is removed.

**Validation rules**
- FR-009: endpoint + realm come from configuration, defaulting to the sandbox production values.
- FR-010: no `localhost` / `127.0.0.1` / dev endpoint is present in any Release-reachable
  source or config (Debug-only in `Debug.xcconfig`); confirmed by search.
- xcconfig URL escaping: the `//` in `http://` is comment-escaped (`http:$()//…`, D2).
- FR-011 (watch): the watch resolves a runtime server override delivered from its iPhone
  companion over `WatchConnectivity` into the watch's own `UserDefaults`, falling back to the
  build-time xcconfig default (`AstralConfig.serverBaseURL`) whenever no companion is installed
  (D12). This override is **opportunistic only** — the path MUST consult
  `WCSession.isCompanionAppInstalled` and MUST NOT block the watch; **no shared App Group** is
  used (D7's least-privilege set excludes `application-groups`). No rebuild required to repoint.
  See Entity **C** (Watch companion configuration).

**Lifecycle**: authored once → selected per build configuration (Debug vs Release) at archive
time → read at app launch → (watch) overridable at runtime via the opportunistic companion path.
Changing a value and rebuilding repoints the app with no source edit.

---

## B. Signing configuration (D1 · D7 · FR-001/FR-002/FR-003/FR-017)

The distribution identity, provisioning, and entitlements that make a build submittable.

**Shape**
- **`DEVELOPMENT_TEAM`** — operator Apple Team ID, supplied via CI env/xcconfig, **never
  committed** (the single missing pbxproj setting today).
- **Signing style** — CI uses **manual** signing with **Apple Distribution** certs + **App
  Store** provisioning profiles — **three**: iOS + macOS (both `com.personalailabs.astraldeep`; per bundle-id **and platform**) and watchOS (`…​.watch`) (**and**
  `com.personalailabs.astraldeep.watch` — the embedded watch app carries its own profile);
  local dev may keep `CODE_SIGN_STYLE=Automatic`.
- **Entitlement definitions** (version-controlled, per target):
  - `apple-clients/AstralApp/AstralApp.entitlements` — Keychain access group; on **macOS**
    additionally `com.apple.security.app-sandbox=true` + `com.apple.security.network.client=true`
    + Hardened Runtime (D7, Mac App Store mandatory).
  - `apple-clients/AstralApp/AstralWatch.entitlements` — Keychain access group.
- **Project wiring** — `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` sets
  `CODE_SIGN_ENTITLEMENTS`, `CODE_SIGN_STYLE`, sandbox/hardened-runtime (macOS Release).

**Validation rules**
- FR-001: Release builds sign with a distribution identity, **no manual per-build Xcode
  selection**.
- FR-002: every capability's entitlement is version-controlled (keychain; macOS sandbox).
- FR-003: macOS Release enables App Sandbox + Hardened Runtime, entitlements scoped to a
  network + keychain client; no Developer-ID direct-download build.
- FR-017: certificates, private keys, and App Store Connect keys are **runtime CI secrets
  only** — never committed or baked into an image (gitleaks gate enforces).
- Least privilege: no temporary-exception entitlements, no App Group (D7).

**Lifecycle**: entitlements authored + committed → Team ID and cert/profiles (one per bundle id)
injected at CI runtime into a temporary keychain (`security create-keychain` → import →
`set-key-partition-list`) → consumed by `xcodebuild archive` → keychain torn down at job end.
Retires the KNOWN-ISSUES "legacy login keychain until real signing" note (D7).

---

## C. Watch companion configuration (D12 · D19 · FR-007/FR-011/FR-011a)

The Info.plist keys, build-phase, and connectivity posture that convert `AstralWatch` from a
**watch-only** app into an **embedded companion** app carried inside the iOS build. The working
tree today has `WKWatchOnly = true`, **no** `WKCompanionAppBundleIdentifier`, **no** "Embed Watch
Content" phase, and **zero** `WatchConnectivity`/`WCSession` code — none of the runtime override
was reachable, because a watch-only app has no companion to sync from (D12).

**Shape**
- **`AstralApp/WatchInfo.plist`**:
  - **remove** `WKWatchOnly` (was `true`).
  - **add** `WKCompanionAppBundleIdentifier = com.personalailabs.astraldeep` (the iOS bundle id).
  - **keep** `WKApplication = YES`.
  - **add** `WKRunsIndependentlyOfCompanionApp = YES` — the watch still installs and runs
    without the phone app, preserving standalone QR device-login.
  - `ITSAppUsesNonExemptEncryption=false` — the watch's own export-compliance declaration
    (also listed in Entity **D**), consistent with the iOS companion.
- **Embed phase** — an **"Embed Watch Content"** copy-files build phase on the **iOS** target
  (`project.pbxproj`) embeds the built watch app into the iOS `.app` bundle. XcodeGen cannot
  emit this phase, which is one reason the generator is retired (D18, Entity **F**).
- **WatchConnectivity (new Swift code)** — an opportunistic `WCSession`-based override reader
  (none exists today) that writes any companion-pushed endpoint into the watch's `UserDefaults`.
  It MUST consult `WCSession.isCompanionAppInstalled` and fall back to the build-time xcconfig
  default when the companion is absent. **No App Group entitlement** (D7 excludes
  `com.apple.security.application-groups`).

**Validation rules**
- FR-011a: the watch is an **embedded companion** (not watch-only): `WKWatchOnly` absent;
  `WKCompanionAppBundleIdentifier` = iOS bundle id; embedded in the iOS target;
  `WKRunsIndependentlyOfCompanionApp = YES` so it still installs/runs standalone.
- FR-011: the connectivity override is **opportunistic** — `isCompanionAppInstalled`-guarded,
  fail-open to the build-time default, and it **never blocks** the watch.
- Companion prefix (Apple): the iOS bundle id MUST be a strict prefix of the watch bundle id
  (`com.personalailabs.astraldeep` → `…​.watch`) — asserted in Entity **F**.
- FR-007: the watch carries its own export-compliance status consistent with the iOS target.

**Lifecycle**: authored in `WatchInfo.plist` + the iOS-target embed phase → the watch is built
and embedded into the **iOS** archive (D19, Entity **G** store topology), not shipped as its own
record → at runtime the companion may push an override, else the build-time default applies →
verified on-device including the no-companion fallback (Constitution X).

---

## D. App Store compliance assets (D4 · D15 · FR-004/FR-004a/FR-005/FR-006/FR-007/FR-030)

Icon set (now **generated and on disk**), privacy manifest, purpose strings, ATS posture, and
export-compliance declaration required for upload/review. Screenshots are a **separate** entity
(Entity **E**).

**App icon set — GENERATED (blocker closed).** Derived from the operator master
`android-client/Android Raw Assets/AppIcon.png` (3000×3000, RGB + a **100% opaque** alpha
channel) by the committed **`apple-clients/Scripts/generate_app_icons.py`** — stdlib Python +
Apple `sips`, **zero new dependencies** (Constitution V). Emitted files, already on disk:

- `apple-clients/AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` +
  `AppIcon-1024-dark.png` — 1024×1024, **no alpha** (an alpha channel fails upload as
  **ITMS-90717**; stripping is lossless because the master is already opaque).
- ten **macOS** slots `mac-{16,32,128,256,512}x…@{1,2}x.png` — a rounded-rect "squircle" body
  (824 on the 1024 canvas, ~185.4 px continuous-corner radius) inside a **transparent gutter**.
  RGBA is **correct** here: classic macOS asset catalogs do **not** auto-mask, so the artwork
  supplies the shape.
- new watch catalog
  `apple-clients/AstralWatch/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` + `Contents.json`
  (the watch target previously had **no** asset catalog at all).
- a rewritten `AppIcon.appiconset/Contents.json`.

**Opacity rule per platform** (the generator's `--check` mode asserts all three, so an icon
regression fails loudly rather than at upload): **iOS + watchOS** App Store icon = 1024×1024,
fully **opaque** (no alpha — ITMS-90717); **macOS** slots = transparent **gutter retained** (no
auto-mask). A blanket "strip all alpha" step would break the macOS slots.

**Still TODO (a task, not done)**: set `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` on the
**AstralWatch** target's build configs in `project.pbxproj` (currently set only on AstralApp).

**Verified**: `sips` reports `hasAlpha=no` on the three 1024 icons and `hasAlpha=yes` on the macOS
slots; `xcodebuild -scheme AstralApp -destination 'generic/platform=iOS Simulator' -configuration
Debug` **BUILD SUCCEEDED**; `actool` emitted `AppIcon60x60@2x.png` and `AppIcon76x76@2x~ipad.png`;
`Assets.car` carries phone+pad renditions in default **and** dark appearances.

**Other compliance shape**
- **Privacy manifests** — `apple-clients/AstralApp/PrivacyInfo.xcprivacy` **and** `apple-clients/AstralWatch/PrivacyInfo.xcprivacy` (the embedded watch is its own `.app` bundle; its manifest declares the `UserDefaults` CA92.1 required reason used by the override) (per app target as
  required): `NSPrivacyTracking=false`; `NSPrivacyCollectedDataTypes` reflecting reality
  (first-party backend, no third-party tracking); `NSPrivacyAccessedAPITypes` required-reason
  entries (e.g. `UserDefaults` `CA92.1`) finalized by auditing reason-coded APIs actually
  called (D4).
- **Usage / purpose strings** — in the relevant Info.plist: `NSSpeechRecognitionUsageDescription`
  + `NSMicrophoneUsageDescription` wherever the watch dictation/voice path exists.
- **ATS posture** — `NSAllowsArbitraryLoads` removed; Release is ATS-clean (HTTPS backend); the
  localhost exception (`NSAllowsLocalNetworking` / scoped `NSExceptionDomains`) is **Debug-only**.
- **Export compliance** — `ITSAppUsesNonExemptEncryption=false` in `WatchInfo.plist` (already
  present in iOS `Info.plist`); standard HTTPS/OS crypto is exempt.

**Validation rules**
- FR-004: every required rendered icon present incl. the opaque 1024px marketing icons and the
  ten gutter-preserving macOS slots, reproducible by the committed script → passes upload
  validation. (Icons are on disk and build-verified.)
- FR-004a: the watch target has its own asset catalog (done) with its app icon wired via
  `ASSETCATALOG_COMPILER_APPICON_NAME` (the remaining build-setting task).
- FR-030: icons are derived by a committed, dependency-free script whose `--check` self-check
  verifies slot sizes, iOS/watch opacity, and macOS gutter retention.
- FR-005: privacy manifest declares data-collection + required-reason API usage; every runtime
  permission has a user-facing purpose string.
- FR-006: no blanket arbitrary-loads exception applies to Release; any localhost exception is
  Debug-scoped.
- FR-007: watch export-compliance status consistent with the companion phone target.
- Honesty (Constitution XIII): declared collection must match reality; no speculative entries.

**Lifecycle**: icons **generated** from the supplied master (the "operator must supply icon
artwork" prerequisite is now **satisfied**) → the one remaining wiring task sets the watch
appicon build setting → manifest/usage strings/ATS/export-compliance authored + committed →
validated by `xcrun altool --validate-app` during the release workflow.

---

## E. App Store screenshots (D16 · D17 · FR-031/FR-032/FR-015a)

The per-device-class screenshot set — captured **natively** from the real Apple apps (no supplied
Android asset transfers) and given brand/caption overlays — that the single store listing requires
before submission.

**Shape**
- **Required device classes** for this record (the iOS app declares
  `TARGETED_DEVICE_FAMILY = "1,2"` and the build emits `AppIcon76x76@2x~ipad.png`, so **iPad is
  supported**): **iPhone 6.9"**, **iPad 13"**, **Mac**, **Apple Watch**.
- **Accepted pixel sizes** — pick **one** per class (Apple Watch: the **same** size across all
  localizations); 1–10 screenshots per class:

  | Class | Accepted pixel sizes (portrait; landscape swaps W/H) |
  |---|---|
  | iPhone 6.9" | 1260×2736 · 1290×2796 · 1320×2868 |
  | iPad 13" | 2048×2732 · 2064×2752 |
  | Mac | 1280×800 · 1440×900 · 2560×1600 · 2880×1800 (16:10) |
  | Apple Watch | 422×514 · 416×496 · 410×502 · 396×484 · 368×448 · 312×390 |

- **Capture** — `xcrun simctl io <device> screenshot` for iOS/iPad/watch (native-resolution
  PNGs); macOS needs a window capture. **Operator-assisted**: the automation environment cannot
  tap/type in a simulator, so the operator drives the app to each screen (or deep links are
  scripted). Overlays are composited afterward.
- **Brand-asset reuse mapping** (D17 · FR-032) — every supplied asset's status recorded so none
  is silently ignored and none wrongly shipped:

  | Supplied asset (actual pixels) | Status | Reason |
  |---|---|---|
  | `AppIcon.png` — 3000×3000, opaque | **Usable** | Master for all Apple icons (Entity **D**) |
  | `feature-graphic.png` — 1024×500 | **Not transferable** | Google-Play-only; App Store has no feature-graphic slot |
  | `1920X1080.png` — actually 5760×3240 (16:9) | **Reference-only** | Desktop/web render; Mac needs 16:10 native capture |
  | `2560x1440.png` — actually 7680×4320 (16:9) | **Reference-only** | As above (3× supersampled; filename misdescribes pixels) |
  | `phone-{1,2}-*.png` — 1080×1920 (9:16) | **Reference-only** | Wrong aspect for iPhone 6.9" |
  | `tablet7-*`, `tablet10-*` — 16:9 landscape | **Reference-only** | Wrong aspect for iPad 13" (needs 4:3) |

**Validation rules**
- FR-031: each required class has ≥1 screenshot captured from the **real Apple app** at an
  exactly-accepted pixel size; overlays are permitted but the underlying pixels MUST show the app
  **in use** — not a splash/login/title card (App Review Guideline **2.3.3**).
- FR-032: the reuse status (usable / reference-only / not transferable) of every supplied asset
  is recorded explicitly; no asset silently dropped or wrongly shipped.
- FR-015a: a screenshot set for **each** required class exists in the listing before submission.

**Lifecycle**: operator drives the real app to each target screen (or scripted deep links) →
native PNG captured at an accepted size → brand/caption overlay composited → uploaded into the
**single** listing (Entity **G**) before the version is submitted.

---

## F. Client identity (D8 · D9 · D18 · FR-012/FR-013/FR-014)

The bundle-identifier family, URL scheme, OAuth client ids, and shared schemes that must agree
across the committed project, the docs, and the realm — with the generator **retired** so no
second source of project truth can silently diverge (the **shared-client** model).

**Shape** (authoritative shipped values)
- **Bundle-id family** — `com.personalailabs.astraldeep` (app) / `com.personalailabs.astraldeep.watch`
  (watch). The app id is a **strict prefix** of the watch id, as Apple requires for an embedded
  companion (Entity **C**).
- **URL scheme** — `com.personalailabs.astraldeep` (redirect `com.personalailabs.astraldeep:/oauth2redirect`).
- **OAuth client ids** — `astral-mobile` (iOS, shared with Android) / `astral-desktop` (macOS,
  shared with Windows) / `astral-watch`.
- **Shared schemes** — `AstralApp.xcscheme` and a restored `AstralWatch.xcscheme` under
  `apple-clients/AstralApp/AstralApp.xcodeproj/xcshareddata/xcschemes/` (the management plist
  declares it shared but the file is absent today, D9).
- **Single canonical project** — the committed
  `apple-clients/AstralApp/AstralApp.xcodeproj` is the **only** project.
  `apple-clients/project.yml` is **deleted** (D18): it had drifted to
  `bundleIdPrefix = com.kyopenscience.astral` / scheme `astral`, **and** XcodeGen cannot emit the
  "Embed Watch Content" phase the companion watch app now needs — regenerating would silently
  ship a project with **no watch app**. Docs corrected to match code: `apple-clients/README.md`
  (names the `.xcodeproj` as canonical), `docs/keycloak-realm-settings.md`, and the
  `.env.example` `KEYCLOAK_ALLOWED_AZP` comment (all previously drifted to
  `com.kyopenscience.astral` / scheme `astral` / `astral-ios`·`astral-macos`).

**Validation rules**
- FR-012: exactly **one** canonical project exists — `apple-clients/project.yml` no longer exists,
  and the README documents the committed `.xcodeproj` as canonical. (This replaces the old
  "regenerating the project preserves a working OAuth redirect" claim; there is no generator to
  regenerate from — see SC-005.)
- FR-012 (companion prefix): the iOS bundle id is a **strict prefix** of the watch bundle id, as
  Apple requires for an embedded companion.
- FR-013: clients use `astral-mobile`/`astral-desktop`/`astral-watch`; realm-settings docs name
  the same ids and redirects with no unresolved conflict.
- FR-014: a shared scheme exists for **every** buildable target incl. the watch, so a clean
  clone and CI build each by name.
- Shared-client consequence: the Apple redirect must be a Valid Redirect URI on the **shared**
  `astral-mobile`/`astral-desktop` clients (realm step, see Entity **I** / D10).

**Lifecycle**: shipped code is authoritative → `project.yml` **deleted**; README updated to name
the committed project canonical → realm-docs / README / `.env.example` corrected to match code →
a clean-clone build of all three schemes reproduces the working redirect, and no generator path
remains to drift from.

---

## G. Store topology (D19 · FR-015/FR-015a)

The App Store Connect record shape the two archives upload into — **one** record, not three.

**Shape**
- **One** App Store Connect record — **Universal Purchase** — carrying **two platform versions**:
  iOS and macOS. Both targets set `PRODUCT_BUNDLE_IDENTIFIER = com.personalailabs.astraldeep`; a
  bundle id is unique per record and Universal Purchase is precisely "same Apple ID / SKU / bundle
  id across platforms", so iOS + macOS **must** be one record with two platform versions.
- The **watch app is embedded** inside the iOS build (Entity **C** companion + Embed Watch Content
  phase), **not** its own record. (Had the watch stayed `WKWatchOnly`, Apple would force a
  separate watch-only record and block embedding it in a companion.)
- **Net**: **1 record, 1 listing, 2 archives** (iOS-with-embedded-watch, macOS), 2 uploads,
  1 submission.

**Validation rules**
- FR-015: both archives upload into the single record, and the version is submitted for review.
- FR-015a: a **single** complete listing (name, description, keywords, URLs, per-class
  screenshots, privacy-policy URL, age rating, export-compliance answer) exists on that one record
  before submission.
- Corrects the earlier "three apps / three listings / three archives" assumption.

**Lifecycle**: operator creates **one** app record (Universal Purchase) → the pipeline uploads the
two platform builds → **one** submission for review.

---

## H. Release-pipeline inputs (D14 · FR-015/FR-016/FR-017)

The tag-triggered workflow and the CI secret set it consumes. The workflow itself is
`.github/workflows/apple-release.yml` (additive; mirrors `release-windows.yml`); contract
detail lives in `contracts/release-pipeline.md`.

**Shape** — CI secret set (all GitHub secrets, never committed):

| Secret | Purpose |
|---|---|
| `APPLE_TEAM_ID` | `DEVELOPMENT_TEAM` for signing |
| `APPLE_DISTRIBUTION_CERT_P12_BASE64` | Apple Distribution cert (imported to temp keychain) |
| `APPLE_CERT_PASSWORD` | P12 import password |
| `APPLE_PROVISION_PROFILE_BASE64` | Carries **three** App Store profiles: iOS + macOS (same bundle id `com.personalailabs.astraldeep`, different platforms) and watchOS (`…​.watch`). A profile is per bundle-id **and platform**. |
| `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_P8_BASE64` | App Store Connect API key (upload + submit) |

**Also inputs** (not secrets): the tag namespace `apple-v*` — chosen because it does **not** begin
with `v`, so the Windows release's `v*` tag filter cannot match it (a `v-apple-*` tag WOULD be
matched by `v*` and double-fire that workflow); `MARKETING_VERSION` (tag-vs-version guard);
`CURRENT_PROJECT_VERSION` derived from `GITHUB_RUN_NUMBER` (D5, collision-free monotonic build
number, FR-008); per-platform `ExportOptions-ios.plist` / `ExportOptions-macos.plist` (`method=app-store`); and **two archives** (iOS with the
embedded watch app, and macOS) uploaded into the **one** App Store Connect record (Entity **G**).

**Validation rules**
- FR-015: the tag-triggered workflow archives → exports (app-store) → uploads → submits for review
  the **two** platform builds — iOS (containing the embedded watch app) and macOS — into the
  **single** Universal Purchase record, using injected secrets, and **fails clearly** (no unsigned
  artifact, no leaked secret) when signing material is missing.
- FR-015a: a complete App Store Connect listing (name, description, keywords, URLs, per-device
  screenshots for each required class, privacy-policy URL, age rating, export-compliance answer)
  exists on the record before submission — operator-supplied (blocking prerequisite).
- FR-016: the six backend CI gates and the unsigned `apple-ci.yml` compile matrix are untouched.
- FR-017: all signing material is runtime-injected, never committed or baked into an image.
- D6 terminology: App Store flow is archive→export→**upload**→submit; no `notarytool` step
  (that is the Developer-ID path, not produced here).

**Lifecycle**: operator provisions secrets + **one** App Store Connect app record + listing →
push a `apple-v*` tag → workflow signs/archives (two)/validates/uploads (two)/submits (one); the
live upload/submit step is **gated on operator-supplied signing material (profiles for both
bundle ids) and listing metadata (incl. screenshots)** — the icon artwork gate is now **closed**
(icons generated, Entity **D**); all other pipeline wiring proceeds in parallel.

---

## I. Deployment posture (D10 · D11 · FR-018/FR-019/FR-020/FR-021)

The `.env` values, realm settings, and image contents that make the target backend
production-correct and fail-closed. Verified (not changed) — the backend already runs.
Contract detail in `contracts/deployment-env.md`; checklist in `docs/production-deployment.md`.

**Shape** — production `.env` keys (verified against the checklist):
- `ASTRAL_ENV=production` (or unset → fail-closed); `USE_MOCK_AUTH=false`
- `KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral`
- `KEYCLOAK_ALLOWED_AZP` includes `astral-desktop,astral-mobile,astral-watch` (+ web)
- `KEYCLOAK_DEVICE_CLIENTS=astral-watch`; `FF_DEVICE_LOGIN=true`; `FF_LLM_STREAMING=true`
- Real high-entropy secrets: `WEB_SESSION_ENC_KEY`, `OFFLINE_GRANT_ENC_KEY`,
  `CREDENTIAL_ENCRYPTION_KEY`, `MEMORY_HMAC_KEY`, `AGENT_API_KEY`, `AUDIT_HMAC_SECRET`,
  `KEYCLOAK_CLIENT_SECRET` (≠ placeholder)
- `FORWARDED_ALLOW_IPS` = the TLS proxy
- `DB_POOL_MAX × process_count < Postgres max_connections`

**Realm prerequisites (operator)**: well-known advertises `device_authorization_endpoint`;
`astral-watch` has the Device Authorization Grant capability (verified 2026-07-08); the Apple
redirect `com.personalailabs.astraldeep:/oauth2redirect` is registered on `astral-mobile` and
`astral-desktop`. **Image**: `backend/requirements.txt` `astralprims>=0.2.0` resolves a wheel
whose vocabulary yields exactly the 35 component types the Apple drift guard asserts (D11,
`ManifestDriftTests.swift`).

**Validation rules**
- FR-018: every required `.env` key set to a production-correct value, no placeholder; pool
  sizing within the Postgres connection limit for the process count.
- FR-019: realm well-known advertises the device-authorization endpoint and lists the shipped
  redirect URIs / azp values, so watch QR + PKCE do not fail closed.
- FR-020: baked `astralprims` provides exactly the client-expected vocabulary (drift guard green).
- FR-021: fail-closed preserved — production-posture boot refuses missing/placeholder secrets
  (documented exit 78); dev mock auth does not boot in production.

**Lifecycle**: authored `.env` + realm config → verified against the documented checklist →
fail-closed on any missing/placeholder secret. This entity is **asserted, not migrated**.

---

## J. Verification evidence artifacts (FR-022/FR-023/FR-024/FR-025 · US6)

Per-client captured proof that signed builds work as intended and stay consistent across
clients, stored under `specs/053-apple-production-release/verification/` mirroring the 051
layout.

**Shape** — per-client evidence records covering:
- PKCE sign-in on a signed build (iOS/macOS); watch QR device-login end-to-end.
- Session/keychain persistence across an app reinstall (every platform, SC-009).
- The watch **no-companion fallback**: an embedded-companion watch build launched without the
  iPhone app falls back to the build-time endpoint and stays usable via QR device-login (D12).
- Live `FF_LLM_STREAMING` narrative streaming rendering coherently and superseded by the final
  `ui_render` on iOS, macOS, and watchOS (watch highest risk, D13).
- The outstanding **051** evidence completed: round-trip latency p95 (T046, inherits the 051
  target) and the browser short-code device-login path (T041).

**Validation rules**
- FR-022/FR-023: each signed build verified end-to-end on its device family; streaming verified
  rendering on all three, consistent with the final authoritative render (SC-007).
- FR-024: the previously-unchecked 051 round-trip timing and browser short-code items captured.
- FR-025: cross-client SDUI parity preserved — the `ui_protocol.json` drift guard stays green
  and is **extended, not forked**, if the vocabulary ever changes.

**Lifecycle**: produced during on-device verification of the signed builds → committed as
gitignored-artifact-adjacent evidence under the feature's `verification/` dir → referenced by
the vault release-pipeline page (FR-029).

> Documentation & knowledge artifacts (FR-028/FR-029) — README, `docs/production-deployment.md`,
> `docs/keycloak-realm-settings.md`, and the ~7 obsidian-vault pages — are content, not
> data-model entities; they record the above and are covered by the plan's structure section.

---

## Migrations

**None required.** This feature touches client packaging/signing/config, additive CI
(`apple-release.yml`), and docs only. The backend server→client contract is byte-identical
since 051, no table is added or altered, and no data is written by this feature beyond the
existing verification side effects already covered by 051's schema.

- **Rollback** = **revert the PR** (config / CI-YAML / docs / committed assets). No data
  migration, no `_init_db` delta, no down-migration.
- **Constitution IX fallback**: were a schema change ever to become genuinely necessary
  (FR-027), it would ship as an idempotent, guarded `_init_db` startup delta with its rollback
  documented here first. The current design deliberately avoids one.
