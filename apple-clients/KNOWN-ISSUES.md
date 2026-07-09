# Known issues — apple-clients (features 051 + 053)

Honest state of the tree (041 convention). Task numbers refer to
`specs/051-apple-native-clients/tasks.md` and
`specs/053-apple-app-store/tasks.md`.

1. **Realm prerequisites (RESOLVED on the dev realm 2026-07-07, needed per
   realm)**: (a) "OAuth 2.0 Device Authorization Grant" enabled on
   `astral-watch`; (b) `com.personalailabs.astraldeep:/oauth2redirect` in the
   Valid redirect URIs of `astral-mobile` (iOS/iPad) AND `astral-desktop`
   (macOS) — single slash after the colon, exact match. With both in place the
   full watch QR sign-in and macOS/iOS PKCE logins are live-verified
   (verification/results.md §Session 2). Note: realms that enforce a PKCE
   policy on `astral-watch` are supported — the broker sends S256
   `code_challenge` on start and the verifier on the token poll.
2. **macOS legacy login keychain — LOCAL ad-hoc builds only.** A local macOS
   build signed "Sign to Run Locally" (ad-hoc, and unsandboxed under Debug)
   writes tokens to the login keychain, so a rebuild that changes the code
   signature can trigger a keychain prompt or drop access (dev-machine
   annoyance, not a data leak). This does NOT apply to the shipped app: the
   **Release** configuration now enables App Sandbox + Hardened Runtime
   (`ENABLE_APP_SANDBOX[sdk=macosx*]` / `ENABLE_HARDENED_RUNTIME[sdk=macosx*]`,
   entitlements `AstralApp-macOS.entitlements`) and signs with a real
   distribution identity. Tokens live under the **default** per-app keychain
   access group — no `keychain-access-groups` entitlement is requested (least
   privilege, research D7). iOS/watchOS use the data-protection keychain with
   `AfterFirstUnlockThisDeviceOnly`.
3. **Keychain items survive app deletion on iOS/watchOS.** Deleting the app
   does not revoke the session; a reinstall silently resumes it (inside the
   365-day interactive anchor). Acceptable for the sign-in-once-per-device
   posture — sign out from the app (server-revoking) to actually end a
   session. Tokens are ThisDeviceOnly, so they never ride iCloud backups.
4. **`audio`/`generative` components are server-substituted** on iOS/macOS
   (044 channel decision, same as Windows/Android); the readable fallback
   view is the client-side safety net. The watch renders the profile's
   compact set natively and text-falls-back for the rest (FR-032).
5. **The watch is deliberately theme-static.** It uses the shared brand
   tokens (WatchTheme.swift) but does not consume `user_preferences` restyles
   or presets — recorded as a disposition in the parity matrix, not a gap.
6. **`param_picker` checklist/number field kinds** render natively but with
   simple controls (toggle list, decimal text field); date/file kinds fall
   back to text entry.
7. **Plotly charts render as native approximations** (first trace, bar/line/
   pie) exactly like the Windows/Android approximations; unsupported trace
   kinds show the readable fallback.
8. **Dev-backend LLM tool-calling degradation** (observed 2026-07-07): the
   dev orchestrator's configured LLM intermittently emits malformed tool
   calls, so agents reply "interactive components unavailable" with markdown
   fallbacks and occasionally leak raw tool-call markup into text. This hits
   ALL six clients identically — it is an LLM/config issue behind `_call_llm`,
   not a client rendering defect (the clients faithfully render what the
   server sends).
