# Contract: Agentic Creation (027)

## Meta-tool injection

When `flags.is_enabled("agentic_creation")` AND the turn is not a draft-test session
(`draft_agent_id is None`), the tools_desc build appends two orchestrator-internal tools.
`tool_to_agent[name] = "__orchestrator__"`; both dispatch paths intercept that pseudo-agent id
**before** the agent-existence gate and route to `agentic_creation.handle_meta_tool(...)`.

### `create_capability`
```json
{
  "name": "create_capability",
  "description": "Create a new agent with the tools needed to serve the user's request when NO available tool can. Do NOT call this when an existing tool is merely disabled or unauthorized — tell the user and point them at Settings → Agents & permissions instead.",
  "parameters": {
    "type": "object",
    "properties": {
      "agent_name":  {"type": "string", "description": "Short human name for the new agent"},
      "description": {"type": "string", "description": "What the agent does, in plain language"},
      "tools_spec":  {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name", "description"]},
        "description": "1-4 tools the agent needs"}
    },
    "required": ["agent_name", "description", "tools_spec"]
  }
}
```

### `extend_agent`
```json
{
  "name": "extend_agent",
  "description": "Add or change a tool on a live agent the user OWNS. Prepares a draft revision; nothing changes on the live agent until the user approves and security checks pass.",
  "parameters": {
    "type": "object",
    "properties": {
      "agent_id":    {"type": "string", "description": "Live agent id to extend (must be owned by the user)"},
      "instruction": {"type": "string", "description": "What to add/change, in plain language"}
    },
    "required": ["agent_id", "instruction"]
  }
}
```

System-prompt addendum (injected with the meta-tools): when no offered tool fits, prefer
`create_capability`; if `disabled_tools_hint` (computed by the existing diagnostic gate) lists a
matching disabled/unauthorized tool, answer with that pointer instead (FR-008).

## Handler behavior (`agentic_creation.py`)

### `create_capability` execution
1. **Fingerprint** = sha256 of normalized `agent_name` + sorted tool names → `gap_fingerprint`.
2. **Dedup (FR-007)**: existing non-terminal draft for `(user_id, source_chat_id, fingerprint)`
   → return a card pointing at the existing draft; no new creation.
3. Audit `lifecycle.gap_detected` (in_progress, new correlation_id).
4. `db.create_draft_agent(origin='auto_chat', source_chat_id, gap_fingerprint, ...)` →
   `lifecycle.generate_code(draft_id)` (existing pipeline incl. security analyzer + validator).
5. `lifecycle.start_draft_agent(draft_id)`.
6. **Self-test**: submit `handle_chat_message(vws, <original user request>, test_chat_id,
   draft_agent_id=draft_id)` on a `VirtualWebSocket` via `BackgroundTaskManager`; hard timeout
   (default 120 s); on failure, at most ONE auto-refine (`refine_agent` with the failure summary)
   + retest (A11 bound). Persist outcome to `draft_agents.self_test`.
7. Audit `lifecycle.auto_created` + `lifecycle.self_test` (same correlation_id).
8. **Return** an MCPResponse whose `_ui_components` is the creation card (astralprims primitives):
   name, description, self-test outcome (+ result preview), and buttons
   `draft_approve {draft_id}` / `draft_refine {draft_id}` / `draft_discard {draft_id}`.
   The card renders into chat via the normal tool-result path; turn ends normally.

### `extend_agent` execution
1. Ownership check (`agent_ownership.owner_email == user`); not owned → error result telling the
   user why (never silent).
2. Dedup as above (fingerprint over agent_id + instruction).
3. Clone live agent dir → `agents/{slug}__rev{n}/`; create draft row `origin='revision'`,
   `revises_agent_id`; `refine_tools_file(clone, instruction)`; gates; start clone; self-test the
   clone with the user's request.
4. Card buttons: `revision_apply {draft_id}` / `draft_refine {draft_id}` / `revision_discard {draft_id}`.

### Decision actions (handled via chrome_events dispatcher; usable from chat cards and the Drafts surface)
| action | behavior |
|---|---|
| `draft_approve {draft_id}` | existing `approve_agent` (security gate → live, or rejected-with-failures card); success card confirms immediate usability; audit `lifecycle.approved`/`lifecycle.rejected` |
| `draft_refine {draft_id, message?}` | existing `refine_agent`; without `message`, renders a refine input card |
| `draft_discard {draft_id}` | existing `delete_draft`; audit `lifecycle.discarded` (FR-002 decline) |
| `revision_apply {draft_id}` | **apply_revision**: stop live → backup `mcp_tools.py` → install revised file → security analyzer + compile + validator on live dir → restart. Pass: delete clone+row, audit `lifecycle.revision_applied`. Fail: restore backup, restart original, draft stays rejected-editable, audit `lifecycle.revision_rolled_back` (FR-006 rollback safety) |
| `revision_discard {draft_id}` | delete clone + row; audit `lifecycle.discarded` |

All actions verify the acting user owns the draft. Every event carries the gap's correlation_id.

## Bounds & failure contract

- Per-conversation: max one non-terminal auto-draft per fingerprint (dedup); self-test ≤ 120 s
  + ≤ 1 auto-refine. Generation failure → recoverable error card (retry / edit description /
  abandon) per 012 FR-005.
- Meta-tool results NEVER bypass scope/permission/credential gates: the draft test path already
  enforces owner-only access; promotion uses existing ownership + scopes-default-off rules
  (FR-010), with private visibility.
- `agentic_creation` flag off → tools not injected; everything else (chrome) unaffected.
