# Contract: Standardized component action (028 Part B — interaction loop)

## Action kinds (FR-035)

| Kind | Transport | Semantics |
|---|---|---|
| **Deterministic** (`refresh`/`invoke`) | `ui_event {action:'component_action', …}` | Re-executes the component's source capability without LLM involvement; result upserts a workspace component in place. |
| **Intent** | existing client idiom: composed chat message (param_picker precedent) | Enters the conversation as a user message; full Re-Act loop. |

Buttons/primitives declare which kind they emit via their `data-action`/payload (authored by agents through astralprims as today). `component_action` is the single deterministic verb.

## `component_action` (client→server `ui_event`)

```json
{
  "type": "ui_event",
  "action": "component_action",
  "payload": {
    "chat_id": "…",
    "component_id": "wc_ab12…",          // REQUIRED: emitting component (FR-034)
    "kind": "refresh",                    // 'refresh' (re-run source) | 'invoke' (named verb on source tool)
    "params_patch": { "page": 3 },       // optional shallow merge over _source_params
    "target_component_id": "wc_cd34…"    // optional cross-component target (FR-037); default = component_id
  }
}
```

## Server pipeline (orchestrator `handle_ui_message`)

1. **Resolve**: workspace row for `(chat_id, component_id)` scoped to the socket's validated `user_id`. Missing ⇒ chat-target Alert "This component is no longer available." (graceful, FR-037).
2. **Provenance**: `_source_agent`, `_source_tool`, `_source_params` from the stored component dict; effective params = `_source_params ⊕ params_patch` (shallow; `params_patch` keys validated against the tool's schema where available).
3. **Authorize** (FR-036): recompute the CURRENT chat-path effective-tool set for this user/agent — agent scopes (`agent_scopes`), per-tool overrides (`tool_overrides.permission_kind`, 013), security-flag blocks — identical logic to the chat Re-Act path. Not permitted ⇒ chat-target Alert + audit `workspace.action_denied` (event_class `conversation`). No execution.
4. **Timeline guard**: socket in timeline mode ⇒ refuse (`reason:'timeline_readonly'`).
5. **Execute**: `_execute_with_retry(agent, tool, params)` (existing path, delegation token included as for chat-initiated tools).
6. **Apply**: result components upsert into `target_component_id` (or `component_id`); identity preserved — the result inherits the target's `component_id` regardless of new params (this is how "refresh with new filters" updates in place).
7. **Snapshot**: `workspace_snapshot(cause='component_action')` (FR-039).
8. **Broadcast**: `ui_upsert` to all of the user's sockets on this chat (FR-040).
9. **Audit**: `workspace.component_updated` with provenance + actor.

Failures in 5 produce a chat-target error Alert (existing error routing) — the workspace component is left untouched.

## Concurrency

Per-chat serialization: component actions on the same chat queue behind one another (reuse the `_serialized_chat`-style per-key lock). Last completed action wins; no interleaved partial writes (spec edge case).

## Migration of bespoke behaviors (FR-038)

- `table_paginate` → emitted payloads become `component_action {kind:'refresh', params_patch:{page,page_size}}`. The legacy `table_paginate` ui_event action remains as a server-side alias mapping onto the same pipeline (one release), now updating only the table component instead of replacing the canvas.
- `param_picker` → unchanged client-side intent idiom (documented as the canonical Intent kind).
- `color_picker`/`save_theme`, chrome `chrome_*` actions → out of scope; unchanged.

## Rate limiting / abuse

Deterministic actions are user-initiated tool executions: they inherit the same per-user audit trail as chat tool calls. A simple per-socket in-flight cap (1 concurrent deterministic action per chat, queued) bounds rapid-fire clicking; no separate quota system in 028.
