# Contract: Device Sign-In Broker (`/api/auth/device/*`)

All endpoints are unauthenticated (pre-auth surface), rate-limited, and gated by
`FF_DEVICE_LOGIN` (default on) — flag off, IdP unreachable, or device grant not enabled on the
realm ⇒ `503 {"error": "device_login_unavailable", "detail": …}` (fail-closed, actionable).

## POST /api/auth/device/start

Request: `{"client": "astral-watch"}` (only allow-listed device-grant clients accepted).

Response `200`:

```json
{
  "handle": "<opaque fernet token>",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://idp/realms/astral/device",
  "verification_uri_complete": "https://idp/realms/astral/device?user_code=WDJB-MJHT",
  "expires_in": 600,
  "interval": 5,
  "qr_png_base64": "<PNG, backend-rendered via shared/qr.py>",
  "qr_matrix": [[0,1,…],…]
}
```

Errors: `400 unknown_client`, `429 rate_limited`, `503 device_login_unavailable`.

## POST /api/auth/device/poll

Request: `{"handle": "<opaque>"}`.

Response `200`, by state:

- `{"status": "pending", "interval": 5}`
- `{"status": "slow_down", "interval": 10}` — early poll is answered locally; no IdP call
- `{"status": "approved", "tokens": {"access_token": …, "refresh_token": …, "expires_in": …,
  "refresh_expires_in": …, "token_type": "Bearer"}}` — returned exactly once; role gate
  (`user`/`admin`) enforced before release, else `denied_no_access` + IdP-side revocation
- `{"status": "denied", "reason": "access_denied" | "denied_no_access"}`
- `{"status": "expired"}`

Errors: `400 invalid_handle` (undecryptable/expired handle), `429 rate_limited`.

## POST /api/auth/device/refresh

Request: `{"client": "astral-watch", "refresh_token": …}`. Pure proxy to the IdP token
endpoint (`grant_type=refresh_token`); response mirrors the token payload or
`401 {"error": "invalid_grant"}`. iOS/macOS refresh directly against the IdP (Windows
precedent) — this proxy exists so the watch keeps a single TLS peer.

## Non-negotiables

- Codes/handles single-use, TTL-bound, server-authoritative expiry (SC-009).
- No token material in logs; audit rows: `auth.device_login_{started,approved,denied,expired}`.
- Watch never contacts the IdP directly (FR-021).
- Existing logout contract reused for sign-out: `POST /api/auth/logout` with
  `client_id=astral-watch` (044 revocation queue).
