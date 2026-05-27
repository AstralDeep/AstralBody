# Phase 1 Data Model: Agentic Soul Integration

All new tables are created idempotently in `backend/shared/database.py::Database._init_db()` following the existing convention (`CREATE TABLE IF NOT EXISTS`, `_column_exists()` guards for later columns, `CREATE INDEX IF NOT EXISTS`). All tables are **per-user scoped** (`user_id TEXT`) and carry `created_at BIGINT` / `updated_at BIGINT` epoch-ms timestamps like existing tables. No existing table requires a schema change.

Timestamp convention: epoch-ms `BIGINT` (matches `chats`, `agent_scopes`, `tool_overrides`) except where `TIMESTAMPTZ` is the existing norm for lifecycle rows (matches `onboarding_state`); each table notes which it uses.

---

## Existing tables reused (no change)

- **`agent_scopes`** `(user_id, agent_id, scope, enabled)` — authoritative for skill (=tool) availability; `VALID_SCOPES = tools:read|write|search|system`.
- **`tool_overrides`** `(user_id, agent_id, tool_name, enabled, permission_kind)` — per-tool enable/disable = **skill enable/disable**.
- **`user_preferences`** `(user_id, preferences JSON)` — may hold lightweight UI prefs (e.g., dreaming-enabled toggle mirror); source of truth for dreaming-enabled is `user_personalization`.
- **`onboarding_state`** `(user_id, status, last_step_id, …)` — extended in use (new tutorial steps), not in schema.
- **`tutorial_step`** `(slug, audience, display_order, target_kind, target_key, title, body)` — new personalization rows seeded (`target_kind='sdui'`).
- **`audit_events`** — append-only hash-chained log; new `event_class` values only.
- **`chats` / `messages`** — scheduled-job and dream outputs persist here as normal assistant turns.

---

## New tables

### 1. `user_personalization` — the "soul" + profile (one row per user)

| Column | Type | Notes |
|---|---|---|
| `user_id` | TEXT PRIMARY KEY | one row per user |
| `profession` | TEXT NULL | non-PHI personalization |
| `goals` | JSONB NOT NULL DEFAULT '[]' | list of short goal strings |
| `personality` | JSONB NOT NULL DEFAULT '{}' | structured "soul": tone, directness, humor, verbosity, boundaries (free-text style notes allowed, non-PHI) |
| `dreaming_enabled` | BOOLEAN NOT NULL DEFAULT TRUE | opt-out default (FR-029) |
| `created_at` / `updated_at` | BIGINT | epoch-ms |

- **Scope**: strictly `user_id`. **Validation**: `personality` style notes pass the PHI gate (R3) on write. **Lifecycle**: created lazily at onboarding or first edit; editable/deletable (delete resets to defaults).

### 2. `memory_item` — durable, non-PHI personalization facts

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `user_id` | TEXT NOT NULL | scope |
| `category` | TEXT NOT NULL CHECK (category IN ('profession','goal','preference','workflow_tag','context')) | structured-only (R3) |
| `value` | TEXT NOT NULL | short typed value; PHI-gated on write |
| `source` | TEXT NOT NULL CHECK (source IN ('explicit','promoted')) | explicit "remember" vs dreaming-promoted |
| `salience` | REAL NOT NULL DEFAULT 0 | promotion score snapshot |
| `created_at` / `updated_at` | BIGINT | |

- **Index**: `(user_id, category)`. **Validation**: every write passes `phi_gate` (R3); rejected content never persists. **Lifecycle**: created by explicit `remember` or by promotion; viewable/correctable/deletable (FR-018); all mutations audited (FR-019).

### 3. `short_term_signal` — transient promotion candidates

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `user_id` | TEXT NOT NULL | scope |
| `category` | TEXT NOT NULL | same allowed set as `memory_item` |
| `value` | TEXT NOT NULL | PHI-gated on capture |
| `recall_count` | INTEGER NOT NULL DEFAULT 0 | recurrence signal |
| `last_seen_at` | BIGINT | recency signal |
| `created_at` | BIGINT | |

- **Index**: `(user_id, last_seen_at)`. **Lifecycle**: auto-captured post-turn (R5); consumed/aged-out by the consolidation sweep (promoted → `memory_item` or discarded). Never injected as "durable" memory.

### 4. `scheduled_job` — a user's recurring/future task

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `user_id` | TEXT NOT NULL | owner/scope |
| `agent_id` | TEXT NULL | target agent (NULL = orchestrator default) |
| `name` | TEXT NOT NULL | display name |
| `instruction` | TEXT NOT NULL | the prompt to run |
| `schedule_kind` | TEXT NOT NULL CHECK (schedule_kind IN ('one_shot','interval','cron')) | (FR-020) |
| `schedule_expr` | TEXT NOT NULL | ISO-8601 (one_shot), "N{m,h,d}" (interval), or 5-field cron |
| `timezone` | TEXT NOT NULL DEFAULT 'UTC' | tz-aware evaluation |
| `consented_scopes` | JSONB NOT NULL | subset of `tools:*` the user consented at creation |
| `delivery` | TEXT NOT NULL DEFAULT 'in_app' CHECK (delivery = 'in_app') | in-app only (FR-022/SC-006) |
| `status` | TEXT NOT NULL CHECK (status IN ('active','paused','expired','completed','disabled')) | |
| `target_chat_id` | TEXT NULL | chat to deliver into (or a per-job system chat) |
| `next_run_at` | BIGINT NULL | computed by `scheduler/cron.py` |
| `last_run_at` | BIGINT NULL | |
| `offline_grant_id` | UUID NULL REFERENCES user_offline_grant(id) | the authority captured at consent |
| `created_at` / `updated_at` | BIGINT | |

- **Index**: `(status, next_run_at)` (scheduler poll), `(user_id, status)` (governance/list). **Governance** (FR-038): per-user active-job cap + min-interval floor enforced on create. **Lifecycle**: active → paused/resume → expired (grant cap reached) / completed (one-shot) / disabled (deleted). One-shot auto-completes; recurring recompute `next_run_at` after each run.

### 5. `job_run` — one execution record

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `job_id` | UUID NOT NULL REFERENCES scheduled_job(id) ON DELETE CASCADE | |
| `user_id` | TEXT NOT NULL | scope |
| `started_at` | BIGINT NOT NULL | |
| `ended_at` | BIGINT NULL | |
| `outcome` | TEXT NOT NULL CHECK (outcome IN ('running','success','failure','interrupted','skipped_auth')) | |
| `auth_ref` | TEXT NULL | correlation id of the auth.offline_grant_minted audit event |
| `correlation_id` | UUID NOT NULL | groups the run's audit events |
| `summary` | TEXT NULL | short, PHI-redacted result summary |

- **Index**: `(job_id, started_at DESC)`. **Restart recovery** (R9/FR-025): any `running` row at startup → `interrupted`. **`skipped_auth`**: produced when the grant is revoked/expired (FR-024).

### 6. `consolidation_sweep` — a "dream" record

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `user_id` | TEXT NOT NULL | scope |
| `ran_at` | BIGINT NOT NULL | |
| `candidates_considered` | INTEGER NOT NULL DEFAULT 0 | |
| `promoted_count` | INTEGER NOT NULL DEFAULT 0 | |
| `summary` | TEXT NOT NULL | human-readable "what was promoted and why" (FR-029) |
| `trigger` | TEXT NOT NULL CHECK (trigger IN ('scheduled','manual')) | |

- **Index**: `(user_id, ran_at DESC)`. **Lifecycle**: append-only review trail; every sweep audited (FR-030).

### 7. `user_offline_grant` — encrypted authority for unattended jobs (sensitive)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `user_id` | TEXT NOT NULL | scope |
| `agent_id` | TEXT NULL | grant may be agent-scoped |
| `refresh_token_enc` | BYTEA NOT NULL | **encrypted at rest** (`cryptography`, key from env/secret) — never returned by any API |
| `issued_at` | BIGINT NOT NULL | |
| `expires_at` | BIGINT NOT NULL | `issued_at + 365 days` hard cap (FR-024) |
| `revoked_at` | BIGINT NULL | set on logout/scope-revocation/sign-out-everywhere |
| `created_at` / `updated_at` | BIGINT | |

- **Index**: `(user_id, agent_id)` partial WHERE `revoked_at IS NULL`. **Security** (Constitution VII, R2): encrypted; never logged or returned; re-derivation audited; honored against live revocation + 365-day cap. **Lifecycle**: created at job-creation consent (live session); read only by `scheduler/runner.py` to mint a fresh access token; invalidated on revocation/expiry.

---

## New audit `event_class` values (add to `audit/schemas.py::EVENT_CLASSES`)

| event_class | example action_type | emitted when |
|---|---|---|
| `personalization` | `personalization.profile_update`, `personalization.personality_update` | profile/soul edited |
| `memory` | `memory.create`, `memory.view`, `memory.update`, `memory.delete`, `memory.promote` | memory mutations + recall view (FR-019) |
| `skill` | `skill.enable`, `skill.disable` | enable/disable (FR-010) — may reuse existing `settings`/tool-permission audit if already covered |
| `schedule` | `schedule.create`, `schedule.run`, `schedule.pause`, `schedule.resume`, `schedule.delete`, `schedule.skipped_auth` | job lifecycle + each run (FR-033) |
| `dreaming` | `dreaming.sweep`, `dreaming.enable`, `dreaming.disable`, `dreaming.trigger` | consolidation (FR-030) |
| `auth` (existing) | `auth.offline_grant_minted`, `auth.offline_grant_revoked` | per-run token mint + revocation (R2) |

(If review prefers fewer classes, `skill.*` and `personalization.*` may fold into the existing `settings` class; the action_type names stay distinct.)

---

## Entity → spec mapping

| Spec entity | Table(s) |
|---|---|
| User Personalization Profile | `user_personalization` |
| Skill | (view over `agent_scopes` + `tool_overrides` + tool registry) — no new table |
| Personality ("Soul") | `user_personalization.personality` |
| Memory Item | `memory_item` |
| Short-Term Signal | `short_term_signal` |
| Scheduled Job | `scheduled_job` (+ `user_offline_grant` for authority) |
| Job Run | `job_run` |
| Consolidation Sweep ("Dream") | `consolidation_sweep` |
| Onboarding State | `onboarding_state` (existing) |
