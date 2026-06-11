# Production deployment (operator guide)

AstralBody is a **server-driven UI (SDUI) backend service**: one Python
process serves the web shell, static assets, REST API, WebSocket channel, and
the rendered UI itself on port **8001**. There is no frontend build step, no
Node toolchain, and no separate static server — `astralprims` defines the
primitives, the orchestrator renders them (`backend/webrender/`), and ROTE
adapts the output per device.

Companion docs: [keycloak-realm-settings.md](keycloak-realm-settings.md)
(identity provider), [keycloak_agent_delegation_setup.md](keycloak_agent_delegation_setup.md)
(RFC 8693 agent delegation).

## Fail-closed posture (read this first)

`ASTRAL_ENV` **unset means production**. A production-mode boot refuses to
serve (exit code 78, one consolidated operator checklist in the log) unless:

| Requirement | Why |
|---|---|
| `USE_MOCK_AUTH=false` | Mock auth accepts any token as an admin user. |
| `WEB_SESSION_ENC_KEY` (or `OFFLINE_GRANT_ENC_KEY`) set | Durable web sessions are Fernet-encrypted at rest; refused unencrypted. |
| `AUDIT_HMAC_SECRET` set to a real value | The audit hash chain is forgeable under the shipped placeholder. |
| `KEYCLOAK_AUTHORITY` / `KEYCLOAK_CLIENT_ID` / `KEYCLOAK_CLIENT_SECRET` set | The OIDC flow cannot operate without them. |

Additionally, in production mode:

- **Agent registrations without a valid `AGENT_API_KEY` are refused**
  (WS close 1008). Leaving it unset is safe but means no specialist agents
  come up — the boot log warns about this.
- Unauthenticated shell requests redirect to Keycloak; unauthenticated
  REST/WS requests are refused. Entry requires the `user` or `admin` realm
  role.

Local development opts out explicitly with `ASTRAL_ENV=development`.

## Secrets are runtime-only

The image does **not** bake `.env` (secrets in image layers leak via
`docker history` and registry caches). Configuration enters at runtime:

```bash
docker compose up -d            # uses env_file: .env (already wired)
docker run --env-file .env …    # for non-compose runs
```

Generate the Fernet keys:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## TLS / reverse proxy

The service speaks plain HTTP on `:8001` and expects a TLS-terminating
reverse proxy (nginx, Caddy, Traefik) in front of it in production:

1. Proxy `https://your-host/` → `http://127.0.0.1:8001` and forward
   `X-Forwarded-Proto` / `X-Forwarded-For` (every mainstream proxy's default).
2. The orchestrator trusts those headers only from `FORWARDED_ALLOW_IPS`
   (default `127.0.0.1`; set to your proxy's address or `*` inside a private
   network). This is what makes `request.base_url` https — which drives the
   session cookie's `secure` flag and the OIDC `redirect_uri`.
3. WebSockets: ensure the proxy upgrades `/ws` (and `/agent` if agents
   connect through it). nginx needs the standard
   `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`.
4. Set `PUBLIC_BASE_URL`/`BACKEND_PUBLIC_URL` to the public https origin and
   register `https://your-host/auth/callback` as a valid redirect URI on the
   Keycloak client.

## Health probes

| Endpoint | Meaning | Use |
|---|---|---|
| `GET /healthz` | Process is serving | Liveness probe |
| `GET /readyz` | Database answers (`503` + `{"db":"unreachable"}` otherwise) | Readiness probe / compose healthcheck |

Both are ungated (no user data) and excluded from access logs.
`docker-compose.yml` wires `/readyz` as the container healthcheck
(`start_period: 90s` covers agent auto-start).

## Sessions, sign-out, multi-instance

- Sessions live in Postgres (`web_session`, encrypted) — restarts and N>1
  instances do not log anyone out. All instances must share
  `WEB_SESSION_ENC_KEY` (cookie signatures fall back to it via
  `WEB_SESSION_SECRET → WEB_SESSION_ENC_KEY → OFFLINE_GRANT_ENC_KEY`).
- Silent renewal is server-side and never extends the 365-day interactive
  anchor; sign-out revokes the Keycloak refresh token (queued in
  `auth_revocation_queue` and retried when the IdP is unreachable) plus all
  feature-025 offline grants.

## Database

- Postgres 17 (compose service `postgres`, named volume `pgdata`).
- Schema migrations are idempotent and run automatically at boot
  (`shared/database.py::_init_db`) — no migration step to operate.
- Back up `pgdata` and the `backend/data` bind mount (uploads, agent keys).

## Logging & observability

- `LOG_LEVEL` (default `info`) controls uvicorn/app verbosity; health-probe
  and agent-card polls are filtered out of access logs.
- The tamper-evident audit trail (per-user HMAC hash chain) is queryable via
  `GET /api/audit` (per-user) and verifiable server-side:
  `python -m audit.cli verify-chain --user-id <id>`.

## Deploying to sandbox.ai.uky.edu (GHCR pull)

CI (feature 029, `.github/workflows/ci.yml`) publishes the production image
to GitHub Container Registry on every push to `main` that passes all gates:
an immutable `ghcr.io/<owner>/<repo>:sha-<commit>` tag plus a moving
`:latest`. The sandbox host **pulls the verified image** instead of building
locally — the bytes that passed CI are the bytes that serve.

### 1. Pull the image

```bash
docker login ghcr.io -u <github-username>        # PAT with read:packages
docker pull ghcr.io/<owner>/<repo>:sha-<commit>  # always pin the immutable tag
```

Deploy by `sha-<commit>` (the tag CI stamped on the exact verified build);
treat `:latest` as a convenience pointer only — never as the deployed ref.

### 2. Compose override — `image:` instead of `build:`

Keep the repo's `docker-compose.yml` (its `env_file`, volumes, healthcheck
and `depends_on` all still apply) and add a `docker-compose.override.yml`
on the host that swaps the local build for the registry image:

```yaml
# docker-compose.override.yml (sandbox host)
services:
  astralbody:
    image: ghcr.io/<owner>/<repo>:sha-<commit>
    build: !reset null   # drop the build: block (compose >= 2.24)
```

On older compose without `!reset`, omit that line and start with
`docker compose up -d --no-build` so the registry image is used as-is.

### 3. Host `.env` posture

Everything in [Fail-closed posture](#fail-closed-posture-read-this-first)
applies; for sandbox.ai.uky.edu specifically:

```bash
# Public origin (TLS proxy in front — see below)
PUBLIC_BASE_URL=https://sandbox.ai.uky.edu
BACKEND_PUBLIC_URL=https://sandbox.ai.uky.edu

# Identity — realm + client settings per docs/keycloak-realm-settings.md
KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/<realm>
KEYCLOAK_CLIENT_ID=astral-frontend
KEYCLOAK_CLIENT_SECRET=<client credentials tab>

# Production posture — the exit-78 boot gate checks all of these
# (leave ASTRAL_ENV unset: unset == production, fail closed)
USE_MOCK_AUTH=false
WEB_SESSION_ENC_KEY=<generated Fernet key>
OFFLINE_GRANT_ENC_KEY=<generated Fernet key>
AUDIT_HMAC_SECRET=<high-entropy value>
AGENT_API_KEY=<random secret>

# Trust X-Forwarded-* only from the TLS proxy
FORWARDED_ALLOW_IPS=<proxy ip>

# Database stays compose-internal (service `postgres`)
DB_USER=astral
DB_PASSWORD=<strong password>
DB_NAME=astralbody
DB_PORT=5432
```

### 4. Reverse proxy + Keycloak client

- TLS terminates at the proxy: `https://sandbox.ai.uky.edu/` →
  `http://127.0.0.1:8001`, forwarding `X-Forwarded-Proto`/`X-Forwarded-For`.
- The orchestrator trusts those headers **only** from `FORWARDED_ALLOW_IPS`
  (set it to the proxy's address — this is what makes the session cookie
  `secure` and the OIDC `redirect_uri` https).
- The proxy must upgrade WebSockets on `/ws` (and `/agent` if agents connect
  through it).
- On the Keycloak `astral-frontend` client, register
  `https://sandbox.ai.uky.edu/auth/callback` as a valid redirect URI and
  `https://sandbox.ai.uky.edu/` as a post-logout redirect URI
  ([keycloak-realm-settings.md](keycloak-realm-settings.md)).

The exit-78 boot gate is the final guard: if the host `.env` is incomplete,
the pulled image refuses to serve and prints one consolidated checklist in
`docker compose logs astralbody` — fix and `docker compose up -d` again.

## Deployment checklist

```text
[ ] Image pulled from GHCR by its immutable sha-<commit> tag (not :latest,
    not a local build)
[ ] docker-compose.override.yml points services.astralbody.image at that tag
    (build: dropped or compose started with --no-build)
[ ] ASTRAL_ENV unset (or =production) on the host — NOT development
[ ] USE_MOCK_AUTH=false
[ ] WEB_SESSION_ENC_KEY + OFFLINE_GRANT_ENC_KEY generated (Fernet)
[ ] AUDIT_HMAC_SECRET high-entropy (placeholder is refused at boot)
[ ] AGENT_API_KEY set (agents refuse to register without it)
[ ] KEYCLOAK_* configured; realm per docs/keycloak-realm-settings.md
    (incl. Remember Me OFF, Offline Session ≥ 365 d, roles user/admin)
[ ] PUBLIC_BASE_URL/BACKEND_PUBLIC_URL = public https origin
[ ] Reverse proxy terminates TLS, forwards X-Forwarded-*, upgrades /ws
[ ] FORWARDED_ALLOW_IPS = proxy address
[ ] https://host/auth/callback registered on the Keycloak client
[ ] docker compose up -d; container healthcheck goes healthy (/readyz)
[ ] Boot log shows no posture warnings; GET / redirects to Keycloak
```
