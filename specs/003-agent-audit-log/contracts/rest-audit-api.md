# Contract: REST Audit API

**Branch**: `003-agent-audit-log`
**Mounted at**: `/api/audit` (under existing FastAPI app in `backend/orchestrator/api.py`)
**Authentication**: Existing Keycloak JWT bearer; mock-auth in dev.

## Authorization model

All endpoints derive `actor_user_id` exclusively from the authenticated principal's token (`sub` claim, or `act.sub` for delegated tokens — though in practice direct user requests on this API are not delegated). **No endpoint accepts `actor_user_id`, `user_id`, or any equivalent as input.** Any attempt to scope by another user via path/query/body parameter MUST be rejected before it reaches the database. There is no admin override and no `?as_user=` parameter (FR-019).

Every successful read of this API itself produces an `audit_view` audit event in the caller's own log (AU-2 / AU-12 — auditing the audit reads).

## `GET /api/audit`

List the authenticated user's audit entries.

### Query parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | int (1–200) | 50 | Page size. |
| `cursor` | string | null | Opaque cursor returned by previous response; encodes `(recorded_at, event_id)`. |
| `event_class` | string (repeatable) | none | One of the `event_class` values; multiple = OR filter. (US3) |
| `outcome` | string (repeatable) | none | `success` / `failure` / `interrupted` / `in_progress`. (US3) |
| `from` | RFC 3339 datetime | null | Inclusive lower bound on `recorded_at`. (US3) |
| `to` | RFC 3339 datetime | null | Exclusive upper bound on `recorded_at`. (US3) |
| `q` | string | null | Keyword match against `description` / `action_type`. (US3) |

### Response 200

```jsonc
{
  "items": [ /* AuditEvent DTO[] — see data-model.md */ ],
  "next_cursor": "opaque-string-or-null",
  "filters_echo": { /* normalized filters, for UI confirmation */ }
}
```

Items are ordered by `recorded_at DESC, event_id DESC` (FR-006).

### Response 400

Invalid filter values, `limit` out of range, or any attempt to pass a forbidden parameter (e.g., `actor_user_id`).

### Response 401

Missing or invalid token.

## `GET /api/audit/{event_id}`

Fetch a single audit entry by ID.

### Response 200

The `AuditEvent` DTO (see data-model.md). The `artifact_pointers[].available` field is recomputed at read time (FR-017) — `false` if the artifact's own retention has elapsed.

### Response 404

Returned for **either** "no such event" **or** "event exists but does not belong to the caller". The two are intentionally indistinguishable to avoid leaking the existence of other users' audit IDs (FR-007 / FR-019).

### Response 401

Missing or invalid token.

## Things this API explicitly does NOT expose

- `prev_hash`, `entry_hash`, `key_id`, `schema_version` — internal AU-9 fields. Verification happens via a separate operator-only tool (see quickstart.md), not this user-facing API.
- `auth_principal` — exposing the agent's token `sub` adds no user value and bloats the entity.
- A list-by-other-user endpoint. There is no such endpoint and there will not be one within this feature.
- Any `PATCH`, `PUT`, or `DELETE` verbs. The API is read-only.

## Rate limits

Bounded by the existing API gateway's per-user rate limit. No feature-specific rate limit. Excessive list-paging is naturally bounded by `limit` + cursor.

## Error envelope

Standard FastAPI JSON error envelope already used elsewhere in `backend/orchestrator/api.py`:

```jsonc
{ "detail": "human-readable message", "code": "audit.invalid_filter" }
```

## Test obligations

Contract tests live in `backend/tests/contract/audit/test_rest_contract.py` and MUST cover:

1. `GET /api/audit` returns only entries with `actor_user_id == authenticated user`, even when the database contains entries for other users.
2. `GET /api/audit?actor_user_id=other` returns 400.
3. `GET /api/audit/{event_id}` for another user's event returns 404, indistinguishable from a non-existent ID.
4. Successful reads create an `audit_view` entry in the caller's own log.
5. Pagination is stable under concurrent inserts (cursor-based, not offset-based).
6. `artifact_pointers[].available` flips to `false` when the source artifact is deleted between two reads.
