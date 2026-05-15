# Phase 1 — Data Model: Persistent Login Across App Restarts

## Database schema

**No changes.** This feature adds zero tables, zero columns, zero indexes, zero constraints, and zero migrations. Constitution IX is satisfied by N/A.

The existing `audit_events` table receives three new `action_type` values under the existing `event_class="auth"` bucket. `event_class` itself is unchanged, so no DDL or `EVENT_CLASSES` tuple amendment is required.

## Client-side persistent state (browser localStorage / Flutter WebView localStorage)

Two records are kept per browser origin (or per Flutter-configured backend URL — both surface as the same browser-origin semantics inside the embedded WebView).

### Record 1 — OIDC user record (managed by `oidc-client-ts`)

**Key**: `oidc.user:<authority>:<client_id>`
- `<authority>` is the Keycloak issuer URL from `VITE_KEYCLOAK_AUTHORITY`
- `<client_id>` is `VITE_KEYCLOAK_CLIENT_ID`

**Value**: JSON-serialized `User` object as defined by `oidc-client-ts`:

```text
{
  "id_token":     "<JWT>",
  "session_state": "<opaque>",
  "access_token": "<JWT, short-lived>",
  "refresh_token":"<JWT, long-lived offline_access>",
  "token_type":   "Bearer",
  "scope":        "openid profile email offline_access",
  "profile":      { sub, preferred_username, email, name, ... },
  "expires_at":   <unix-seconds for access_token expiry>
}
```

**Lifecycle**:
- **Created**: by `oidc-client-ts` on successful `signinRedirectCallback()` after the user completes the Keycloak login flow.
- **Updated**: by `oidc-client-ts` on every successful silent renew (every ~5–15 min while the app is open, driven by the access-token TTL).
- **Destroyed**: on `userManager.removeUser()` (explicit signout, hard-max-exceeded clear, user-switch overwrite, or storage-write-error fallback).

We **never write to this record directly** — `oidc-client-ts` owns it.

### Record 2 — AstralBody persistent-login anchor (managed by this feature)

**Key**: `astralbody.persistentLogin.v1`

**Value** (JSON):

```text
{
  "schema_version":     1,
  "initial_login_at":   "2026-05-15T14:30:00.000Z",  // ISO-8601 UTC
  "last_user_sub":      "<OIDC sub claim of the last successful interactive login>",
  "deployment_origin":  "https://sandbox.ai.uky.edu"  // window.location.origin at login time
}
```

**Field semantics**:
| Field | Type | Purpose | Constraint |
|-------|------|---------|------------|
| `schema_version` | integer | Forward-compatibility marker. If a future version of this feature changes the shape, increment this field; older readers MUST treat a higher version as "unknown — discard and re-login". | currently exactly `1` |
| `initial_login_at` | ISO-8601 UTC string | Anchor for FR-013's 365-day hard maximum. **Never updated by silent renew.** Reset only on a fresh `onSigninCallback`. | ISO-8601 with millisecond precision |
| `last_user_sub` | string | OIDC `sub` of the user who completed the most recent interactive login on this surface. Used by FR-008 to detect user-switch. | non-empty |
| `deployment_origin` | string | The browser origin in effect when the credential was minted. Used as a defense-in-depth check in case browser origin isolation behaves unexpectedly (e.g., custom Flutter WebView origin). On every silent resume, the system rejects the stored credential if `window.location.origin !== deployment_origin`. | URL origin form (`https://host[:port]`) |

**Lifecycle**:
| Event | Action on `astralbody.persistentLogin.v1` |
|-------|-------------------------------------------|
| Fresh interactive login (`onSigninCallback` fires) | Write a new record with `initial_login_at = now`, `last_user_sub = new sub`, `deployment_origin = window.location.origin`. **Always overwrites** any prior record. |
| Silent renew | Untouched. |
| App launch with record present and `(now - initial_login_at) > 365 days` | Clear both the OIDC user record and this anchor record. Route to login screen with "session expired" message. |
| App launch with `deployment_origin !== window.location.origin` | Clear both records. Route to login screen. |
| Explicit sign-out (FR-009) | Clear this record synchronously, regardless of whether the server revocation succeeded. |
| User-switch detected (`new sub !== last_user_sub`) | Enqueue revocation of the prior user's refresh token, then overwrite. |
| Storage `set` rejected (FR-006) | Skip writing this record. The current session uses in-memory auth state only; next launch sees no record and falls through to login. |

**Read operations**:
- `getAnchor(): Anchor | null` — used on app launch before mounting `<AuthProvider>` to decide whether to clear OIDC state.
- `getInitialLoginAt(): Date | null` — used by acceptance tests to assert the 365-day cap.

**Write operations**:
- `recordInteractiveLogin(sub: string): void` — called from `onSigninCallback`.
- `clear(): void` — called from sign-out, hard-max-exceeded, deployment-mismatch, and user-switch paths.

### Record 3 — Revocation retry queue (managed by this feature)

**Key**: `astralbody.revocationQueue.v1` (in **sessionStorage**, deliberately not localStorage — see R-5 in [research.md](research.md))

**Value** (JSON array, FIFO):

```text
[
  {
    "refresh_token": "<JWT>",
    "authority":     "<Keycloak issuer URL>",
    "client_id":     "<OIDC client id>",
    "queued_at":     "<ISO-8601 UTC>",
    "attempts":      <integer, starts at 0>
  },
  ...
]
```

**Constraints**:
- Maximum queue length: **16 entries**. Inserts beyond this drop the oldest entry (FIFO eviction).
- Per-entry max attempts: **5**. After 5 failures, the entry is dropped and a `console.warn` is logged.
- The queue is drained on the `online` event and at app launch; entries that succeed are removed; entries that fail with a transient error (network/5xx) increment `attempts`; entries that fail with a definitive error (4xx — token already invalid) are removed immediately as the goal has been achieved.

**Why sessionStorage and not localStorage**: an attacker with localStorage read access already has the refresh token in Record 1; preserving the same token elsewhere is pure attack surface. The queue is only useful within a single browser session ("you signed out, your network came back, here's the retry"); persistence across full app restarts is not required.

## Server-side state

**None added by this feature.** The backend continues to validate JWTs against Keycloak's JWKS on every request. Three new `action_type` strings appear in the `audit_events` table once usage begins, but no schema or code change is required to accommodate them beyond the recording sites listed in [contracts/audit-actions.md](contracts/audit-actions.md).

## Stored Credential entity (spec § Key Entities) — concrete mapping

| Spec attribute | Concrete location |
|----------------|-------------------|
| issuer identity | OIDC record's `profile.iss` claim + the localStorage *key* `oidc.user:<authority>:<client_id>` |
| subject identity | OIDC record's `profile.sub` claim, mirrored to anchor's `last_user_sub` |
| expiry (short-lived access) | OIDC record's `expires_at` |
| expiry (long-lived offline) | The `refresh_token`'s own `exp` claim, plus the client-side `initial_login_at + 365 days` ceiling |
| opaque secret | OIDC record's `refresh_token` |
| **interactive-login timestamp** *(new — closes the spec-clarify-3 data-model gap)* | Anchor record's `initial_login_at` |

## State diagram (text)

```text
[fresh install / cleared storage]
        |
        | user types password in Keycloak
        v
[interactive login completes]
        |
        | onSigninCallback fires
        |   - oidc-client-ts writes oidc.user:* record
        |   - persistentLogin.recordInteractiveLogin(sub) writes anchor
        |   - if last_user_sub != new sub: enqueue revocation of old refresh_token
        |   - audit: auth.login_interactive recorded
        v
[authenticated, persistent]
        |
        |---- (every 5-15 min while app open) ---- silent renew ----+
        |                                                            |
        |   <- updates oidc.user:*.access_token + refresh_token       |
        |   <- anchor untouched                                       |
        |                                                            |
        |<-----------------------------------------------------------+
        |
        |---- user closes browser / Flutter app ----------+
                                                          |
                                                          v
                                            [storage at rest, app not running]
                                                          |
                                                          | user reopens app
                                                          v
                                              [app launch]
                                                          |
                                                          | persistentLogin.checkOnLaunch():
                                                          |   if anchor missing -> normal login flow
                                                          |   if (now - initial_login_at) > 365d -> clear all, "session expired"
                                                          |   if deployment_origin mismatch -> clear all, login
                                                          |   else -> let oidc-client-ts attempt silent renew
                                                          v
                                              [silent renew attempt]
                                                /         |         \
                                          success      transient     definitive
                                              |        failure        failure
                                              |          |              |
                                              |     (retry up         (clear all
                                              |      to 3x with        records,
                                              |      1/3/9s)           audit:
                                              |          |             auth.session_
                                              |          v             resume_failed,
                                              |     give up ->         route to
                                              |     "could not        login)
                                              |      sign you in"
                                              v
                                  [authenticated, persistent]
                                  audit: auth.session_resumed
                                  (continues the cycle)
```

## Invariants

- **I-1**: `initial_login_at` is monotonically non-decreasing across silent renews (i.e., never modified by renew).
- **I-2**: `last_user_sub` always matches `oidc.user:*.profile.sub` after a successful interactive login.
- **I-3**: `deployment_origin` is always exactly `window.location.origin` at the moment of interactive login.
- **I-4**: The revocation queue never contains more than 16 entries.
- **I-5**: A successful `clear()` removes both the OIDC user record AND the anchor record. Removing one without the other is forbidden.
- **I-6**: If `astralbody.persistentLogin.v1` is missing but `oidc.user:*` is present, the latter is treated as orphan and cleared on next launch (defensive — should not happen in normal operation).

These invariants are checked by unit tests in `frontend/src/auth/__tests__/persistentLogin.test.tsx`.
