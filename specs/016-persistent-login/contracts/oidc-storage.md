# Contract: OIDC Storage Layout (Frontend)

This contract defines the localStorage and sessionStorage layout used by the persistent-login feature. It is the authoritative reference for tests, debugging, and future migration work.

## 1. Storage backends

| Record | Backend | Key | Owner |
|--------|---------|-----|-------|
| OIDC user (tokens + profile) | `window.localStorage` | `oidc.user:<authority>:<client_id>` | `oidc-client-ts` |
| Persistent-login anchor | `window.localStorage` | `astralbody.persistentLogin.v1` | this feature |
| Revocation retry queue | `window.sessionStorage` | `astralbody.revocationQueue.v1` | this feature |

> **Why two backends?** localStorage survives full browser/app restart, which is what we want for the tokens and the anchor. sessionStorage clears on tab/app close, which is what we want for the retry queue (see [research.md](../research.md) §R-5).

## 2. Key format details

### `oidc.user:<authority>:<client_id>`

- `<authority>` MUST be the exact string passed as `authority` in the `oidcConfig` (no trailing slash).
- `<client_id>` MUST be the exact OIDC `client_id`.
- Example: `oidc.user:https://keycloak.ai.uky.edu/realms/astralbody:astral-frontend`

### `astralbody.persistentLogin.v1`

- The literal trailing `.v1` is the schema-version marker. Future versions MUST bump this to `.v2` etc. and MUST NOT modify the v1 record in place.
- Older readers encountering an unrecognized version key MUST ignore it. Newer readers encountering only an older version MUST clear it and force a single re-login (matches the spec's "force a single re-login on migration — never a corrupt/stuck state" edge case).

### `astralbody.revocationQueue.v1`

- Same versioning rule as the anchor record above.

## 3. Payload shapes

### OIDC user record (read-only from our code)

`oidc-client-ts`'s `User.toStorageString()` output. Treat as opaque from our side; only `oidc-client-ts` reads/writes it.

### Anchor record

```json
{
  "schema_version": 1,
  "initial_login_at": "2026-05-15T14:30:00.000Z",
  "last_user_sub": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "deployment_origin": "https://sandbox.ai.uky.edu"
}
```

- All four fields MUST be present.
- `initial_login_at` MUST parse as a valid ISO-8601 UTC instant.
- `last_user_sub` MUST be non-empty.
- `deployment_origin` MUST be exactly `window.location.origin` form (`<scheme>://<host>[:<port>]`).

### Revocation queue record

```json
[
  {
    "refresh_token": "eyJhbGciOi…",
    "authority": "https://keycloak.ai.uky.edu/realms/astralbody",
    "client_id": "astral-frontend",
    "queued_at": "2026-05-15T14:42:11.123Z",
    "attempts": 0
  }
]
```

- The array MUST contain ≤ 16 entries (FIFO eviction).
- `attempts` MUST be in `0..5`.

## 4. Wiring in `main.tsx`

The change is mechanical:

```ts
import { WebStorageStateStore } from 'oidc-client-ts';

const oidcConfig = {
  authority: AUTHORITY,
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
  redirect_uri: window.location.origin,
  metadata: { /* … unchanged … */ },
  scope: "openid profile email offline_access",
  automaticSilentRenew: true,
  filterProtocolClaims: true,
  // === NEW ===
  userStore: new SafeWebStorageStateStore({ store: window.localStorage }),
  stateStore: new SafeWebStorageStateStore({ store: window.localStorage }),
  // === END NEW ===
  onSigninCallback: () => {
    // existing chat-param preservation + NEW: recordInteractiveLogin(user.profile.sub)
  }
};
```

Both `userStore` (which holds the `User` object) and `stateStore` (which holds the in-flight authorization-code-flow state during the redirect dance) are switched to localStorage. `stateStore` lives only for the duration of the redirect anyway, so this is harmless and saves us from one more inconsistency.

`SafeWebStorageStateStore` is the wrapper from R-10 that swallows write failures and toasts.

## 5. Test fixtures

Tests SHOULD construct a fake localStorage backed by an in-memory `Map<string, string>` and inject it via the `store` option, exactly like the production code injects `window.localStorage`. This keeps unit tests synchronous and isolated from `window`.
