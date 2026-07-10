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

Implemented state (ground truth, branch `053-apple-production-release` — **this contract's surface is DONE and verified**):

- Exactly **one** `*.entitlements` file exists — `apple-clients/AstralApp/AstralApp-macOS.entitlements` (`com.apple.security.app-sandbox` + `com.apple.security.network.client`), wired via `CODE_SIGN_ENTITLEMENTS[sdk=macosx*]` on the **Release** config, alongside `ENABLE_APP_SANDBOX[sdk=macosx*] = YES` and `ENABLE_HARDENED_RUNTIME[sdk=macosx*] = YES`. There is **no** iOS entitlements file and **no** watch entitlements file — and **no `keychain-access-groups`** anywhere (tokens use the default per-app keychain access group; see §1).
- Both privacy manifests exist — `apple-clients/AstralApp/AstralApp/PrivacyInfo.xcprivacy` (iOS/macOS) and `apple-clients/AstralWatch/PrivacyInfo.xcprivacy` (watch), each **inside its file-system-synchronized folder** so it is actually bundled; each declares `NSPrivacyTracking=false` and the `UserDefaults` required reason `CA92.1` (§2).
- `ITSAppUsesNonExemptEncryption=false` is now present in **both** `Info.plist` and `WatchInfo.plist` (§3). `WatchInfo.plist` has been converted to the embedded companion (`WKWatchOnly` removed; `WKCompanionAppBundleIdentifier` + `WKRunsIndependentlyOfCompanionApp` added; keys owned by [`contracts/build-config.md`](build-config.md)).
- `AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset/` is populated and the **new** `AstralWatch/Assets.xcassets/AppIcon.appiconset/` exists; `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` is now set on the **AstralWatch** target (§4).
- **No microphone / speech usage strings were added — none are needed** (the watch dictates via SwiftUI `TextFieldLink` out-of-process and only plays audio; §2, "Usage / purpose strings").

---

## 1. Entitlements per target (FR-002, FR-003 · D7)

Each target declares **only** the entitlements its capabilities require (least
privilege — no temporary-exception entitlements, D7). In the shipped implementation
that means exactly **one** entitlements file — for macOS — because neither iOS nor
watchOS needs one.

### File & wiring

| File (repo-relative) | Target / SDK | Wired via |
|---|---|---|
| `apple-clients/AstralApp/AstralApp-macOS.entitlements` | AstralApp, **macOS only** | `CODE_SIGN_ENTITLEMENTS[sdk=macosx*] = AstralApp/AstralApp-macOS.entitlements` on the **Release** config |

There is **no** `AstralApp.entitlements` (iOS) and **no** `AstralWatch.entitlements`
file, and **no `keychain-access-groups`** entitlement on any target. The sdk-scoped
wiring guarantees the sandbox/entitlements land on the macOS product only.

### iOS & watchOS — no entitlements file (least privilege, D7)

Neither the iOS app nor the embedded watch app ships an entitlements file. Both store
tokens under the **default per-app keychain access group**, so a
`keychain-access-groups` (Keychain Sharing) entitlement would be needless privilege
(research D7). iOS is always sandboxed implicitly and needs no network entitlement, so
it carries no entitlements file at all.

The watch, in particular, MUST **NOT** declare `com.apple.security.application-groups`:
the companion server-endpoint override (D12) is delivered over `WatchConnectivity` into
the watch's **own** `UserDefaults`, not a shared App Group container, so no App Group
entitlement is needed on either the watch or the phone (override wiring owned by
[`contracts/build-config.md`](build-config.md)).

The watch is an **embedded companion** (D12/FR-011a) whose bundle id is the iOS id plus
a `.watch` suffix (`com.personalailabs.astraldeep.watch`). Even with no entitlements
file, signing still requires the watch's **own** App Store provisioning profile for that
id (a `.mobileprovision` is per bundle-id **and** platform), imported alongside the
app's profiles at CI signing time (secret injection owned by
[`contracts/release-pipeline.md`](release-pipeline.md)).

### macOS — App Sandbox + Hardened Runtime (FR-003 · D7)

The macOS product ships to the **Mac App Store**, so its Release configuration enables
**App Sandbox** and **Hardened Runtime** with a network client's minimum entitlement
set. `AstralApp-macOS.entitlements` contains **only**:

- `com.apple.security.app-sandbox` = `true` — **mandatory for Mac App Store** (FR-003).
- `com.apple.security.network.client` = `true` — outbound WSS/HTTPS to the backend (the app makes no inbound connections, so **no** `network.server`).

It carries **no `keychain-access-groups`** (the default per-app group backs the token
store under the sandbox). Sandbox and Hardened Runtime are enabled via build settings on
the macOS Release configuration — `ENABLE_APP_SANDBOX[sdk=macosx*] = YES` and
`ENABLE_HARDENED_RUNTIME[sdk=macosx*] = YES` — alongside the `CODE_SIGN_ENTITLEMENTS[sdk=macosx*]`
wiring above (not entitlement keys). No `com.apple.security.cs.*` Hardened-Runtime
exceptions (e.g. `disable-library-validation`, `allow-jit`) are present — the app needs
none.

**MUST NOT** (all platforms): any `com.apple.security.temporary-exception.*` entitlement,
`com.apple.security.application-groups` (the watch override uses WatchConnectivity →
per-app `UserDefaults`, not a shared App Group — D12), `keychain-access-groups` (default
per-app group is used everywhere), `get-task-allow=true` in a Release/distribution build,
or any sandbox scope beyond the macOS network-client need (`files.user-selected.*`,
`network.server`, `device.*`). Least privilege is the review-risk mitigation and the D7
mandate.

---

## 2. Privacy manifest per app target — `PrivacyInfo.xcprivacy` (FR-005 · D4)

Each **app** target MUST ship a `PrivacyInfo.xcprivacy` bundled resource. (The
`AstralCore`/`AstralPrims` SwiftPM package is first-party and non-tracking; if any
reason-coded API is reached through it, the app-target manifest still accounts for it.)

### Files

| File (repo-relative) | Covers |
|---|---|
| `apple-clients/AstralApp/AstralApp/PrivacyInfo.xcprivacy` | iOS + macOS app product (**inside** the file-system-synchronized `AstralApp/` folder so it is bundled — a manifest at the target root would not be) |
| `apple-clients/AstralWatch/PrivacyInfo.xcprivacy` | watchOS app product (inside the watch's file-system-synchronized folder) |

### Required keys

- **`NSPrivacyTracking`** = `false` — the app performs **no** cross-app/cross-site
  tracking; auth tokens and chat content go only to the first-party AstralDeep backend.
- **`NSPrivacyTrackingDomains`** = empty array — consistent with `NSPrivacyTracking=false`.
- **`NSPrivacyCollectedDataTypes`** — declares **only** what is actually collected, honestly
  (Constitution XIII). Chat content the user types is transmitted to the first-party backend
  to provide the service; if declared, it is `NSPrivacyCollectedDataTypeOtherUserContent`
  with `LinkedToUser` per identity reality, `NSPrivacyCollectedDataTypeUsedForTracking=false`,
  and purpose `AppFunctionality`. **No** speculative entries (e.g. no advertising, analytics,
  or location categories the app does not collect). The final set is confirmed during
  implementation by auditing what the client transmits.
- **`NSPrivacyAccessedAPITypes`** — one required-reason entry per reason-coded API the code
  **actually** calls, finalized by auditing the reason-coded APIs actually invoked (not a
  boilerplate set). **Shipped result**: each manifest declares exactly one entry —
  `NSPrivacyAccessedAPICategoryUserDefaults` with reason `CA92.1` (access to the app's own
  defaults — the endpoint-override / config persistence). No file-timestamp, disk-space, or
  system-boot-time categories are declared, because none are reached. Keychain access is
  **not** a reason-coded API category and needs no `NSPrivacyAccessedAPITypes` entry.

### Usage / purpose strings (FR-005 · D4)

Every runtime permission the app requests MUST have a user-facing purpose string in the
target's `Info.plist`, or the request crashes at runtime and fails review. **In the shipped
implementation no usage strings are needed, and none were added** — the premise that the
voice path requires them is disproved.

The watch voice path does **not** call the microphone or Speech-framework APIs: the watch
dictates via SwiftUI `TextFieldLink` (the system dictation sheet, which runs
**out-of-process**) and only **plays** audio (`AVAudioSession(.ambient)` + speech
synthesis). Because the app never invokes microphone capture (`AVAudioEngine`) or
`SFSpeechRecognizer`, adding **`NSMicrophoneUsageDescription`** /
**`NSSpeechRecognitionUsageDescription`** would declare capabilities the app does not use —
gratuitous, and a needless review-risk. Targets with no permission request MUST NOT carry
gratuitous usage strings, so **none** of the three targets carries a mic/speech usage
string.

---

## 3. Export compliance (FR-007 · D4)

The app uses only **exempt** standard cryptography (OS-provided TLS/HTTPS, PKCE hashing,
Keychain, Fernet/AES via system frameworks) — no proprietary or non-standard encryption.
Therefore each target MUST declare non-exempt encryption = false:

- **`ITSAppUsesNonExemptEncryption`** = `false`.

State per target:

- `AstralApp/Info.plist` — **already present** (`<key>ITSAppUsesNonExemptEncryption</key><false/>`). No change.
- `AstralApp/WatchInfo.plist` — **now present** (added in this feature; was previously absent),
  **consistent with the companion phone target** (FR-007): both `false`.

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

**FR-004a — icon wiring DONE:** `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` is now set on
the **AstralWatch** target's build configurations in `project.pbxproj` (it was previously set
on **AstralApp** only), so the watch catalog is live and the embedded watch archive carries
its own app icon (US1 acceptance scenario 3). **Verified**: `assetutil` reports `AppIcon
idiom=watch 1024x1024` in the compiled watch catalog.

**Build-verified:** `xcodebuild -scheme AstralApp -destination 'generic/platform=iOS
Simulator' -configuration Debug` **BUILD SUCCEEDED**; `actool` emitted `AppIcon60x60@2x.png`
and `AppIcon76x76@2x~ipad.png`, and `Assets.car` carries phone + pad renditions in default and
dark appearances.

---

## Compliance summary matrix

| Item | iOS (AstralApp) | macOS (AstralApp) | watchOS (AstralWatch) | FR |
|---|---|---|---|---|
| Entitlements file | — none (default keychain group) | `AstralApp-macOS.entitlements` | — none | FR-002 |
| `keychain-access-groups` entitlement | ✅ absent | ✅ absent | ✅ absent | FR-002 |
| `com.apple.security.app-sandbox` | — | ✅ (MAS) | — | FR-003 |
| `com.apple.security.network.client` | — | ✅ | — | FR-003 |
| Hardened Runtime (`ENABLE_HARDENED_RUNTIME[sdk=macosx*]=YES`) | — | ✅ | — | FR-003 |
| No temporary-exception entitlements | ✅ | ✅ | ✅ | FR-002/003 |
| No `com.apple.security.application-groups` (D12) | ✅ absent | ✅ absent | ✅ absent | FR-002 |
| Own App Store provisioning profile | `…astraldeep` | `…astraldeep` | `…astraldeep.watch` | D1 |
| `PrivacyInfo.xcprivacy` (`NSPrivacyTracking=false`) | ✅ | ✅ | ✅ | FR-005 |
| `NSPrivacyAccessedAPITypes` (audited: only `CA92.1`) | ✅ | ✅ | ✅ | FR-005 |
| Speech + Mic usage strings | — not used | — not used | — not used (`TextFieldLink` out-of-process) | FR-005 |
| `ITSAppUsesNonExemptEncryption=false` | ✅ present | ✅ present | ✅ present | FR-007 |
| `AppIcon.appiconset` populated (generated) | ✅ done | ✅ done | ✅ new catalog | FR-004 |
| Opaque 1024×1024 App Store icon (no alpha) | ✅ | n/a (gutter) | ✅ | FR-004 |
| `ASSETCATALOG_COMPILER_APPICON_NAME=AppIcon` | ✅ set (AstralApp) | ✅ set (AstralApp) | ✅ set (AstralWatch) | FR-004a |

---

## Reviewer / implementer checklist

Run before archiving; all MUST pass for the SC-001 zero-compliance-error bar.

- [x] Exactly one entitlements file exists — `AstralApp-macOS.entitlements` — wired via
      `CODE_SIGN_ENTITLEMENTS[sdk=macosx*]` on the macOS Release config. **No** iOS or watch
      entitlements file, and **no `keychain-access-groups`** on any target (default per-app
      keychain access group is used everywhere).
- [x] The watch declares **no `com.apple.security.application-groups`** (the override uses
      WatchConnectivity → per-app `UserDefaults`, D12).
- [x] macOS Release has `com.apple.security.app-sandbox=true`, `com.apple.security.network.client=true`,
      `ENABLE_APP_SANDBOX[sdk=macosx*]=YES`, and `ENABLE_HARDENED_RUNTIME[sdk=macosx*]=YES` — and
      **nothing else** (no `keychain-access-groups`).
- [x] No `com.apple.security.temporary-exception.*`, no `com.apple.security.application-groups`,
      no Hardened-Runtime `cs.*` exceptions, no `get-task-allow=true` in any Release/distribution build.
- [ ] The embedded watch app has **its own App Store provisioning profile** for
      `com.personalailabs.astraldeep.watch`, imported alongside the app profile at CI signing
      (see [`contracts/release-pipeline.md`](release-pipeline.md)).
- [x] The watch-companion `WatchInfo.plist` keys are in place — `WKWatchOnly` **removed**,
      `WKCompanionAppBundleIdentifier=com.personalailabs.astraldeep`,
      `WKRunsIndependentlyOfCompanionApp=true`, `WKApplication` kept (keys owned by
      [`contracts/build-config.md`](build-config.md); confirmed here because they gate the
      embedded-archive validation).
- [x] `PrivacyInfo.xcprivacy` present in each app target's **file-system-synchronized** folder
      (`AstralApp/AstralApp/PrivacyInfo.xcprivacy`, `AstralWatch/PrivacyInfo.xcprivacy`);
      `NSPrivacyTracking=false`; `NSPrivacyCollectedDataTypes` matches reality (no speculative entries).
- [x] `NSPrivacyAccessedAPITypes` finalized by auditing the reason-coded APIs the code actually
      calls — the one declared entry is `NSPrivacyAccessedAPICategoryUserDefaults` reason `CA92.1`.
- [x] **No** `NSSpeechRecognitionUsageDescription` / `NSMicrophoneUsageDescription` on any target —
      the watch dictates via `TextFieldLink` (out-of-process) and only plays audio, so it calls
      neither the microphone nor Speech APIs; adding them would declare unused capabilities.
- [x] `ITSAppUsesNonExemptEncryption=false` present in **both** `Info.plist` **and** `WatchInfo.plist`,
      consistent across companion + watch.
- [x] `AppIcon.appiconset` populated (generated by `Scripts/generate_app_icons.py`) for iOS + macOS,
      the **new** `AstralWatch` asset catalog exists, and the generator `--check` runs in CI (slot sizes,
      iOS/watch opacity, macOS gutter) — detail in [`contracts/brand-assets.md`](brand-assets.md).
- [x] `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` set on the **AstralWatch** target's build configs
      (FR-004a) — `assetutil` confirms `AppIcon idiom=watch 1024x1024`.
- [ ] `xcrun altool --validate-app` (or App Store Connect API validation) per platform archive
      (iOS-with-embedded-watch, macOS) reports **no** missing-icon, missing-privacy-manifest, ATS,
      entitlement, or signing error (SC-001).
