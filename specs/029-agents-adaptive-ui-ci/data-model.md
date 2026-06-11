# Data Model: Agent Catalog Overhaul, Adaptive UI Designer & Production CI

**Date**: 2026-06-11 · All deltas land in `shared/database.py::_init_db()` (idempotent, auto-run at boot — Constitution IX).

## New table: `workspace_layout`

Per-chat, per-round designed arrangement. An overlay: it references components, never owns them.

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| chat_id | TEXT NOT NULL | FK-by-convention to `chats` (matches `saved_components` posture) |
| user_id | TEXT NOT NULL | scoping/audit parity with `saved_components` |
| layout_key | TEXT NOT NULL | deterministic per round: `ly_<sha1(chat_id|turn_marker)[:16]>` |
| position | INTEGER NOT NULL | canvas ordering relative to other layouts and unclaimed components |
| layout | JSONB NOT NULL | the designed tree (ref leaves + inline garnish; contract in contracts/ui-designer-llm.md) |
| created_at / updated_at | TIMESTAMPTZ | default now() |

- `UNIQUE(chat_id, layout_key)` — re-designing the same round upserts in place (FR-019: garnish updates, never duplicates).
- Index on `(chat_id, position)`.
- Deleted when its chat is deleted (same lifecycle hook that clears `saved_components`).

**Validation rules** (enforced in `WorkspaceManager`, not DDL): every `ref` leaf must name a live `saved_components.component_id` for the same chat at write time; a component_id may be claimed by at most one live layout (later layout wins; earlier layout's ref is pruned on write).

**Rollback**: `DROP TABLE workspace_layout;` — canvas degrades to the flat position-ordered rendering of `saved_components` (pre-029 behavior). No component data is lost because layouts never own content.

## Altered table: `workspace_snapshot`

| Delta | Type | Notes |
|---|---|---|
| `layouts` | JSONB NULL (additive) | the chat's live layout rows at snapshot time; NULL for pre-029 snapshots |

Timeline rendering treats NULL as "no arrangements" (flat render) — old snapshots remain fully viewable.

**Rollback**: `ALTER TABLE workspace_snapshot DROP COLUMN layouts;`

## One-time guarded migration: ml_services identity remap

Carried out at boot inside `_init_db()` behind a sentinel check (e.g. presence of any rows still naming the old ids), so re-execution is a no-op:

1. `agent_ownership`, `agent_scopes`, `tool_overrides`, `chats.agent_id`: rows whose agent id matches the classify/forecaster/llm_factory identities (exact ids read from the live table at migration time — the dir-derived `<name>-1` convention) are rewritten to `ml_services-1`. Duplicate-key collisions (a user had rows for two of the three) resolve by keep-first + delete-rest for ownership, and by UNION semantics for scopes/overrides (a scope granted on any of the three remains granted).
2. `tool_overrides.tool_name` remap for the ten prefixed verbs: `submit_dataset → classify_submit_dataset` when the row's old agent id was classify's, `→ forecaster_submit_dataset` when forecaster's; same for `start_training_job`, `get_job_status`, `get_results`, `delete_dataset`.
3. Per-user credentials: stored under credential KEY names (`CLASSIFY_URL`, `CLASSIFY_API_KEY`, `FORECASTER_URL`, `FORECASTER_API_KEY`, `LLM_FACTORY_URL`, `LLM_FACTORY_API_KEY`), which are unchanged — the consolidated agent's `card_metadata.required_credentials` lists all three bundles, so saved credentials resolve with **no migration needed** (verified against credential_manager key-based storage at implementation time; if storage proves agent-scoped, the same remap pattern as (1) applies).

**Rollback**: documented reverse UPDATEs (remap `ml_services-1` rows back to the three ids by tool-name ownership; strip the verb prefixes). Practical note: rollback also requires restoring the three agent directories from git history.

## One-time guarded migration: removed-agent row cleanup

`DELETE FROM agent_ownership / agent_scopes / tool_overrides WHERE agent_id` matches the six removed identities (email_tracker, grant_budgets, grants, linkedin, nefarious, nocodb `<name>-1` forms). Idempotent by nature (deleting zero rows is fine).

**Explicitly NOT deleted** (FR-004): `audit_events` (append-only by trigger design), `chats` transcripts, `saved_components` rows originating from removed agents — these remain viewable; re-execution attempts hit the new retirement guard and produce `workspace.action_denied`-class audit records.

**Rollback**: rows are reconstructable by re-adding the agent directories — `start.py:51-70` re-seeds ownership from `DEFAULT_AGENT_OWNER` on next boot; scopes/overrides were user preferences and are documented as intentionally destroyed (lead-dev-approved destructive migration per Constitution IX, recorded in the PR).

## Unchanged but load-bearing (contracts honored, no schema delta)

- `saved_components` (+ `component_id`, `position`, `updated_at`): identity resolution, single-source supersede, and `component_action` provenance are untouched by the designer (reference-leaf model).
- `web_session`, `auth_revocation_queue`, audit hash-chain: untouched.
- New agents (web_research, summarizer) add **no** tables; their registration follows the standard ownership-seeding path.

## Entity relationships

```text
chats 1 ──── * saved_components          (existing; identity rows — the designer never writes these)
chats 1 ──── * workspace_layout          (NEW; ref leaves point at saved_components.component_id)
chats 1 ──── * workspace_snapshot        (existing; + layouts column capturing workspace_layout state)
agent_ownership/agent_scopes/tool_overrides ── agent_id strings   (remapped: 3→ml_services-1; 6 deleted)
```
