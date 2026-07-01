# Contract — Session Lifecycle: Reconnect, Expiry, Sign-out (044)

**Satisfies**: FR-003, FR-004, FR-005, SC-004, SC-005 | **Research**: R3, R4, R5

## 1. Reconnect & outbound queue (both natives)

State machine per [data-model.md §6.1](../data-model.md). Normative points:

- **Backoff**: base 1 s, ×2 per attempt, cap 30 s, counter resets on successful open
  (Android's `backoffDelayMs` is the shared reference; Windows ports it into
  `astral_client/protocol.py::OrchestratorClient` as a reconnect loop around `_main`).
- **Resume**: on open the client re-sends `register_ui` (token + device caps +
  `supported_types`), then re-issues `discover_agents` + `get_history`; an active chat view
  re-loads via `load_chat`. Within 30 s of server availability the session is usable with no
  user action (SC-005).
- **Visibility**: connection state is always user-visible — the server model's `status`
  top-bar control shows `Connected / Reconnecting (n) / Offline / Signing in…`, plus a
  non-modal banner while not connected.
- **Outbound while disconnected**: bounded FIFO queue, 64 frames, flushed on open. Overflow →
  the oldest frame is dropped **and a visible failure notice is shown** naming the lost
  action ("message not sent — reconnect and retry"). A `chat_message` composed while
  disconnected either queues (within bounds) or fails visibly; it never silently vanishes.
  *(This upgrades Android's current silent drop-oldest as well.)*

## 2. Session expiry (both natives)

On `auth_required` (transport) / register rejection:

1. Holding a refresh credential → silent refresh against the token endpoint → reconnect with
   the new access token. Bounded attempts (2) with backoff.
2. No/invalid refresh credential, or refresh fails non-transiently → **explicit sign-in
   affordance**: Windows shows a sign-in dialog that triggers the existing `oidc_login`
   loopback flow off the UI thread, then `_reconnect(new_token)`; Android routes to
   `SignInScreen`. The frozen "Re-authenticating…" caption and log-only failure paths are
   removed — no configuration may dead-end (FR-004).
3. Offline during refresh → treated as reconnect-pending ("offline, will retry"), not
   signed-out (spec Edge Case 4).

## 3. Native sign-out (server-revoking, offline-tolerant)

### 3.1 New REST endpoint (additive)

```
POST /api/auth/logout
Authorization: Bearer <access JWT>            (existing get_current_user_payload dependency)
Body: {"refresh_token": "<opaque>", "client_id": "astral-desktop" | "astral-mobile"}
→ 200 {"revoked": true | "queued": true}
→ 400 malformed body / client_id not in KEYCLOAK_ALLOWED_AZP
→ 401 invalid bearer
```

Server behavior (mirrors web `/auth/logout` semantics exactly):

1. Validate `client_id` against the existing `KEYCLOAK_ALLOWED_AZP` allowlist; the bearer's
   `azp`/`sub` binds the request to the calling user.
2. `_revoke_or_queue(user_id, refresh_token, client_id=…)` — RFC 7009 revoke at
   `{authority}/protocol/openid-connect/revoke` with the **originating** `client_id`
   (Keycloak only revokes a token for its issuing client); on IdP failure, enqueue into
   `auth_revocation_queue` (now storing `client_id`; the existing 60 s retrier drains it,
   using the stored client id, falling back to the configured web client id when NULL).
3. `OfflineGrantStore().revoke_for_user(user_id)` — feature-025 parity with web logout.
4. Audit `auth.logout` with the channel (`windows`/`android`) in details.

Schema delta: `auth_revocation_queue.client_id TEXT NULL` (idempotent `_init_db`; rollback
documented in [data-model.md §8](../data-model.md)).

### 3.2 Client ladder (both natives)

```
sign out → 1) POST /api/auth/logout            (primary — inherits queued revocation)
           2) if backend unreachable: best-effort direct POST
              {authority}/protocol/openid-connect/logout  (client_id + refresh_token)
           3) ALWAYS: clear local credentials (Windows in-memory session;
              Android TokenStore.clear()) and enter signed_out state
           log the revocation outcome (revoked / queued / failed-local-only)
```

Windows then quits (current UX); Android shows `SignInScreen`. Sign-out never blocks on the
network (spec Edge Case 5).

### 3.3 Verification semantics (SC-004)

Post-logout, the **refresh token must be rejected** by Keycloak on the next refresh attempt
(3/3 clients). Note recorded in the matrix: an unexpired access JWT remains signature-valid
until `exp` on any client — identical to the web after its session row dies; the durable
session credential is the refresh token, and that is what revocation kills.
