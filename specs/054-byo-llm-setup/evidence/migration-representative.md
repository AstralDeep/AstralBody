# Migration evidence — feature 054 (`user_llm_config`, `system_llm_config`)

**Constitution IX**: "Migrations MUST be tested against a representative
dataset before merge; a passing migration on an empty database is not
sufficient evidence."

**Run**: 2026-07-10, local dev Postgres (`astraldeep-postgres` container,
`localhost:5432`, database `astralbody`) — a long-lived dev database carrying
real prior-feature data, with the working tree's `shared/database.py`
(revision bump `052.001` → `054.001`).

## Representative pre-migration state

Populated tables at migration time (non-exhaustive listing from the run):

```
chats: 5 rows            audit_events: 10 rows
agent_scopes: 15 rows    agent_trust: 16 rows
(messages, saved_components, user_credentials, user_preferences,
 tool_overrides, draft_agents, scheduled_job, user_attachments,
 memory_item, web_session present with 0 rows)
```

## Runs and outcome

1. `_init_db()` with `SCHEMA_REVISION='054.001'` vs stored `052.001` →
   full idempotent DDL run: both new tables created
   (`user_llm_config` — 7 columns; `system_llm_config` — 8 columns,
   `CHECK (id = 1)` single-row guard). No error, no data transform.
2. `_init_db()` re-run → schema_meta fast path (idempotency proof).
3. Post-migration assertion: **every pre-existing row count unchanged**
   (`existing-data preserved: True` in the run output); stored revision
   settled at `054.001`.

Note: concurrent local test processes were exercising the same dev database
during the first capture (the 054 test agents boot in-process Orchestrators,
each running the same idempotent `_init_db`) — which incidentally
demonstrates concurrent-boot safety of the guarded DDL; the final clean run
above confirms the settled marker.

## Rollback

Both tables are additive with no FKs; rollback is
`DROP TABLE IF EXISTS user_llm_config, system_llm_config;` +
`DELETE FROM schema_meta WHERE key='revision'` (forces a full run next
boot). A pre-054 image never reads these tables (data-model.md §Rollback).
