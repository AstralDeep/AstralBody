# Feature 053 — operator prerequisites

Everything the automation cannot do for itself. Each item blocks only the step
named; all engineering work is complete and verified without them (see
[implementation-evidence.md](verification/implementation-evidence.md)).

**No secret value appears in this repository.** Only key *names* are listed.

---

## 1. Apple Developer + App Store Connect

| Input | Why | Blocks |
|---|---|---|
| Apple Developer Program membership + **Team ID** | signs every build | signed archive, upload |
| **Apple Distribution** certificate (`.p12` + its password) | the signing identity | signed archive |
| **Three** App Store provisioning profiles | see below | export, upload |
| App Store Connect **app record** for `com.personalailabs.astraldeep` | the destination | upload |
| App Store Connect **API key** (`.p8`, key id, issuer id) | headless upload | upload |

### Why three provisioning profiles, not two

A `.mobileprovision` is scoped per **bundle id _and_ platform**. iOS and macOS
share the bundle id `com.personalailabs.astraldeep` — that is precisely what makes
them a single Universal Purchase record — but they are different platforms, so
each needs its own profile. The embedded watch app has its own bundle id.

| Profile | Bundle id | Platform |
|---|---|---|
| iOS App Store | `com.personalailabs.astraldeep` | iOS |
| macOS App Store | `com.personalailabs.astraldeep` | macOS |
| watchOS App Store | `com.personalailabs.astraldeep.watch` | watchOS |

All three are packaged into **one** base64 tar and supplied as a single secret;
the workflow extracts them, installs each, and **fails if it does not find three**.

---

## 2. GitHub Actions secrets

`.github/workflows/apple-release.yml` fails *before any signing step* if any of
these is empty, naming the missing keys and never their values.

| Secret | Contents |
|---|---|
| `APPLE_TEAM_ID` | the 10-character Team ID |
| `APPLE_DISTRIBUTION_CERT_P12_BASE64` | base64 of the Apple Distribution `.p12` |
| `APPLE_CERT_PASSWORD` | the `.p12` export password |
| `APPLE_PROVISION_PROFILE_BASE64` | base64 of a tar containing all **three** profiles |
| `ASC_KEY_ID` | App Store Connect API key id |
| `ASC_ISSUER_ID` | App Store Connect API issuer id |
| `ASC_KEY_P8_BASE64` | base64 of the `AuthKey_*.p8` |

Plus three profile **names** (not secret material, but deployment-specific), used
to render the export-options plists:

`APPLE_PROFILE_IOS`, `APPLE_PROFILE_MACOS`, `APPLE_PROFILE_WATCH`

---

## 3. Store listing (blocks Submit for Review only)

The pipeline archives, signs, exports, validates and **uploads** both builds. It
stops there, deliberately: Apple's submission API refuses an incomplete listing,
so pressing **Submit for Review** is an operator action once the listing exists.

Required for the single Universal Purchase record:

- App name, subtitle, description, keywords, promotional text
- Support URL, marketing URL, **privacy policy URL**
- Age rating questionnaire
- Export compliance answer (the apps declare `ITSAppUsesNonExemptEncryption = false`)
- **Screenshots for every required device class** (below)

### Screenshots — operator-assisted

The icon prerequisite is **satisfied** (derived from your `AppIcon.png`). Screenshots
are not, and cannot be: none of the supplied Android/desktop renders matches an
Apple aspect ratio, and Guideline 2.3.3 requires the *real app in use*. They must be
captured from the Apple apps, and the automation environment cannot tap or type into
a simulator — so someone drives each app to the screen being captured.

| Class | Pick exactly one size | Required because |
|---|---|---|
| iPhone 6.9" | 1260×2736 · 1290×2796 · 1320×2868 | app runs on iPhone |
| iPad 13" | 2048×2732 · 2064×2752 | `TARGETED_DEVICE_FAMILY = "1,2"`; the build emits `AppIcon76x76@2x~ipad.png` |
| Mac | 1280×800 · 1440×900 · 2560×1600 · 2880×1800 | Mac App Store |
| Apple Watch | 422×514 · 416×496 · 410×502 · 396×484 · 368×448 · 312×390 | the embedded watch app |

1–10 per class. Use the **same** Apple Watch size across every localization.
Capture with `xcrun simctl io "<device>" screenshot out.png`; the Mac needs a window
capture. Brand/caption overlays are explicitly permitted by 2.3.3.

---

## 4. Keycloak realm (operator/realm admin)

Verified live on 2026-07-08 — the realm already advertises
`device_authorization_endpoint` and the `device_code` grant, so watch QR sign-in
will not fail closed.

Still to confirm for the shipped Apple identities:

- The Apple redirect `com.personalailabs.astraldeep:/oauth2redirect` (single slash)
  is a **Valid Redirect URI** on the **shared** clients `astral-mobile` (iOS, shared
  with Android) and `astral-desktop` (macOS, shared with Windows). There is no
  dedicated `astral-ios`/`astral-macos` client.
- `astral-watch` has the Device Authorization Grant enabled.
- The deployment `.env` sets `KEYCLOAK_ALLOWED_AZP` to include
  `astral-mobile,astral-desktop,astral-watch` and `KEYCLOAK_DEVICE_CLIENTS=astral-watch`.

---

## 5. Releasing

```bash
# 1. bump the human-facing version
#    (apple-clients/AstralApp/AstralApp.xcodeproj → MARKETING_VERSION)
# 2. tag with the apple-scoped namespace — NOT v-apple-*, which the Windows
#    release workflow's `v*` filter would also match and double-fire
git tag apple-v1.0.0 && git push origin apple-v1.0.0
```

The build number is stamped from `GITHUB_RUN_NUMBER`, so successive runs never
collide. Then press **Submit for Review** in App Store Connect.
