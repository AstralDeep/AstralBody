# Contract: Authentication Flow

**Version**: 1.0 | **Date**: 2026-04-03

## Overview

The Flutter client authenticates users via two methods: (1) username/password form and (2) Keycloak OIDC SSO. Both methods result in a JWT access token used for all subsequent API and WebSocket calls. The backend BFF proxy at `/auth/token` handles client secret injection.

---

## Method 1: Username/Password Login (Mock Auth)

### Endpoint: `POST /auth/login`

**Request**:
```
POST {BACKEND_HOST}:{BACKEND_PORT}/auth/login
Content-Type: application/json

{
  "username": "test_user",
  "password": "hJ.3w}Hs)agaKmvtk6qps4)z!J~Ae!%)b^7HEBHpDhi-LM.4V@wWoqF:mYp0ZjaiK=d.VR2fJV0+M*pwK}dum890UgdMx14%s6+c"
}
```

**Success Response** (200):
```json
{
  "user": {
    "id": "dev-user-id",
    "username": "test_user",
    "roles": ["admin", "user"]
  },
  "access_token": "<JWT>",
  "token_type": "Bearer"
}
```

**Error Response** (401):
```json
{
  "detail": "Invalid credentials"
}
```

### Client Behavior
1. Submit username + password from login form
2. On 200: store `access_token` in `flutter_secure_storage`, decode JWT for profile, navigate to dashboard
3. On 401: display inline error, keep form accessible
4. On network error: display "Cannot reach server" error, allow retry

---

## Method 2: Keycloak OIDC SSO

### Flow: Authorization Code + PKCE

```
┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────┐
│  Flutter │     │ System       │     │  Keycloak    │     │ Backend │
│  Client  │     │ Browser      │     │  IAM         │     │ BFF     │
└────┬─────┘     └──────┬───────┘     └──────┬───────┘     └────┬────┘
     │                  │                    │                   │
     │ 1. Tap SSO btn   │                    │                   │
     │──────────────────>│                    │                   │
     │  (flutter_appauth │                    │                   │
     │   opens browser)  │                    │                   │
     │                  │ 2. GET /authorize   │                   │
     │                  │───────────────────> │                   │
     │                  │                    │                   │
     │                  │ 3. Login form      │                   │
     │                  │<─────────────────── │                   │
     │                  │                    │                   │
     │                  │ 4. POST creds      │                   │
     │                  │───────────────────> │                   │
     │                  │                    │                   │
     │                  │ 5. Redirect with   │                   │
     │                  │    auth code       │                   │
     │ <────────────────│ (deep link)        │                   │
     │                  │                    │                   │
     │ 6. POST /auth/token (code + PKCE verifier)              │
     │─────────────────────────────────────────────────────────>│
     │                                                          │
     │                  7. Backend injects client_secret,       │
     │                     forwards to Keycloak token endpoint  │
     │                                                          │
     │ 8. Token response (access_token, refresh_token, id_token)│
     │<─────────────────────────────────────────────────────────│
     │                                                          │
```

### BFF Token Proxy: `POST /auth/token`

**Request** (authorization_code grant):
```
POST {BACKEND_HOST}:{BACKEND_PORT}/auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code={auth_code}
&redirect_uri={redirect_uri}
&code_verifier={pkce_verifier}
&client_id=astral-frontend
```

**Request** (refresh_token grant):
```
POST {BACKEND_HOST}:{BACKEND_PORT}/auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&refresh_token={refresh_token}
&client_id=astral-frontend
```

**Success Response** (200):
```json
{
  "access_token": "<JWT>",
  "refresh_token": "<refresh_token>",
  "expires_in": 300,
  "token_type": "Bearer",
  "id_token": "<ID_token>"
}
```

### OIDC Configuration

| Parameter | Value | Source |
|-----------|-------|--------|
| Authority | `https://iam.ai.uky.edu/realms/Astral` | `.env` `VITE_KEYCLOAK_AUTHORITY` |
| Client ID | `astral-frontend` | `.env` `VITE_KEYCLOAK_CLIENT_ID` |
| Scopes | `openid profile email offline_access` | Matching React |
| Redirect URI | `com.astraldeep.app://callback` | Platform deep link |
| Token Endpoint | `{BACKEND_HOST}:{BACKEND_PORT}/auth/token` | BFF override |

### Client Behavior
1. Tap "Sign in with SSO" button
2. `flutter_appauth` opens system browser to Keycloak authorize endpoint
3. User authenticates in browser → redirect back via deep link
4. `flutter_appauth` exchanges code via BFF `/auth/token`
5. Store tokens in `flutter_secure_storage`
6. Decode JWT for user profile
7. Navigate to dashboard

---

## JWT Token Structure

```json
{
  "sub": "user-uuid",
  "preferred_username": "test_user",
  "realm_access": {
    "roles": ["admin", "user"]
  },
  "resource_access": {
    "astral-frontend": {
      "roles": ["admin", "user"]
    }
  },
  "exp": 1743700000,
  "iat": 1743699700
}
```

### Role Extraction Rules
1. Check `realm_access.roles` for `"admin"` → `globalRole = "admin"`
2. Else check `realm_access.roles` for `"user"` → `globalRole = "user"`
3. Client-specific roles at `resource_access.astral-frontend.roles`

---

## Token Lifecycle

| Event | Action |
|-------|--------|
| App launch | Restore from `flutter_secure_storage`; check expiry |
| Token near expiry | Silent refresh via `/auth/token` (refresh_token grant) |
| Refresh fails | Clear tokens; redirect to login |
| Logout | Clear tokens; disconnect WebSocket |
| WebSocket connect | Send `access_token` in `register_ui` message |

---

## Test Credentials

| Variable | Value | Purpose |
|----------|-------|---------|
| `KEYCLOAK_TEST_USER` | `test_user` | Login form username |
| `KEYCLOAK_TEST_PASSWORD` | *(in .env)* | Login form password |
| `AGENT_SERVICE_CLIENT_ID` | `astral-agent-service` | Agent-to-agent auth |
| `AGENT_SERVICE_CLIENT_SECRET` | *(in .env)* | Agent token exchange |
