# Contract: Cross-Client Identity (feature 053)

The bundle-identifier family, URL scheme, PKCE redirect, and OAuth client ids
are a **single authoritative set** that MUST agree across the committed Xcode
project, the README, `Configuration.swift`, the backend realm docs,
`.env.example`, and the Keycloak realm itself. (There is no longer a project
generator to keep in agreement — `project.yml` is retired, D18.) This contract
fixes that set and enumerates every place that currently diverges from it.
Resolves the US3 drift (FR-012/FR-013/FR-014) per research **D8** (identity
reconciliation), **D9** (missing shared scheme), **D18** (the project generator
is retired), and **D19** (one shared app bundle id → one Universal Purchase
record).

## Authoritative source

The shipped, dev-verified
[`AstralCore/Sources/AstralCore/Configuration.swift`](../../../apple-clients/AstralCore/Sources/AstralCore/Configuration.swift)
is **ground truth**. Its values are known-working against the live realm; the
drift lived in the project generator (now **deleted**, D18), the README, and the
backend docs (D8). The rule for every remaining reconciliation below is therefore
**fix the docs to match the code**, never the reverse (per the 2026-07-08
clarification — the `astral-ios`/`astral-macos` variant in older docs is
rejected).

## The authoritative identity set (MUST agree everywhere)

| Facet | Authoritative value | Defined in `Configuration.swift` |
|---|---|---|
| App bundle-id | `com.personalailabs.astraldeep` | (Xcode project — INFOPLIST) |
| Watch bundle-id | `com.personalailabs.astraldeep.watch` | (Xcode project — INFOPLIST) |
| URL scheme (PKCE) | `com.personalailabs.astraldeep` | `redirectScheme` |
| Redirect URI | `com.personalailabs.astraldeep:/oauth2redirect` (**single slash**) | `redirectURI` |
| iOS OAuth client | `astral-mobile` — **shared with Android** | `iosClientId` |
| macOS OAuth client | `astral-desktop` — **shared with Windows** | `macosClientId` |
| watch OAuth client | `astral-watch` — **device-grant only**, no redirect | `watchClientId` |
| Realm authority | `https://iam.ai.uky.edu/realms/Astral` | `keycloakAuthority` |

### Single-slash redirect invariant

The redirect is `com.personalailabs.astraldeep:/oauth2redirect` — a custom
scheme followed by a **single** `/`. The diverging artifacts encode the scheme
as `astral`, which yields `astral://oauth2redirect` (double slash). Both the
scheme string **and** the slash form must land exactly on the value above,
because the Keycloak Valid Redirect URI is matched literally — a double-slash
or a different scheme fails the PKCE exchange closed.

### Shared-client model

iOS and macOS do **not** get dedicated Apple OAuth clients. They reuse the
existing cross-platform public clients (`astral-mobile` = the Android client's;
`astral-desktop` = the Windows client's). The consequence for the realm (see
[deployment-env.md](deployment-env.md) / D10): the Apple redirect
`com.personalailabs.astraldeep:/oauth2redirect` must be **added to the Valid
Redirect URIs of the shared `astral-mobile` and `astral-desktop` clients** — it
is not a new client, it is an added redirect on two existing ones. `astral-watch`
stays a device-authorization-grant-only client with no redirect.

### Companion bundle-id prefix (Apple requirement) — already satisfied

Now that the watch ships as an **embedded companion** (spec US8 / research D12,
not a watch-only app), Apple requires the companion's watch bundle id to be the
app bundle id **plus exactly one suffix segment** — the app id must be a strict
prefix. The shipped pair already satisfies this:
`com.personalailabs.astraldeep` (app) is a strict prefix of
`com.personalailabs.astraldeep.watch` (watch). This is not a change to make but
an invariant to preserve: `WKCompanionAppBundleIdentifier` in the watch
Info.plist points at the app bundle id, and the prefix relationship is what makes
the embed valid.

### One shared app bundle-id → one Universal Purchase record (D19)

The iOS and macOS targets both set `PRODUCT_BUNDLE_IDENTIFIER =
com.personalailabs.astraldeep`. A bundle id is unique per App Store Connect
record, so the two platforms **cannot** be separate records — they are a single
Universal Purchase record with two platform versions, and the embedded watch app
rides inside the iOS build. The identity set above is therefore also the
store-topology anchor: one bundle id here means one record, one listing, two
archives (iOS-with-embedded-watch, macOS). Signing consequently needs App Store
**three** provisioning profiles (iOS + macOS for the app bundle id; watchOS for `…​.watch`)
(`com.personalailabs.astraldeep` **and** `com.personalailabs.astraldeep.watch`).

## Divergences that MUST be fixed

### D-1 — the `project.yml` generator is retired (not reconciled)

[`apple-clients/project.yml`](../../../apple-clients/project.yml) carried the
pre-ship `com.kyopenscience.astral` family and the `astral` scheme, so
regenerating from it would have rewritten the working bundle ids and redirect
scheme and broken OAuth (the FR-012 hazard). It is **not reconciled — it is
deleted** (research **D18**). Three reasons compound:

- It had already drifted (`bundleIdPrefix: com.kyopenscience.astral`, scheme
  `astral`, an unconditional Release ATS exception) from the shipped
  `com.personalailabs.astraldeep` identities.
- XcodeGen **cannot** emit the "Embed Watch Content" copy-files phase the
  companion watch app now requires (D12), so a regenerated project would silently
  ship **without the watch app** — a failure that still compiles.
- Its own header already declared it optional and never required by CI or runtime.

The committed
[`AstralApp.xcodeproj`](../../../apple-clients/AstralApp/AstralApp.xcodeproj) is
the single canonical project, documented in the README. Retiring the generator
removes the entire drift class rather than patching it — there is no longer a
second source of project truth to keep in agreement, and no ATS/bundle-id/scheme
regeneration hazard to guard against.

### D-2 — README uses the old scheme and client-id list

[`apple-clients/README.md`](../../../apple-clients/README.md):

- **Step 4** ("URL Types: add scheme **`astral`**") → scheme
  `com.personalailabs.astraldeep`.
- **Step 6** (watch target — "no URL scheme needed"): the statement stays true
  (the watch runs no browser flow); the surrounding manual-setup steps must
  reflect the app scheme above and name the committed `.xcodeproj` as the single
  canonical project (there is no generator to regenerate from — D18).
- "Running against the dev backend" step 1 lists
  `KEYCLOAK_ALLOWED_AZP=…,astral-ios,astral-macos,astral-watch` → replace with
  `astral-mobile,astral-desktop,astral-watch`.

### D-3 — `docs/keycloak-realm-settings.md` §051 names rejected clients

The §051 table names `astral-ios` / `astral-macos` with redirect
`astral://oauth2redirect`. Fix so the docs name the code's identities:

- `astral-ios` → `astral-mobile` (note it is the client **shared with the
  Android client**, not a new one)
- `astral-macos` → `astral-desktop` (shared with the Windows client)
- redirect `astral://oauth2redirect` → `com.personalailabs.astraldeep:/oauth2redirect`
- remove the unresolved doc-vs-code conflict note; state the shared-client
  redirect step (add the Apple redirect to the two shared clients).

### D-4 — `.env.example` `KEYCLOAK_ALLOWED_AZP` comment names rejected clients

[`.env.example`](../../../.env.example) (the `KEYCLOAK_ALLOWED_AZP` block,
~lines 149–153): the comment says the Apple clients "use `astral-ios`,
`astral-macos` and `astral-watch`" and the example value lists
`…,astral-ios,astral-macos,astral-watch`. Fix both to
`astral-mobile,astral-desktop,astral-watch` (the deployable value is
`astral-desktop,astral-mobile,astral-watch` plus the web client).

### D-5 — Missing shared `AstralWatch.xcscheme` (D9 / FR-014)

`AstralApp.xcodeproj/xcuserdata/…/xcschememanagement.plist` already declares
`AstralWatch.xcscheme_^#shared#^_` as shared, but the file is **absent** from
`AstralApp.xcodeproj/xcshareddata/xcschemes/` (only `AstralApp.xcscheme` is
present). A clean clone therefore has no `AstralWatch` scheme, so
`apple-ci.yml`'s `-scheme AstralWatch` matrix leg and any clean-clone watch
build fail. Fix: **commit
`AstralApp.xcodeproj/xcshareddata/xcschemes/AstralWatch.xcscheme`** (marked
shared), so all three schemes resolve by name on a fresh checkout.

## Reconciliation table

| Location | Current | Must become |
|---|---|---|
| `apple-clients/project.yml` (generator) | present, drifted (`com.kyopenscience.astral` family, scheme `astral`, unconditional Release ATS) | **deleted — generator retired; committed `.xcodeproj` is canonical** (D18/FR-012) |
| `README.md` step 4 scheme | `astral` | `com.personalailabs.astraldeep` |
| `README.md` dev-backend AZP list | `astral-ios,astral-macos,astral-watch` | `astral-mobile,astral-desktop,astral-watch` |
| `docs/keycloak-realm-settings.md` §051 iOS client | `astral-ios` | `astral-mobile` (shared w/ Android) |
| `docs/keycloak-realm-settings.md` §051 macOS client | `astral-macos` | `astral-desktop` (shared w/ Windows) |
| `docs/keycloak-realm-settings.md` §051 redirect | `astral://oauth2redirect` | `com.personalailabs.astraldeep:/oauth2redirect` |
| `.env.example` AZP comment + example | `astral-ios,astral-macos,astral-watch` | `astral-mobile,astral-desktop,astral-watch` |
| `xcshareddata/xcschemes/AstralWatch.xcscheme` | absent (declared shared) | committed shared scheme |

Left unchanged (already authoritative): `Configuration.swift`, the committed
`AstralApp.xcodeproj` (now the **single canonical project**) INFOPLIST bundle ids
and `CFBundleURLTypes`, the app→watch bundle-id prefix relationship, and
`KEYCLOAK_DEVICE_CLIENTS=astral-watch`.

## Invariants

- **I-1 (FR-012 / SC-005)** — **Exactly one canonical Xcode project exists**:
  `apple-clients/project.yml` no longer exists in the repository, so there is no
  second source of project truth that can drift from the committed
  `AstralApp.xcodeproj`, and no regeneration hazard for OAuth to break. (Replaces
  the retired "regenerating reproduces a working redirect" invariant — there is
  no generator to regenerate from, D18.)
- **I-2 (FR-014 / SC-004)** — A clean clone builds all three schemes
  (`AstralApp` iOS, `AstralApp` macOS, `AstralWatch`) **by name** with no manual
  scheme creation, because every buildable target has a committed shared scheme.
- **I-3 (FR-013 / SC-010)** — The realm-settings doc and `.env.example` name the
  **same** OAuth client ids the code uses (`astral-mobile` / `astral-desktop` /
  `astral-watch`) and the same redirect, with no unresolved conflict note.
- **I-4** — The single-slash redirect `com.personalailabs.astraldeep:/oauth2redirect`
  is byte-identical across `Configuration.swift`, the committed
  `CFBundleURLTypes`, the realm Valid Redirect URIs on the two shared clients,
  and the docs.
- **I-5 (US8 / D19)** — The app bundle id is a strict **prefix** of the watch
  bundle id (`com.personalailabs.astraldeep` → `…​.watch`), as Apple requires for
  an embedded companion; and iOS + macOS share the app bundle id, fixing the
  store topology at **one** Universal Purchase record. Both are already satisfied
  by the committed project and must be preserved.

## Verification

- **Clean-clone build** (I-2): fresh checkout →
  `xcodebuild -scheme AstralApp` (iOS + macOS destinations) and
  `xcodebuild -scheme AstralWatch` resolve and compile; mirrors the
  `apple-ci.yml` matrix (quickstart US3 leg).
- **Single canonical project** (I-1): fresh checkout →
  `test ! -e apple-clients/project.yml` (no generator present); the committed
  `AstralApp.xcodeproj` is the only Xcode project and the README names it
  canonical. (Replaces the retired regeneration-parity check.)
- **Companion prefix + topology** (I-5): the watch bundle id begins with the app
  bundle id plus one segment, and the iOS and macOS targets resolve the same
  `PRODUCT_BUNDLE_IDENTIFIER` (grep the committed project) — confirming the
  single Universal Purchase record.
- **Doc/code identity match** (I-3): grep `docs/keycloak-realm-settings.md`,
  `.env.example`, and `README.md` for `astral-ios`/`astral-macos`/`astral`
  (bare scheme) → zero hits; the client ids present equal
  `Configuration.swift`'s.
