# Contract: Authentication gate & session lifecycle (028 Part A)

## HTTP routes (all on `:8001`)

### `GET /` (shell) — gated
- Valid session (after silent refresh attempt) → 200 shell with `%%ASTRAL_TOKEN%%` = fresh access token, `%%ASTRAL_TOPBAR%%` role-gated.
- No/dead session → `302 /auth/login?next=<relpath>` where `<relpath>` is the original path+query. No shell markup is served (FR-001, SC-001).
- Static assets under `/static/*` remain ungated (no user data; required pre-auth is none since the shell is the only consumer — they contain no content).

### `GET /auth/login?next=…`
- Existing PKCE authorize redirect. `next` validated: must start with `/`, must not start with `//` or contain a scheme; else replaced by `/`. Stored server-side with the pending PKCE state.
- Mock-auth dev mode: establishes the dev session immediately and redirects to `next` (no Keycloak).

### `GET /auth/callback`
- Existing code exchange. New: user-switch check — valid cookie for a different `sub` ⇒ revoke prior session first (D6, audited `auth.logout` cause `user_switch`). Creates the durable `web_session` row, sets the signed cookie, audits `auth.login_interactive`, then `302 next`.
- IdP error / state mismatch → `302 /auth/error` style bounded response: a minimal server-rendered chrome page with a "Try again" link to `/auth/login?next=…` (no loop: the error page itself is ungated and never auto-redirects) (FR-004).

### `GET /auth/session`
- Returns `{authenticated, access_token, resumed, user_id}` for the WS handshake — **after** silent refresh: if the access token expires <60 s from now, refresh at Keycloak (`grant_type=refresh_token`), rotate stored tokens. Refresh never moves `interactive_anchor`; `now ≥ hard_expires_at` ⇒ refuse locally, delete row, return `{authenticated:false, reason:'hard_cap'}`.
- Refresh failure (IdP 4xx) ⇒ session deleted, `{authenticated:false, reason:'refresh_failed'}`, audit `auth.token_refresh_failed`.

### `GET|POST /auth/logout`
- Order: delete session row+cache (unconditional) → best-effort Keycloak `revoke` (refresh token) → `OfflineGrantStore.revoke_for_user` → audit `auth.logout` → redirect to Keycloak end-session (best-effort, offline-tolerant). Keycloak unreachable ⇒ enqueue in `auth_revocation_queue` (retried with backoff by a background worker) and still complete locally (FR-012/FR-013).

## WebSocket

### `register_ui` (client→server, existing)
- Unchanged shape. On validation failure server now sends `auth_required` instead of an error Alert; the socket stays open for one retry.

### `auth_required` (server→client, NEW, additive)
```json
{ "type": "auth_required", "reason": "expired|invalid|hard_cap" }
```
Client behavior: `fetch('/auth/session')` → if `authenticated`, retry `register_ui` with the fresh token; else `location = '/auth/login?next='+encodeURIComponent(location.pathname+location.search)`.
Client also re-fetches `/auth/session` before every reconnect (never reuses a stale boot token) and the `'dev-token'` literal fallback is removed.

## Startup (fail-closed, D7)
- `ASTRAL_ENV` unset or `production`: `USE_MOCK_AUTH=true` ⇒ fatal refusal to serve (clear operator log). `AGENT_API_KEY` unset ⇒ agent connections refused (logged), not allowed.
- `ASTRAL_ENV=development`: current dev behavior preserved.

## Audit (event_class `auth`)
- Existing: `auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed` (unchanged meanings).
- New: `auth.logout` (detail.cause: `user|user_switch`), `auth.token_refresh_failed`. Successful silent refreshes are NOT audited (FR-011 noise rule).

## Invariants
- Only `/auth/callback` (interactive) sets/moves `interactive_anchor`.
- Access/refresh tokens never reach the client except the access token embedded in the shell / returned by `/auth/session` (same-origin, existing design).
- ±5 min clock skew tolerated on `exp` checks (016).
- Sessions survive process restart and N>1 workers (DB-backed; in-memory dict is cache only).
