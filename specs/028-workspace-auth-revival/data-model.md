# Data Model: 028-workspace-auth-revival

All schema changes ship as idempotent statements inside the existing `_init_db()` in `backend/shared/database.py` (Constitution IX, house pattern per 013/027). No existing column is altered or dropped; everything is additive.

## New table: `web_session` (Part A — D3)

Durable server-side OIDC sessions (replaces the in-memory `_SESSIONS` dict as source of truth).

| Column | Type | Notes |
|---|---|---|
| `sid` | TEXT PK | Random 128-bit id; the signed cookie carries this (HMAC unchanged). |
| `user_id` | TEXT NOT NULL | Keycloak `sub`. Indexed. |
| `access_token_enc` | TEXT NOT NULL | Fernet-encrypted (key: `WEB_SESSION_ENC_KEY` → fallback `OFFLINE_GRANT_ENC_KEY`; production fail-closed if neither). |
| `refresh_token_enc` | TEXT NOT NULL | Fernet-encrypted; rotated on every refresh. |
| `interactive_anchor` | BIGINT NOT NULL | Epoch seconds of last **interactive** login; never moved by refresh (016 hard cap). |
| `hard_expires_at` | BIGINT NOT NULL | `interactive_anchor + OFFLINE_GRANT_MAX_DAYS*86400` (365 d default). |
| `last_refresh_at` | BIGINT NOT NULL | Bookkeeping/diagnostics. |
| `resumed` | BOOLEAN DEFAULT FALSE | Whether the most recent establishment was a resume (016 `RegisterUI.resumed`). |
| `created_at` | BIGINT NOT NULL | |

Lifecycle: created at `/auth/callback`; row updated in place on refresh; deleted on logout, user-switch revocation, hard-cap expiry, or failed refresh. Opportunistic purge of expired rows on access.

## New table: `auth_revocation_queue` (Part A — D5)

Offline-tolerant revocation retries (server-side analog of 016's client revocation queue).

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `user_id` | TEXT NOT NULL | |
| `refresh_token_enc` | TEXT NOT NULL | Fernet-encrypted token awaiting revocation at Keycloak. |
| `enqueued_at` | BIGINT NOT NULL | |
| `attempts` | INTEGER DEFAULT 0 | Exponential backoff; row deleted on success or after token's natural hard-cap expiry. |

## Modified table: `saved_components` → live workspace store (Part B — D13)

Existing columns unchanged (`id`, `chat_id` FK CASCADE, `user_id`, `component_data`, `component_type`, `title`, `created_at`). Additive columns:

| Column | Type | Notes |
|---|---|---|
| `component_id` | TEXT | Stable identity (D11): author `Primitive.id` or `wc_<sha1(...)[:16]>`. UNIQUE per chat via index `ux_saved_components_chat_component (chat_id, component_id)`. NULL allowed for legacy rows (treated as pre-028 saved items; assigned on first touch). |
| `position` | INTEGER | Workspace ordering; appended monotonically; NULL legacy rows sort by `created_at`. |
| `updated_at` | BIGINT | Bumped on in-place upsert. |

Behavior change (code, not schema): upserts UPDATE the existing row keyed `(chat_id, component_id)` — `replace_components`' delete+reinsert with fresh uuid4 is retired. Row `id` becomes stable for the component's lifetime.

## New table: `workspace_snapshot` (Part B — D14)

One immutable full-state snapshot per assistant turn and per component-action mutation.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `chat_id` | TEXT NOT NULL FK → chats ON DELETE CASCADE | Timeline dies with the chat (FR-033). |
| `user_id` | TEXT NOT NULL | Scoping per house convention. |
| `turn_message_id` | INTEGER NULL FK → messages(id) ON DELETE CASCADE | The assistant message closing the turn; NULL for component-action snapshots between turns. |
| `cause` | TEXT NOT NULL | `'turn'` \| `'component_action'` \| `'combine'` \| `'condense'` \| `'remove'`. |
| `components` | TEXT NOT NULL | Ordered JSON array of the full workspace (structured dicts incl. `component_id`, provenance). Message-grade content — same protection class as `messages.content` (A11). |
| `created_at` | BIGINT NOT NULL | Indexed with `chat_id` for timeline listing. |

## Entity relationships

```text
chats 1 ── * messages
chats 1 ── * saved_components      (live workspace; ordered by position)
chats 1 ── * workspace_snapshot    (timeline; FK CASCADE both ways)
workspace_snapshot * ── 0..1 messages (turn_message_id)
users 1 ── * web_session           (multiple browsers/devices)
users 1 ── * auth_revocation_queue
users 1 ── * user_offline_grant    (existing, 025 — revoked on logout)
```

## Validation rules

- `component_id` is required on every workspace write from 028 code; uniqueness enforced per chat by the index.
- `web_session` reads MUST verify `now < hard_expires_at` before any refresh attempt; violations delete the row.
- All queries user_id-scoped (existing HistoryManager convention).
- `workspace_snapshot.components` is written atomically with the workspace mutation that caused it (same transaction where the DB layer allows).

## State transitions

**Web session**: `created(interactive)` → `active` ⇄ `refreshed` → `revoked(logout | user_switch | hard_cap | refresh_failed)`. Only `created(interactive)` sets `interactive_anchor`.

**Workspace component**: `created(turn | component_action)` → `updated(...)` * → `removed(user | supersession)`. Every transition writes a snapshot row and an audit event.

## Migration (idempotent, in `_init_db()`)

```sql
CREATE TABLE IF NOT EXISTS web_session (...);
CREATE TABLE IF NOT EXISTS auth_revocation_queue (...);
CREATE TABLE IF NOT EXISTS workspace_snapshot (...);
ALTER TABLE saved_components ADD COLUMN IF NOT EXISTS component_id TEXT;
ALTER TABLE saved_components ADD COLUMN IF NOT EXISTS position INTEGER;
ALTER TABLE saved_components ADD COLUMN IF NOT EXISTS updated_at BIGINT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_saved_components_chat_component
  ON saved_components (chat_id, component_id) WHERE component_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_workspace_snapshot_chat ON workspace_snapshot (chat_id, created_at);
CREATE INDEX IF NOT EXISTS ix_web_session_user ON web_session (user_id);
```

**Rollback path**: all 028 objects are additive — `DROP TABLE web_session, auth_revocation_queue, workspace_snapshot;` and `ALTER TABLE saved_components DROP COLUMN component_id, DROP COLUMN position, DROP COLUMN updated_at;` restore the prior schema. Dropping `web_session` only forces re-login (no data loss); dropping snapshots loses timeline history only. Tested against a representative dataset (seeded chats + components) per Constitution IX.
