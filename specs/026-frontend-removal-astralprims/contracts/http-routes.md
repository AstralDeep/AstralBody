# Contract: HTTP Routes (FastAPI, port 8001)

The orchestrator already serves REST routers under `/api/*`, the WS at `/ws`, and OpenAPI docs at `/docs`
(Constitution VI). This feature adds UI delivery + server-side auth routes. All existing `/api/*` routers are
preserved.

## UI delivery

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve the static `shell.html` (session token substituted in; mounts `client.js` + `astral.css`); the only full page. |
| GET | `/static/*` | Serve `backend/webrender/static/` via FastAPI `StaticFiles` (`client.js`, `astral.css`, self-hosted Plotly/vendor). Replaces the old `:5173` static server. |

The shell establishes the WebSocket (`/ws`) and drives all subsequent UI via the protocol; there are no other
HTML page routes (single-shell, server-rendered fragments over WS).

## Authentication (server-side OIDC code flow — Keycloak)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/auth/login` | Redirect to Keycloak authorization endpoint (Authorization Code + PKCE). |
| GET | `/auth/callback` | Exchange code → tokens; establish server session; audit `auth.login_interactive`. |
| POST | `/auth/logout` | End session; Keycloak logout; flush offline sign-out queue (feature 016). |
| GET | `/auth/session` | Report current session/token for the WS `register_ui` handshake; supports 365-day persistent resume; audits `auth.session_resumed` / `auth.session_resume_failed`. |

**Preserved from feature 016**: 365-day persistent-login cap, user-switch revocation, offline-tolerant
sign-out, and the audit `action_type`s under `event_class="auth"` (including the existing
`POST /api/audit/session-resume-failed`). Tokens are held server-side (not in the browser), replacing the
client-side `oidc-client-ts` userStore.

## Removed

- The separate static frontend server on `:5173` (`start-docker.sh`) and its `docker-compose.yml` mapping.
- All `frontend/` build output; no Vite/Node stage in the Docker image.
