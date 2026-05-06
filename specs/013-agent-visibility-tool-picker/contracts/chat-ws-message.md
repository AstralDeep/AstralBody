# Contract — Chat WebSocket Message (`chat_message` action)

Updates the existing `ui_event` / `chat_message` WS payload to carry the user's tool-selection narrowing for this query. The orchestrator honors the narrowing on top of existing scope and per-tool-permission filtering.

## Outgoing (frontend → backend)

```json
{
  "type": "ui_event",
  "action": "chat_message",
  "session_id": "<chat_id>",
  "payload": {
    "message": "<full message including any attachment hints>",
    "chat_id": "<chat_id>",
    "display_message": "<human-readable display text>",
    "selected_tools": ["search_web", "read_file"]
  }
}
```

### `selected_tools` semantics

| Sent value | Meaning | Orchestrator behavior |
|---|---|---|
| Field absent | No narrowing — use the agent's full permission-allowed set | Existing behavior (FR-019) |
| `null` | Same as absent | Existing behavior |
| Non-empty array | The agent's tools list is narrowed to the intersection of (this array) ∩ (agent's tools that pass scope + per-tool permission checks) | FR-018 / FR-020 |
| `[]` (empty array) | Should never reach the backend — UI blocks send (FR-021) | Defensive: log at WARN with `reason="empty_selection_received"`; treat as no narrowing for the current request |

The frontend's `useWebSocket.sendMessage` (today at [`frontend/src/hooks/useWebSocket.ts:986-1004`](../../frontend/src/hooks/useWebSocket.ts#L986-L1004)) reads the per-user preference for the active `agent_id` (via `getUserToolSelection(agentId)` — see [api-tool-selection-pref.md](./api-tool-selection-pref.md)) before send. If the saved selection is null, the field is omitted.

## Backend filter chain (orchestrator)

In [`backend/orchestrator/orchestrator.py`](../../backend/orchestrator/orchestrator.py) inside `handle_chat_message` (line ~1756), after the existing tool-collection loop:

```python
# Existing code at ~line 1841
for skill in agent_card.skills:
    if security_flags[agent_id][skill.id].blocked:
        continue
    if not tool_permissions.is_tool_allowed(user_id, agent_id, skill.id):
        logger.debug(f"Tool '{skill.id}' blocked for user={user_id} agent={agent_id} reason=scope_or_override")
        continue

    # NEW — narrow by user's in-chat selection
    if selected_tools is not None and skill.id not in selected_tools:
        logger.debug(
            f"Tool '{skill.id}' excluded for user={user_id} agent={agent_id} "
            f"reason=user_selection"
        )
        continue

    tools_desc.append(build_tool_def(skill))
```

The new filter:

- Only ever **subtracts** from the candidate set; cannot widen.
- Logs with a distinct `reason="user_selection"` to satisfy FR-023.
- Sees `selected_tools=None` for unmodified default behavior; sees a list when narrowing.

## Incoming (backend → frontend)

No structural change. Tool-call deltas and assistant message frames remain identical. The unavailable-agent flow (FR-009) is implemented via existing `chat_status` events plus the new top-of-body banner; it does not require a new WS message type.

## Compatibility

- A backend that receives a `selected_tools` field but is older than this feature MUST ignore unknown payload fields (existing JSON-tolerant parsing pattern). New backend, old frontend continues to behave exactly as today (no `selected_tools` sent → no narrowing).
