# Phase 0 — Research: Agent Visibility, Active-Agent Clarity, Per-Tool Permissions, In-Chat Tool Picker

This document captures the load-bearing technical choices behind the implementation plan. Every NEEDS CLARIFICATION marker that the plan template would have raised is resolved here.

---

## R1. Storage shape for per-tool permissions

**Decision**: Reuse the existing `tool_overrides` table by adding a `permission_kind TEXT NULL` column and changing the unique key from `(user_id, agent_id, tool_name)` to `(user_id, agent_id, tool_name, COALESCE(permission_kind, ''))`. A row with `permission_kind = NULL` continues to mean "tool-wide override" (legacy). A row with `permission_kind = 'tools:read' | 'tools:write' | 'tools:search' | 'tools:system'` means "this specific tool/permission pair is on/off for this user."

**Rationale**:

- Avoids a new table — schema delta is minimal (one column + index update) which keeps the migration short and the data model coherent with what already ships.
- `tool_overrides` is already plumbed through `is_tool_allowed` ([backend/orchestrator/tool_permissions.py:207-224](../../backend/orchestrator/tool_permissions.py#L207-L224)); extending it is one local change rather than wiring a new table through the orchestrator path.
- Constitution V (no new third-party libs) and IX (auto migrations) are both satisfied with a tiny ALTER + idempotent backfill.

**Alternatives considered**:

- **New table `tool_permissions(user_id, agent_id, tool_name, permission_kind, enabled)`**: cleaner schema, but doubles the surface area in `tool_permissions.py` and creates a synchronization concern between two stores. Rejected — the `tool_overrides` table is already exactly the right shape minus one column.
- **JSON blob on `agent_ownership`**: violates the existing pattern of typed permission rows; harder to query for "which users have write enabled on tool X." Rejected.

**Backfill strategy**: On first run of the migration, for every `(user_id, agent_id, scope)` row in `agent_scopes` with `enabled=true`, insert one `tool_overrides` row per tool whose required scope equals that scope, with `permission_kind=scope` and `enabled=true`. The migration is idempotent — guarded by a `WHERE NOT EXISTS` clause keyed on `(user_id, agent_id, tool_name, permission_kind)`. `agent_scopes` is not dropped; it remains as a fallback for tools whose required scope is enabled but no per-tool row was written yet (e.g., new tools added after migration).

---

## R2. Where to store the in-chat tool selection (per-user global preference)

**Decision**: Store under the existing `user_preferences` JSON blob (`backend/shared/database.py` — `get_user_preferences` / `set_user_preferences`) under a key shaped like:

```json
{
  "tool_selection": {
    "<agent_id>": ["tool_name_a", "tool_name_b"]
  }
}
```

**Rationale**:

- The clarification (Q5) is "per-user global, with reset" — but tool sets differ by agent, so the saved selection has to be keyed by agent for the data to be meaningful. Storing it as a per-agent map under one user-level preference key keeps it a single round-trip read/write.
- `user_preferences` already exists with read/write helpers, so no new table or migration is required for this story.
- "Reset to default" simply deletes the key for that agent (or sets it to `null`), and the orchestrator's default branch (FR-019) takes over.

**Alternatives considered**:

- **New table `user_tool_selection(user_id, agent_id, tool_name)`**: Cleaner relational shape but adds a migration and a new query path for what is effectively a small JSON-shaped preference. Rejected per Constitution IX preference for minimal schema deltas where existing storage works.
- **Per-chat-session storage**: the user explicitly chose D over A in clarification Q5 — selection is a user pref, not a chat property. Rejected by spec.

---

## R3. Linking a chat session to an agent (Story 2 + clarification Q3)

**Decision**: Add `agent_id TEXT NULL` to the existing `chats` table. Populate it on chat creation; read it for the active-agent header and the unavailable-agent banner.

**Rationale**:

- The exploration showed that today the `chats` table has only `(id, user_id, title, created_at, updated_at)` — no agent linkage. Story 2 needs the active agent name to render in the header before the user types, and Q3 needs to detect when that agent has gone away. The cleanest way is a column.
- `NULL`-able preserves backward compatibility for any chat created before the migration; the frontend renders an "Unknown agent" / "Pick an agent" state if the column is null on old rows.
- Migration is one ALTER; no rewrite of existing rows is required.

**Alternatives considered**:

- **Derive agent from message metadata** (look at the most recent assistant message and infer): brittle when messages are deleted or when no message has been sent yet (FR-006 requires the indicator before the first message). Rejected.
- **Map (user, chat) → agent in `user_preferences`**: stretches `user_preferences` beyond its purpose (preferences vs. chat-state). Rejected.

---

## R4. Active-agent indicator placement and unavailable-banner UX

**Decision**: The active-agent indicator lives in the existing chat panel header at [`FloatingChatPanel.tsx:569-588`](../../frontend/src/components/FloatingChatPanel.tsx#L569-L588) — same row as the title and status text. Use the existing `Bot` lucide icon already used in message bubbles (line 611-615) to keep visual language consistent. The unavailable-agent banner uses the same visual treatment as `TextOnlyBanner` ([`frontend/src/components/TextOnlyBanner.tsx`](../../frontend/src/components/TextOnlyBanner.tsx)) — a top-of-body banner above the message list — so the user has a single, familiar place to look for chat-level system notices.

**Rationale**:

- Reuses existing primitives (Constitution VIII).
- Keeps the chat header from growing — agent name slots into space that today shows only the title.
- TextOnlyBanner already handles the "agent disabled / chat constrained" UX pattern; the unavailable-agent case is a sibling of it.

**Alternatives considered**:

- **Floating chip near the composer**: more eye-catching but adds clutter near the message-input area where users are already focused on typing. Rejected.
- **Per-message agent name on every bubble**: helpful for multi-agent timelines but excessive in a single-agent chat (the common case). Adopted as a complement (FR-007) rather than the primary indicator.

---

## R5. In-chat tool picker placement

**Decision**: A small icon button inserted into the composer's right-side button cluster (between the existing voice-input button and the send button at [`FloatingChatPanel.tsx:741-764`](../../frontend/src/components/FloatingChatPanel.tsx#L741-L764)). Clicking opens a popover anchored to the button containing a checkbox list of the agent's permission-allowed tools, the (i) info per tool, and a "Reset to default" link at the bottom.

**Rationale**:

- The composer button cluster is the existing home of context-of-this-message affordances (file upload, voice input, TTS toggle). The tool picker is the same flavor of "what should this message do?" affordance.
- A popover is collapsible, so it does not consume vertical chat space when not in use — relevant for SC-007 (no regression in time-to-send).
- "Reset to default" inside the popover keeps the action proximate to the selection it modifies.

**Alternatives considered**:

- **Always-visible chip row above composer**: increases discoverability but adds permanent vertical space and is noisy when the user does not want to narrow. Rejected.
- **Sidebar drawer**: heavy interaction for what should be a per-message choice. Rejected.

---

## R6. Where the user-selected tool list joins the orchestrator filter chain

**Decision**: Inject the user's selected-tool subset at [`backend/orchestrator/orchestrator.py:1841`](../../backend/orchestrator/orchestrator.py#L1841) — immediately after the existing `is_tool_allowed(...)` check inside the tool-collection loop. If the selection is non-empty, a tool that passes scope+per-tool-permission checks but is not in the selection is excluded from the `tools_desc` list passed to the LLM. If the selection is empty (user has not narrowed for this agent), the existing default behavior runs unchanged (FR-019).

**Rationale**:

- Keeps selection strictly narrowing — selection cannot widen what scope/permission allow because it is applied **after** the existing filters. Satisfies FR-020 and the security posture in Constitution VII (RFC 8693 attenuated scopes are not bypassed; the new filter is purely subtractive).
- Single-line addition in the hottest path of chat dispatch keeps the diff small and the perf impact bounded.
- The existing log line at [`orchestrator.py:1842`](../../backend/orchestrator/orchestrator.py#L1842) is extended with a structured `reason="user_selection"` field for FR-023.

**Alternatives considered**:

- **Filter at the WebSocket boundary**: too coarse — a malformed payload could flow into the LLM. Filtering inside the orchestrator next to scope-check keeps all narrowing logic in one auditable place.
- **Pass selection to the LLM and ask it to ignore non-selected tools**: violates the "100% correctness" target in SC-005 and Constitution VII; we cannot rely on the LLM to enforce permissions.

---

## R7. Migration safety for tool_overrides schema change

**Decision**: The migration script:

1. Adds `permission_kind TEXT NULL` to `tool_overrides`.
2. Drops the existing UNIQUE on `(user_id, agent_id, tool_name)` and replaces it with UNIQUE on `(user_id, agent_id, tool_name, COALESCE(permission_kind, ''))`. The COALESCE preserves the legacy "tool-wide" semantics for existing rows.
3. Backfills per-tool permission rows from `agent_scopes` (R1) — idempotent via `INSERT ... WHERE NOT EXISTS`.
4. Adds `agent_id TEXT NULL` to `chats`.
5. Records a marker row (e.g., in a `migrations_applied` table or by adding the migration filename to the existing tracking mechanism) so reruns are skipped at the SQL level too.

Down path: drop the new column and revert the unique key. The pre-migration `agent_scopes` data is preserved untouched, so falling back to scope-only enforcement works.

**Rationale**:

- Constitution IX: idempotent, auto-running, with a documented rollback. Tested against a representative dataset in staging before merge per Constitution X.

**Alternatives considered**:

- **Non-idempotent backfill** (just INSERT): risks duplicate rows on rerun. Rejected — Constitution IX requires idempotence.

---

## Out-of-scope research (intentionally deferred)

- **Per-tool i18n of the (i) info text**: existing copy is in English; localization is a separate, broader initiative.
- **Bulk select / search inside the per-tool permissions panel**: only required for agents with very many tools (Edge Case "Long tool names or many tools"). Will be added if usage data shows the panel is unwieldy; not blocking for the current four-permission set.
- **Real-time push of "agent unavailable" state**: today the frontend will detect unavailability on its next agents-list refresh. A WS push for agent state changes is a separate concern with its own observability story.

---

## Summary

No `NEEDS CLARIFICATION` markers remain. All seven decisions above are recorded with their rationale and rejected alternatives, and each maps to a concrete code path called out in [plan.md](./plan.md).
