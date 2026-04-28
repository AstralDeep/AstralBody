# Data Model: Tool Tips and Getting Started Tutorial

**Feature**: 005-tooltips-tutorial
**Date**: 2026-04-28
**Phase**: 1

## Overview

Three new PostgreSQL tables added to `Database._init_db()` (raw psycopg2, matching the convention from features 003 and 004 — no SQLAlchemy / Alembic), plus one additive optional field on the existing `Component` primitive dataclass. No changes are made to the audit-log schema; new event classes are recorded through the existing `audit_events` table via the existing recorder.

## Tables

### 1. `onboarding_state`

One row per user, holding the user's tutorial lifecycle state and resume pointer. Created lazily on first state mutation (not at user sign-up); absence of a row is interpreted as "not started" (FR-001).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `user_id` | `text` | `PRIMARY KEY` | Keycloak `sub` claim from the verified JWT. Single source of identity, mirroring `audit_events.user_id`. |
| `status` | `text` | `NOT NULL`, `CHECK (status IN ('not_started','in_progress','completed','skipped'))` | Lifecycle state. `not_started` is only ever the implicit absence-of-row default; rows that exist will have one of the other three values. |
| `last_step_id` | `bigint` | `NULL`, `REFERENCES tutorial_step(id) ON DELETE SET NULL` | The step the user most recently saw. Used for resume-on-reload (FR-013). |
| `started_at` | `timestamptz` | `NOT NULL DEFAULT now()` | When the user first transitioned into `in_progress`. |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | Bumped on every state mutation. |
| `completed_at` | `timestamptz` | `NULL` | Set when status transitions to `completed`. |
| `skipped_at` | `timestamptz` | `NULL` | Set when status transitions to `skipped`. |

**Indices**: `PRIMARY KEY` on `user_id` is sufficient; access is always per-user.

**Row lifecycle / state transitions**:

```
(no row)                                    ── /tutorial start ──▶  in_progress
in_progress                                  ── next step ──▶       in_progress (last_step_id advances)
in_progress                                  ── final step Done ──▶ completed
in_progress | completed | skipped            ── Skip ──▶            skipped
completed | skipped                          ── Replay ──▶          (no state change; transient)
```

Replay does **not** mutate the row (per Decision 8 in research.md) — the user's existing terminal state is preserved so auto-launch suppression (FR-001, SC-006) remains correct.

**Constraints**:
- Cross-user reads/writes are forbidden; the API layer always binds `user_id` to the verified JWT subject (FR-018-style isolation, mirroring feature 003's strict per-user policy).
- An `in_progress` row whose `last_step_id` points at an archived step is still valid; the resume logic (Decision 7) falls back to the next non-archived step.

---

### 2. `tutorial_step`

Canonical, current-state copy of every tutorial step. Edited by admins through `/api/admin/tutorial/steps` (FR-015). Soft-delete via `archived_at` so revision history (and any in-flight resumes) keep working.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `bigserial` | `PRIMARY KEY` | Stable id; referenced by `onboarding_state.last_step_id` and `tutorial_step_revision.step_id`. |
| `slug` | `text` | `NOT NULL`, `UNIQUE` | Human-readable id used by the frontend to pick a target (e.g., `chat-with-agent`, `open-audit-log`). Stable across copy edits. |
| `audience` | `text` | `NOT NULL`, `CHECK (audience IN ('user','admin'))` | `user` steps go to everyone; `admin` steps are appended only for users with the admin role (Q3, FR-002). |
| `display_order` | `integer` | `NOT NULL` | Ascending order. Admins may renumber via the admin endpoint; gaps are allowed. |
| `target_kind` | `text` | `NOT NULL`, `CHECK (target_kind IN ('static','sdui','none'))` | `static` = anchored to a known frontend element id; `sdui` = anchored to a server-rendered component slug; `none` = no target (introductory/closing step). |
| `target_key` | `text` | `NULL` | When `target_kind='static'`, the catalog key (e.g., `sidebar.audit`). When `target_kind='sdui'`, a component-slug or component-id pattern. `NULL` allowed when `target_kind='none'`. |
| `title` | `text` | `NOT NULL`, length ≤ 120 | Step heading shown in the overlay. |
| `body` | `text` | `NOT NULL`, length ≤ 1000 | Step body copy. Plain text (no HTML); rendered as React text nodes — no `dangerouslySetInnerHTML`. |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | Bumped on every admin edit. |
| `archived_at` | `timestamptz` | `NULL` | Soft-delete marker. Archived steps are not returned to user reads but remain readable via the admin endpoint for history. |

**Indices**:
- `UNIQUE (slug)`
- `(archived_at, audience, display_order)` — supports the user read path (`WHERE archived_at IS NULL AND audience IN (…)` ordered by `display_order`).

**Validation rules**:
- `title` and `body` must be non-empty after trimming.
- `target_kind = 'static'` and `'sdui'` require non-null, non-empty `target_key`.
- `target_kind = 'none'` requires `target_key IS NULL`.

---

### 3. `tutorial_step_revision`

Append-only history of every admin edit to `tutorial_step`. Preserves the *full* before/after content of each edit; the audit log carries only the diff summary (per Decision 5).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `bigserial` | `PRIMARY KEY` | |
| `step_id` | `bigint` | `NOT NULL`, `REFERENCES tutorial_step(id) ON DELETE CASCADE` | The step this revision belongs to. (For deleted-then-purged steps the cascade keeps tables tidy; the audit log retains the historical record independently.) |
| `editor_user_id` | `text` | `NOT NULL` | Keycloak `sub` of the admin who made the edit. |
| `edited_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `previous` | `jsonb` | `NULL` | Snapshot of the step row *before* the edit (NULL only for the initial-creation revision). |
| `current` | `jsonb` | `NOT NULL` | Snapshot of the step row *after* the edit. |
| `change_kind` | `text` | `NOT NULL`, `CHECK (change_kind IN ('create','update','archive','restore'))` | Discriminates lifecycle events on the step. |

**Indices**:
- `(step_id, edited_at DESC)` — supports the admin "view history" view.
- `(editor_user_id, edited_at DESC)` — supports support-user audits.

---

## Component primitive change

`backend/shared/primitives.py` — additive optional field on the base dataclass:

```python
@dataclass
class Component:
    type: str
    id: Optional[str] = None
    style: Dict[str, str] = field(default_factory=dict)
    tooltip: Optional[str] = None   # NEW — shown on hover/focus by the frontend wrapper
```

Because `tooltip` defaults to `None` and is appended after the existing defaulted fields, this change is binary-compatible with every existing serialized payload and every existing subclass (`Container`, `Text`, `Button`, etc.). No subclass needs to redeclare it. `to_json()` will include `"tooltip": null` for emitted components that do not set one — the frontend `Tooltip` wrapper treats `null`/empty-string as "no tooltip" (FR-008).

## Audit-log integration

No schema change to `audit_events`. New event classes recorded through the existing recorder:

| `event_class` | Emitted when | Key payload fields |
|---------------|--------------|--------------------|
| `onboarding_started` | First mutation flips an absent or `not_started` row to `in_progress` | `user_id`, `step_slug` (first step) |
| `onboarding_completed` | Status transitions to `completed` | `user_id`, `last_step_slug`, `duration_seconds` |
| `onboarding_skipped` | Status transitions to `skipped` | `user_id`, `last_step_slug` (where the user was when they skipped) |
| `onboarding_replayed` | Replay endpoint is hit | `user_id`, `prior_status` |
| `tutorial_step_edited` | Admin successfully creates/updates/archives/restores a step | `actor_user_id` (the admin), `step_id`, `step_slug`, `change_kind`, `changed_fields` (list of column names whose values changed) |

All five inherit feature 003's per-user hash-chain and PII-redaction guarantees by virtue of going through the existing recorder.

## Per-user isolation

Mirroring feature 003: REST handlers always derive `user_id` from the validated JWT and never accept a `user_id`/`actor_user_id`/`as_user` query parameter. Cross-user reads return 404 (indistinguishable from "no such row"), not 403, so the existence of another user's onboarding state cannot be inferred. Admin endpoints (`/api/admin/tutorial/steps*`) are gated by Keycloak admin role at the FastAPI dependency layer (Decision 4).
