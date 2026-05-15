# Feature Specification: Persistent Login Across App Restarts (Web + Flutter Wrapper)

**Feature Branch**: `016-persistent-login`
**Created**: 2026-05-15
**Status**: Draft
**Input**: User description: "I serve the AstralBody system through a flutter project for various devices. basically it just renders the html to an app (iphone/android/whatever) called flutter-passthrough. What I want to add is credential storage on device (or browser) that allow the user to stay logged in for a year, so they do not have to log in every time they open the app. can you add this to the AstralBody system"

## Clarifications

### Session 2026-05-15

- Q: Is the 1-year retention a hard maximum lifetime, an idle window, or sliding renewal? → A: Hard maximum — 365 days from the initial interactive login, the user must re-authenticate regardless of activity.
- Q: On app/browser open with a stored credential, when is a fresh user-presence check (device biometric / OS passcode / re-entered password) required before reaching the dashboard? → A: Never — the stored credential always silently resumes to the dashboard; the device's own lockscreen is the protection layer.
- Q: What does the "visible indicator that the user is staying signed in" look like? → A: The user's identity (username/avatar) is visible in the existing sidebar/header with a one-click "Sign out" reachable from it — no new dedicated banner or toast.
- Q: How are credentials isolated when more than one deployment (e.g., sandbox + prod) is in play? → A: Per-deployment on web (browser-origin isolation), and on the Flutter wrapper the credential store may hold multiple deployments simultaneously so a user can swap between configured backend URLs without re-login.
- Q: What happens on sign-out when the auth server is unreachable (offline, server down)? → A: Clear local credentials unconditionally and immediately; queue the server-side revocation request for best-effort retry on next online opportunity; surface a small "signed out locally, server confirmation pending" notice to the user.
- Q: How quickly must a server-side revocation (admin lockout, password change, account disabled) take effect on a session that is already open? → A: On every silent token refresh — propagation is bounded by the short-lived access credential's TTL (typically minutes); no separate revocation poll is required.
- Q: When user Y signs in on a surface where user X's credential is still stored (X never explicitly signed out), what happens to X's leftover credential? → A: Local clear plus server-side revoke of X's leftover credential before Y is signed in — closes the "leftover extracted before deletion" replay window at near-zero cost.
- Q: Which identifier is displayed in the sidebar/header identity element for the signed-in user? → A: Avatar/initial only — no text label in the chrome; the full identity (name + email) appears only on hover or click of the avatar.
- Q: What is the concrete bounded-retry policy on transient refresh failures (FR-011)? → A: 3 attempts total with exponential backoff (1 s, 3 s, 9 s) — ~13 s of total wait before falling back to the login screen.
- Q: What is the concrete clock-skew tolerance for credential expiry checks (FR-010)? → A: ±5 minutes — the industry-default JWT clock-skew leeway.
- Q: Is there an explicit "Stay signed in" / "Remember me" toggle on the login screen, or is 365-day persistence automatic on every successful login? → A: Always on — every successful interactive login enrolls for 365-day persistence; there is no login-time toggle. The existing sign-out control is the user's only off-switch.
- Q: How is the "staying signed in" indicator surfaced — new avatar element, header text, popover menu? → A: No new UI is introduced. The application chrome stays exactly as it is today. The existing sign-out button is the only signed-in affordance and is considered sufficient.
- Q: What does the user see during the brief window between "stored credential detected" and "dashboard ready" on launch? → A: Reuse the existing initial-loading state (the same one already shown while the app boots) — no new loading UI, no transient login-screen flash, no dedicated "signing you in" splash.
- Q: What audit identifiers are introduced for the silent-resume vs interactive-login distinction (FR-015)? → A: Three new `action_type` values under the existing `event_class="auth"` bucket — `auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed` — mirroring the existing dotted convention used by `auth.ws_register` and `auth.ws_disconnect`. No new `event_class` values are added.
- Q: What happens when the platform's protected-storage facility rejects the credential write at login time (Keychain/Keystore disabled, sandbox failure, disk full)? → A: Soft-fail — the login completes and the user proceeds into the dashboard for the current session; a dismissible warning informs the user that persistence is disabled for this session and they will need to sign in again at next launch.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Returning Web User Stays Signed In (Priority: P1)

A user signs in to AstralBody in a desktop or laptop browser, closes the browser tab (or the entire browser), and reopens the application later — from minutes to many months later. On reopening, they land directly in the dashboard without seeing the login screen and without typing a password, exactly as if they had never left. This holds for the full retention window the system promises (target: up to 1 year).

**Why this priority**: This is the foundational capability and the highest-impact slice. Today every browser session that ends forces a fresh interactive login, which is the main friction point the user is asking us to remove. If we ship only this slice, web users — the largest share of traffic — already get the promised "stay logged in for a year" experience.

**Independent Test**: Sign in fresh, perform any normal authenticated action (e.g., open a chat). Fully close the browser. Reopen the application URL at +1 minute, +1 hour, +7 days, and +30 days. In every case, the dashboard renders without any login prompt and any backend call (e.g., loading chat history) succeeds with the user's identity.

**Acceptance Scenarios**:

1. **Given** a user who has just signed in on the web, **When** they close every tab/window and reopen the app from a bookmark, **Then** they arrive at the dashboard authenticated, without entering credentials.
2. **Given** a user whose access window has expired but whose long-lived credential is still valid, **When** they open the app, **Then** the system silently refreshes their access in the background and the dashboard renders without a perceptible delay attributable to authentication.
3. **Given** a user who has not opened the app for more than the retention window, **When** they open the app, **Then** they are taken to the login screen with a message indicating their session has expired.
4. **Given** a user whose stored long-lived credential has been revoked server-side (e.g., they were removed from the realm, the operator forced a logout, the password was changed), **When** they open the app, **Then** the locally stored credential is discarded and they are sent to the login screen with a clear message that they must sign in again.

---

### User Story 2 — Returning Mobile App User Stays Signed In (Priority: P1)

A user installs the Flutter-wrapped AstralBody app on iPhone or Android, signs in inside the app's web view, and then backgrounds, force-quits, or reboots the device. The next time they tap the app icon — minutes, days, or months later — the app opens directly into the dashboard with no login prompt, for the full retention window (target: up to 1 year).

**Why this priority**: Mobile is the primary delivery vehicle for the flutter-passthrough product, and re-typing a password on a phone keyboard every session is exactly the friction the user is asking us to eliminate. Without this slice, the feature does not meaningfully change the mobile experience even if web persistence works.

**Independent Test**: On a fresh install, sign in inside the Flutter app. Force-quit the app from the OS app switcher. Reboot the device. Reopen the app after each of the following intervals: +1 minute, +1 hour, +7 days, +30 days. In every case, the dashboard renders without a login prompt and the user's authenticated identity is correctly attributed in any backend audit event triggered by an in-app action.

**Acceptance Scenarios**:

1. **Given** a user who has signed in inside the Flutter wrapper on iOS or Android, **When** they force-quit the app and relaunch it, **Then** they arrive at the dashboard authenticated, without entering credentials.
2. **Given** the same user, **When** they reboot the device and then open the app, **Then** they arrive at the dashboard authenticated.
3. **Given** the OS has not deleted app data, **When** the user opens the app at any point inside the retention window, **Then** they remain signed in without entering credentials.
4. **Given** the OS or the user has cleared the app's data (e.g., uninstall/reinstall, "clear storage", iOS app offload), **When** the user opens the app, **Then** they see the login screen and a fresh sign-in is required — this is acceptable and expected.

---

### User Story 3 — User Can Sign Out and Be Forgotten (Priority: P2)

A user who chooses "Sign out" from inside the app is fully signed out: their long-lived credential is cleared from the device or browser, the credential is also invalidated server-side so that it cannot be reused even if extracted from local storage, and reopening the app afterward returns them to the login screen.

**Why this priority**: Without an explicit, trustworthy sign-out, the persistent-login behavior creates an unacceptable security and shared-device risk. This must ship alongside the persistence work, but persistence is what delivers the headline value, hence P2.

**Independent Test**: Sign in, then choose "Sign out". Reopen the app immediately and after 1 day — in both cases the login screen appears. Additionally, attempt to replay the previously-issued long-lived credential against the backend; the backend rejects it as invalid.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they choose "Sign out", **Then** all stored credentials for that user are removed from the device or browser before the app navigates away from the dashboard.
2. **Given** a user who has signed out, **When** they reopen the app, **Then** the login screen is shown.
3. **Given** a user who has signed out, **When** a copy of their previously-stored long-lived credential is replayed against the backend, **Then** the backend rejects it.
4. **Given** a user has signed out on device A, **When** they continue to use device B (where they had also signed in), **Then** device B's session is unaffected — sign-out is local to the device that initiated it.

---

### User Story 4 — Refresh Failure Recovers Gracefully (Priority: P2)

When the system attempts to use a stored long-lived credential and the attempt fails for any reason — network offline, server unreachable, credential revoked, credential expired, account disabled — the app must not get stuck on a blank screen, must not show a cryptic error, and must not silently retry forever. The user is presented with a clear next step.

**Why this priority**: This is the failure mode that turns the feature from "magic" into "broken" if mishandled. It must ship together with the happy path but does not itself deliver headline value, hence P2.

**Independent Test**: Manually invalidate the stored credential (e.g., revoke from the auth server, or corrupt the local value), then reopen the app. Verify the user sees a login screen with a message explaining the session ended, rather than a perpetual spinner or an unauthenticated dashboard.

**Acceptance Scenarios**:

1. **Given** a stored credential that the server now rejects, **When** the app starts, **Then** the user is taken to the login screen with a message such as "Your session expired. Please sign in again."
2. **Given** the device has no network at app launch, **When** the app attempts to refresh, **Then** the app surfaces an offline indicator and offers retry, rather than silently leaving the user on a stale unauthenticated state.
3. **Given** a transient server outage, **When** refresh fails with a 5xx, **Then** the app retries silently a bounded number of times before falling back to the login screen with a "We could not sign you in — please try again" message.

---

### Edge Cases

- The user signs in on the web and then later opens the Flutter app on the same device account — each surface maintains its own persistent credential; they do not need to share storage.
- The user is signed in on multiple devices. Signing out on one device must not sign them out on the others. Server-side revocation by an administrator (e.g., emergency lockout) must invalidate every device on next refresh.
- The user's underlying identity provider account is deleted or disabled while the device is offline. On next online use, the next refresh attempt fails and the user is returned to the login screen.
- A device is shared (kiosk, library terminal, family tablet). Persistent login is appropriate for personal devices but risky for shared ones. The existing sign-out control is the only built-in safeguard against this; per FR-012 no additional UI cue is added. Users on shared devices are expected to invoke sign-out themselves; the feature does not attempt to detect shared-device usage.
- The system clock on the device is wrong (far future or far past). The system tolerates up to ±5 minutes of clock skew per FR-010. Beyond that, the device's local expiry check may reject a credential the server would still accept (or vice versa); the next online refresh attempt corrects the outcome because the server is the authoritative judge.
- The protected-storage facility rejects the credential write at login time (storage full, keychain/keystore disabled, sandbox failure). The user proceeds into the dashboard for the current session per FR-006; a dismissible warning informs them that persistence is disabled and they will need to sign in again at next launch. The system MUST NOT silently fall back to a less-protected store.
- The user upgrades the Flutter app to a new version that changes how storage is keyed. Stored credentials from the previous version must either be migrated forward transparently or, at worst, force a single re-login — never a corrupt/stuck state.
- The user toggles their browser's "private/incognito" mode. Persistence in incognito is best-effort; if storage is wiped on tab close, the user re-authenticates on next open. This is expected and not a defect.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST, on every successful interactive login, persist enough authentication state on the user's device or browser that the user remains signed in across full app/browser restarts for up to 365 days from that login (subject to FR-013's hard maximum). Persistence MUST be enabled automatically; the login screen MUST NOT present a "Stay signed in" / "Remember me" toggle, and there MUST NOT be an in-app setting that disables persistence for future logins on this device. The user's only way to opt out of the persisted session is to invoke the sign-out control described in FR-012.
- **FR-002**: System MUST, on app or browser launch, detect a previously stored credential, validate it against the auth server, and place the user into the dashboard without an interactive login prompt whenever validation succeeds.
- **FR-003**: System MUST, when stored credentials are not present, are expired, or are rejected by the auth server, route the user to the existing interactive login screen with a message that distinguishes "your session ended" from a first-time login.
- **FR-004**: System MUST refresh the user's short-lived access credential silently in the background whenever it is close to expiring, without interrupting the user's current activity, for as long as the long-lived credential remains valid. Each silent refresh attempt MUST exchange the long-lived credential with the auth server, which means a server-side revocation of the long-lived credential (admin lockout, password change, account disabled) MUST cause the next refresh to fail and the user to be redirected to the login screen. Propagation of any such revocation to an active session is bounded by the short-lived access credential's TTL; no separate revocation poll is required.
- **FR-005**: System MUST persist credentials in storage that survives full application restart and device reboot on all supported targets — browser, iOS Flutter wrapper, Android Flutter wrapper.
- **FR-006**: System MUST store credentials using each platform's recommended protected storage facility (e.g., OS-managed secure storage on mobile, browser-managed origin-isolated storage on web) rather than in locations that other applications on the same device can read. If that protected store rejects the write at login time (e.g., Keychain/Keystore disabled, sandbox failure, disk full), the system MUST NOT block the login: the user MUST be allowed to proceed into the dashboard for the current session, and the system MUST surface a clear, dismissible warning that persistence is disabled for this session and they will need to sign in again at next launch. The system MUST NOT silently fall back to a less-protected store.
- **FR-007**: System MUST scope every stored credential to the originating server identity (issuer + backend base URL) so that a credential issued by one deployment is never sent to a different deployment. On the web, this isolation is provided by browser-origin partitioning. On the Flutter wrapper, the credential store MUST be capable of holding multiple deployments simultaneously, keyed by backend URL, so that a user who switches the configured backend (e.g., between sandbox and production) MUST find their prior credential for that backend still present and usable without a forced re-login — provided that credential is still within its retention window and has not been revoked.
- **FR-008**: System MUST scope stored credentials to a single user account per device or browser profile. When a different user signs in on the same surface, the prior user's stored credentials MUST be replaced, not merged. Specifically, before the new user's credential is written: (a) the prior user's long-lived credential MUST be submitted to the auth server as a revocation request on a best-effort basis, applying the same offline-tolerant queue-and-retry behavior as FR-009(b); (b) the prior user's stored credentials MUST be cleared from local storage unconditionally regardless of whether the revocation request succeeded. The new sign-in MUST NOT be blocked by failure of the revocation request. Sign-out on one device MUST continue to be local to that device and MUST NOT sign the prior user out of their other devices.
- **FR-009**: Users MUST be able to sign out from inside the app, and on sign-out the system MUST:
  - (a) Remove all stored credentials for the active deployment from the device or browser **unconditionally and synchronously**, before navigating away from the authenticated UI. This step MUST succeed and the user MUST appear signed out locally regardless of network state.
  - (b) Request that the auth server invalidate the long-lived credential so that any leaked copy cannot be reused. If this request cannot complete at sign-out time (network offline, auth server unreachable, 5xx), the system MUST queue it for best-effort retry on the next online opportunity, and MUST surface a small, non-blocking notice to the user that the local sign-out succeeded but the server-side revocation is pending confirmation.
  - (c) Sign-out MUST NOT be blocked or refused on the user because of (b) failing.
- **FR-010**: System MUST tolerate up to ±5 minutes of device clock skew when judging credential expiry (the industry-default JWT clock-skew leeway). A credential whose claimed expiry is within 5 minutes of "now" on either side MUST NOT cause a hard rejection on skew alone; the system relies on the server-side refresh exchange (FR-004) to be the authoritative check in those marginal cases.
- **FR-011**: System MUST retry transient refresh failures (network errors, 5xx) up to 3 total attempts with exponential backoff of 1 s, 3 s, and 9 s between attempts (≈13 s total wall-clock). After the third failure, the system MUST fall back to the login screen with a "we could not sign you in — please try again" message. The system MUST NOT enter an infinite refresh loop, and MUST NOT retry on definitive failures (4xx auth errors indicating the long-lived credential is revoked or expired) — those go straight to the login screen with the "session expired" message from FR-003.
- **FR-012**: This feature MUST NOT introduce any new application-chrome UI to signal that the user is staying signed in. The existing sign-out control already present in the application is the sole signed-in affordance; it MUST remain reachable in the same place and with the same behavior it has today. No avatar element, header identity label, persistent banner, first-time toast, or popover menu is introduced by this feature.
- **FR-013**: System MUST enforce a hard maximum credential lifetime of 365 days from the timestamp of the most recent successful interactive login. Once 365 days have elapsed since that login, the stored credential MUST be treated as expired and the user MUST be sent to the interactive login screen on the next launch, regardless of whether they have been actively using the app in the interim. Subsequent silent background refreshes MUST NOT extend this 365-day clock; only a new interactive login resets it.
- **FR-014**: System MUST NOT impose any additional user-presence check (biometric, OS passcode, or re-entered password) on the silent-resume path. Whenever a valid stored credential is present, the user MUST be placed into the dashboard without any interactive prompt. Protection of the stored credential at rest is delegated to the device's own lockscreen and the platform-provided protected-storage facility (FR-006); the application MUST NOT add a second user-facing unlock step on top of that.
- **FR-015**: Audit logging MUST record three new `action_type` values under the existing `event_class="auth"` bucket to distinguish how a user reached the authenticated UI on a given launch: `auth.login_interactive` (a fresh interactive login completed), `auth.session_resumed` (a silent session resume from a stored credential succeeded), and `auth.session_resume_failed` (a stored credential was present but the resume attempt was rejected or could not complete, and the user was bounced to the login screen). Naming MUST follow the existing dotted convention used by `auth.ws_register` and `auth.ws_disconnect`. No new `event_class` values are added. The existing audit pipeline (recorder, repository, hash-chain) is reused; no new audit infrastructure is introduced.
- **FR-016**: When stored credentials are present but cannot currently be validated due to lack of network connectivity, system MUST surface a clear offline state with a retry control rather than dropping the user into either an unauthenticated dashboard or an indefinite loading state.
- **FR-018**: During the brief window between detecting a stored credential and the dashboard becoming interactive (typical 100–800 ms while the silent refresh completes), the system MUST display the existing initial-loading state already shown during normal app boot. The login screen MUST NOT be shown transiently in this window (no page-flash regression of feature 010), and no new "Signing you in…" splash or skeleton state MUST be introduced specifically for this feature.
- **FR-017**: System MUST NOT introduce any new way for a user's credential to be sent to or stored by a third-party service that does not already receive it today.

### Key Entities

- **Stored Credential**: The long-lived authentication material held on the user's device or browser. Has at minimum: an issuer identity (which deployment issued it), a subject identity (which user it represents), an expiry, and an opaque secret that can be exchanged with the auth server for short-lived access. Created on successful interactive login, replaced on every silent refresh, and destroyed on sign-out, on server rejection, or on user switch.
- **Active Session**: The short-lived in-memory state that authorizes the current run of the app to call the backend. Derived from a Stored Credential at app launch and rotated periodically while the app is open. Never written to persistent storage in a form usable after process exit.
- **Sign-out Event**: A user-initiated or server-initiated action that destroys the Stored Credential on at least one device and asks the auth server to invalidate it everywhere it might still be replayed from.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who signs in once and then opens the app within the retention window sees the dashboard within 2 seconds of app launch on a representative device, with no login screen shown — measured on a representative web browser, iOS device, and Android device.
- **SC-002**: Across a 30-day window of normal use, fewer than 1 in 100 user-app-opens force a re-authentication for any reason other than (a) explicit sign-out, (b) the retention window elapsing, or (c) a server-side revocation.
- **SC-003**: After a user signs out, the previously stored long-lived credential is rejected by the auth server in 100% of replay attempts.
- **SC-004**: Median time to dashboard on a returning user open (i.e., relaunch with a valid stored credential) is no slower than the current cold-start time to dashboard on a fresh login by more than 500 ms.
- **SC-005**: The number of support contacts citing "I have to log in every time I open the app" drops by at least 80% within 60 days of release.
- **SC-006**: 100% of stored credentials on all supported surfaces (web, iOS, Android) are placed in the platform's documented protected-storage facility — not in plain, world-readable locations.
- **SC-007**: For users who explicitly sign out, 0 stored credential artifacts remain on the device or browser within 1 second of the sign-out action completing.

## Assumptions

- The system continues to use the existing identity provider (Keycloak / OIDC) and the existing interactive login screen — this feature changes how the result of that login is *remembered*, not how the login itself is conducted.
- The existing OIDC realm can be configured to issue long-lived credentials (or an equivalent capability) suitable for a roughly 1-year persistence window; if it cannot, the realm-side configuration changes are in scope for the implementation plan but not for this spec.
- The Flutter wrapper continues to be primarily a WebView host; the spec does not assume a native login UI is added inside Flutter — it assumes only that the wrapper can provide secure storage and pass it through to the embedded web app, or that the embedded web app can use storage that the wrapper's WebView preserves across launches.
- Each user uses one identity at a time on a given device or browser profile; multi-account / fast-user-switching on a single surface is out of scope for v1.
- "Browser" means an evergreen mainstream desktop or mobile browser. Niche browsers that aggressively wipe storage on every tab close are best-effort only.
- The retention target is "up to 1 year" — the auth server, deployment policy, or administrator action may rightfully cut a session short before then; the spec only constrains what happens when those external forces are not in play.
- Existing audit-logging infrastructure (the `audit_events` table and recorder) is reused; no new audit pipeline is introduced.
- Out of scope for this feature: changing the login UI itself, adding new auth methods (social login, magic links), passwordless flows, server-to-server credential delegation, sharing one signed-in session across multiple devices (single sign-on between devices), and offline operation beyond the offline-detection requirements stated above.
