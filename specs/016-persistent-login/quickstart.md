# Quickstart — Persistent Login

This is the minimal end-to-end smoke test for the persistent-login feature once implemented. Run it after `/speckit-implement` to verify the core promise: **users do not have to log in every time they open the website or app**.

## Prerequisites

- Backend running locally (`cd backend && .venv/Scripts/python.exe start.py`)
- Frontend running (`cd frontend && npm run dev` for local dev, or the baked container build for parity testing)
- A valid Keycloak account on the configured realm
- Browser DevTools open to the Application → Local Storage panel (for manual inspection)

## Smoke test — Web

1. **Fresh install state**. In DevTools, clear localStorage for the AstralBody origin. Reload the page.
2. **Interactive login**. Click "Sign in", complete the Keycloak login flow. Land on the dashboard.
3. **Verify storage**. In DevTools, confirm both of these keys exist in localStorage:
   - `oidc.user:<authority>:<client_id>` — populated by `oidc-client-ts`
   - `astralbody.persistentLogin.v1` — JSON with `initial_login_at` set to ~now, `last_user_sub` set to your OIDC sub, `deployment_origin` set to the page origin
4. **Full close**. Quit the browser entirely (not just close the tab).
5. **Reopen**. Launch the browser and navigate to the AstralBody URL.
6. **Expected**: the dashboard renders directly. No Keycloak login screen. No password prompt.
7. **Verify audit**. Open the Audit Log panel in the UI; the most recent `event_class="auth"` row MUST have `action_type="auth.session_resumed"`. The login from step 2 is recorded as `action_type="auth.login_interactive"` (earlier in the log).

## Smoke test — Flutter wrapper (mobile)

1. **Fresh install**. Uninstall the app, then `flutter run` it on the target device.
2. **Sign in inside the WebView**. Complete the Keycloak flow.
3. **Force-quit**. Swipe the app out of the iOS app switcher or kill from the Android Recents.
4. **Relaunch**. Tap the app icon.
5. **Expected**: the dashboard renders directly. No Keycloak login screen.
6. **Edge case — device reboot**. Repeat steps 3–5 after a full device reboot. Expected: still no login prompt.

## Smoke test — Sign-out flow (FR-009)

1. From the authenticated dashboard, click the existing sign-out control.
2. **Verify**: localStorage `oidc.user:*` and `astralbody.persistentLogin.v1` are both removed within ~1 second of the click.
3. **Verify**: the page redirects to the Keycloak end-session endpoint, then back to the AstralBody login screen.
4. **Verify**: reload the page — the login screen MUST appear, not the dashboard.
5. **Replay attempt** (optional): copy the prior refresh token before signing out; after signing out, attempt to exchange it directly at `${authority}/protocol/openid-connect/token`. Expected: HTTP 400 `invalid_grant`.

## Smoke test — 365-day hard cap (FR-013)

This is artificial because we can't fast-forward real time. Use the test hook:

1. In DevTools, run:
   ```js
   const anchor = JSON.parse(localStorage.getItem('astralbody.persistentLogin.v1'));
   anchor.initial_login_at = new Date(Date.now() - 366 * 24 * 60 * 60 * 1000).toISOString();
   localStorage.setItem('astralbody.persistentLogin.v1', JSON.stringify(anchor));
   ```
2. Reload the page.
3. **Expected**: the login screen appears (not the dashboard) with the "session expired" message. localStorage records have been cleared by the on-launch check.
4. **Verify audit**: a new `auth.session_resume_failed` row exists with `outcome_detail` mentioning hard-max.

## Smoke test — Offline silent-resume (FR-016)

1. Sign in normally.
2. Disable network (DevTools → Network → Offline).
3. Force-reload the page.
4. **Expected**: the UI shows the offline-state retry control (the same one used elsewhere in AstralBody when the WS can't connect). The user is NOT bounced to the login screen, NOT left on an unauthenticated dashboard, NOT stuck on a perpetual spinner.
5. Re-enable network and click retry. Expected: dashboard renders.

## Smoke test — Storage-write rejection (FR-006)

1. In a fresh browser profile, open DevTools and patch `localStorage.setItem` to throw `QuotaExceededError`:
   ```js
   localStorage.setItem = () => { throw new DOMException('quota', 'QuotaExceededError'); };
   ```
2. Complete an interactive login.
3. **Expected**: a toast warns that persistence is disabled for this session.
4. **Expected**: the current session works fully (chat, etc.).
5. Close the browser. Reopen.
6. **Expected**: the login screen appears (because nothing was persisted).

## Pass criteria

All seven smoke tests above MUST pass. Any failure blocks the feature from being declared done per Constitution X (Production Readiness).
