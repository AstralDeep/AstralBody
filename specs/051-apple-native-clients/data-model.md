# Data Model: Native Apple Clients (051)

**Schema changes: none.** (FR-035; Constitution IX fallback documented below.)

## DeviceLoginRequest (transient, never persisted)

One watch sign-in attempt, brokered against the IdP. Backend state is *stateless*: everything
the poll endpoint needs rides in an opaque handle returned to the watch.

| Field | Source | Notes |
|---|---|---|
| `device_code` | IdP | Never shown to the user; embedded in the encrypted handle only |
| `user_code` | IdP | Short human-readable code shown on the watch |
| `verification_uri` / `verification_uri_complete` | IdP | Complete URI is the QR payload |
| `expires_in` / `interval` | IdP | TTL + minimum poll spacing (server-authoritative) |
| `handle` | backend | Fernet token over `{device_code, client_id, iat, exp}` using the existing web-session key; single logical use; expiry enforced on decrypt |

**Lifecycle**: `pending → approved | denied | expired` (+ transient `slow_down`).
Terminal states are terminal — a used/expired/denied handle can never mint a session
(SC-009). Approval performs the role gate (`user`/`admin`) *before* tokens are released to
the watch; roleless approval → refresh token revoked at IdP, `denied_no_access`.

**Rate limiting**: in-memory token buckets keyed by client address for `start`; per-handle
minimum-interval enforcement for `poll` (early poll → `slow_down`, no IdP call).

## Existing rows written (no new tables)

- `auth_revocation_queue` — watch/iOS/macOS logout attribution via existing `client_id`
  column (044).
- `audit_events` — new `auth`-class actions: `auth.device_login_started`,
  `auth.device_login_approved`, `auth.device_login_denied`, `auth.device_login_expired`.

## ROTE profile additions (code, not schema)

`DeviceType.IOS = "ios"`, `DeviceType.MACOS = "macos"` + full-capability host-config entries
(the 041 `android` pattern); `watch` profile reused unchanged as the degradation authority.

## Constitution IX fallback

If implementation discovers persistence is genuinely required (e.g. cross-process rate-limit
state under multi-worker deployment), it ships as an idempotent guarded `_init_db` delta with
rollback documented here first. Current design avoids it deliberately.
