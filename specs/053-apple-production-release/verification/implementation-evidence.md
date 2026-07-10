# Feature 053 — implementation evidence

Everything below was **executed**, not asserted. Commands were run on macOS with
Xcode 26.6 (Build 17F113) against the working tree on branch
`053-apple-production-release`. Anything not listed here is **not** verified —
see [Outstanding](#outstanding).

---

## US1 — builds, archives, icons, compliance

### Builds (all unsigned, as CI runs them)

| Target | Destination | Config | Result |
|---|---|---|---|
| `AstralApp` | `generic/platform=iOS Simulator` | Debug | **BUILD SUCCEEDED** |
| `AstralApp` | `platform=macOS` | Debug | **BUILD SUCCEEDED** |
| `AstralWatch` | `generic/platform=watchOS Simulator` | Debug | **BUILD SUCCEEDED** |
| `AstralApp` | `platform=macOS` | Release | **BUILD SUCCEEDED** |
| `AstralApp` archive | `generic/platform=iOS` | Release | **ARCHIVE SUCCEEDED** |

### The embed phase is platform-filtered (FR-011b, D20)

This is the failure that would still compile and only surface at Mac App Store
validation, so it is asserted on both sides:

```
iOS  archive: Products/Applications/AstralDeep.app/Watch/AstralWatch.app  -> PRESENT
macOS product: find … -name 'AstralWatch.app'                             -> EMPTY
```

The embedded watch app's `Info.plist`, read out of the built iOS product:

```
CFBundleIdentifier                com.personalailabs.astraldeep.watch
WKCompanionAppBundleIdentifier    com.personalailabs.astraldeep
WKRunsIndependentlyOfCompanionApp true
WKWatchOnly                       (absent)
ITSAppUsesNonExemptEncryption     false
```

### Icons (FR-004, FR-004a, SC-005a)

`python3 apple-clients/Scripts/generate_app_icons.py --check` →
`OK: sizes correct; iOS/watch icons opaque; macOS slots retain the gutter`

Independently, via `sips`:

```
AppIcon-1024.png          1024x1024 alpha=no    <- iOS App Store slot (ITMS-90717)
watch AppIcon-1024.png    1024x1024 alpha=no    <- watchOS App Store slot
mac-512x512@2x.png        1024x1024 alpha=yes   <- macOS keeps its transparent gutter
mac-16x16@1x.png            16x16   alpha=yes
```

`actool` output, read out of the built products:

- iOS app bundle: `AppIcon60x60@2x.png` **and** `AppIcon76x76@2x~ipad.png`
  (confirms iPad support at build level, so iPad 13" screenshots are required)
- iOS `Assets.car`: `AppIcon` renditions for `idiom=phone` and `idiom=pad`, in
  default and `UIAppearanceDark` appearances
- watch `Assets.car`: `AppIcon idiom=watch 1024x1024`

### Compliance (FR-003, FR-005, FR-006, FR-007)

macOS Release entitlements, read back off an ad-hoc-signed Release product with
`codesign -d --entitlements :-`:

```
com.apple.security.app-sandbox                    => true
com.apple.security.network.client                 => true
com.apple.security.files.user-selected.read-write => true
CodeDirectory flags=0x10002(adhoc,runtime)   <- Hardened Runtime
```

The file entitlement is required, not optional: `ChatView`'s `.fileImporter` and the macOS
`NSSavePanel` in `ComponentView` both touch user-selected files, and under the sandbox they
would open and then silently fail without it.

macOS Release resolved build settings:

```
ENABLE_APP_SANDBOX      = YES
ENABLE_HARDENED_RUNTIME = YES
CODE_SIGN_ENTITLEMENTS  = AstralApp-macOS.entitlements
```

macOS Release product `Info.plist`:

```
NSAllowsArbitraryLoads    (absent)   <- ATS-clean
NSAllowsLocalNetworking   true       <- loopback/.local only; App-Store-safe
```

The watch bundle contains `PrivacyInfo.xcprivacy`.

---

## US2 — build-time endpoint configuration (FR-009, FR-010, SC-003)

Read out of the built products, proving the xcconfig → Info.plist → runtime chain:

| Configuration | `ASTRALServerBaseURL` | `ASTRALKeycloakAuthority` |
|---|---|---|
| Debug | `http://localhost:8001` | `https://iam.ai.uky.edu/realms/Astral` |
| Release | `https://sandbox.ai.uky.edu` | `https://iam.ai.uky.edu/realms/Astral` |

The `//` in a URL starts an xcconfig comment; `https:/$()/host` defeats the
comment scanner. That this substitution actually works is proven by the table
above, not assumed.

`swift test --package-path apple-clients/AstralCore` → **74 tests, 0 failures**,
including the `ui_protocol.json` drift guard (47 push / 35 component / 67 accept)
and 10 new `ConfigurationResolutionTests`. Those cover the resolution ladder
(override > Info.plist > fallback), rejection of blank/non-HTTP/host-less
overrides, and rejection of an **unsubstituted** `$(ASTRAL_SERVER_BASE_URL)`
literal — the failure mode where a rewired project silently points the app at a
nonsense host.

---

## US3 — one canonical project (FR-012, FR-014, SC-004, SC-005)

```
$ xcodebuild -project apple-clients/AstralApp/AstralApp.xcodeproj -list
Schemes: AstralApp, AstralCore, AstralWatch
```

`AstralWatch.xcscheme` is restored (it was declared shared in
`xcschememanagement.plist` but the file was absent, so a clean clone and the
`apple-ci.yml` watch leg could not resolve it).

`apple-clients/project.yml` is deleted. No project generator remains.

---

## US4 — release pipeline (FR-015, FR-016, FR-017, SC-006)

All four workflows parse (`YAML.load_file`):
`apple-release.yml`, `apple-ci.yml`, `ci.yml`, `release-windows.yml`.

**Tag disjointness, proven rather than asserted:**

```
fnmatch('apple-v1.0.0',   'v*') -> False   # our namespace cannot double-fire Windows
fnmatch('v-apple-1.0.0',  'v*') -> True    # …which is exactly why we did not use it
```

`ExportOptions` rendering:

```
missing env      -> exit 1, "needs these environment values: APPLE_PROFILE_IOS, APPLE_PROFILE_WATCH, APPLE_TEAM_ID"
full env         -> rendered, plutil -lint OK
                    method = app-store-connect   (the older `app-store` is deprecated)
                    ios:   2 provisioningProfiles entries (app + embedded watch)
                    macos: 1 provisioningProfiles entry
```

No signing material, Team ID, or profile name is committed; a grep for PEM
headers and long base64 blobs across the templates and the workflow is clean.

---

## US5 — backend posture (FR-019) — *partially verified*

Live checks against the production realm and backend:

```
GET https://iam.ai.uky.edu/realms/Astral/.well-known/openid-configuration
  issuer                        = https://iam.ai.uky.edu/realms/Astral
  device_authorization_endpoint = …/protocol/openid-connect/auth/device   <- present
  grant_types_supported         includes urn:ietf:params:oauth:grant-type:device_code

GET https://sandbox.ai.uky.edu/         -> HTTP 302   (auth redirect, expected since 028)
GET https://sandbox.ai.uky.edu/healthz  -> HTTP 200
```

So the watch QR device-login broker will **not** fail closed on the realm side.

---

## Signed release — executed 2026-07-09

Tag `apple-v1.0` → run [29036053155](https://github.com/AstralDeep/AstralDeep/actions/runs/29036053155), conclusion **success**.

```
✓ validate iOS    ✓ validate macOS
✓ upload iOS      ✓ upload macOS
VERIFY SUCCEEDED : 2      UPLOAD SUCCEEDED : 2      FAILED with : 0
  export-ios/AstralDeep.ipa   -> Delivery UUID b6a0f233-3b11-4a21-87ff-329041395b7d
  export-macos/AstralDeep.pkg -> Delivery UUID fd1f2dd6-f874-4d7d-8d0c-4d8a6e9351dc
```

Both platform builds are in the single Universal Purchase App Store Connect record.
Four defects had to be fixed to get here, each caught by execution rather than review:

| # | Symptom | Root cause |
|---|---|---|
| 1 | `No '3rd Party Mac Developer Installer' identity` | a Mac App Store `.pkg` is signed by a **second** certificate |
| 2 | `"AstralApp"/"AstralWatch" requires a provisioning profile` | manual signing needs a profile **per target and per platform**; one command-line value hits every target |
| 3 | `exportOptionsPlist error for key "method" expected one {}` | the watch had `SKIP_INSTALL = NO`, so the archive held a **second top-level app**; Xcode wrote no `ApplicationProperties`, so every distribution method rejected it |
| 4 | Green job, only iOS uploaded | Apple rejected the `.pkg` for a missing `LSApplicationCategoryType`, and **`altool` exited 0 while printing `UPLOAD FAILED`** |

Defect 4 is the dangerous one: the pipeline reported success having shipped half the
release. `Scripts/altool_strict.sh` now fails on a non-zero exit, on any failure
marker, and on the *absence* of a success marker.

## Outstanding

Not verified, and not claimed to be:

- **Signed** archives, `altool --validate-app`, upload, and Submit for Review.
  All require the operator's Apple Team ID, distribution certificate, three App
  Store provisioning profiles (iOS, macOS, watchOS), and the App Store Connect
  API key. The unsigned archive path is verified; the signed one is not.
- **Screenshots** for iPhone 6.9", iPad 13", Mac and Apple Watch. Capture requires
  driving each app to the right screen, which the automation environment cannot do
  (no tap/type into a simulator).
- **US6 on-device evidence**: PKCE sign-in, keychain persistence across reinstall,
  watch QR sign-in, and live `FF_LLM_STREAMING` narrative rendering — all need a
  human at the keyboard against the live backend.
- **The companion override end-to-end** (FR-011): the resolution ladder is
  unit-tested and the WatchConnectivity plumbing compiles for both sides, but the
  phone→watch push has not been exercised on a paired device.
- The deployment host's real `.env` (its values are not in this repo).
