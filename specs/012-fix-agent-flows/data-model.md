# Phase 1 Data Model: Fix Agent Creation, Test, and Management Flows

**Feature**: 012-fix-agent-flows
**Date**: 2026-05-01

This feature introduces no new tables, columns, indexes, or enums. The data model below documents the **existing** entities the fixes rely on, so reviewers can verify each functional requirement maps to existing schema and so future changes don't violate the lifecycle assumptions.

## Entities

### Draft Agent

**Storage**: Existing `draft_agents` table — see [`backend/shared/database.py:217–238`](../../backend/shared/database.py#L217-L238).

| Field | Used by | Notes |
|---|---|---|
| `id` (TEXT, PK) | All FRs | Stable identifier; survives draft → live promotion. |
| `user_id` (TEXT) | FR-006, FR-016, FR-017 | Owner; used for visibility filtering and delete authorization. |
| `agent_name` (TEXT) | FR-002 | Displayed on Test screen and in drafts list. |
| `agent_slug` (TEXT) | FR-003, FR-004 | Used to derive `draft_agent_id` sent on the test WebSocket. |
| `description` (TEXT) | UI display | — |
| `tools_spec`, `skill_tags`, `packages` (TEXT, JSON) | Generation input | Not changed by this feature. |
| `status` (TEXT) | FR-001, FR-008, FR-010, FR-010a | See *Status transitions* below. |
| `generation_log`, `security_report`, `validation_report` (TEXT, JSON) | FR-005, FR-010 | Surfaced to the user on rejection or generation error. |
| `error_message` (TEXT) | FR-005 | User-facing failure reason. |
| `port` (INTEGER) | FR-003, FR-004 | Allocated by `start_draft_agent`; freed on stop. |
| `required_credentials` (TEXT, JSON) | FR-006a, FR-006b | Surfaced on the Test screen so the user knows what's missing. |
| `created_at`, `updated_at` (BIGINT) | UI ordering | — |

### Live Agent

**Storage**: In-memory only — `orchestrator.agent_cards: dict[str, AgentCard]` ([`orchestrator.py:111`](../../backend/orchestrator/orchestrator.py#L111)). The originating `draft_agents` row is preserved with `status='live'`; no separate "live agents" table exists.

| Field | Source | Notes |
|---|---|---|
| `agent_id` | Same as `draft_agents.id` | Identity is preserved across promotion (FR-009). |
| `card` (AgentCard) | Built by orchestrator on registration | Carries the agent's tools and metadata for routing. |

### Agent Ownership

**Storage**: Existing `agent_ownership` table — see [`backend/shared/database.py:154–161`](../../backend/shared/database.py#L154-L161). Touched by `set_agent_ownership` ([`database.py:551`](../../backend/shared/database.py#L551)).

| Field | Used by | Notes |
|---|---|---|
| `agent_id` (TEXT) | FR-008, FR-009, FR-015 | Same identity as Draft Agent / Live Agent. |
| `owner_email` (TEXT) | FR-008 | Visibility filter for the user's live agents list. |
| `is_public` (BOOLEAN) | Existing | Not changed by this feature. |

This feature **re-asserts** the ownership row inside `approve_agent` so promotion never leaves an agent without ownership. (See research.md R3.)

### Permission Scope

**Storage**: Existing `agent_scopes` table; semantics owned by RFC 8693 token exchange — see Constitution Principle VII.

This feature does **not** modify the scope model. The Permissions modal fix (Story 4) is purely a frontend mount/dismount fix; the data model is untouched.

### Agent Credential

**Storage**: Existing per-user, per-agent credential storage (whatever path `onFetchAgentCredentials` already uses).

This feature does **not** modify how credentials are stored or fetched. The Test screen surfaces the existing `required_credentials` list and links into the existing Permissions screen for entry (FR-006b).

---

## Status transitions (Draft Agent lifecycle)

The `status` column is the single source of truth for where a draft sits in the lifecycle. This feature enforces the following transitions; everything else is a bug.

```
                       ┌───────────┐
   create draft ──────▶│  pending  │
                       └─────┬─────┘
                             │ generate_agent (LLM job)
                             ▼
                       ┌───────────┐
                       │ generating│
                       └─────┬─────┘
              ┌──────────────┴──────────────┐
              │ success                    │ failure
              ▼                            ▼
        ┌──────────┐                  ┌────────┐
        │ generated│                  │ error  │
        └─────┬────┘                  └────────┘
              │ user opens Step 4 + WS connects (FR-001, FR-003)
              ▼
        ┌──────────┐
        │ testing  │  ◀──┐  user keeps testing (FR-004)
        └─────┬────┘     │
              │ user approves (FR-007)
              ▼          │
        ┌──────────┐     │
        │ analyzing│     │  ──── security checks running ────
        └─────┬────┘     │
              │          │
       ┌──────┴───────┐  │
       │ pass         │ fail
       ▼              ▼  │
  ┌────────┐    ┌──────────┐
  │  live  │    │ rejected │ ──▶ user refines (FR-010a) ──▶ generating
  └────────┘    └──────────┘
       │
       │ owner deletes (FR-017)
       ▼
   row removed
```

### Allowed source/target pairs

| From | Valid next states |
|---|---|
| `pending` | `generating` |
| `generating` | `generated`, `error` |
| `generated` | `testing` (on first WS open), `analyzing` (if user approves without testing), row removed (FR-017) |
| `testing` | `testing` (more turns), `analyzing` (on approve), `generated` (on idle wind-down), row removed (FR-017) |
| `analyzing` | `live`, `rejected` |
| `rejected` | `generating` (on refine + re-approve), row removed (FR-017) |
| `error` | `generating` (on retry), row removed (FR-017) |
| `live` | terminal for the draft lifecycle (live agent management takes over) |

States explicitly **not** used by this feature: `pending_review`, `approved`. The clarification ruled out a human-in-the-loop review step; existing rows in `pending_review`/`approved` (if any) are out of scope here and continue to behave as the current code does.

### Invariants

- **Identity preserved**: `draft_agents.id` is the same value as `agent_cards[agent_id].id` after promotion (FR-009).
- **Ownership preserved**: An `agent_ownership` row exists for every `agent_id` in `agent_cards`. `approve_agent` re-asserts it on promotion. `delete_draft` removes both rows together.
- **No duplicate live**: `approve_agent` is a no-op when `agent_id` is already in `agent_cards` and `status='live'` (FR-011).
- **Idle wind-down doesn't lose the row**: A draft whose subprocess wound down stays in `draft_agents` with the same `id`; the row is only removed by explicit user delete (FR-016).

---

## Validation rules added by this feature

These are enforced at the application layer; no DB-level constraints change.

| Rule | Where enforced | FR |
|---|---|---|
| User may only delete their own drafts. | `delete_draft` route in `api.py` (existing check; verified, not changed). | FR-017 |
| Approve is rejected if status is not in {`generated`, `testing`}. | `approve_agent` precondition check. | FR-010, FR-011 |
| `start_draft_agent` failure surfaces as a typed error to the WS client. | New error event in test-WS protocol (see contracts/websocket-events.md). | FR-005 |
| Live promotion broadcasts `agent_list` over the owner's WS. | `approve_agent` → orchestrator broadcast. | FR-009, SC-003 |
