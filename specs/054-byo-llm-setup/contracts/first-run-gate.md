# Contracts: First-Run Gate, Credential Store & Cross-Client Delivery (054)

All deltas ride existing frame types and endpoints. **No new frame types; no
`ui_protocol.json` manifest change; no drift-guard churn** (guards assert frame
type names only — verified against all four client guard suites).

## 1. WebSocket frames

### `chrome_surface` (server → native clients) — additive field VALUE

```jsonc
{
  "type": "chrome_surface",
  "surface_key": "llm",
  "title": "Set up your AI provider",
  "admin_only": false,
  "components": [ /* ROTE-adapted astralprims dicts (ParamPicker form) */ ],
  "mode": "mandatory"        // reserved field, previously always "replace"
}
```

- `mode:"mandatory"` semantics (Windows/Android/iOS/macOS): render the surface
  immediately even though unsolicited; suppress every dismissal affordance
  (close/Escape/back/top-bar navigation) until the server replaces or closes
  the surface. Clients that predate this feature degrade safely: Android/Apple
  show an error banner (existing unsolicited-surface behavior) and the
  server-side gate still refuses everything — no security regression, only UX.
- Watch: never receives `chrome_surface` (unchanged disposition).

### `chrome_render` (server → web) — additive HTML marker

```jsonc
{ "type": "chrome_render", "region": "modal", "html": "<div class=\"astral-modal-card\" data-mandatory=\"1\" ...>" }
```

- The mandatory variant of `render_modal_shell` omits the ✕ button and stamps
  `data-mandatory="1"`; `client.js closeModal()` refuses while present
  (single choke point for ✕/backdrop/Escape).

### `llm_config_set` / `llm_config_clear` / `llm_config_ack` (client ↔ server)

Wire shape unchanged. Semantics change server-side only:

- `llm_config_set {config:{api_key, base_url, model, provider?}}` → validates,
  **re-runs the connection probe server-side**, persists to `user_llm_config`
  (Fernet), invalidates the gate cache, acks `llm_config_ack {ok:true}`.
  Probe failure ⇒ `{type:"error", code:"llm_config_invalid",
  detail:{error_class}}` and nothing stored. New optional `provider` field is
  additive (defaults to `"custom"` for old clients).
- `llm_config_clear` → deletes the row, audits, immediately re-gates: the
  server pushes the mandatory dialog to all of the user's sockets.
- `register_ui.llm_config` seeding: retired (vestigial; server storage is
  authoritative). Field remains accepted-and-ignored for wire compatibility.

### Gate transitions (server → all of the user's sockets)

- On save success: web sockets receive the modal-close `chrome_render`
  (existing empty/close instruction) followed by the welcome `ui_render`;
  native sockets receive `chrome_surface {surface_key:"llm", mode:"replace",
  components:[]}` (existing close instruction) followed by welcome.
- On clear: the reverse — mandatory dialog pushed everywhere.

## 2. Chrome actions (`ui_event` → `chrome_events` dispatch)

| Action | Change |
|---|---|
| `chrome_open` | While unconfigured: any `surface != "llm"` is rewritten to `"llm"` (audited `llm_unconfigured{feature:"chrome_open"}`) |
| `chrome_close` | While unconfigured: refused (no-op + audit) |
| `chrome_llm_models` / `chrome_llm_test` / `chrome_llm_save` / `chrome_llm_clear` | Unchanged action names; save/clear now persist via the store; the surface composition adds the provider dropdown (existing ParamPicker option vocabulary — no new manifest `accept_actions`) |
| `chrome_llm_sys_models` / `chrome_llm_sys_test` / `chrome_llm_sys_save` / `chrome_llm_sys_clear` | NEW handlers on the NEW `llm_system` surface (admin role enforced server-side per handler). Surface handlers are registered the existing way (`HANDLERS` dict); native menus receive the item only for admins via the server-owned menu model |

## 3. REST

| Endpoint | Change |
|---|---|
| `POST /api/llm/test` | Unchanged contract (creds in body, never persisted, always 200 with `{ok, error_class, ...}`). Used by the dialog on all clients. |
| `POST /api/llm/list-models` | Unchanged. |
| `GET /api/chrome/menu` | Unchanged shape; admins additionally see the `llm_system` item (server-owned model). |

Both `/api/llm/*` endpoints remain reachable while gated (they are the setup
path); every other LLM-dependent verb refuses with the audited
`llm_unconfigured` condition while the caller is unconfigured.

## 4. Server-side resolution contract

```
resolve(websocket):
  user socket        -> user_llm_config[sub]      | LLMUnavailable (gate)
  None / VirtualWS   -> system_llm_config         | LLMUnavailable (honest skip/fail)
never: user->system fallback, system->user fallback, cross-user access
audit:  credential_source ∈ {"user", "system"}   (operator_default retired for new rows)
```

## 5. Provider catalog (server-owned)

`GET`-less: the catalog is embedded in the surface composition (web `<select>`
options / SDUI picker options) from `llm_config/providers.py`. Preset keys:
`openai, anthropic, gemini, xai, openrouter, groq, together, mistral, ollama,
lmstudio, custom`. Selecting a preset prefills `base_url` (editable only for
`custom`); `key_required=False` presets (ollama, lmstudio) permit empty key.

## 6. Audit events

| Event | Delta |
|---|---|
| `llm_config_change` | actions gain `scope:"user"|"system"`; new action `discarded_undecryptable`; key-substring assertion unchanged |
| `llm_unconfigured` | unchanged shape; new `feature` values (`chrome_open`, `register_gate`, `scheduled_job`, ...) |
| `llm_call` | `credential_source` gains `system`; `operator_default` retired for new rows |
