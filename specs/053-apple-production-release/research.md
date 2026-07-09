# Phase 0 Research: Apple Clients Production Release

All decisions below resolve the "how" for the spec's requirements. No `NEEDS CLARIFICATION` remains. Ground truth was read from the repo on branch `053-apple-production-release` (commit context: `e94d5c7`).

---

## D1 — Distribution & code-signing style

**Decision**: Distribute through **App Store Connect** as **one Universal Purchase record with two platform builds** — iOS (containing the embedded watch app) and macOS (**Mac App Store**). See D19 for why the record count is one, not three. Use **manual signing** with **Apple Distribution** certificates + **App Store** provisioning profiles — **three** of them: iOS and macOS (both `com.personalailabs.astraldeep`; a profile is per bundle-id **and platform**) plus watchOS (`…​.watch`), imported at CI runtime from base64 GitHub secrets into a temporary keychain (`security create-keychain` → `import` → `set-key-partition-list`), with `DEVELOPMENT_TEAM` supplied via CI env/xcconfig, not committed. Local developer builds may keep `CODE_SIGN_STYLE=Automatic` with the developer's own team.

**Rationale**: Manual signing is the only reliable, reproducible path in headless CI (automatic signing needs an interactive Xcode session / Apple ID). Mirrors the `release-windows.yml` precedent of "no long-lived secret in the repo; credentials injected at job runtime." `DEVELOPMENT_TEAM` is the single missing setting today (pbxproj has `CODE_SIGN_STYLE=Automatic` but no team).

**Alternatives considered**: (a) Automatic signing in CI — rejected, not headless-friendly. (b) fastlane `match` — rejected, new third-party dependency (Constitution V) and adds a private cert repo. (c) Xcode Cloud — rejected, moves CI off GitHub Actions and off the established pattern.

---

## D2 — Build-time endpoint/realm indirection

**Decision**: Introduce `apple-clients/Config/{Base,Debug,Release}.xcconfig` defining `ASTRAL_SERVER_BASE_URL` and `ASTRAL_KEYCLOAK_AUTHORITY` (Debug → `http://localhost:8001`; Release → `https://sandbox.ai.uky.edu` + `https://iam.ai.uky.edu/realms/Astral`). Surface them into each target's Info.plist as custom keys (`ASTRALServerBaseURL`, `ASTRALKeycloakAuthority`) via `$(ASTRAL_SERVER_BASE_URL)` substitution, and rewrite `AstralConfig.serverBaseURL`/`keycloakAuthority` in `Configuration.swift` to read `Bundle.main.object(forInfoDictionaryKey:)` (falling back to the sandbox default if absent, so `AstralCore` unit tests with no bundle still resolve). This removes the `#if DEBUG` hardcode and leaves **no dev endpoint reachable in a Release build**.

**Rationale**: xcconfig + Info.plist substitution is the idiomatic, dependency-free Apple mechanism for per-configuration values; keeps `AstralCore` decoupled from build flags; satisfies FR-009/FR-010 and Constitution X ("no hardcoded localhost"). URL-scheme note (`:` in `http://`) is handled by xcconfig `//`-comment escaping (`ASTRAL_SERVER_BASE_URL = http:$()//...`).

**Alternatives considered**: (a) Keep `#if DEBUG` but swap the release literal — rejected, still hardcoded, fails FR-010 intent and can't repoint without a code edit. (b) Compile-time `-D` flags — rejected, clumsier than xcconfig and not readable at runtime. (c) Remote config fetch — rejected, over-engineered and adds a network dependency before auth.

---

## D3 — App Transport Security scoping

**Decision**: Remove the unconditional `NSAllowsArbitraryLoads=true` from `AstralApp/Info.plist` and `WatchInfo.plist`. Release ships **ATS-clean** (backend is HTTPS). The Debug localhost exception is expressed as `NSAllowsLocalNetworking=true` (or a scoped `NSExceptionDomains` for `localhost`) applied only to the Debug configuration — matching the *former* `project.yml` intent (it used `NSAllowsLocalNetworking`); that generator is now retired (D18).

**Rationale**: A blanket arbitrary-loads exception in a Release build is an App Store review flag and unnecessary (Release is HTTPS). `NSAllowsLocalNetworking` is the App-Store-safe way to permit `http://localhost` for dev. Satisfies FR-006.

**Alternatives considered**: Keep arbitrary-loads with a review justification — rejected, gratuitous risk for zero benefit.

---

## D4 — Privacy manifest, usage strings, export compliance

**Decision**: Add `PrivacyInfo.xcprivacy` to each app target declaring: `NSPrivacyTracking=false`, an empty/collected-data set reflecting reality (auth tokens + chat content sent to the first-party backend are **not** third-party tracking; declare `NSPrivacyCollectedDataTypes` only for what is actually collected, e.g. user content if applicable), and `NSPrivacyAccessedAPITypes` required-reason entries for any reason-coded API used (e.g. `UserDefaults` category `CA92.1`, file-timestamp/disk-space if used by Keychain/telemetry). Add `NSSpeechRecognitionUsageDescription` + `NSMicrophoneUsageDescription` where the watch dictation/voice path is present. Set `ITSAppUsesNonExemptEncryption=false` in **`WatchInfo.plist`** (already present in iOS `Info.plist`) — the app uses only standard HTTPS/OS crypto (exempt).

**Rationale**: Apple requires a privacy manifest and required-reason declarations for App Store submission; missing usage strings crash on permission request and fail review. Satisfies FR-005/FR-007. The exact `NSPrivacyAccessedAPITypes` set is finalized during implementation by auditing the reason-coded APIs the code actually calls (documented in the compliance contract).

**Alternatives considered**: Omit the manifest — rejected, hard submission blocker. Declare speculative data collection — rejected, must match reality (Constitution XIII honesty).

---

## D5 — Version & build-number automation

**Decision**: Keep `MARKETING_VERSION` as the human-set release version (bumped per release, guarded like `release-windows.yml`'s tag-vs-`__version__` check). Derive `CURRENT_PROJECT_VERSION` (build number) automatically in the release workflow from the CI run (`agvtool new-version -all "$GITHUB_RUN_NUMBER"` or an `xcconfig`/`-setting` override at archive time), so successive archives never collide.

**Rationale**: App Store Connect rejects duplicate build numbers; a monotonic CI-run-derived number is collision-free and reproducible. Satisfies FR-008. A tag-vs-`MARKETING_VERSION` guard (mirroring Windows) prevents shipping a mislabeled build.

**Alternatives considered**: Timestamp build numbers — rejected (`Date.now()`-style nondeterminism, and CI run number is already monotonic). Manual bumps — rejected, error-prone and the current collision risk.

---

## D6 — App Store submission flow (terminology correction)

**Decision**: The release pipeline performs **archive → export (App Store distribution) → upload to App Store Connect → submit for review**, using `xcodebuild -exportArchive` with per-platform `ExportOptions-{ios,macos}.plist` (`method = app-store`) and `xcrun altool --upload-app` / Transporter with an **App Store Connect API key** (issuer + key id + `.p8`, all CI secrets). **No `notarytool` step** is used: developer notarization is the Developer-ID (outside-store) path; App Store builds are processed/signed-checked by Apple server-side. The spec's FR-015 word "notarize" maps to Apple's server-side processing of the uploaded build.

**Rationale**: Correctly reflects Apple's two distinct distribution flows. Mac App Store macOS builds go through App Store Connect exactly like iOS — not through `notarytool`. Avoids a wasted/incorrect notarization step. Satisfies FR-015 accurately and is documented in the plan's Complexity note.

**Alternatives considered**: Add `notarytool` "for safety" — rejected, it is inapplicable to App Store distribution and would confuse the pipeline. Developer-ID direct download for macOS — rejected per D-clarification (Mac App Store chosen).

---

## D7 — macOS Mac App Store entitlements

**Decision**: macOS Release enables **App Sandbox** (`com.apple.security.app-sandbox=true`, mandatory for MAS) + **Hardened Runtime**, with the minimum entitlements a network+keychain SDUI client needs: `com.apple.security.network.client=true` (outbound WS/HTTPS), Keychain access (data-protection keychain via `keychain-access-groups` once a Team ID exists), and no unnecessary temporary-exception entitlements. iOS/watch entitlements declare only Keychain access group. This retires the KNOWN-ISSUES #2 "legacy login keychain until real signing exists" note.

**Rationale**: MAS requires the sandbox; a network client works fully within `network.client`. Keeps the entitlement surface minimal (review-friendly, least privilege). Satisfies FR-002/FR-003.

**Alternatives considered**: Broad temporary-exception entitlements — rejected, review risk and unnecessary. No sandbox — rejected, MAS-ineligible.

---

## D8 — Cross-client identity reconciliation

**Decision**: Standardize on the **shipped** identities everywhere: bundle-id family `com.personalailabs.astraldeep` (app) / `.watch`; URL scheme `com.personalailabs.astraldeep`; OAuth clients `astral-mobile` (iOS, shared with Android) / `astral-desktop` (macOS, shared with Windows) / `astral-watch`. **Superseded in part by D18**: `project.yml` is *retired*, not edited — there is no generator to reconcile, so the former "regenerating the project reproduces the working OAuth redirect" goal is replaced by "exactly one canonical project exists." What remains is to fix README steps 4/6 (URL scheme + bundle id). Fix `docs/keycloak-realm-settings.md §051` and the `.env.example` `KEYCLOAK_ALLOWED_AZP` comment (which currently list `astral-ios`/`astral-macos`) to name `astral-mobile`/`astral-desktop`/`astral-watch`.

**Rationale**: `Configuration.swift` (shipped, verified) already uses these; the drift lives only in the generator/docs. "Fix docs to match code" is the least-risk resolution (per clarification) and prevents a regenerated project from breaking auth (FR-012/FR-013). The shared-client model means the Apple redirect `com.personalailabs.astraldeep:/oauth2redirect` must be added to the **shared** `astral-mobile`/`astral-desktop` clients' Valid Redirect URIs (see D10).

**Alternatives considered**: Switch to dedicated `astral-ios`/`astral-macos` clients (as older docs describe) — rejected by clarification (more realm work, changes verified-working code, higher risk).

---

## D9 — Missing `AstralWatch.xcscheme` shared scheme

**Decision**: Commit a shared `AstralWatch.xcscheme` under `AstralApp.xcodeproj/xcshareddata/xcschemes/` (the file `xcschememanagement.plist` already declares it shared but the file is absent). Verify a clean clone + `apple-ci.yml`'s `-scheme AstralWatch` matrix leg resolves it.

**Rationale**: Without the shared scheme, clean clones and the watchOS CI leg cannot build the watch by scheme name (scheme autocreation is off). Satisfies FR-014.

**Alternatives considered**: Rely on autocreated user schemes — rejected, not committed, breaks CI/clean-clone reproducibility.

---

## D10 — `.env` / Keycloak realm production posture

**Decision**: Produce a documented production checklist (in `docs/production-deployment.md`) and verify the deployment `.env` against it. Required production values: `ASTRAL_ENV=production` (or unset → fail-closed), `USE_MOCK_AUTH=false`, `KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral`, `KEYCLOAK_ALLOWED_AZP` includes `astral-desktop,astral-mobile,astral-watch` (+ web), `KEYCLOAK_DEVICE_CLIENTS=astral-watch`, `FF_DEVICE_LOGIN=true`, `FF_LLM_STREAMING=true`, all encryption/HMAC/agent secrets set to real high-entropy values (`WEB_SESSION_ENC_KEY`, `OFFLINE_GRANT_ENC_KEY`, `CREDENTIAL_ENCRYPTION_KEY`, `MEMORY_HMAC_KEY`, `AGENT_API_KEY`, `AUDIT_HMAC_SECRET` ≠ placeholder, `KEYCLOAK_CLIENT_SECRET`), `FORWARDED_ALLOW_IPS` set to the TLS proxy, and `DB_POOL_MAX × process_count < Postgres max_connections`. Realm prerequisites (operator): the realm well-known advertises `device_authorization_endpoint`; `astral-watch` has the Device Authorization Grant capability enabled (already verified 2026-07-08); the Apple redirect `com.personalailabs.astraldeep:/oauth2redirect` is a Valid Redirect URI on `astral-mobile` and `astral-desktop`.

**Rationale**: The clients are only production-ready if the backend they target is correctly configured and fail-closed. `.env.example` already carries the right feature-flag defaults; the gaps are secrets, the AZP comment fix (D8), and the redirect-URI realm step. Satisfies FR-018/FR-019/FR-021. Production-posture boot already exits 78 on missing/placeholder secrets (fail-closed) — this is asserted, not changed.

**Alternatives considered**: Assume `.env` is correct — rejected, the env recon was inconclusive and the user explicitly asked to verify it.

---

## D11 — `astralprims` baked version

**Decision**: `backend/requirements.txt` pins `astralprims>=0.2.0`, and **0.2.0 is the version that adds the dashboard primitives** (badge/hero/keyvalue/timeline/rating) that make up the manifest's 35 component types. The action is to **confirm** the production image resolves a wheel whose vocabulary yields exactly the 35 component types the Apple drift guard asserts (`ManifestDriftTests.swift`), and — if the resolved wheel differs — pin it explicitly. No functional change expected; the `ui_protocol.json` drift guard is the mechanical check that server vocabulary == client expectation.

**Rationale**: Resolves the recon ambiguity (051 Swift mirror "assumes 0.3.0" but the 35-type vocabulary is from 0.2.0). Satisfies FR-020 without over-pinning. Honest per Constitution XIII: the claim ("35 types available") is verified against the drift guard, not asserted.

**Alternatives considered**: Force-pin `==0.3.0` — deferred unless the confirmation shows the image needs it; over-pinning without cause is avoided.

---

## D12 — Watch runtime server-override affordance

**Decision (REVISED — the original D12 was infeasible)**: Convert `AstralWatch` from a **watch-only** app into an **embedded companion** app, then deliver the endpoint override from the iPhone companion over `WatchConnectivity` into the watch's own `UserDefaults`, falling back to the xcconfig default.

Concretely: remove `WKWatchOnly` from `WatchInfo.plist`; add `WKCompanionAppBundleIdentifier = com.personalailabs.astraldeep`; embed the watch app in the iOS target (an "Embed Watch Content" copy-files phase); keep `WKApplication = YES`; and set `WKRunsIndependentlyOfCompanionApp = YES` so the watch still installs and runs without the phone app (preserving standalone QR device-login).

Because the watch runs independently, `WatchConnectivity` is an **opportunistic optimization, never a dependency**: the override path MUST consult `WCSession.isCompanionAppInstalled` and fall back to the build-time default when the companion is absent. Not a shared App Group (that would need `com.apple.security.application-groups`, which D7's least-privilege set excludes).

**Rationale**: The working tree has `WKWatchOnly = true` in `AstralApp/WatchInfo.plist`, no `WKCompanionAppBundleIdentifier`, no embed build phase, and zero `WatchConnectivity`/`WCSession` code. Apple defines `WKWatchOnly` as an app "only available on Apple Watch, **with no related iOS app**", and states that independent watch apps "can't rely on the Watch Connectivity framework to transfer data or files from a companion iOS app." The original "paired-iPhone companion settings" design therefore had **no companion to sync from** — it could never have worked. Converting to a companion app is the smallest change that makes FR-011 realizable, and it additionally collapses the store topology (D19). Verified on-device per Constitution X, including the no-companion fallback.

**Alternatives considered**: (a) On-watch preset picker (a list of endpoints baked into xcconfig) — viable and needs no restructuring, but leaves the watch as its own separate App Store record and forgoes companion sync. (b) Drop the watch override entirely (rebuild-only) — rejected, fails FR-011. (c) On-watch free-text URL entry — rejected, unusable UX.

**Sources**: [`WKWatchOnly`](https://developer.apple.com/documentation/bundleresources/information-property-list/wkwatchonly); [Creating independent watchOS apps](https://developer.apple.com/documentation/watchOS-Apps/creating-independent-watchos-apps); [`WCSession`](https://developer.apple.com/documentation/watchconnectivity/wcsession); [`isCompanionAppInstalled`](https://developer.apple.com/documentation/watchconnectivity/wcsession/iscompanionappinstalled) (retrieved 2026-07-08).

---

## D13 — `FF_LLM_STREAMING` on-device verification

**Decision**: Verify live narrative streaming on all three signed clients by driving an ordinary chat turn against the live backend (`FF_LLM_STREAMING=true`) and confirming the streamed `ui_stream_data` narrative renders coherently and is superseded by the final `ui_render` — with the watch as the highest-risk surface. `AstralCore/Streaming.swift` already dispositions the frame; this is an on-device render check, not a code change (unless a defect is found, in which case it is fixed with a test).

**Rationale**: The drift guard proves a disposition exists, not that narrative Text-markdown frames render correctly on-device. Satisfies FR-023/SC-007 and Constitution X/XII (verify every client). Fail-safe available (`FF_LLM_STREAMING=false`) but not used per clarification.

**Alternatives considered**: Trust the unit disposition only — rejected, insufficient for Principle X.

---

## D14 — Release CI workflow shape

**Decision**: `apple-release.yml`, `runs-on: macos-15`, triggered on `push: tags: ['apple-v*']` + `workflow_dispatch`. The `apple-v*` namespace is chosen because it does **not** begin with `v`: `release-windows.yml` triggers on `tags: ["v*"]`, and a GitHub Actions `*` matches any character except `/`, so a `v`-prefixed Apple tag (e.g. `v-apple-1.0.0`) **would** also be matched by `v*` and would double-fire the Windows release, whose tag-vs-`__version__` guard then fails the run. Only a non-`v` prefix is provably disjoint. Steps: checkout → select Xcode → tag-vs-`MARKETING_VERSION` guard → import signing cert + profile from secrets into a temp keychain → set build number from run → `xcodebuild archive` per target → `-exportArchive` (app-store) → `altool --validate-app` → `altool --upload-app` → optional API-driven submit-for-review. All secrets (`APPLE_DISTRIBUTION_CERT_P12_BASE64`, `APPLE_CERT_PASSWORD`, `APPLE_PROVISION_PROFILE_BASE64`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8_BASE64`, `APPLE_TEAM_ID`) are GitHub secrets. The existing six backend gates + `apple-ci.yml` are untouched.

**Rationale**: Direct analogue of `release-windows.yml` (tag-triggered, version-guarded, secret-injected, additive). Separate tag namespace avoids double-firing with the Windows release. Satisfies FR-015/FR-016/FR-017 and Constitution XI (additive).

**Alternatives considered**: Reuse the `v*` tag — rejected, would fire both release workflows. Put release steps in `apple-ci.yml` — rejected, mixes PR compile gate with tag-only signed release (FR-016 separation).

---

## D15 — App icon assets

**Decision (REVISED — artwork now supplied; icons generated in this feature)**: Derive every Apple icon from the operator's `android-client/Android Raw Assets/AppIcon.png` (3000×3000, RGB + an alpha channel that is **100% opaque**) using the committed `apple-clients/Scripts/generate_app_icons.py` — stdlib Python + the Apple `sips` tool, **zero new dependencies** (Constitution V).

Per-platform, because the platforms genuinely differ:

- **iOS + watchOS** — a single 1024×1024 **square, full-bleed, fully opaque** PNG each. The system masks corners (rounded-rect on iOS, circle on watchOS), so rounding MUST NOT be baked in. An alpha channel fails upload validation as **ITMS-90717** ("The App Store Icon … can't be transparent nor contain an alpha channel"). Stripping the master's alpha is *lossless* here because it is already fully opaque; the generator refuses to proceed if real transparency is ever present.
- **macOS** — the classic `AppIcon.appiconset` workflow does **not** auto-mask, so each of the ten slots (16/32/128/256/512 at @1x and @2x) must itself supply the rounded-rect shape inside a transparent gutter. Apple's macOS grid places an 824×824 body on the 1024 canvas (~100 px gutter) with a ~185.4 px continuous-corner radius. Transparency here is expected and is **not** an ITMS-90717 violation — that rule governs the iOS/watchOS App Store icon slot.

The generator ships a `--check` mode asserting slot sizes, iOS/watch opacity, and macOS gutter retention, so an icon regression fails loudly rather than at upload.

**Verified**: the generator ran, `sips` independently confirms `hasAlpha: no` on the three 1024 icons and `hasAlpha: yes` on the macOS slots, and `xcodebuild` (iOS Simulator, Debug) **succeeded** — `actool` emitted `AppIcon60x60@2x.png` and `AppIcon76x76@2x~ipad.png`, and `Assets.car` carries phone+pad renditions in default and dark appearances.

**Alternatives considered**: Hand-cut each size — rejected, error-prone. `sips`-only alpha strip — rejected, `sips` has no reliable "remove alpha channel" for PNG (round-tripping via JPEG is lossy); a stdlib re-encode is exact. Icon Composer (`.icon`, Xcode 26) — deferred; the project uses classic asset catalogs, which remain valid for submission.

**Sources**: [ITMS-90717](https://developer.apple.com/forums/thread/96003); [HIG — App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons); [Configuring your app icon](https://developer.apple.com/documentation/xcode/configuring-your-app-icon) (retrieved 2026-07-08).

---

## D16 — App Store screenshots

**Decision**: Capture screenshots from the **real Apple apps** at exactly one accepted pixel size per required device class, then composite AstralDeep brand/caption overlays. Required classes for this record: **iPhone 6.9"**, **iPad 13"** (the iOS app declares `TARGETED_DEVICE_FAMILY = "1,2"`, and the build emits `AppIcon76x76@2x~ipad.png`, so iPad is supported), **Mac**, and **Apple Watch**.

Accepted sizes (pick one per class, and use the **same** Apple Watch size across all localizations):

| Class | Accepted pixel sizes (portrait; landscape swaps W/H) |
|---|---|
| iPhone 6.9" | 1260×2736 · 1290×2796 · 1320×2868 |
| iPad 13" | 2048×2732 · 2064×2752 |
| Mac | 1280×800 · 1440×900 · 2560×1600 · 2880×1800 (16:10) |
| Apple Watch | 422×514 · 416×496 · 410×502 · 396×484 · 368×448 · 312×390 |

1–10 screenshots per class. Overlays are explicitly permitted; the underlying pixels must show the app **in use** — not a title card, login, or splash screen (Guideline 2.3.3).

**Rationale**: No supplied Android asset can satisfy these (see D17). Native capture is the only path that is both dimensionally exact and 2.3.3-compliant. Simulator capture (`xcrun simctl io <device> screenshot`) yields native-resolution PNGs; macOS needs a window capture. Operator-assisted, because the automation environment cannot tap/type in a simulator.

**Alternatives considered**: Reframe the Android/desktop renders onto Apple canvases — rejected: aspect ratios mismatch on every class (phone 9:16 vs ~0.46; tablets 16:9 vs iPad 4:3; desktop 16:9 vs Mac 16:10) and the pixels show the Android/web UI, a real 2.3.3 rejection risk.

**Sources**: [Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/); [App Review Guidelines §2.3.3](https://developer.apple.com/app-store/review/guidelines/) (retrieved 2026-07-08).

---

## D17 — Brand-asset reuse mapping

**Decision**: Record the transfer status of each supplied asset explicitly (FR-032). Exactly one asset yields shippable Apple pixels.

| Supplied asset (actual pixels) | Status | Apple use |
|---|---|---|
| `AppIcon.png` — 3000×3000, opaque | **Usable** | Master for **all** Apple icons (D15) |
| `feature-graphic.png` — 1024×500 | **Not transferable** | Google-Play-only slot; App Store has no feature graphic |
| `1920X1080.png` — actually 5760×3240 (16:9) | Reference-only | Desktop/web dashboard render; Mac needs 16:10 native capture |
| `2560x1440.png` — actually 7680×4320 (16:9) | Reference-only | As above |
| `phone-{1,2}-*.png` — 1080×1920 (9:16) | Reference-only | Composition/shot-list for iPhone captures |
| `tablet7-*`, `tablet10-*` — 16:9 landscape | Reference-only | Composition/shot-list for iPad captures |

**Rationale**: Honest accounting (Constitution XIII) — an asset that cannot ship must be recorded as such, not silently dropped. The two `*x*.png` files are misleadingly named: they are 3× supersampled, so their filenames do not describe their pixels.

---

## D18 — Retire the XcodeGen project generator

**Decision**: Delete `apple-clients/project.yml`. The committed `AstralApp.xcodeproj` is the single canonical project, documented in the README.

**Rationale**: Three converging reasons. (a) It had already drifted — `bundleIdPrefix: com.kyopenscience.astral` and URL scheme `astral` versus the shipped `com.personalailabs.astraldeep`, so regenerating would break the OAuth redirect. (b) XcodeGen cannot emit the "Embed Watch Content" copy-files phase the companion watch app now requires, so a regenerated project would silently ship **without the watch app** — a failure that still compiles. (c) Its own header already declared it "OPTIONAL … never required by CI or runtime." Retiring it removes an entire drift class and one source of project truth. Satisfies FR-012; replaces the old SC-005 ("regenerating reproduces a working redirect") with "exactly one canonical project exists."

**Alternatives considered**: Fix it and document a post-generation embed step — rejected, a footgun that fails silently. Investigate whether current XcodeGen can express the phase — rejected as scope for a file nothing depends on.

**Source**: [XcodeGen #1463 — no Embed Watch Content phase](https://github.com/yonaskolb/XcodeGen/issues/1463) (retrieved 2026-07-08).

---

## D20 — The embed phase must be platform-filtered to iOS

**Decision**: The "Embed Watch Content" copy-files phase added to `AstralApp` (D12) MUST carry a **platform filter restricting it to iOS** (in the Xcode UI, the "Filters" control beside the embedded content, with macOS unchecked; in `project.pbxproj`, `platformFilters` on the phase's build file).

**Rationale**: `AstralApp` is not two targets — it is **one multiplatform target** with `SUPPORTED_PLATFORMS = "iphoneos iphonesimulator macosx"` and `TARGETED_DEVICE_FAMILY = "1,2"`. An unfiltered embed phase therefore also runs for the **macOS** destination, attempting to embed a watchOS app into the Mac App Store archive. A macOS app must not contain a watch app; Apple's documented mechanism for exactly this case is per-platform build-phase/embedded-content filters. Without the filter the iOS build looks fine and the macOS archive is silently wrong — the same failure mode class as the retired generator (D18).

**Alternatives considered**: Split `AstralApp` into separate iOS and macOS targets — rejected, a much larger restructuring of a shipped, verified client for no other benefit. Skip the filter and hope the macOS archive ignores the phase — rejected, unverified and exactly the kind of silent breakage this feature exists to remove.

**Sources**: [Customizing the build phases of a target](https://developer.apple.com/documentation/xcode/customizing-the-build-phases-of-a-target); [Apple Developer Forums — multiplatform target, uncheck macOS in embedded-content Filters](https://developer.apple.com/forums/thread/708682); [XcodeGen #1463](https://github.com/yonaskolb/XcodeGen/issues/1463) (retrieved 2026-07-08).

---

## D19 — App Store record topology

**Decision**: **One** App Store Connect record, Universal Purchase, carrying two platform versions (iOS, macOS); the watch app ships embedded inside the iOS build. One store listing.

**Rationale**: The iOS and macOS targets both set `PRODUCT_BUNDLE_IDENTIFIER = com.personalailabs.astraldeep`. Bundle ids are unique per record, and Universal Purchase is precisely "same Apple ID, SKU, and bundle ID" across platforms — so iOS+macOS *must* be one record with two platform versions. Once the watch becomes an embedded companion (D12), it is carried inside the iOS app bundle rather than being its own watch-only record. Net: 1 record, 1 listing, 2 archives, 2 uploads, 1 submission. (Had the watch remained `WKWatchOnly`, it would have been a **separate** record — Apple explicitly blocks embedding a watch-only app in a companion.)

This corrects the earlier spec text that assumed three apps, three listings, three archives.

**Sources**: [Add platforms / Universal Purchase](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-platforms/); [Add watchOS app information](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-watchos-app-information) (retrieved 2026-07-08).

---

## Open verification items (carried into tasks, not blockers)

- Confirm the production image's resolved `astralprims` wheel yields the 35-type vocabulary (D11).
- Confirm the realm well-known advertises `device_authorization_endpoint` and the Apple redirect is registered on the shared clients (D10) — operator/realm step.
- Operator to supply Team ID, distribution cert/profile, App Store Connect app records + API key, master icon, and store-listing metadata before the live upload/submit step (blocking prerequisites).
