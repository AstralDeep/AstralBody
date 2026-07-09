# Contract: App Store Compliance & Entitlements

**Feature**: 053-apple-production-release · **Phase**: 1 (Design & Contracts)
**Decisions**: D1 (signing style), D4 (privacy manifest / usage strings / export compliance), D7 (macOS MAS entitlements), D12 (watch = embedded companion), D15 (app icon — generated; detailed icon contract in [`contracts/brand-assets.md`](brand-assets.md))
**Requirements**: FR-002, FR-003, FR-004, FR-004a, FR-005, FR-007
**Bar**: **SC-001** — both platform archives (iOS with the embedded watch app, and macOS) pass App Store Connect upload validation with **zero signing or compliance errors**; **SC-005a** — every icon slot is present at its exact size, the iOS/watch 1024×1024 icons carry no alpha, and the macOS slots keep their gutter.

This contract defines the version-controlled compliance surface each Apple target
must carry to validate for upload. It is a design/contract doc — it specifies the
required files, keys, and values, not their literal file bodies. Every item is a
**MUST** and maps to a functional requirement; the acceptance bar for the whole
contract is SC-001 (clean upload validation) with SC-001a (submission) downstream.
The **icon gap is now CLOSED** — the icons are generated, committed, and build-verified
in this feature; §4 states only the compliance surface and defers the full icon
contract to [`contracts/brand-assets.md`](brand-assets.md).

Current state (ground truth, branch `053-apple-production-release`):

- `apple-clients/` has **no** `*.entitlements` file and **no** `PrivacyInfo.xcprivacy` (both absent — must be added).
- `AstralApp/Info.plist` already sets `ITSAppUsesNonExemptEncryption=false`; `WatchInfo.plist` does **not** (must be added), and `WatchInfo.plist` still carries `WKWatchOnly=true` with **no** companion keys — the watch-only → embedded-companion conversion (D12/FR-011a, keys owned by [`contracts/build-config.md`](build-config.md)) is a prerequisite for the single-record topology this contract validates against.
- `AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/` is now **populated** (was `Contents.json` only, zero PNGs): the generated opaque 1024×1024 iOS marketing icon (+ dark variant) and the ten macOS rounded-rect slots. A **new** `AstralWatch/Assets.xcassets/AppIcon.appiconset/` now exists (the watch target previously had **no** asset catalog). The only remaining icon-wiring task is setting `ASSETCATALOG_COMPILER_APPICON_NAME` on the **AstralWatch** target (FR-004a, §4).

---

## 1. Entitlements per target (FR-002, FR-003 · D7)

Each target MUST declare **only** the entitlements its capabilities require
(least privilege — no temporary-exception entitlements, D7). Entitlement files are
version-controlled and wired to the build via the `CODE_SIGN_ENTITLEMENTS` build
setting on the target's Release (and Debug) configuration in `project.pbxproj`.

### Files & wiring

| File (repo-relative) | Target(s) | Wired via |
|---|---|---|
| `apple-clients/AstralApp/AstralApp.entitlements` | AstralApp (iOS **and** macOS) | `CODE_SIGN_ENTITLEMENTS = AstralApp/AstralApp.entitlements` |
| `apple-clients/AstralApp/AstralWatch.entitlements` | AstralWatch (watchOS) | `CODE_SIGN_ENTITLEMENTS = AstralApp/AstralWatch.entitlements` |

> If iOS and macOS need divergent entitlement sets (they do — macOS adds the App
> Sandbox keys, iOS does not), split into `AstralApp-iOS.entitlements` and
> `AstralApp-macOS.entitlements` and wire each per the platform-conditioned build
> setting. The default is one shared file plus macOS-only keys gated by config; the
> reviewer MUST confirm the sandbox keys land on the macOS product only.

### iOS — `AstralApp.entitlements` (iOS)

MUST contain **only**:

- `keychain-access-groups` — one group, `$(AppIdentifierPrefix)com.personalailabs.astraldeep`
  (Team-ID-prefixed; the prefix resolves once `DEVELOPMENT_TEAM` is supplied, D1). Backs
  the existing Keychain token store; retires the KNOWN-ISSUES "legacy keychain until real
  signing" note (D7).

MUST NOT contain: App Sandbox keys (iOS is always sandboxed implicitly), network
entitlements (not required on iOS), or any `com.apple.security.temporary-exception.*`.

### watchOS — `AstralWatch.entitlements`

The watch is an **embedded companion** app (D12/FR-011a) that ships *inside* the iOS
archive, so its bundle id is the iOS id plus a `.watch` suffix
(`com.personalailabs.astraldeep.watch`) and it needs **its own App Store provisioning
profile** for that id — distinct from the app's profile — imported alongside the app's at
CI signing time (secret injection owned by [`contracts/release-pipeline.md`](release-pipeline.md)).

MUST contain **only**:

- `keychain-access-groups` — the same Team-ID-prefixed group as iOS so a paired token
  store is coherent.

MUST NOT contain any sandbox/network/temporary-exception keys, and — critically — MUST
**NOT** declare `com.apple.security.application-groups`. The companion server-endpoint
override (D12) is delivered over `WatchConnectivity` into the watch's **own**
`UserDefaults`, not a shared App Group container, so no App Group entitlement is needed on
either the watch or the phone; adding one would be gratuitous privilege (D7) and an extra
provisioning capability. The override wiring itself is owned by
[`contracts/build-config.md`](build-config.md).

### macOS — App Sandbox + Hardened Runtime (FR-003 · D7)

The macOS product ships to the **Mac App Store**, so its Release configuration MUST
enable **App Sandbox** and **Hardened Runtime**, with a network+keychain client's minimum
entitlement set:

- `com.apple.security.app-sandbox` = `true` — **mandatory for Mac App Store** (FR-003).
- `com.apple.security.network.client` = `true` — outbound WSS/HTTPS to the backend (the app makes no inbound connections, so **no** `network.server`).
- `keychain-access-groups` — the Team-ID-prefixed group (data-protection keychain under sandbox).

Hardened Runtime is enabled via the build setting **`ENABLE_HARDENED_RUNTIME = YES`** on
the macOS Release configuration (not an entitlement key). No `com.apple.security.cs.*`
Hardened-Runtime exceptions (e.g. `disable-library-validation`, `allow-jit`) may be present
— the app needs none.

**MUST NOT** (all platforms): any `com.apple.security.temporary-exception.*` entitlement,
`com.apple.security.application-groups` (the watch override uses WatchConnectivity → per-app
`UserDefaults`, not a shared App Group — D12), `get-task-allow=true` in a
Release/distribution build, or `com.apple.security.app-sandbox` scoped so broadly (e.g.
`files.user-selected.read-write`, `network.server`, `device.*`) beyond the network-client +
keychain need. Least privilege is the review-risk mitigation and the D7 mandate.

---

## 2. Privacy manifest per app target — `PrivacyInfo.xcprivacy` (FR-005 · D4)

Each **app** target MUST ship a `PrivacyInfo.xcprivacy` bundled resource. (The
`AstralCore`/`AstralPrims` SwiftPM package is first-party and non-tracking; if any
reason-coded API is reached through it, the app-target manifest still accounts for it.)

### Files

| File (repo-relative) | Covers |
|---|---|
| `apple-clients/AstralApp/PrivacyInfo.xcprivacy` | iOS + macOS app product (added to the Copy-Bundle-Resources phase) |
| `apple-clients/AstralWatch/PrivacyInfo.xcprivacy` | watchOS app product |

### Required keys

- **`NSPrivacyTracking`** = `false` — the app performs **no** cross-app/cross-site
  tracking; auth tokens and chat content go only to the first-party AstralBody backend.
- **`NSPrivacyTrackingDomains`** = empty array — consistent with `NSPrivacyTracking=false`.
- **`NSPrivacyCollectedDataTypes`** — declares **only** what is actually collected, honestly
  (Constitution XIII). Chat content the user types is transmitted to the first-party backend
  to provide the service; if declared, it is `NSPrivacyCollectedDataTypeOtherUserContent`
  with `LinkedToUser` per identity reality, `NSPrivacyCollectedDataTypeUsedForTracking=false`,
  and purpose `AppFunctionality`. **No** speculative entries (e.g. no advertising, analytics,
  or location categories the app does not collect). The final set is confirmed during
  implementation by auditing what the client transmits.
- **`NSPrivacyAccessedAPITypes`** — one required-reason entry per reason-coded API the code
  **actually** calls. **This list is finalized during implementation by auditing the
  reason-coded APIs actually invoked** (do not copy a boilerplate set). Likely candidates to
  verify (declare only those reached):
  - `NSPrivacyAccessedAPICategoryUserDefaults` — reason `CA92.1` (access to app's own defaults) if `UserDefaults` is used for config/override storage.
  - `NSPrivacyAccessedAPICategoryFileTimestamp` — reason `C617.1` / `DDA9.1` only if file-timestamp APIs are reached.
  - `NSPrivacyAccessedAPICategoryDiskSpace` / `NSPrivacyAccessedAPICategorySystemBootTime` — declare only if actually called.

  Keychain access is **not** a reason-coded API category and needs no `NSPrivacyAccessedAPITypes` entry.

### Usage / purpose strings (FR-005 · D4)

Every runtime permission the app requests MUST have a user-facing purpose string in the
target's `Info.plist`, or the request crashes at runtime and fails review. Because the
**watch voice path** (dictation → device-login and voice-target rendition, feature 051)
exists, the watch target's Info source MUST carry:

- **`NSSpeechRecognitionUsageDescription`** — why the watch transcribes speech.
- **`NSMicrophoneUsageDescription`** — why the watch captures audio.

These belong wherever the voice path is reachable (watch target; and the phone target if it
brokers dictation). Targets with no such permission MUST NOT carry gratuitous usage strings.

---

## 3. Export compliance (FR-007 · D4)

The app uses only **exempt** standard cryptography (OS-provided TLS/HTTPS, PKCE hashing,
Keychain, Fernet/AES via system frameworks) — no proprietary or non-standard encryption.
Therefore each target MUST declare non-exempt encryption = false:

- **`ITSAppUsesNonExemptEncryption`** = `false`.

State per target:

- `AstralApp/Info.plist` — **already present** (`<key>ITSAppUsesNonExemptEncryption</key><false/>`). No change.
- `AstralApp/WatchInfo.plist` — **MUST be ADDED** (currently absent). The watch declaration
  must be **consistent with the companion phone target** (FR-007): both `false`.

This lets each upload skip the manual per-build export-compliance questionnaire in App Store
Connect and keeps the watch consistent with the phone (FR-007).

---

## 4. App icon set (FR-004, FR-004a · D15)

**Status: the icon gap is CLOSED.** The icons have been generated, committed, and
build-verified in this feature. The detailed icon contract — the master, the per-platform
slot tables, the alpha/gutter rules, and the generator's `--check` self-test — lives in
[`contracts/brand-assets.md`](brand-assets.md) and is **not** duplicated here. This section
states only what the compliance surface requires and confirms the gap is closed.

`apple-clients/Scripts/generate_app_icons.py` (stdlib Python + Apple `sips`, **zero new
dependencies**, D15/FR-030) derives every Apple icon from the operator master
`android-client/Android Raw Assets/AppIcon.png` (3000×3000, fully opaque). It has already
emitted, and the working tree already carries:

- `AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/` — populated (was `Contents.json`
  only): the iOS **1024×1024 opaque** marketing icon (+ dark variant), the ten macOS
  rounded-rect slots, and a rewritten `Contents.json`.
- `AstralWatch/Assets.xcassets/AppIcon.appiconset/` — a **new** watch asset catalog with a
  1024×1024 opaque watch icon + `Contents.json`. The watch target previously had **no asset
  catalog at all**.

Compliance invariants (mechanically checked by the generator's `--check` and asserted by
**SC-005a**):

- The iOS **and** watchOS App Store 1024×1024 icons MUST be **fully opaque** — an alpha
  channel fails upload as **ITMS-90717**. (`sips` independently reports `hasAlpha: no` on all
  three 1024 icons.)
- The macOS slots MUST **retain** their transparent gutter (classic asset catalogs do not
  auto-mask, so the artwork itself supplies the rounded-rect shape). A blanket "strip all
  alpha" step would break them — so the opacity rule is scoped to the iOS/watch slots only.

**FR-004a — remaining wiring (a task, not yet done):** the watch's icon renders only once
`ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` is set on the **AstralWatch** target's build
configurations in `project.pbxproj` — it is currently set on **AstralApp** only. Without it
the new watch catalog is inert and the embedded watch archive fails US1 acceptance scenario 3
(the watch must carry its own app icon).

**Build-verified:** `xcodebuild -scheme AstralApp -destination 'generic/platform=iOS
Simulator' -configuration Debug` **BUILD SUCCEEDED**; `actool` emitted `AppIcon60x60@2x.png`
and `AppIcon76x76@2x~ipad.png`, and `Assets.car` carries phone + pad renditions in default and
dark appearances.

---

## Compliance summary matrix

| Item | iOS (AstralApp) | macOS (AstralApp) | watchOS (AstralWatch) | FR |
|---|---|---|---|---|
| `keychain-access-groups` entitlement | ✅ | ✅ | ✅ | FR-002 |
| `com.apple.security.app-sandbox` | — | ✅ (MAS) | — | FR-003 |
| `com.apple.security.network.client` | — | ✅ | — | FR-003 |
| Hardened Runtime (`ENABLE_HARDENED_RUNTIME=YES`) | — | ✅ | — | FR-003 |
| No temporary-exception entitlements | ✅ | ✅ | ✅ | FR-002/003 |
| No `com.apple.security.application-groups` (D12) | ✅ absent | ✅ absent | ✅ absent | FR-002 |
| Own App Store provisioning profile | `…astraldeep` | `…astraldeep` | `…astraldeep.watch` | D1 |
| `PrivacyInfo.xcprivacy` (`NSPrivacyTracking=false`) | ✅ | ✅ | ✅ | FR-005 |
| `NSPrivacyAccessedAPITypes` (audited set) | ✅ | ✅ | ✅ | FR-005 |
| Speech + Mic usage strings | (if voice path) | (if voice path) | ✅ | FR-005 |
| `ITSAppUsesNonExemptEncryption=false` | ✅ present | ✅ present | ➕ **ADD** | FR-007 |
| `AppIcon.appiconset` populated (generated) | ✅ done | ✅ done | ✅ **new catalog** | FR-004 |
| Opaque 1024×1024 App Store icon (no alpha) | ✅ | n/a (gutter) | ✅ | FR-004 |
| `ASSETCATALOG_COMPILER_APPICON_NAME=AppIcon` | ✅ set (AstralApp) | ✅ set (AstralApp) | ➕ **ADD** (AstralWatch) | FR-004a |

---

## Reviewer / implementer checklist

Run before archiving; all MUST pass for the SC-001 zero-compliance-error bar.

- [ ] `AstralApp.entitlements` and `AstralWatch.entitlements` exist and are wired via
      `CODE_SIGN_ENTITLEMENTS` on every configuration of their targets.
- [ ] iOS/watch entitlements contain **only** `keychain-access-groups` (Team-prefixed); no
      sandbox/network/temporary-exception keys, and **no `com.apple.security.application-groups`**
      (the watch override uses WatchConnectivity → per-app `UserDefaults`, D12).
- [ ] macOS Release has `com.apple.security.app-sandbox=true`, `com.apple.security.network.client=true`,
      `keychain-access-groups`, and `ENABLE_HARDENED_RUNTIME=YES` — and **nothing else**.
- [ ] No `com.apple.security.temporary-exception.*`, no `com.apple.security.application-groups`,
      no Hardened-Runtime `cs.*` exceptions, no `get-task-allow=true` in any Release/distribution build.
- [ ] The embedded watch app has **its own App Store provisioning profile** for
      `com.personalailabs.astraldeep.watch`, imported alongside the app profile at CI signing
      (see [`contracts/release-pipeline.md`](release-pipeline.md)).
- [ ] The watch-companion `WatchInfo.plist` keys are in place — `WKWatchOnly` **removed**,
      `WKCompanionAppBundleIdentifier=com.personalailabs.astraldeep`,
      `WKRunsIndependentlyOfCompanionApp=YES`, `WKApplication=YES` (keys owned by
      [`contracts/build-config.md`](build-config.md); confirmed here because they gate the
      embedded-archive validation).
- [ ] `PrivacyInfo.xcprivacy` present in each app target's bundle resources (AstralApp + AstralWatch);
      `NSPrivacyTracking=false`; `NSPrivacyCollectedDataTypes` matches reality (no speculative entries).
- [ ] `NSPrivacyAccessedAPITypes` finalized by **auditing the reason-coded APIs the code actually
      calls** (not copied boilerplate); each entry has a valid reason code.
- [ ] Watch target carries `NSSpeechRecognitionUsageDescription` + `NSMicrophoneUsageDescription`
      (voice path present); no gratuitous usage strings elsewhere.
- [ ] `ITSAppUsesNonExemptEncryption=false` present in **both** `Info.plist` **and** `WatchInfo.plist`,
      consistent across companion + watch.
- [ ] `AppIcon.appiconset` populated (generated by `Scripts/generate_app_icons.py`) for iOS + macOS,
      the **new** `AstralWatch` asset catalog exists, and the generator `--check` passes (slot sizes,
      iOS/watch opacity, macOS gutter) — detail in [`contracts/brand-assets.md`](brand-assets.md).
- [ ] `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` set on the **AstralWatch** target's build configs
      (FR-004a) — currently set on AstralApp only.
- [ ] `xcrun altool --validate-app` (or App Store Connect API validation) per platform archive
      (iOS-with-embedded-watch, macOS) reports **no** missing-icon, missing-privacy-manifest, ATS,
      entitlement, or signing error (SC-001).
