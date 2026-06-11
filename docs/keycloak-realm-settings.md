# Keycloak realm settings for AstralBody (operator guide)

> Feature 028 (FR-017). This document replaces the never-committed
> `keycloak-persistent-login-realm-settings.md` referenced by earlier docs.
> Agent-delegation (RFC 8693) client setup lives in
> [keycloak_agent_delegation_setup.md](keycloak_agent_delegation_setup.md).

AstralBody authenticates exclusively against Keycloak (Constitution VII).
The orchestrator drives a **server-side** OIDC Authorization Code + PKCE flow
(`/auth/login` → Keycloak → `/auth/callback`); tokens never live in the
browser beyond the short-lived access token used for the WS handshake.

## Realm

| Setting | Required value | Why |
|---|---|---|
| SSO Session Idle / Max | operator's choice (browser SSO only) | The app session does not depend on the Keycloak browser session after login. |
| **Offline Session Idle** | **≥ 365 days** | The app requests `offline_access`; silent refresh + unattended jobs (feature 025) use offline refresh tokens. Idle below 365 d silently breaks the persistent-login promise (016 FR-001). |
| **Offline Session Max Limited** | **disabled**, or Max ≥ 365 days | Same as above. |
| **Access Token Lifespan** | **5–15 minutes** | The orchestrator refreshes silently server-side (028 D2); short access tokens keep revocation latency bounded (SC-004). |
| Revocation endpoint | enabled (default) | `/auth/logout` POSTs the refresh token to `…/protocol/openid-connect/revoke` (028 FR-012). |
| Login → Remember Me | **OFF** (Keycloak default) | 028 FR-010 / 016 FR-001: the sign-in page must not offer a "Remember me"/"Stay signed in" choice — persistence is the app's 365-day server-side session, not a user toggle. |

## Roles (required)

Create realm (or `astral-frontend` client) roles:

- `user` — required to enter the application at all.
- `admin` — admin chrome surfaces + admin REST endpoints.

A token carrying **neither** role is rejected at the WebSocket handshake and
by every REST dependency; the user gets an explicit no-access outcome.

## Client: `astral-frontend` (confidential)

| Setting | Value |
|---|---|
| Client authentication | On (confidential; secret → `KEYCLOAK_CLIENT_SECRET`) |
| Standard flow | Enabled (Authorization Code) |
| PKCE | `S256` (Advanced → Proof Key for Code Exchange) |
| Valid redirect URIs | `https://<host>/auth/callback` (plus `http://localhost:8001/auth/callback` for dev) |
| Valid post-logout redirect URIs | `https://<host>/` |
| Default/optional scopes | must include `offline_access` (the app requests `openid profile email offline_access`) |
| OAuth 2.0 Token Exchange | Enabled (agent delegation — see the delegation doc) |

## Orchestrator environment

```bash
KEYCLOAK_AUTHORITY=https://<keycloak-host>/realms/<Realm>   # full realm URL
KEYCLOAK_CLIENT_ID=astral-frontend
KEYCLOAK_CLIENT_SECRET=<from the client credentials tab>
AGENT_SERVICE_CLIENT_ID=astral-agent-service
AGENT_SERVICE_CLIENT_SECRET=<from the client credentials tab>
ASTRAL_ENV=production            # unset == production (fail closed)
USE_MOCK_AUTH=false              # mock auth refuses to boot in production
WEB_SESSION_ENC_KEY=<fernet key> # encrypts durable web sessions at rest (REQUIRED in production)
AGENT_API_KEY=<random secret>    # agent connections are refused without it in production
OFFLINE_GRANT_ENC_KEY=<fernet>   # feature 025 offline grants (logout revokes them)
WEB_SESSION_SECRET=<random>      # cookie HMAC (falls back to WEB_SESSION_ENC_KEY, then OFFLINE_GRANT_ENC_KEY)
```

Generate Fernet keys with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

## Behavior summary (what these settings power)

- Unauthenticated `GET /` → 302 to Keycloak; after login the user lands on
  their original destination (deep links included).
- Sessions renew silently server-side for up to **365 days from the last
  interactive login** — refreshes never extend that cap; at the cap the user
  must sign in interactively again.
- Sessions are stored (encrypted) in Postgres: backend restarts and
  multi-instance deploys do not log anyone out.
- Sign-out: server session deleted → refresh token revoked at Keycloak
  (queued and retried if Keycloak is unreachable) → all of the user's
  feature-025 offline grants revoked → Keycloak end-session redirect.
- A different user signing in on the same browser revokes the prior user's
  session first.
