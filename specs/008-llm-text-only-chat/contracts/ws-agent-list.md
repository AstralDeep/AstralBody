# Contract: `agent_list` WebSocket Message (extended)

**Feature**: 008-llm-text-only-chat
**Type**: Backend → Frontend WebSocket message
**Status**: Existing message, additive change

---

## Direction & Triggering

| Sent by | Backend orchestrator |
| Sent to | Connected UI WebSocket client |
| Triggered when | Agent registers, agent disconnects, user permissions change, security flags change. (No new triggers introduced by this feature.) |

The current send sites live around [backend/orchestrator/orchestrator.py:893, 911, 4037](../../../backend/orchestrator/orchestrator.py#L4037).

---

## Existing payload shape (preserved)

```json
{
  "type": "agent_list",
  "agents": [
    {
      "id": "agent-id",
      "name": "Agent Name",
      "description": "...",
      "tools": ["tool_a", "tool_b"],
      "tool_descriptions": {"tool_a": "..."},
      "scopes": {"scope_a": true},
      "tool_scope_map": {"tool_a": "scope_a"},
      "permissions": {"tool_a": true},
      "security_flags": {"tool_a": {"blocked": false}},
      "metadata": {},
      "status": "connected",
      "owner_email": "...",
      "is_public": false
    }
  ]
}
```

(Maps to the `Agent` interface at [frontend/src/hooks/useWebSocket.ts:32-46](../../../frontend/src/hooks/useWebSocket.ts#L32-L46).)

---

## Additive change introduced by this feature

A single boolean field is added at the top level:

```json
{
  "type": "agent_list",
  "tools_available_for_user": true,
  "agents": [ ... ]
}
```

### Field semantics

| Field | Type | Required? | Definition |
|-------|------|-----------|------------|
| `tools_available_for_user` | `boolean` | YES (added unconditionally) | `true` if and only if running the existing per-turn tool resolution loop ([orchestrator.py:1799-1829](../../../backend/orchestrator/orchestrator.py#L1799-L1829)) for the requesting user would yield at least one tool. `false` collapses three reasons: no agents connected, all tools filtered by user permissions, or all tools blocked by security flags. |

### Scope rules

- The flag MUST be computed for the user identified by the receiving WebSocket (`self._get_user_id(websocket)`), not globally.
- The flag MUST exclude any draft-agent scope: it represents what an ordinary, non-draft chat would see right now.
- The backend MUST recompute and re-broadcast `agent_list` (with the refreshed flag) on the same triggers as today — no new triggers required, since every event that changes tool availability already broadcasts `agent_list`.

### Backwards compatibility

- Older frontends that ignore the new field continue to work — the existing `agents` array is unchanged.
- Newer frontends rely on the field but MUST tolerate its absence by falling back to `agents.length > 0` if the field is missing (defensive default for in-flight upgrade scenarios).

---

## Frontend consumption

| Consumer | Behavior |
|----------|----------|
| `useWebSocket.ts` `case "agent_list"` handler | Set both the existing `agents` state AND the new `toolsAvailableForUser` boolean state. |
| `App.tsx` → `DashboardLayout` → `ChatInterface` | Pass `toolsAvailableForUser` down to `ChatInterface`. |
| `TextOnlyBanner.tsx` | Render the banner iff `toolsAvailableForUser === false`. |

---

## Acceptance signals

- A unit test in `backend/tests/test_chat_text_only.py` MUST assert that an `agent_list` payload sent after a user blocks all tool permissions has `tools_available_for_user: false`.
- A frontend test (`TextOnlyBanner.test.tsx`) MUST assert that the banner mounts when the flag is `false` and unmounts when it flips to `true`.
