# AstralBody — native Apple clients (feature 051)

Three SDUI targets on one shared, zero-dependency Swift package:

```text
AstralCore/    # SPM package: protocol, dispositions + drift guard, WS client,
               # PKCE, device-login client, token stores, REST (swift test-able)
AstralApp/     # iOS (twin of android-client) + macOS (twin of windows-client)
AstralWatch/   # watchOS: QR sign-in (RFC 8628 via backend broker), voice in,
               # server-supplied spoken rendition out (on-device TTS)
```

Spec: `specs/051-apple-native-clients/` (contracts: `device-login.md`,
`spoken-rendition.md`). **No third-party Swift dependencies** (Constitution V).

## AstralPrims — the Swift `astralprims` mirror

`AstralCore/Sources/AstralCore/Primitives/` mirrors the first-party
[`astralprims`](https://github.com/AstralDeep/Astral-Primitives) Python
package (currently v0.3.0): the same 32 primitives (`AstralPrims.Text`,
`.Card`, `.Table`, `.Hero`, …) with the same serialization semantics —
`toDict()` ≙ `to_dict()`, `createUIResponse` ≙ `create_ui_response`,
`attributes` merged last (and able to override), `class_name` → `"class"`,
empty `css` omitted, non-Optional defaults emitted. Types are namespaced
under `AstralPrims` so nothing collides with SwiftUI. This is the AUTHORING
layer only — the consuming/render model stays `AstralComponent`
(Constitution II: astralprims defines → orchestrator renders → ROTE adapts).

```swift
let canvas = AstralPrims.createUIResponse([
    AstralPrims.Hero(title: "Q3 Sales", variant: "gradient"),
    AstralPrims.Grid(columns: 2).add(
        AstralPrims.MetricCard(title: "Revenue", value: "$1.2M", subtitle: "+12%"),
        AstralPrims.MetricCard(title: "New users", value: "3,401", variant: "success")),
])
```

Fidelity is pinned by known-answer fixtures generated FROM the live Python
package: every Swift construction in `PrimitivesTests` must byte-match its
Python `to_dict()`. When the pip package version bumps, regenerate:

```bash
docker cp apple-clients/AstralCore/Tests/AstralCoreTests/Fixtures/generate_fixtures.py \
  astralbody:/tmp/gen_fixtures.py
docker exec astralbody python3 /tmp/gen_fixtures.py
docker cp astralbody:/tmp/fixtures_out.json \
  apple-clients/AstralCore/Tests/AstralCoreTests/Fixtures/astralprims-fixtures.json
swift test --package-path apple-clients/AstralCore   # fails on any drift
```

## Test the core (any Mac, no Xcode project needed)

```bash
cd apple-clients/AstralCore
swift test        # includes the ui_protocol.json drift guard (FR-038)
```

## Creating the Xcode project (canonical, one-time)

1. Xcode → File → New → Project… → **Multiplatform App**, name `AstralApp`,
   save into `apple-clients/` (uncheck "create Git repository").
2. Delete the template `ContentView.swift`/`AstralAppApp.swift`; add the
   `AstralApp/` folder's sources to the target (uncheck "copy items").
3. File → Add Package Dependencies… → **Add Local…** → select
   `apple-clients/AstralCore`; link `AstralCore` to the target.
4. Target → Info → URL Types: add scheme **`astral`** (PKCE redirect).
5. App Transport Security: allow local networking for dev
   (`NSAllowsLocalNetworking`), or use HTTPS to the dev backend.
6. File → New → Target… → **watchOS App**, name `AstralWatch` (watch-only,
   not paired-companion); repeat steps 2-3 with the `AstralWatch/` sources;
   no URL scheme needed (the watch never runs a browser flow).
7. Signing: your development team on all targets.

**Shortcut**: `brew install xcodegen && cd apple-clients && xcodegen` writes
`AstralBody.xcodeproj` from `project.yml` (optional dev convenience only).

## Running against the dev backend

1. Backend up (`docker compose up -d`) with `.env`:
   `FF_DEVICE_LOGIN=true`, `KEYCLOAK_ALLOWED_AZP=…,astral-ios,astral-macos,astral-watch`,
   `KEYCLOAK_DEVICE_CLIENTS=astral-watch`.
2. Keycloak realm: create the three public clients per
   `docs/keycloak-realm-settings.md` §051 (device grant ON for `astral-watch`).
3. iOS/macOS app: enter the server URL + realm URL on the sign-in screen →
   Sign in (system browser PKCE).
4. Watch app: launches straight into the QR screen (server default
   `http://127.0.0.1:8001`; simulators reach the host directly). Scan with a
   phone camera or type the short code at the realm's `/device` page.

## Parity + CI

- Per-frame/per-component dispositions live in
  `AstralCore/Sources/AstralCore/Protocol/Dispositions.swift` — the
  machine-checked seed of the 044 parity matrix rows for ios/macos/watch.
- CI: `.github/workflows/apple-ci.yml` runs `swift test` on a macOS runner;
  the app-build job lands once the Xcode project is committed (tasks.md T052).
- Known gaps: `KNOWN-ISSUES.md`.
