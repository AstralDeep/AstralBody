# US1 — Apple targets: local build + test evidence (macOS host)

**Date**: 2026-07-13 · **Machine**: Sam's Mac (Apple Silicon, Xcode 26 toolchain, macOS 26)
**Branch**: `055-uniform-artifacts` @ post-US1 (b31f66a includes Phase 1 vocabulary)

The 2026-07-13 US1 implementation session (Windows machine) deferred Apple
compilation to CI; this records the first local Apple verification.

| Check | Command | Result |
|---|---|---|
| AstralCore suite (incl. `WelcomePurgeTests`, `ManifestDriftTests`) | `swift test --package-path apple-clients/AstralCore` | **111 tests, 0 failures** |
| iOS app compiles | `xcodebuild -scheme AstralApp -destination "generic/platform=iOS Simulator" build` (unsigned, Debug) | **BUILD SUCCEEDED** |
| macOS app compiles | `xcodebuild -scheme AstralApp -destination "platform=macOS" build` | **BUILD SUCCEEDED** |
| watchOS app compiles | `xcodebuild -scheme AstralWatch -destination "generic/platform=watchOS Simulator" build` | **BUILD SUCCEEDED** |
| T016 first-turn contract tests | `xcodebuild test -scheme AstralApp -destination "platform=iOS Simulator,name=iPhone 17 Pro"` | **`AppModelFirstTurnContractTests` 7/7 passed** (AstralAppTests 12/12) |

Known non-blocking warnings: `mutation of captured var 'resumed'` in
`AppModel.swift:419` / `WatchModel.swift:300` (Swift 6 language-mode advisory;
pre-existing, not introduced by 055).

Live on-simulator interaction (quickstart §US1 items 3–4) requires an
interactive Keycloak sign-in (the Apple clients have no dev-token path;
`iam.ai.uky.edu` PKCE only). Simulators are staged — iPhone 17 Pro + Watch
Series 11 booted, Debug apps installed, `serverBase` override prefilled to
`http://localhost:8001` — pending the operator's one-time sign-in; results to
be appended here.
