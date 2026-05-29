# Contract: WebSocket UI Protocol (preserved, extended with `html`)

Endpoint: `ws://<host>:8001/ws` (FastAPI, `@app.websocket("/ws")`). Message types are defined in
`backend/shared/protocol.py` and are **preserved**. The only additive change: server→client render messages
may carry a rendered `html` field alongside the structured `components` dicts.

## Client → Server

### `register_ui` (on connect; re-sent on viewport/capability change)
```jsonc
{
  "type": "register_ui",
  "capabilities": ["charts","tables", ...],
  "session_id": "<auth session>",          // optional
  "token": "<JWT bearer>",                  // optional; from server-side OIDC session
  "device": {                                // drives ROTE DeviceProfile
    "device_type": "browser|tablet|mobile|watch|tv|voice",
    "viewport_width": 1920, "viewport_height": 1080,
    "has_touch": false, "connection_type": "wifi", "user_agent": "..."
  },
  "llm_config": { ... },                     // optional
  "resumed": false                            // feature 016 silent-resume flag
}
```
**Server behavior**: `ROTE.register_device(ws, device)`; auth via `token`/`session_id`; reply may include the
derived device profile. Client MUST send this before expecting renders.

### User actions (unchanged message types)
Button/form/pagination/upload/theme interactions post the existing action/`chat` messages with
`action` + `payload` (e.g., a `Button`'s `action`/`payload`, a `ParamPicker` submit interpolated via
`submit_message_template`, a `Table` page request using `source_tool`/`source_agent`/`source_params`).

## Server → Client

### `ui_render` (full render into a target region)
```jsonc
{
  "type": "ui_render",
  "components": [ <astralprims dict>, ... ],  // structured form — ROTE-adapted (FR-018 preserved)
  "html": "<section>…rendered fragment…</section>", // NEW — escaped-by-default HTML for the web client
  "target": "canvas" | "chat"
}
```
Produced by `Orchestrator.send_ui_render(ws, components, target)` → `ROTE.adapt` → `webrender.render`.

### `ui_update` / `ui_append`
Same shape as `ui_render` (replace / append). Carry both `components` and `html`.

### `ui_stream_data` / `tool_stream_end` / `tool_stream_cancel` (streaming)
```jsonc
{
  "type": "ui_stream_data",
  "request_id": "...", "stream_id": "...", "agent_id": "...", "tool_name": "...",
  "seq": 3, "terminal": false,
  "components": [ <dict>, ... ],
  "html": "<...fragment...>",                 // NEW
  "error": null
}
```
**Client behavior**: merge by `stream_id` (and `seq`/component index) into the existing DOM region without a
full-page reload (SC-007). `terminal: true` / `tool_stream_end` finalizes the stream.

### Other preserved messages (unchanged)
`chat_step`, `tool_progress`, `chat_status`, `user_message_acked`, `audit_append`,
`llm_config_*`, `llm_usage_report`, `agent_creation_progress`, history/feedback messages.

## Compatibility rules
- A consumer that ignores `html` and reads only `components` still works (programmatic/non-web — FR-018).
- The web `client.js` prefers `html`; if absent, it may request/await a render. ROTE adaptation happens
  **before** rendering, so `components` and `html` always describe the same device-adapted tree.
