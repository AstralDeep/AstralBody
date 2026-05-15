# Phase 0 — Research: Persistent Login Across App Restarts

This document records the focused investigation behind the plan choices. No NEEDS CLARIFICATION items remain after this phase.

## R-1 — Switching `react-oidc-context` from sessionStorage to localStorage

**Decision**: Add `userStore: new WebStorageStateStore({ store: window.localStorage })` to the `oidcConfig` object in `frontend/src/main.tsx`.

**Rationale**:
- `react-oidc-context` is a thin React wrapper around `oidc-client-ts`. Both `UserManager` and `AuthProvider` accept a `userStore` option of type `StateStore`. The default is `WebStorageStateStore({ store: sessionStorage })`, which is *exactly why* current users get logged out when they close the browser.
- `WebStorageStateStore` is exported from `oidc-client-ts`, which is already in `frontend/package.json` (`^3.4.1`) as a transitive (declared sibling) of `react-oidc-context`. Importing from `oidc-client-ts` directly does not add a new dependency under Constitution V.
- All other OIDC concerns — silent renew (`automaticSilentRenew: true`), clock skew, refresh-token handling, sign-out via `end_session_endpoint` — continue to function identically. The library's storage layer is intentionally decoupled.

**Alternatives considered**:
- Roll our own IndexedDB-backed `StateStore` to gain encryption-at-rest. **Rejected**: browser localStorage on a same-origin app is already protected by browser origin partitioning and is exactly what the OIDC working group recommends for browser-based clients (RFC 8252 §8 + RFC 9700 §6.5). Adding encryption on top of that without a hardware-backed key (which the browser doesn't provide) would be security theater and would require a new dependency for envelope encryption — barred by Constitution V.
- HttpOnly cookie + BFF rotation. **Rejected**: this is a genuinely better security posture for refresh tokens, but it requires substantial backend changes (cookie issuance route, CSRF protection, opaque-token store), violates the user's explicit "respect the current login method, just extend the credential storing" instruction, and would expand scope beyond this feature.

## R-2 — Flutter WebView localStorage persistence across cold launches

**Decision**: Make zero changes to `flutter-passthrough/`. Rely on `webview_flutter`'s default behavior.

**Rationale**:
- **iOS** (`webview_flutter` → `WKWebView`): localStorage is persisted in the app's `Library/WebKit/WebsiteData/LocalStorage/` directory inside the app sandbox. iOS Data Protection class is `NSFileProtectionCompleteUntilFirstUserAuthentication` by default, which means the data is encrypted at rest and unlocked once the user has unlocked the device after boot. Persistence survives app force-quit and device reboot. The only way the data is removed is uninstall, "Offload App" (with "Keep documents" off), or explicit `WKWebsiteDataStore` purge calls — none of which the current `webview_screen.dart` triggers.
- **Android** (`webview_flutter` → `android.webkit.WebView`): localStorage / IndexedDB / cookies live under the app's private data directory `/data/data/<pkg>/app_webview/Default/Local Storage/`. `setDomStorageEnabled(true)` is the package default. Persistence survives app kill and device reboot. Cleared only on app uninstall, "Clear storage" from app settings, or explicit `WebStorage.deleteAllData()` calls.
- Current `webview_screen.dart` neither calls `WebStorage.deleteAllData()` nor configures a non-default data store, so the default persistent behavior is already in effect.

**Alternatives considered**:
- Add `flutter_secure_storage` to back up the refresh token in iOS Keychain / Android EncryptedSharedPreferences and inject it into the WebView at launch. **Rejected**: this adds a new dependency (Constitution V, lead-dev approval required), adds a non-trivial JS↔Dart bridging shim, and solves a problem that doesn't exist — WebView localStorage already lives in the app's protected sandbox and survives all the same events that Keychain/Keystore survive. The only difference is that Keychain survives an iOS app "Offload" with documents kept; the spec already lists that scenario as acceptable to force a re-login.
- Migrate to a native Flutter login UI with `flutter_appauth`. **Rejected**: violates the user's explicit "respect the current login method" instruction.

## R-3 — Keycloak realm offline-session lifespan settings

**Decision**: Set realm-level **Offline Session Idle** and **Offline Session Max** to ≥ 365 days (or `0` = unlimited for Max). Keep client **Access Token Lifespan** in its current 5–15 min range.

**Rationale**:
- The frontend already requests the `offline_access` scope. Keycloak issues an *offline token* under this scope which is exempt from regular SSO Session Idle limits but capped by the realm's Offline Session settings.
- Per Keycloak docs (Server Administration Guide §"Timeouts"): if Offline Session Idle is shorter than 365 days, the refresh token expires server-side after that many days of inactivity, which would break US1/US2 even though our local 365-day client cap hasn't elapsed. Setting it to at least 365 days makes the server's contract match the spec's.
- The Access Token Lifespan drives FR-004's revocation-propagation cadence; leaving it in the existing 5–15 min range is correct (matches the clarification Q1-of-session-2 answer).
- Note: this is operator configuration, not application code. The PR for this feature will include a `docs/keycloak-realm-settings.md` snippet documenting the required setting; the task list will include verifying it in staging.

**Alternatives considered**:
- Use regular (online) refresh tokens with `SSO Session Idle` extended to 365 days. **Rejected**: SSO Session Idle is shared across *all* clients in the realm; lengthening it would affect other applications that legitimately want short SSO timeouts. `offline_access` was designed for this exact "long-lived mobile/desktop client" use case.

## R-4 — 365-day client-side hard cap (FR-013)

**Decision**: Persist `initial_login_at: ISO8601` in our own `astralbody.persistentLogin.v1` localStorage record. On every app launch, before mounting `<AuthProvider>`, check whether `Date.now() - initial_login_at > 365 days`. If yes, clear all OIDC state (call `userManager.removeUser()` indirectly via `localStorage.removeItem` of the OIDC key) and fall through to the login screen.

**Rationale**:
- The OIDC library does not natively cap based on "time since interactive login" — its only expiry concept is the access-token / refresh-token expiry claim. Tracking the interactive-login anchor is therefore our responsibility.
- Doing it client-side is sufficient because the client controls the resume path. A leaked refresh token submitted directly to Keycloak after our local 365-day mark would still be honored by Keycloak (until *its* offline-session-max kicks in), but that's a stolen-credential scenario, not a returning-user-resume scenario; FR-009's revocation-on-signout and FR-004's per-refresh server check cover it.
- Setting `Offline Session Max` to exactly 365 days at the realm level gives us a server-side belt to go with the client-side suspenders — both terminate the session at the same time.

**Alternatives considered**:
- Encode the interactive-login timestamp into a custom Keycloak token claim and check it server-side on every request. **Rejected**: requires writing a Keycloak protocol mapper SPI (or a JWT post-processor) plus backend changes to honor a non-standard claim. Pure overhead for a guarantee we already get with the simpler client check.
- Skip the 365-day cap entirely and trust the realm setting. **Rejected**: the spec was explicit (Q1 session 1) that the 365-day clock is anchored at *interactive login*, not at refresh. Pure server enforcement would re-anchor on every refresh (sliding window), which is option C of that clarification — the rejected one.

## R-5 — Offline-tolerant revocation queue (FR-009b, FR-008)

**Decision**: Add a small `frontend/src/auth/revocationQueue.ts` module that:
- Exposes `enqueue(refresh_token: string, deployment_origin: string)`.
- Persists the queue in `sessionStorage` under the key `astralbody.revocationQueue.v1` (not localStorage — see below).
- Drains the queue on the `online` event and on app launch, calling Keycloak's revocation endpoint for each entry; removes successful entries; leaves failures for the next attempt.
- Hard-caps queue size at 16 entries (newest wins) to bound storage use.

**Rationale**:
- `sessionStorage` is the right home for this queue because if the user clears their browser data, we want the queue *gone* — replaying a sign-out for a credential whose local trace is already erased is wasted work, and we should not preserve a long-lived list of identifiers an attacker with localStorage read could harvest. (`sessionStorage` is also origin-scoped, so cross-deployment isolation comes for free.)
- The 16-entry cap is generous: realistic case is "user signs out once, network was down, retry on next launch" — queue size 1. The cap exists to bound an adversarial worst case.

**Alternatives considered**:
- Use `navigator.sendBeacon()` on the `pagehide` event to fire-and-forget the revocation. **Rejected**: works on web but not inside `WKWebView` reliably (varies by iOS version), and silently fails when offline — we wouldn't know to retry.
- Drop the queue entirely; rely on the offline-session timeout to invalidate eventually. **Rejected**: SC-003 demands 100 % rejection of replayed credentials after signout. Without the queue, an attacker who steals a token before the server-side timeout could replay it for up to a year.

## R-6 — Distinguishing interactive vs silent at audit time (FR-015)

**Decision**: Add an optional `resumed: boolean` field to the `register_ui` WS message (default `false` for backward compatibility). The frontend computes `resumed = wasSilentResume()` — true iff the OIDC `onSigninCallback` did **not** fire on this page load but the user is authenticated. The orchestrator's WS handler reads this flag and records `auth.session_resumed` instead of the existing `auth.ws_register` action_type pair when true. A separate `auth.login_interactive` is recorded after the `onSigninCallback` completes (before the WS connects).

**Rationale**:
- The existing audit hook in `backend/audit/hooks.py:65` records `event_class="auth", action_type=f"auth.{action}"`. Adding three new dotted actions is a one-line registry update plus three call sites; no schema change.
- Doing the resumed-detection on the client is correct: the server has no other way to tell — every WS connect looks the same to the backend.
- `auth.session_resume_failed` is recorded by the backend when the orchestrator rejects a WS register due to JWT validation failure on a request that included `resumed: true` (i.e., the client tried to silently resume but the server said no).

**Alternatives considered**:
- Roll all three identifiers into one with a payload field `entry_mode`. **Rejected** (Q4 session 3): the user explicitly chose option A (three distinct action_types). Naming things explicitly aids the audit-log UI's filter dropdown.
- Record only success cases (`login_interactive`, `session_resumed`) and let failures fall into the existing generic `auth.ws_register` failure path. **Rejected** for the same reason — explicit failure attribution lets operators quickly distinguish "user typed wrong password" from "stored credential rejected".

## R-7 — User-switch revocation on the same surface (FR-008)

**Decision**: At the moment a successful `onSigninCallback` completes, compare the new user's `sub` claim against `astralbody.persistentLogin.v1.last_user_sub`. If they differ AND `last_user_sub` is not null, push the prior user's refresh token (read from the soon-to-be-overwritten OIDC localStorage record) onto the revocation queue, then proceed with the normal callback. Once the queue drains, the prior user's credential is invalidated server-side.

**Rationale**:
- Catching the user switch at callback time is the only deterministic point: by the time the new tokens have been written, the old ones are gone. We read the previous OIDC record one tick before `react-oidc-context` overwrites it.
- The revocation request is fire-and-forget through the queue, so the new user's sign-in is never blocked by the prior user's revocation (matches the spec FR-008 wording).

**Alternatives considered**:
- Detect user-switch on launch instead of callback. **Rejected**: by the time the user has finished the OIDC redirect dance, the local OIDC record has already been replaced — there's no prior credential to revoke.
- Force the user to confirm "Replace previous user?" before allowing the new login. **Rejected** (Q2 session 2 option C — rejected by recommendation).

## R-8 — `oidc-client-ts` clock-skew default

**Decision**: No change. `oidc-client-ts` defaults `clockSkewInSeconds: 300` (5 minutes), which matches FR-010 (Q5 session 2) without any code change.

**Rationale**: confirmed by reading `oidc-client-ts` source — the `UserManagerSettings` interface initializes `clockSkewInSeconds` to `60 * 5` when undefined. We do not override it, so the value is correct by default.

## R-9 — Loading state during silent resume (FR-018)

**Decision**: Reuse the existing initial-loading UI rendered by `App.tsx` while `auth.isLoading === true`. No new component, no new splash. This is already the path taken on first paint today; the only difference is that `isLoading` now becomes true on every app launch (silent renew in progress) rather than only on a fresh login redirect.

**Rationale**: confirmed by reading `frontend/src/App.tsx` — the auth-gate branch renders the same `<LoginScreen />` if not authenticated; while loading, it returns null today (causing the 010 page-flash bug, fixed by feature 010's `loading: true` early-return path). We rely on that same path.

**Alternatives considered**: none — FR-018 was explicit (Q3 session 3 option A: "no new loading UI").

## R-10 — Soft-fail when protected store rejects the write (FR-006)

**Decision**: Wrap the `WebStorageStateStore.set()` calls in a try/catch via a thin `SafeWebStorageStateStore` adapter. On `QuotaExceededError`, `SecurityError` (private mode in some browsers), or `Error` from cross-origin storage policies, the adapter (a) discards the persisted write silently, (b) emits a `console.warn`, and (c) raises a one-time toast on the next render with the FR-006 message. The OIDC library still has the in-memory user, so the current session works; on next launch there is no persisted record and the login screen appears, which matches the spec.

**Rationale**:
- This is the smallest change that satisfies the spec: the existing `WebStorageStateStore` is a 30-line class; subclassing or wrapping it with a try/catch on `set()` is straightforward and adds no dependencies.
- We deliberately do not fall back to a less-protected store (FR-006 forbids this).

**Alternatives considered**: hard-block login on storage failure — explicitly rejected (Q5 session 3 option A).

---

All decisions above are reflected in the data model and contracts in Phase 1. No further research items remain.
