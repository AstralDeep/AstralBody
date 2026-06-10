# Quickstart: 028-workspace-auth-revival

## Dev setup

```powershell
# 1. Env — dev mode keeps mock auth working (fail-closed posture otherwise)
#    .env additions:
#      ASTRAL_ENV=development          # REQUIRED for USE_MOCK_AUTH=true from 028 on
#      USE_MOCK_AUTH=true              # unchanged dev default
#      WEB_SESSION_ENC_KEY=<fernet>    # optional in dev; REQUIRED in production
# 2. DB migrations run automatically at startup (_init_db) — new: web_session,
#    workspace_snapshot, auth_revocation_queue, saved_components columns.
docker compose up -d postgres
cd backend; python -m orchestrator   # or the existing run entrypoint
# Shell: http://localhost:8001
```

For **real Keycloak** testing: set `ASTRAL_ENV=development`, `USE_MOCK_AUTH=false`, `KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral`, `KEYCLOAK_CLIENT_ID=astral-frontend`, `KEYCLOAK_CLIENT_SECRET=…` and configure the realm per [docs/keycloak-realm-settings.md](../../docs/keycloak-realm-settings.md).

## Manual verification walkthrough (browser gate)

**Part A — auth**
1. Fresh browser, real-auth mode: `GET http://localhost:8001/?chat=test` → lands on Keycloak; sign in → back on `?chat=test`. View source pre-login: no app markup served.
2. Wait past the access-token lifespan (or set realm lifespan to 1 min) → reload → no Keycloak redirect, no flash (silent refresh).
3. Restart the backend container → reload → still signed in (durable session).
4. Sign out → check Keycloak admin: offline session revoked; `user_offline_grant` rows revoked; re-open `/` → Keycloak login.
5. Production posture: `ASTRAL_ENV=production USE_MOCK_AUTH=true` → process refuses to start with operator-facing error.

**Part B — workspace**
1. New chat → ask for a table, then a chart → both visible. Ask to "refresh the table" → table updates in place, chart untouched (watch for absence of full-canvas flash).
2. Click table pagination → only the table changes (legacy wipe gone).
3. Reload the page / reopen the chat → workspace restored exactly; transcript shows rendered cards for old component messages (no empty bubbles).
4. Topbar → Workspace timeline → pick an earlier turn → canvas shows that state read-only with banner; trigger an agent update from a second tab → banner notes live moved on; "Back to live" → current state incl. the new update.
5. Second device/tab on the same chat → updates appear on both within ~2 s.
6. Permissions: disable the source tool for the user (013 tool picker) → "Refresh" on its component → denied Alert + `workspace.action_denied` audit row.

## Tests

```powershell
cd backend
python -m pytest tests/test_auth_gate.py tests/test_session_store_refresh.py `
  tests/test_logout_revocation.py tests/test_fail_closed_boot.py `
  tests/test_workspace_manager.py tests/test_workspace_snapshots.py `
  tests/test_component_action.py tests/test_ui_upsert_render.py tests/test_rehydration.py -v
python -m pytest --cov   # ≥90% on changed code (Constitution III)
ruff check .
```

Evidence for the browser gate goes to `specs/028-workspace-auth-revival/evidence/` (026/027 convention).
