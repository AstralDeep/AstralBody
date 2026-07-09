# Feature Specification: Apple Clients Production Release

**Feature Branch**: `053-apple-production-release`

**Created**: 2026-07-08

**Status**: Draft

**Input**: User description: "Get the apple client builds ready for production deployment. The backend has had major updates since the last time we chatted. Be thorough and make sure all platforms work as intended and are consistent across all clients. Make sure the .env is set up correctly. Reference and update knowledge stored in the obsidian vault."

## Overview

Feature 051 delivered the Apple client family (iOS, macOS, watchOS) as functionally complete, dev-verified SDUI clients that build unsigned and run against the local/sandbox backend. This feature takes them the rest of the way to a **public App Store release**: real code signing and entitlements, App Store compliance artifacts (icon, privacy manifest, ATS, export compliance), build-time endpoint configuration (no hardcoded values), retirement of the drifted XcodeGen generator in favour of a single canonical project, reconciliation of the OAuth-client drift between code and docs, generation of the Apple icon set from the operator's brand master, a signed automated release pipeline, a verified production `.env` posture for the backend the clients target, end-to-end verification on signed builds of every platform, and an update of the Obsidian knowledge vault to reflect the shipped release process.

No product code stubs remain from 051 — every item here is packaging, signing, store-compliance, configuration indirection, cross-client consistency, verification, or documentation. Backend contract drift since 051 is zero (the server→client manifest is byte-identical; the drift guard still asserts 47 push / 35 component / 67 accept types); the only client-observable backend change is that narrative prose now streams over the already-dispositioned streaming frame, which must be verified rendering on-device.

Two structural facts, established by inspecting the working tree, shape this feature:

1. **Store topology is one record, not three.** The iOS and macOS apps share the bundle id `com.personalailabs.astraldeep`, so they *must* be a single App Store Connect record with two platform versions (Universal Purchase). The watch app is converted from a watch-only app into an **embedded companion** that ships inside the iOS build. Net: **one record, one listing, two archives** (iOS-with-embedded-watch, macOS).
2. **Brand assets exist but only partly transfer.** The operator supplied `android-client/Android Raw Assets/`. Exactly one asset yields shippable Apple pixels — the 3000×3000 `AppIcon.png` master, from which every Apple icon is derived. No screenshot transfers: each Android/desktop render mismatches Apple's required aspect ratios, and App Review Guideline 2.3.3 requires screenshots of the real app in use. Screenshots are therefore captured natively and given brand overlays.

## Clarifications

### Session 2026-07-08

- Q: What is the target distribution channel? → A: **Public App Store.** Distribution signing, marketing icon, privacy manifest, macOS App Sandbox + Hardened Runtime, and ATS compliance are all mandatory.
- Q: What should the signed Release build point at, and how? → A: **Build-time configuration** (xcconfig/Info.plist indirection), defaulting to `sandbox.ai.uky.edu` + realm `iam.ai.uky.edu/realms/Astral`. Remove the hardcoded `#if DEBUG` endpoint selection.
- Q: How do we resolve the iOS/macOS OAuth client-id + bundle-id conflict? → A: **Keep the shipped identities** — OAuth clients `astral-mobile` / `astral-desktop` / `astral-watch` and bundle-id family `com.personalailabs.astraldeep`. Fix the generator config, README, and realm docs to match the shipped code.
- Q: What is in scope for this feature? → A: Signed release CI pipeline (`apple-release.yml`); `FF_DEVICE_LOGIN` stays **ON** (watch QR); `FF_LLM_STREAMING` stays **ON** (`.env` `true`) and must be **verified on-device**, not disabled. **Cresco (feature 050) is out of scope.**
- Q: For the macOS app specifically, which distribution form? → A: **Mac App Store** (uploaded to App Store Connect like iOS). App Sandbox is mandatory and Hardened Runtime is enabled; there is no separate Developer ID direct-download build.
- Q: Is the Definition of Done "submission-ready" or an actual live App Store submission? → A: **Actually submit to review.** The feature performs the real archive → sign → upload → **submit for review**. This makes the operator's Apple Team ID + distribution certificates, App Store Connect app record, and complete store-listing metadata **blocking prerequisites within this feature**, and pulls the App Store Connect listing (metadata, screenshots, privacy policy, age rating, export compliance) into scope.

### Session 2026-07-08b — brand assets & watch topology

Triggered by the operator supplying `android-client/Android Raw Assets/` (10 PNGs) and by a verification re-run of the spec against the working tree.

- Q: The watch target is `WKWatchOnly = true` — Apple defines that as "only available on Apple Watch, with **no related iOS app**", so `WatchConnectivity` has no counterpart and the previously-specified "paired-iPhone companion settings" override (old D12) is impossible. How is the watch runtime override satisfied? → A: **Convert the watch to an embedded companion app** — remove `WKWatchOnly`, set `WKCompanionAppBundleIdentifier` to the iOS bundle id, and embed the watch app in the iOS target ("Embed Watch Content" copy-files phase).
- Q: Should the companion watch app still install/run without the iPhone app? → A: **Yes** — `WKRunsIndependentlyOfCompanionApp = YES`, preserving standalone QR device-login. Consequence (per Apple): `WatchConnectivity` becomes an **opportunistic optimization only**; the override MUST check `isCompanionAppInstalled` and fall back to the build-time default.
- Q: How should App Store screenshots be produced, given no Android asset matches Apple's required dimensions and Guideline 2.3.3 requires the real app in use? → A: **Native captures + brand overlay** — capture the actual iOS/iPad/macOS/watchOS app at exact accepted sizes, then composite AstralDeep caption/brand overlays (overlays are explicitly permitted by 2.3.3).
- Q: Should the Apple icon assets be generated now from the supplied master? → A: **Yes.** Done in this feature: `apple-clients/Scripts/generate_app_icons.py` (stdlib + `sips`, zero new dependencies) derives them from `AppIcon.png`.
- Q: XcodeGen cannot emit the required "Embed Watch Content" phase, so regenerating from `apple-clients/project.yml` would silently drop the watch app. What happens to it? → A: **Retire `project.yml`.** The committed `.xcodeproj` becomes the single canonical project, documented in the README. This removes the bundle-id/URL-scheme/ATS drift class entirely.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce an App-Store-submittable signed build for every Apple platform (Priority: P1)

As the release engineer, I can produce the two archives — iOS (carrying the embedded watch app) and macOS — and have each pass App Store Connect validation with no signing or compliance errors, so the version is ready to submit for review.

**Why this priority**: This is the core deliverable. Without a signed, compliant archive, none of the apps can reach users through the App Store; everything else supports or verifies this outcome.

**Independent Test**: Archive both platforms and run App Store validation (the archive→export→validate path). Each archive validates with a distribution signing identity, complete icon set, privacy manifests, ATS-clean Release networking, export-compliance declaration, and a unique build number — zero validation errors.

**Acceptance Scenarios**:

1. **Given** a distribution signing identity is available, **When** the iOS target is archived and validated, **Then** validation reports no missing-icon, missing-privacy-manifest, ATS, entitlement, or signing errors.
2. **Given** the macOS target, **When** it is archived, **Then** it builds with App Sandbox and Hardened Runtime enabled and is Mac-App-Store-eligible.
3. **Given** the watch app is embedded in the iOS target, **When** the iOS app is archived, **Then** the archive contains the watch app, which carries its own export-compliance declaration, its own app icon, and its own App Store provisioning profile, and the combined archive validates.
4. **Given** two successive archives of the same target, **When** each is exported, **Then** they carry distinct, monotonically increasing build numbers without manual editing.
5. **Given** the App Store icon slots, **When** an archive is validated, **Then** no icon carries an alpha channel (which would fail validation as ITMS-90717) and the macOS icon slots retain their transparent gutter.

---

### User Story 2 - Ship the correct production endpoint via build-time configuration (Priority: P2)

As the release engineer, I can point a Release build at the production backend and Keycloak realm through build-time configuration rather than hardcoded source, and the watch can be repointed at runtime, so environments are changed without editing code and no dev endpoint ships in a Release build.

**Why this priority**: Correct, non-hardcoded endpoint configuration is a production-readiness requirement (no hardcoded endpoints) and directly protects users from a Release build that points at a dev host. It builds on the signed-build slice.

**Independent Test**: Inspect a Release build's resolved backend URL + realm and confirm they come from configuration (default `sandbox.ai.uky.edu`). Change the configuration value and rebuild — the app repoints with no source change. Confirm the watch honours a companion-pushed override *and* falls back correctly when no companion is installed. Search the Release-reachable source for hardcoded localhost/dev endpoints and find none.

**Acceptance Scenarios**:

1. **Given** the default configuration, **When** a Release build launches, **Then** it targets `sandbox.ai.uky.edu` and realm `iam.ai.uky.edu/realms/Astral`.
2. **Given** a changed configuration value, **When** the app is rebuilt, **Then** it targets the new endpoint with no code edit.
3. **Given** a signed watch build whose iPhone companion is installed, **When** the operator sets a server override in the companion, **Then** the watch targets the chosen endpoint without a rebuild.
4. **Given** a signed watch build with **no** companion installed (`isCompanionAppInstalled == false`), **When** the watch launches, **Then** it falls back to the build-time default endpoint and remains fully usable via QR device-login — it never blocks on the companion.
5. **Given** a Release build, **When** its reachable source/config is inspected, **Then** no hardcoded `localhost`/`127.0.0.1`/dev endpoint is present.

---

### User Story 3 - One canonical project and one consistent client identity (Priority: P2)

As a developer cloning the repo, there is exactly one canonical Xcode project whose bundle identifiers, URL scheme, OAuth client ids, and shared schemes agree with the README and the backend realm docs, so a clean clone builds every target and no second source of project truth can silently diverge.

**Why this priority**: The drift (committed `com.personalailabs.astraldeep` vs the XcodeGen generator's `com.kyopenscience.astral`/scheme `astral`, plus a missing watch shared scheme and a doc-vs-code OAuth-client conflict) can silently break authentication and blocks clean-clone/CI watch builds. The generator additionally cannot express the "Embed Watch Content" phase the companion watch app now requires, so regenerating would silently drop the watch app. It is retired rather than reconciled.

**Independent Test**: On a clean checkout, build every scheme by name (including `AstralWatch`). Confirm no project generator remains, that the README documents the committed `.xcodeproj` as canonical, and that the realm docs name the same client ids the code uses.

**Acceptance Scenarios**:

1. **Given** a clean checkout, **When** each shared scheme (including `AstralWatch`) is built by name, **Then** all resolve and compile with no manual project fix-up.
2. **Given** the repository, **When** it is searched for a project generator, **Then** `apple-clients/project.yml` no longer exists and the README names the committed `.xcodeproj` as the single canonical project.
3. **Given** the realm settings docs, **When** they are compared to the client code, **Then** they name the same OAuth client ids (`astral-mobile`/`astral-desktop`/`astral-watch`) and redirects with no unresolved conflict note.
4. **Given** the embedded watch app, **When** its bundle id is compared to the iOS app's, **Then** the iOS bundle id is a strict prefix of the watch bundle id (`com.personalailabs.astraldeep` → `…​.watch`), as Apple requires for a companion.

---

### User Story 4 - Automated signed release pipeline that submits to review (Priority: P2)

As the release engineer, I can push a version tag and have CI archive, export, notarize, upload, and submit each Apple app to App Store review using injected secrets, so releases are reproducible and no signing material lives in the repo — without disturbing the existing backend CI gates.

**Why this priority**: Automation makes the signed build and submission repeatable and auditable and mirrors the existing Windows release pipeline; it depends on US1's signing being in place. Because the Definition of Done is an actual submission, this pipeline performs the real upload and submit-for-review once operator credentials are present.

**Independent Test**: Trigger the workflow on a tag and observe it archive/sign/upload/submit the two platform builds (iOS with the embedded watch app, and macOS) into the single App Store Connect record, using CI-injected secrets. Confirm the six backend CI gates and the unsigned Apple compile matrix are unchanged and still pass, and that no signing secret is committed.

**Acceptance Scenarios**:

1. **Given** a version tag is pushed and operator secrets are configured, **When** the release workflow runs, **Then** it produces two signed archives — iOS (containing the embedded watch app) and macOS — uploads both to the single Universal Purchase record, and submits the version for review.
2. **Given** the existing CI, **When** the release workflow is added, **Then** the six backend gates and the unsigned Apple compile matrix are untouched and remain green.
3. **Given** the repository, **When** it is scanned for secrets, **Then** no signing certificate, private key, or App Store Connect key is present in tracked files.
4. **Given** missing or invalid signing material, **When** the workflow runs, **Then** it fails clearly at the signing/upload step without producing an unsigned artifact or leaking partial secrets.

---

### User Story 5 - Verified production backend & `.env` posture for the deployment the clients target (Priority: P3)

As the operator, I have a verified `.env` and realm configuration for the backend the Apple clients connect to, so device-login, streaming, auth, and connection pooling are correct in production and fail closed when misconfigured.

**Why this priority**: The clients are only as production-ready as the backend they target; this verifies the server side without changing client behavior. It is P3 because the backend already runs — this confirms and documents the correct posture.

**Independent Test**: Validate the deployment `.env` against a documented production checklist: `ASTRAL_ENV`, Keycloak realm/authority, `KEYCLOAK_DEVICE_CLIENTS` including `astral-watch`, `FF_DEVICE_LOGIN` on, `FF_LLM_STREAMING` true, DB pool sizing within Postgres limits, and the baked `astralprims` version matching the client-expected vocabulary. Confirm the realm well-known advertises the device-authorization endpoint and that production-posture boot refuses missing/placeholder secrets.

**Acceptance Scenarios**:

1. **Given** the deployment `.env`, **When** it is checked against the production checklist, **Then** every required key is set to a production-correct value with no placeholder.
2. **Given** the realm, **When** its well-known document is fetched, **Then** it advertises the device-authorization endpoint and lists the shipped redirect URIs / azp values so watch QR login does not fail closed.
3. **Given** a production-posture boot with a missing/placeholder secret, **When** the service starts, **Then** it refuses to boot (documented fail-closed exit) rather than serving insecurely.
4. **Given** the running production image, **When** the served component vocabulary is compared to the client drift guard, **Then** they match (no version mismatch).

---

### User Story 6 - End-to-end verification on signed builds across all three clients (Priority: P3)

As the release engineer, I have evidence that each signed build works on its real device family — sign-in, session persistence, watch QR login, and live narrative streaming — and that the outstanding 051 evidence is complete, so I can trust the release behaves as intended and stays consistent with the other clients.

**Why this priority**: Verification is the proof that "all platforms work as intended and are consistent across all clients." It depends on signed builds (US1) and correct config (US2/US5) existing.

**Independent Test**: Install each signed build on its device family and capture evidence for: PKCE sign-in, keychain/session persistence across reinstall, watch QR device-login, and live `FF_LLM_STREAMING` narrative streaming rendering (watch highest risk). Complete 051 T046 (round-trip p95 timing) and T041 (browser short-code path).

**Acceptance Scenarios**:

1. **Given** a signed iOS/macOS build, **When** the user signs in via PKCE, **Then** sign-in succeeds and the session persists across an app reinstall.
2. **Given** a signed watch build, **When** the user scans the QR code, **Then** device-login completes end-to-end.
3. **Given** an ordinary chat turn with streaming enabled, **When** the assistant responds, **Then** the streamed narrative renders correctly on iOS, macOS, and watchOS and matches the final authoritative render.
4. **Given** the 051 evidence set, **When** it is reviewed, **Then** the previously-unchecked round-trip timing and browser short-code items are captured.

---

### User Story 7 - Updated knowledge base reflecting the shipped release process (Priority: P3)

As a future maintainer, I can read the Obsidian vault and the repo docs and learn exactly how the Apple clients are signed, configured, and released to production, with all prior doc-vs-code conflicts resolved.

**Why this priority**: Durable knowledge capture is required by the project's practices and the user's request, but it follows the work it documents.

**Independent Test**: The vault passes its own lint; a new Apple release-pipeline page exists; the affected pages (Apple Clients, Keycloak realm, CI gates, feature flags, feature timeline, project hub) are revised to the shipped state; the source anchor cites the new commit; the log and index are updated; and no unresolved conflict blocks remain. The repo README and realm-settings doc match the shipped code.

**Acceptance Scenarios**:

1. **Given** the shipped release process, **When** the vault is reviewed, **Then** a release-pipeline page documents signing/config/upload/submission and the previously-conflicting client-id and macOS-keychain notes are resolved.
2. **Given** the repo docs, **When** the README and realm-settings doc are read, **Then** they match the shipped bundle ids, URL scheme, and OAuth client ids.

---

### User Story 8 - Store-ready brand assets and a complete listing (Priority: P2)

As the release engineer, the App Store record carries a correct icon on every platform and a screenshot set for every required device class, derived from the supplied brand assets wherever they legitimately transfer and captured natively where they do not — so the version can actually be submitted for review.

**Why this priority**: Missing icons or screenshots are hard upload/submission blockers, equal in force to signing. The operator has now supplied a brand master, which removes the icon blocker; screenshots remain and must be produced correctly rather than reused from a different platform's UI.

**Independent Test**: Run the icon generator's check and confirm every emitted slot has the right size, that iOS/watch App Store icons carry **no** alpha, and that macOS slots keep their gutter. Confirm a screenshot set exists at exactly one accepted size per required class (iPhone 6.9", iPad 13", Mac, Apple Watch), each showing the real Apple app in use, and that the App Store Connect listing is complete.

**Acceptance Scenarios**:

1. **Given** the supplied `AppIcon.png` master, **When** the icon generator runs, **Then** it emits the iOS/watch 1024×1024 opaque icons and the ten macOS rounded-rect slots, and its self-check passes.
2. **Given** the generated catalog, **When** the app is built, **Then** the asset compiler produces the app icon for every idiom with no unassigned-slot or alpha warnings.
3. **Given** the required device classes, **When** screenshots are uploaded, **Then** each is at an exactly-accepted pixel size for its class and depicts the real Apple app in use (not a splash/welcome screen alone, per Guideline 2.3.3).
4. **Given** an Android-only asset (e.g. the Play feature graphic), **When** the asset mapping is reviewed, **Then** it is explicitly recorded as not transferable rather than silently unused.

---

### Edge Cases

- **Watch without its companion**: When the watch app is installed without the iPhone app, `WatchConnectivity` has no counterpart. The watch MUST fall back to its build-time endpoint and stay fully usable via QR device-login — the override is an optimization, never a dependency.
- **Icon alpha regression**: If any App Store icon slot regains an alpha channel (e.g. someone re-exports the master with transparency), upload validation fails with ITMS-90717. The asset generator's check MUST catch this before submission.
- **macOS icon gutter**: Conversely, the macOS icon slots MUST retain transparency (the rounded-rect gutter). A blanket "strip all alpha" step would break them.
- **Screenshot dimension mismatch**: App Store Connect accepts only exact pixel dimensions; an off-by-one or a wrong aspect ratio is rejected at upload. Reusing an Android render (9:16 phone, 16:9 tablet) can never satisfy iPhone 6.9" or iPad 13".
- **Missing signing material**: What happens when the release pipeline runs without a distribution certificate or App Store Connect key? It must fail clearly (not silently produce an unsigned/invalid artifact) and must not leak partial secrets.
- **Endpoint override to an unreachable host**: When the watch is repointed at an unreachable/misconfigured endpoint, sign-in must fail closed with a clear error, not hang or crash.
- **Realm without device grant**: When the realm well-known does not advertise the device-authorization endpoint, watch QR login must fail closed with an actionable message rather than a generic failure.
- **Streaming render on constrained watch UI**: When a long narrative streams to the watch, it must render coherently (dedupe by sequence, clear on terminal) and never leave a stuck partial; a client that ignores stream frames must still receive the final render.
- **Silent macOS mis-embed**: `AstralApp` is one multiplatform target. If the "Embed Watch Content" phase is not platform-filtered to iOS, the **macOS** archive attempts to embed a watchOS app — the iOS build still looks fine, so the breakage is silent until Mac App Store validation. The filter must be asserted, not assumed.
- **Reintroducing a second project source**: The XcodeGen generator was retired because it drifted *and* could not express the embed phase. Re-adding any generator would recreate a source of project truth that silently diverges from the committed `.xcodeproj`.
- **Build-number collision**: When two archives are produced close together, their build numbers must not collide (App Store Connect rejects duplicates).
- **DB pool exhaustion**: When pool size × process count exceeds Postgres `max_connections`, connections are exhausted; the deployment posture must keep the product of these within limits.

## Requirements *(mandatory)*

### Functional Requirements

**Signing, entitlements, and store compliance**

- **FR-001**: Release builds for iOS, macOS, and watchOS MUST be produced with a distribution code-signing identity (Apple Developer Team provided by the operator), with no manual per-build Xcode signing selection required.
- **FR-002**: Each target MUST declare the entitlements its capabilities require, and no more (least privilege), stored as version-controlled entitlement definitions. As built, this is exactly **one** file — `apple-clients/AstralApp/AstralApp-macOS.entitlements` (`com.apple.security.app-sandbox` + `com.apple.security.network.client`) — applied only to the macOS Release configuration via `CODE_SIGN_ENTITLEMENTS[sdk=macosx*]`. There is **no iOS or watch entitlements file** and **no `keychain-access-groups`** entitlement: tokens are stored under the default per-app keychain access group, which works without a Keychain Sharing capability, so requesting one would be an unnecessary entitlement (see research D21).
- **FR-003**: The macOS app MUST ship to the Mac App Store; its Release configuration MUST enable App Sandbox (mandatory for Mac App Store) and Hardened Runtime, with sandbox entitlements scoped for a network + keychain client. No separate Developer ID direct-download build is produced.
- **FR-004**: The app icon set MUST contain every required rendered icon asset for each platform, derived from the operator-supplied master. The iOS and watchOS App Store icons MUST be 1024×1024 square and **fully opaque** (an alpha channel fails validation as ITMS-90717); the macOS slots MUST supply the rounded-rect shape with its transparent gutter at all ten sizes. Icon derivation MUST be reproducible by a committed, dependency-free script.
- **FR-004a**: The watch target MUST have its own asset catalog with its app icon wired (`ASSETCATALOG_COMPILER_APPICON_NAME`), which it currently lacks entirely.
- **FR-005**: A privacy manifest MUST declare the app's data-collection and required-reason API usage. Because the embedded watch app is its own `.app` bundle, **each app target ships its own manifest**, and each MUST live inside its file-system-synchronized source folder to be bundled: `apple-clients/AstralApp/AstralApp/PrivacyInfo.xcprivacy` and `apple-clients/AstralWatch/PrivacyInfo.xcprivacy`. Each declares `NSPrivacyTracking = false` and the `UserDefaults` required-reason category `CA92.1`. **No microphone or speech-recognition usage strings are required and none are added**: the watch dictates via the system `TextFieldLink` sheet (out-of-process — the app never calls the microphone or Speech APIs) and only plays audio via speech synthesis, so declaring `NSMicrophoneUsageDescription`/`NSSpeechRecognitionUsageDescription` would advertise capabilities the app does not use (see research D23).
- **FR-006**: Release network configuration MUST be App-Transport-Security compliant — no blanket arbitrary-loads exception may apply to Release. As built, `NSAllowsArbitraryLoads` is removed from both Info.plists and each carries only `NSAllowsLocalNetworking = true`, **unconditionally**: a static Info.plist cannot be made per-configuration without duplicating it, and `NSAllowsLocalNetworking` is App-Store-safe — it relaxes ATS only for loopback/`.local` and never permits an insecure load to a public host, so Release remains ATS-compliant with it present (verified: `NSAllowsArbitraryLoads` absent from the built macOS Release product; see research D22).
- **FR-007**: The watch target MUST declare export-compliance (non-exempt-encryption) status consistent with the companion phone target.
- **FR-008**: Every archive MUST carry a marketing version and a unique, monotonically increasing build number, applied automatically without manual source edits.

**Build-time configuration**

- **FR-009**: The backend base URL and the Keycloak realm/authority MUST be resolved from build-time configuration rather than hardcoded per build configuration, defaulting to the sandbox production endpoint and realm.
- **FR-010**: No source or configuration reachable in a Release build may contain a hardcoded localhost or dev endpoint.
- **FR-011**: The watch MUST provide a supported way to override its server endpoint at runtime (without a rebuild), delivered from its iPhone companion. Because the watch app also runs independently, this override MUST be treated as an opportunistic optimization: when no companion is installed the watch MUST fall back to its build-time default and remain fully functional.
- **FR-011a**: The watch app MUST be converted from a watch-only app to an **embedded companion** app (no `WKWatchOnly`; `WKCompanionAppBundleIdentifier` set to the iOS bundle id; embedded in the iOS target) while retaining independent installation and execution (`WKRunsIndependentlyOfCompanionApp`).
- **FR-011b**: Because `AstralApp` is a **single multiplatform target** building both `iphoneos` and `macosx`, the "Embed Watch Content" phase (and its target dependency) MUST be **platform-filtered to iOS** (`platformFilter = ios`). An unfiltered phase would attempt to embed a watchOS app into the macOS archive; a macOS app must not contain a watch app. **Verified**: the iOS product and the iOS `.xcarchive` both contain `Watch/AstralWatch.app`, and the macOS product contains **no** watch app at all.

**Cross-client consistency**

- **FR-012**: The committed `.xcodeproj` MUST be the single canonical project. The XcodeGen configuration (`apple-clients/project.yml`) MUST be retired, because it has drifted from the shipped bundle-id/URL-scheme and cannot express the "Embed Watch Content" phase the companion watch app requires — regenerating from it would silently produce a project with no watch app. The README MUST document the committed project as canonical.
- **FR-013**: iOS, macOS, and watchOS MUST use the shipped OAuth client identities (`astral-mobile` / `astral-desktop` / `astral-watch`), and the backend realm-settings documentation MUST name the same identities and redirects with no unresolved conflict.
- **FR-014**: A shared scheme MUST exist for every buildable target, including the watch, so a clean clone and CI can build each target by name.

**Release automation**

- **FR-015**: A tag-triggered release workflow MUST archive, sign, export, **validate**, and **upload** the **two** platform builds — iOS (containing the embedded watch app) and macOS — into the single Universal Purchase App Store Connect record, using CI-injected secrets, and MUST fail clearly (without producing an unsigned artifact or leaking secrets) when signing material is missing. The pipeline automates through upload; the final **Submit for Review is operator-performed**, because Apple's API refuses an incomplete listing and pressing Submit requires a complete store listing (screenshots, description, privacy-policy URL, age rating) that only the operator can author. Uses `method = app-store-connect` in the export options (`app-store` is deprecated) and passes the build number as `CURRENT_PROJECT_VERSION=$GITHUB_RUN_NUMBER` to `xcodebuild`.
- **FR-015a**: A complete App Store Connect listing MUST exist for the record before submission — app name, description, keywords, support/marketing URLs, **screenshots for each required device class (iPhone 6.9", iPad 13", Mac, and Apple Watch)**, privacy policy URL, age rating, and export-compliance answer — sourced from operator-provided metadata.
- **FR-016**: The release workflow MUST NOT modify or weaken the six backend CI gates in `ci.yml`, nor weaken the existing unsigned Apple compile matrix. `apple-ci.yml` MAY gain exactly one **additive** step — the icon asset `--check` — which fails the build on an icon regression; its existing compile matrix stays unchanged.
- **FR-017**: All signing material (certificates, private keys, App Store Connect keys) MUST be supplied at runtime via CI secrets and MUST NOT be committed to the repository or baked into any image.

**Backend & deployment posture**

- **FR-018**: The deployment `.env` MUST set production-correct values for at least: `ASTRAL_ENV`, the Keycloak realm/authority, `KEYCLOAK_DEVICE_CLIENTS` (including `astral-watch`), `FF_DEVICE_LOGIN` (on), `FF_LLM_STREAMING` (true), and DB pool sizing kept within the Postgres connection limit for the deployment's process count.
- **FR-019**: The production realm MUST advertise the device-authorization endpoint in its well-known document and MUST list the shipped redirect URIs and azp values, so watch QR login and PKCE sign-in do not fail closed.
- **FR-020**: The `astralprims` version baked into the production image MUST provide exactly the component vocabulary the clients expect, keeping the client drift guard green.
- **FR-021**: The fail-closed production posture MUST be preserved — production-posture boot MUST refuse missing or placeholder secrets, and dev mock auth MUST NOT boot in production.

**Verification & parity**

- **FR-022**: Each signed build MUST be verified end-to-end on its device family: PKCE sign-in, session/keychain persistence across reinstall, and (watch) QR device-login.
- **FR-023**: Live narrative streaming (`FF_LLM_STREAMING`) MUST be verified rendering correctly on iOS, macOS, and watchOS, consistent with the final authoritative render.
- **FR-024**: The outstanding 051 evidence — round-trip latency (p95) and the browser short-code device-login path — MUST be captured.
- **FR-025**: Cross-client SDUI parity MUST be preserved: the server→client manifest drift guard MUST remain green and be extended (not forked) if the vocabulary ever changes.

**Constraints & governance**

- **FR-026**: The feature MUST add zero new third-party runtime dependencies on either the Swift client side or the backend.
- **FR-027**: If any backend schema change proves necessary, it MUST ship as an idempotent, guarded startup migration with a documented rollback (no ad-hoc SQL). No schema change is anticipated.

**Brand assets & store listing**

- **FR-030**: Apple icon assets MUST be derived from the operator-supplied master (`android-client/Android Raw Assets/AppIcon.png`) by a committed script that introduces **no third-party dependency**, and that script MUST expose a self-check verifying slot sizes, iOS/watch opacity, and macOS gutter retention.
- **FR-031**: Screenshots MUST be captured from the real Apple apps at exactly one accepted pixel size per required device class, then MAY carry brand/caption overlays. Screenshots MUST depict the app in use, not a splash or welcome screen alone.
- **FR-032**: The reuse status of every supplied brand asset MUST be recorded explicitly — usable, reference-only, or not transferable — so that no asset is silently ignored and none is wrongly shipped (e.g. the Google Play feature graphic has no App Store analogue; the Android/desktop screenshots mismatch every Apple aspect ratio).

**Documentation & knowledge**

- **FR-028**: The signing, configuration, asset-generation, and release process MUST be documented in the repo (README + deployment docs) so a new operator can reproduce a signed submission.
- **FR-029**: The Obsidian knowledge vault MUST be updated to reflect the shipped release process — a new release-pipeline page plus revisions to the affected pages, the source anchor refreshed to the new commit, and prior doc-vs-code conflicts resolved.

### Key Entities

- **Signing configuration**: The distribution identity, provisioning, and entitlements that make a build submittable (operator-supplied Team + certificates; version-controlled entitlement definitions).
- **App Store compliance assets**: Icon set, privacy manifest, purpose strings, and export-compliance declaration required for upload/review.
- **Build-time configuration**: The version-controlled configuration source that supplies the backend endpoint and realm to a build, plus the watch runtime override.
- **Client identity**: The bundle-identifier family, URL scheme, and OAuth client ids that must agree across project, generator, docs, and realm.
- **Release pipeline**: The tag-triggered workflow that archives, signs, notarizes, and uploads, consuming CI secrets.
- **Deployment posture**: The `.env` values, realm settings, and image contents that make the target backend production-correct and fail-closed.
- **Verification evidence**: The captured per-client proof that signed builds work as intended and stay consistent across clients.
- **Knowledge artifacts**: The vault pages and repo docs that record the release process.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both platform archives — iOS (with the embedded watch app) and macOS — pass App Store Connect upload validation with zero signing or compliance errors.
- **SC-001a**: The pipeline archives, signs, exports, validates, and **uploads** both platform builds to the single Universal Purchase App Store Connect record. The final **Submit for Review is operator-performed** (Apple's API refuses an incomplete listing, so pressing Submit requires the complete operator-authored store listing); the pipeline does not itself submit, and Apple's review decision is outside this feature's control.
- **SC-002**: A released build connects to the production backend and completes sign-in successfully on the first attempt.
- **SC-003**: Zero hardcoded dev endpoints are reachable in any Release build (confirmed by inspection/search).
- **SC-004**: A clean checkout builds every shared scheme (including `AstralWatch`) by name with no manual project fix-ups.
- **SC-005**: Exactly one canonical Xcode project exists — no project generator remains in the repository, so there is no second source of project truth that can drift.
- **SC-005a**: Every App Store icon slot is present at its exact required size; the iOS and watchOS 1024×1024 icons carry no alpha channel, and the macOS slots retain their transparent gutter (verified mechanically).
- **SC-005b**: Every required screenshot class (iPhone 6.9", iPad 13", Mac, Apple Watch) has at least one screenshot at an exactly-accepted pixel size, captured from the real Apple app.
- **SC-006**: A version tag triggers the release pipeline through archive → notarize → upload (or validated upload) with no manual intervention, while the existing CI gates remain green and changed-line coverage stays at or above the project threshold (≥90%).
- **SC-007**: Live narrative streaming renders correctly on all three Apple clients and remains consistent with the web, Windows, and Android clients.
- **SC-008**: Watch QR device-login succeeds end-to-end on a signed build.
- **SC-009**: A signed-in session persists across an app reinstall on every platform.
- **SC-010**: The knowledge vault passes its lint, documents the shipped release process, and leaves no unresolved doc-vs-code conflict; the repo README and realm-settings doc match the shipped client identities.
- **SC-011**: Zero new third-party runtime dependencies are introduced (Swift or backend).

## Assumptions

- **Operator-provided signing (blocking prerequisite)**: Because the Definition of Done is an actual submission, the operator MUST supply — during this feature — Apple Developer Program membership, a Team ID, distribution certificate(s) + **three** App Store provisioning profiles — iOS and macOS (both `com.personalailabs.astraldeep`; a profile is per bundle-id **and** platform) and watchOS (`com.personalailabs.astraldeep.watch`), the App Store Connect app record, and an App Store Connect API key for CI upload. The client build, entitlements, config, assets, and pipeline wiring proceed in parallel, but the live upload/submit step is blocked until these are present.
- **Icon artwork — SATISFIED**: the operator supplied `android-client/Android Raw Assets/AppIcon.png` (3000×3000, fully opaque). Every Apple icon is derived from it; the "operator must supply a master icon" prerequisite is closed.
- **Screenshots & listing (blocking prerequisite, operator-assisted)**: The operator provides the listing copy (descriptions, keywords, support/marketing/privacy-policy URLs, age rating). Screenshots are captured from the real Apple apps; because a simulator cannot be driven (tapped/typed) from the automation environment, the operator drives the app to each screen — or the capture is scripted via deep links — before overlays are composited.
- **Store topology**: iOS and macOS share a bundle id and therefore form **one** Universal Purchase App Store Connect record; the watch app ships embedded in the iOS build. There is one listing, not three.
- **Production endpoint**: `sandbox.ai.uky.edu` + realm `iam.ai.uky.edu/realms/Astral` are the intended production endpoints. A future distinct production host can be set through the same build-time configuration with no code change.
- **OAuth identities**: The shipped client identities (`astral-mobile` / `astral-desktop` / `astral-watch`, bundle `com.personalailabs.astraldeep`) are authoritative (per clarification); the dedicated `astral-ios`/`astral-macos` variant described in older docs is rejected and the docs are corrected to match code.
- **Feature flags**: `FF_DEVICE_LOGIN` stays ON (the realm device grant is enabled on `astral-watch`); `FF_LLM_STREAMING` stays ON (`true`) and is verified on-device rather than disabled.
- **Backend contract stable**: No server→client contract change is required (the manifest is byte-identical since 051); no backend schema change is anticipated. If either becomes necessary it follows the established drift-guard-extension and idempotent-migration patterns.
- **Submission is in scope**: This feature performs the real archive → sign → upload → submit-for-review for the **two** archives (iOS carrying the embedded watch app, and macOS via the Mac App Store) into the **single** Universal Purchase record. Apple's review verdict and the review turnaround are outside the feature's control; "done" is the submission action completing with a complete listing.
- **Watch server override**: The watch endpoint override is exposed through the paired-iPhone companion (mirroring the existing iOS/macOS sign-in override) rather than an on-watch text field, since watch text entry is impractical. (Default assumption; adjust if an on-watch affordance is required.)
- **Round-trip latency target**: The US6 round-trip p95 verification inherits the 051 target rather than defining a new number.
- **Out of scope**: Cresco (feature 050) integration; any change to the web, Windows, or Android clients beyond preserving cross-client parity; new backend product capabilities.
