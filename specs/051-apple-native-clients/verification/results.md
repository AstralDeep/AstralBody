# Live verification — 2026-07-07 (updated same night: full interactive pass)

## Session 2 — full six-client interactive verification (Screen Recording + Accessibility granted)

| # | Scenario | Result | Evidence |
|---|---|---|---|
| L1 | Realm device grant enabled on `astral-watch` (operator step) | ✅ | Keycloak Capability config |
| L2 | Broker PKCE: realm enforces S256 on the device flow; broker now sends `code_challenge` on start and `code_verifier` on the token poll (rides the encrypted handle) | ✅ | device_login.py + 18/18 broker tests incl. PKCE round-trip assertion |
| L3 | **Watch QR sign-in end-to-end LIVE**: cold launch → backend QR → phone-camera scan → IdP approval → tokens → signed-in home < 5 s | ✅ | `watch/03-qr-live.png`, `watch/05-signedin-home.png`; found+fixed a task-group bug (rotation timer as an outer-Task await was uncancellable, pinning approval handling ~10 min) |
| L4 | Watch identity display (approving account 'Sam Armstrong'), one-tap sign-out affordance | ✅ | `watch/05-signedin-home.png` |
| L5 | Watch conversation: one-tap New conversation → dictation sheet → confirm-before-send (Send/Discard) → standard pipeline (`Processing chat message: 'Weather'`, real chat id) → watch-adapted response with 120-char truncation + speech controls | ✅ | `watch/06-dictation-confirm.png`, `watch/07-conversation-live.png` |
| L6 | Watch keychain persistence across app REINSTALL: resumed signed-in (no QR), re-registered watch profile | ✅ | `watch/08-resume-recents.png` |
| L7 | Cross-device account inheritance: watch Recent list shows conversations created moments earlier on iPad + iPhone (same user; agents/permissions/LLM/personalization are all server-side per-user) | ✅ | `watch/08-resume-recents.png` |
| L8 | Watch chat re-hydration from another device's conversation (chat_loaded + speech-free ui_render), fixed speech-control glyphs | ✅ | `watch/09-rehydrated-chat.png` |
| L9 | iPhone live turn (Run example → `Roll 6d20…`): ack, skeleton canvas, step trail, reasoning snippets, streamed status, final card + History(1) canvas snapshot | ✅ | `ios/05-streaming-lifecycle.png`, `ios/06-components-live.png` |
| L10 | iPad: fresh PKCE sign-in (astral-mobile), split tablet layout (rail+canvas), hardware-keyboard input, live turn with Document component | ✅ | `ios/07-ipad-split-turn.png` |
| L11 | macOS: PKCE sign-in (astral-desktop + custom-scheme redirect URI registered), Windows-twin anatomy, live chat turn with markdown card + History pill | ✅ | `macos/02-signedin.png`, `macos/03-chat-turn.png` |
| L12 | Web client same welcome canvas/copy/palette (six-way consistency) | ✅ | `web-consistency.png` |
| L13 | Dev-backend LLM tool-calling degradation observed (leaked tool-call markup, "interactive components unavailable") — affects ALL clients equally; server/LLM-config issue, not a client defect | ℹ️ | `ios/07-ipad-split-turn.png` |

Remaining gaps: browser short-code entry path not separately captured (same IdP
verification page as the scanned QR, minus the camera); SC-005/SC-006 stopwatch
timings not instrumented (observed: watch flip < 5 s after approval; speech
begins with the delivery frame).


**Environment**: dev backend in the `astraldeep` container (localhost:8001,
`ASTRAL_ENV=development`, `FF_DEVICE_LOGIN=true`,
`KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral`); iPhone 17 Pro
simulator (iOS 26.x), Apple Watch Series 11 (46 mm) simulator; macOS app on
the dev Mac. Builds: `xcodebuild` Debug, all three targets, from this tree.

Result vocabulary: ✅ pass · ⚠️ partial (reason) · ⛔ blocked (external
dependency) — nothing is marked pass without being observed live.

| # | Scenario | Result | Evidence |
|---|---|---|---|
| 1 | AstralCore `swift test` (drift guards, PKCE vector, backoff/queue, device-login pacing) | ✅ 23/23 | CI-equivalent run on the dev Mac |
| 2 | Backend 051 suites in the container (QR, broker, profiles, speech) | ✅ 42/42 | `pytest tests/test_{qr,device_login,apple_profiles,watch_speech}.py` |
| 3 | Full backend container suite (T056 gate, final tree incl. chrome/designer gates, speak flag, webrender changes) | ✅ 3113 passed / 3 skipped / 0 failed | + `ruff check .` clean; diff-cover vs origin/main = 90% on 1040 changed lines |
| 4 | iOS build (`generic/platform=iOS Simulator`) | ✅ | BUILD SUCCEEDED |
| 5 | macOS build (`platform=macOS`) | ✅ | BUILD SUCCEEDED |
| 6 | watchOS build (`generic/platform=watchOS Simulator`) | ✅ | BUILD SUCCEEDED |
| 7 | iOS cold launch → silent keychain resume → WS register with `ios` profile → server-driven welcome canvas rendered natively | ✅ | `ios/01-signin.png`; backend log `ROTE: registered device — type=ios viewport=402x778 charts=True tables=True grid_cols=6` for `oidc.sam.armstrong@uky.edu` |
| 8 | iOS themed chrome (brand mark, New pill, Recent, gear), input bar (mic/paperclip/send), AstralDeep midnight palette | ✅ | `ios/01-signin.png` |
| 8b | Server-owned chrome model reaches `ios` sockets: top-bar Pulse/Timeline actions render from `chrome_menu` after the 051 backend gate fix | ✅ | `ios/02-signedin-chrome.png` (compare 01 — icons absent before the fix) |
| 9 | Watch cold launch signed-out → device-login start against the live broker | ✅ (fail-closed path) | `watch/01-devicelogin.png` |
| 10 | Watch QR + short code + countdown; phone-scan and browser short-code approval (SC-001) | ⛔ realm toggle | The live IdP refuses: *"Device Authorization Grant … disabled for the client"*. Enable **OAuth 2.0 Device Authorization Grant** on `astral-watch` (Keycloak → Clients → astral-watch → Capability config), then rerun. The watch shows the actionable fail-closed message with Retry — FR-026 verified live. |
| 11 | Interactive chat round trip on iOS/macOS (send → progress → components) | ⚠️ needs a human at the sim | Simulator keyboard/tap injection needs assistive access this session doesn't have; the signed-in canvas (scenario 7) already proves auth + WS + ROTE + native SDUI rendering end-to-end. |
| 12 | macOS app launch | ⚠️ launched, not captured | `open …/Debug/AstralDeep.app` succeeded; screen capture needs Screen Recording permission — capture manually or grant and rerun. |
| 13 | SC-005/SC-006 watch voice/TTS timing | ⛔ depends on #10 | Measurable once the watch can sign in (realm toggle). |
| 14 | Device-login broker: single-use handles, TTL, slow_down pacing, role gate, rate limits, no token logging (SC-009) | ✅ | `tests/test_device_login.py` (18 tests) — state-machine coverage with injected fake IdP |
| 15 | Watch degradation sweep: all 35 component types through a watch-profile socket ⇒ bounded visual + speech, zero errors (SC-002) | ✅ | `tests/test_watch_speech.py` sweep (T047) |

**Blocked items (10, 13) are one realm-admin toggle away** — every code path
below them is live- or test-verified. Scenario 11's remaining gap is a
human-driven capture, not a code gap.
