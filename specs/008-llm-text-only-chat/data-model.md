# Phase 1 Data Model: LLM Text-Only Chat

**Feature**: 008-llm-text-only-chat
**Date**: 2026-05-01

This feature does NOT introduce or modify any database tables. The relevant entities are conceptual (per-request) and one piece of seed data appended to an existing table.

---

## Conceptual Entities

### Tool Availability State (per chat turn)

Computed at dispatch time inside `handle_chat_message`. Not persisted.

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `agents_connected` | `bool` | derived from `len(self.agents) > 0` | Whether any agent WebSocket is currently registered. |
| `tools_after_user_perms` | `int` | derived from filter loop in [orchestrator.py:1799-1829](../../backend/orchestrator/orchestrator.py#L1799-L1829) | Number of tools that survive the per-user `tool_permissions.is_tool_allowed` filter. |
| `tools_after_security_flags` | `int` | derived from same loop | Number of tools that survive the security-flag filter. |
| `is_text_only` | `bool` | `tools_after_security_flags == 0 and not draft_agent_id` | TRUE → dispatch enters the text-only branch. |
| `tools_available_for_user` | `bool` | inverse of `is_text_only` for non-draft contexts | The flag broadcast on the `agent_list` WebSocket message; drives the frontend banner. |

State transitions: re-evaluated on every chat turn (FR-005). No history; no persistence.

---

### Chat Turn Audit Record (existing table, new feature tag)

Reuses the existing audit table written by `_record_llm_call` in [backend/llm_config/audit_events.py:195](../../backend/llm_config/audit_events.py#L195).

| Field | Type | Existing? | Notes |
|-------|------|-----------|-------|
| `action_type` | string | existing | `llm.call` (unchanged) |
| `feature` | string | existing | NEW VALUE: `"chat_dispatch_text_only"` (alongside existing `"tool_dispatch"`, `"chat_dispatch"`) |
| `inputs_meta.tools_count` | int | existing | Will be `0` for text-only turns. |
| `outcome` | string | existing | `success` / `failure`, same semantics as existing dispatches. |

No schema change. The new `feature` value is just a string slot — no enum, no constraint update needed.

---

### Tutorial Step (existing table, one new row)

Existing table `tutorial_step` (created in feature 005). One new row added via the idempotent seed at [backend/seeds/tutorial_steps_seed.sql](../../backend/seeds/tutorial_steps_seed.sql).

| Field | Value |
|-------|-------|
| `slug` | `enable-agents` |
| `audience` | `user` |
| `display_order` | `35` |
| `target_kind` | `static` |
| `target_key` | `sidebar.agents` (same anchor as `open-agents-panel`; sequential steps can share a target) |
| `title` | `Turn an agent on` |
| `body` | `Open the Agents panel and switch on at least one agent. Until you do, AstralBody talks to the language model in text-only mode — it can chat, but it can't take actions on your behalf.` |

Insertion clause: `ON CONFLICT (slug) DO NOTHING` — preserves admin overrides of the same slug across re-runs.

---

## What is NOT changing

- No new tables.
- No new columns on existing tables.
- No migration is required (Constitution Principle IX gate already passes — see [plan.md](./plan.md#constitution-check)).
- Chat history schema is unchanged. Text-only turns persist via the same `self.history.add_message(chat_id, "user" | "assistant", ...)` calls used today.
- The `agent_list` WebSocket payload is a runtime contract change only (see [contracts/ws-agent-list.md](./contracts/ws-agent-list.md)); no DB column is read or written for the new flag.
