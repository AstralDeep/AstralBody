# Phase 1 Data Model: Agent & User Action Audit Log

**Branch**: `003-agent-audit-log`
**Date**: 2026-04-28
**Inputs**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md)

## Storage

PostgreSQL, single table `audit_events`, range-partitioned monthly by `recorded_at`. Two database roles: `app_audit_role` (INSERT, SELECT only) used by the application, and `audit_retention_role` (DELETE only on partitions older than 6 years) used exclusively by the retention job. No UPDATE grant exists for any role.

## `audit_events` table

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `event_id` | `UUID` | `PRIMARY KEY` (`DEFAULT gen_random_uuid()`) | Public identifier, exposed in API responses. |
| `actor_user_id` | `TEXT` | `NOT NULL`, indexed | The user the action was performed *for*. The audit log is filtered on this column. Owner of the audit row. |
| `auth_principal` | `TEXT` | `NOT NULL` | The token `sub` that authenticated the action. For agent actions, this is the agent's machine identity (RFC 8693); for direct user actions, equals `actor_user_id`. |
| `agent_id` | `TEXT` | `NULL` | The acting agent's identity, when the action was an agent action. NULL for direct user actions. |
| `event_class` | `TEXT` | `NOT NULL` | One of: `auth`, `conversation`, `file`, `settings`, `agent_tool_call`, `agent_ui_render`, `agent_external_call`, `audit_view`. |
| `action_type` | `TEXT` | `NOT NULL` | Free-form subtype within `event_class`, e.g. `auth.login`, `conversation.create`, `agent_tool_call.web_search`. |
| `description` | `TEXT` | `NOT NULL` | Human-readable summary surfaced in the UI. Generated server-side; never echoes raw user input. |
| `conversation_id` | `TEXT` | `NULL`, indexed | Reference to the originating conversation, if any. Audit row remains intact if the conversation is later deleted (Edge Cases). |
| `correlation_id` | `UUID` | `NOT NULL` | Links related entries (e.g., `in_progress` → `success`/`failure` for the same tool call). |
| `outcome` | `TEXT` | `NOT NULL`, `CHECK outcome IN ('in_progress','success','failure','interrupted')` | State machine in §State transitions. |
| `outcome_detail` | `TEXT` | `NULL` | Plain-language failure reason, when `outcome IN ('failure','interrupted')`. Surfaced in detail view (US2 scenario 2). |
| `inputs_meta` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | Non-PHI metadata for inputs. **No raw payload bytes.** Schema enforced at write time by `backend/audit/schemas.py`. |
| `outputs_meta` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` | Non-PHI metadata for outputs. Same constraints as `inputs_meta`. |
| `artifact_pointers` | `JSONB` | `NOT NULL DEFAULT '[]'::jsonb` | Array of `{artifact_id, store, extension, size_bytes, hmac_digest, key_id}` per FR-004 / FR-015 / FR-016. Filename NOT stored. |
| `started_at` | `TIMESTAMPTZ` | `NOT NULL` | AU-8 timestamp with timezone, server-recorded. |
| `completed_at` | `TIMESTAMPTZ` | `NULL` | Set on transition out of `in_progress`. |
| `recorded_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | Server clock at insert. Used as the partition key and the chronological-display key (Edge Cases — clock skew). |
| `prev_hash` | `BYTEA` | `NOT NULL` | `entry_hash` of the previous entry in this user's chain (R3). Genesis row uses `\x00...` (32 zero bytes). |
| `entry_hash` | `BYTEA` | `NOT NULL` | `HMAC_SHA256(server_secret_for(key_id), prev_hash || canonical_json(row_minus_hash_fields))`. |
| `key_id` | `TEXT` | `NOT NULL` | Identifier of the HMAC key used (R4). Old `key_id`s remain verifiable. |
| `schema_version` | `SMALLINT` | `NOT NULL DEFAULT 1` | Lets the canonicalization for `entry_hash` evolve without breaking historical verification. |

### Indices

- `idx_audit_user_recorded` on (`actor_user_id`, `recorded_at` DESC) — drives the FR-006 "most recent first" listing and the SC-006 first-page query.
- `idx_audit_correlation` on (`correlation_id`) — for joining `in_progress`/`success` pairs in the detail view.
- `idx_audit_user_class_recorded` on (`actor_user_id`, `event_class`, `recorded_at` DESC) — drives US3 filter-by-agent / filter-by-event-class.
- Partial index `idx_audit_user_failures` on (`actor_user_id`, `recorded_at` DESC) `WHERE outcome IN ('failure','interrupted')` — drives "show only failures" filter cheaply at scale.

### Partitioning

`PARTITION BY RANGE (recorded_at)`, monthly partitions named `audit_events_YYYYMM`. The retention job (running under `audit_retention_role`) `DROP`s partitions whose entire range is more than 6 years older than `now()`. Hash chain is unaffected — chains are per-user, and dropped partitions only contain rows already past the legal retention horizon.

### Append-only enforcement

Migration grants:
- `GRANT INSERT, SELECT ON audit_events TO app_audit_role;`
- `GRANT DELETE ON audit_events TO audit_retention_role;` (DELETE only — no UPDATE)
- `REVOKE UPDATE ON audit_events FROM PUBLIC;`

A row-level trigger `audit_events_no_update` raises an exception on `BEFORE UPDATE` regardless of role, as a final defense.

## Public/API entity (DTO)

The shape returned by `GET /api/audit` and `GET /api/audit/{event_id}` is a strict subset — `prev_hash`, `entry_hash`, `key_id`, `schema_version`, and `auth_principal` are NOT exposed to clients:

```jsonc
{
  "event_id": "uuid",
  "event_class": "agent_tool_call",
  "action_type": "agent_tool_call.web_search",
  "description": "Web search agent searched for 'symptom checker'",
  "agent_id": "web-search-agent",
  "conversation_id": "conv_xyz",
  "correlation_id": "uuid",
  "outcome": "success",
  "outcome_detail": null,
  "inputs_meta": { "...": "..." },
  "outputs_meta": { "...": "..." },
  "artifact_pointers": [
    {
      "artifact_id": "art_123",
      "store": "uploads",
      "extension": "dcm",
      "size_bytes": 1048576,
      "available": true
    }
  ],
  "started_at": "2026-04-28T14:00:00Z",
  "completed_at": "2026-04-28T14:00:01Z",
  "recorded_at": "2026-04-28T14:00:01.123Z"
}
```

`available` on each artifact pointer is computed at read time (FR-017): `true` if the source artifact still exists and is reachable; `false` triggers the "source artifact no longer available" UI state.

## Relationships

```
User (1) ─── (N) AuditEvent ─── (0..1) Conversation
                  │
                  ├─── (0..1) Agent              [agent_id, when event_class starts with 'agent_']
                  ├─── (0..N) ArtifactPointer    [embedded in artifact_pointers JSONB]
                  └─── (1)    AuthPrincipal      [auth_principal — token sub at action time]
```

`User` and `Conversation` are foreign references (string IDs) — the audit table does NOT use FK constraints to those tables, so deletions there cannot cascade into audit (FR-014, AU-9).

## State transitions for `outcome`

```
            ┌─────────────┐
            │ in_progress │   (initial state for long-running actions)
            └──────┬──────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌────────────┐
   │ success │ │ failure │ │ interrupted│
   └─────────┘ └─────────┘ └────────────┘
```

Atomic actions write a single row directly in `success` or `failure` (no `in_progress` precursor). Long-running actions (e.g., agent tool calls that may take seconds) write a paired entry: an `in_progress` row at start, and a *new* row (sharing the same `correlation_id`) on completion in `success`/`failure`/`interrupted`. The original `in_progress` row is **never updated** (append-only); the UI joins by `correlation_id` to show the resolved state. `interrupted` is written when a connection drop or crash kills the action mid-flight; a sweeper job converts orphaned `in_progress` rows older than a configurable threshold (default 5 minutes) into `interrupted` follow-up rows.

## Validation rules summarized from FRs

| Rule | Source | Where enforced |
|------|--------|----------------|
| `actor_user_id` always equals the authenticated user when reading | FR-007, FR-019 | `backend/audit/api.py` reads `actor_user_id` from the JWT, never from query params |
| Raw payload bytes never written | FR-004 | `backend/audit/schemas.py` rejects any `inputs_meta` / `outputs_meta` field whose serialized size exceeds a strict cap (e.g., 4 KiB) and whose key/value match a denylist of payload-shaped names |
| Filenames not stored in plaintext | FR-015 | `backend/audit/pii.py` strips filenames before persistence; only `extension` survives |
| Payload digests are HMAC, never raw hash | FR-016 | `backend/audit/pii.py` provides a single `hmac_digest()` helper; raw `hashlib.sha256(...).hexdigest()` of payloads is forbidden by code review + ruff custom rule |
| Append-only | FR-014, FR-019, AU-9 | DB role grants + `audit_events_no_update` trigger + repository code |
| Admin-blind | FR-019 | API filter never reads `actor_user_id` from input; WS publisher filters by connection `user_id` |
| Always-on recording | FR-021, AU-12 | Recording sites enumerated in research.md §R10 each have a coverage test |
| 6-year retention | FR-012, AU-11 | Retention job under `audit_retention_role`, runs monthly, only on partitions whose entire range is past the horizon |
