# Known issues — apple-clients (feature 051, first increment)

Honest state of the tree as committed by the 051 foundational pass
(041 convention). Task numbers refer to `specs/051-apple-native-clients/tasks.md`.

1. **Swift sources are not yet compiler-verified.** The implementation
   sandbox had no Swift toolchain; `swift test` (AstralCore) and the first
   app builds run on the dev Mac and may need small mechanical fixes
   (imports, availability annotations). The logic itself is test-covered
   (drift guard, PKCE vector, backoff/queue contract, device-login pacing).
2. **No committed Xcode project yet.** Follow README §"Creating the Xcode
   project" (or `xcodegen`). CI's app-build job (T052) waits on this.
3. **Renderer coverage is the core subset.** text/alert/card/container/grid/
   metric/badge/hero/list/keyvalue/table/code/image/progress/divider render
   natively; charts, tabs, media and pickers currently use the readable
   fallback view (T025/T035 flip them to native and update
   `Dispositions.swift` + the parity matrix as they land).
4. **iOS attachments + chrome surfaces not started** (T027/T028); macOS
   pagination/theme-restyle rows pending (T033-T035); iPad viewport
   re-reporting pending (T030).
5. **Watch `component_action` round trips** (e.g. tapping a metric to
   re-run its source tool) are out of the first watch increment.
6. **Backend container suite**: the orchestrator send-path touch (speech
   attach) has unit tests but the FULL suite must be re-run in the
   `astralbody` container before merge (tasks.md checkpoint; the sandbox
   ran only the DB-free 051 suites).
7. **Realm verification pending**: the dev/prod Keycloak must have the
   device grant enabled on `astral-watch` (docs/keycloak-realm-settings.md
   §051); the broker fails closed with an actionable 503 until then.
