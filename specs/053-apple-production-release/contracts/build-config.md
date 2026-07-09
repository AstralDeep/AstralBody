# Contract: Build-Time Configuration (endpoint / realm / ATS / versioning)

Governs how a build's backend endpoint, Keycloak realm, App-Transport-Security posture, and
version/build-number are supplied **from version-controlled configuration** rather than from
hardcoded source — so a Release build ships the production endpoint, ATS-clean, and can be
repointed without a code change. Resolves **D2** (endpoint/realm indirection), **D3** (ATS
scoping), **D5** (versioning). Maps **FR-006, FR-008, FR-009, FR-010, FR-011**.

**New files**: `apple-clients/Config/{Base,Debug,Release}.xcconfig`.
**Edited**: `apple-clients/AstralApp/Info.plist`, `apple-clients/AstralApp/WatchInfo.plist`,
`apple-clients/AstralCore/Sources/AstralCore/Configuration.swift`,
`apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj` (xcconfig wiring + versioning),
~~`apple-clients/project.yml`~~ **RETIRED/DELETED** (D18) — the committed `.xcodeproj` is the sole source for these keys; see `contracts/client-identity.md` for the
identity keys; this contract owns the endpoint/ATS keys).

---

## 1. xcconfig key set (D2)

Every build configuration includes `Base.xcconfig`, then a leaf `Debug.xcconfig` /
`Release.xcconfig` override. Wiring is the per-configuration `baseConfigurationReference` in
`project.pbxproj` (or `#include "Base.xcconfig"` from each leaf).

| Key                         | Debug value                            | Release value                          |
| --------------------------- | -------------------------------------- | -------------------------------------- |
| `ASTRAL_SERVER_BASE_URL`    | `http://localhost:8001`                | `https://sandbox.ai.uky.edu`           |
| `ASTRAL_KEYCLOAK_AUTHORITY` | `https://iam.ai.uky.edu/realms/Astral` | `https://iam.ai.uky.edu/realms/Astral` |

Notes:

- `Base.xcconfig` holds shared, non-endpoint settings (the versioning keys in §5) **and** a
  Release-equal default for both endpoint keys, so an unspecified/misconfigured configuration
  fails **safe** (production endpoint), never toward localhost.
- The realm authority is identical across configurations today (both point at the real IdP). It
  is still expressed as a key so a future distinct dev/prod realm is a one-line config edit, not a
  code change (FR-009).
- **`//`-escaping caveat (D2)**: xcconfig treats `//` as a line comment, so a raw `//` inside
  `http://` / `https://` truncates the value. Escape it with the empty-macro trick —
  `ASTRAL_SERVER_BASE_URL = http:$()//localhost:8001` (and `https:$()//…` for Release). `$()`
  expands to nothing at build time, yielding the correct literal while defeating the comment
  scanner. This applies to **every** value containing `//` (both endpoint keys, both configs).

---

## 2. Info.plist surfacing (D2)

Both app plists gain two custom keys whose values are `$(...)` build-setting substitutions of the
xcconfig keys above:

| Info.plist key            | Value (substitution)           |
| ------------------------- | ------------------------------ |
| `ASTRALServerBaseURL`     | `$(ASTRAL_SERVER_BASE_URL)`    |
| `ASTRALKeycloakAuthority` | `$(ASTRAL_KEYCLOAK_AUTHORITY)` |

- Added to **both** `AstralApp/Info.plist` (iOS/macOS) and `AstralApp/WatchInfo.plist` (watchOS),
  so every target resolves its endpoint from its own baked plist.
- Flow at build time: active-configuration `*.xcconfig` value → build setting → `$(...)`
  substitution → the target's `Info.plist` in the built product. The escaped literal from §1 lands
  in the plist as a clean `http://…` / `https://…` string (`$()` already collapsed).

---

## 3. Configuration.swift read contract (D2)

`AstralConfig.serverBaseURL` and `AstralConfig.keycloakAuthority` are rewritten to **read the baked
Info.plist keys at runtime** instead of selecting on `#if DEBUG`:

- Read via `Bundle.main.object(forInfoDictionaryKey: "ASTRALServerBaseURL")` (and
  `"ASTRALKeycloakAuthority"`), cast to `String`, trimmed, require non-empty.
- **Sandbox fallback (required)**: when the key is absent or empty — e.g. `AstralCore` unit tests
  run with **no host bundle**, so `Bundle.main` carries no `Info.plist` keys — resolve to the
  production defaults (`https://sandbox.ai.uky.edu`, `https://iam.ai.uky.edu/realms/Astral`). The
  fallback is the **sandbox** value, never localhost, so a missing/misbuilt plist still fails safe
  (FR-010) and `swift test` still resolves a valid config with no host app.
- **The `#if DEBUG` hardcode is removed.** After this change no compile-time branch embeds
  `http://localhost:8001` in a Release-reachable path — the only localhost string in the tree lives
  in `Debug.xcconfig`, which is not part of a Release build (FR-010 / SC-003).
- The existing OAuth client ids (`iosClientId` / `macosClientId` / `watchClientId`),
  `redirectScheme`, and `redirectURI` in `Configuration.swift` are **unchanged** — they are backend
  contracts shared with the Android/Windows clients (see `contracts/client-identity.md`). Only the
  two endpoint accessors change.
- The watch runtime override (FR-011, D12) layers **on top of** this read: `AstralConfig` supplies
  the default; a companion-synced override, when present, supersedes it at run time without a
  rebuild. The default-resolution contract here is the floor the override falls back to.

---

## 4. ATS contract (D3)

The former blanket `NSAppTransportSecurity → NSAllowsArbitraryLoads = true` in **both**
`AstralApp/Info.plist` and `WatchInfo.plist` is removed. In its place both plists carry **only**
`NSAllowsLocalNetworking = true`, **unconditionally** (not per-configuration).

- **Why unconditional, not Debug-scoped**: a static `Info.plist` cannot be made per-configuration
  without maintaining two duplicate plists. `NSAllowsLocalNetworking` is App-Store-safe in a
  Release build regardless — it relaxes ATS **only** for loopback (`localhost` / `127.0.0.1`) and
  `*.local` names and **never** permits an insecure load to a public host. Carrying it in every
  configuration keeps the Debug localhost endpoint working without ever weakening the Release
  security posture.
- **Release**: ATS-compliant — **no** `NSAllowsArbitraryLoads`, no domain exceptions. The backend
  is HTTPS (`sandbox.ai.uky.edu`), which ATS permits by default; the only relaxation present
  (`NSAllowsLocalNetworking`) cannot reach a public host (FR-006). **VERIFIED** on the macOS
  Release product: `NSAllowsArbitraryLoads` is absent.
- **Debug**: the localhost dev endpoint (`http://localhost:8001`) loads under the same
  `NSAllowsLocalNetworking = true`, which covers `localhost` / `127.0.0.1` / `*.local` — not a
  blanket arbitrary-loads exception (matching the *former* `project.yml` intent, now retired — D18).

---

## 5. Version & build-number contract (D5)

| Setting                   | Source                                  | Rule |
| ------------------------- | --------------------------------------- | ---- |
| `MARKETING_VERSION`       | Human-set in xcconfig / `project.pbxproj` | Bumped per release; **guarded** by a tag-vs-`MARKETING_VERSION` check in `apple-release.yml` (mirrors `release-windows.yml`) so a mislabeled build cannot ship. |
| `CURRENT_PROJECT_VERSION` | CI run number, applied at archive time  | Derived automatically — `CURRENT_PROJECT_VERSION=$GITHUB_RUN_NUMBER` passed to `xcodebuild` at archive time (a build-setting override, **not** `agvtool`), never hand-edited; monotonic → successive archives carry **distinct, increasing** build numbers (FR-008), so App Store Connect never rejects a duplicate. |

- Both surface into the plists via the `$(MARKETING_VERSION)` / `$(CURRENT_PROJECT_VERSION)`
  substitutions already present in `Info.plist` / `WatchInfo.plist`
  (`CFBundleShortVersionString` / `CFBundleVersion`) — no plist change required for versioning.
- The watch and its companion share a consistent `MARKETING_VERSION`; build-number monotonicity is
  applied per archive so paired submissions never collide.
- Full pipeline wiring (secrets, archive/export/upload) lives in `contracts/release-pipeline.md`;
  this contract owns only the *values* and their non-collision guarantee.

---

## 6. Invariants

- **INV-1 (FR-010 / SC-003)** — No hardcoded `localhost` / `127.0.0.1` / dev endpoint is reachable
  in a Release build. The only localhost literal is in `Debug.xcconfig`; the `Configuration.swift`
  fallback is the sandbox endpoint. Verifiable by searching Release-reachable source/config.
- **INV-2 (FR-009)** — Repoint without a code change: editing `ASTRAL_SERVER_BASE_URL` /
  `ASTRAL_KEYCLOAK_AUTHORITY` in the xcconfig and rebuilding retargets every target; no Swift edit.
- **INV-3 (FR-006)** — Release is ATS-compliant: no blanket `NSAllowsArbitraryLoads` anywhere.
  The only relaxation is `NSAllowsLocalNetworking` (loopback/`.local` only, App-Store-safe),
  carried **unconditionally** in both plists; it never permits an insecure load to a public host.
- **INV-4 (FR-008)** — Every archive carries a marketing version and a unique, monotonically
  increasing, auto-applied build number.
- **INV-5 (FR-011)** — The watch endpoint default resolves through this contract; the runtime
  override (companion-synced, D12) is the only path that supersedes it and requires no rebuild.
- **INV-6 (Constitution V / FR-026)** — Achieved with the Apple toolchain only (xcconfig +
  Info.plist substitution + `Bundle.main`) — zero new third-party dependency.
