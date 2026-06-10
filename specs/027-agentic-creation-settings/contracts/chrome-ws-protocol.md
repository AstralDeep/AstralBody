# Contract: Chrome WS Protocol (027)

Additive to the 026 protocol. `ui_render` / `ui_update` / `ui_append` / `ui_stream_data`
(components **and** html — FR-018) are untouched.

## Server → client

### `chrome_render`
```json
{ "type": "chrome_render", "region": "modal" | "topbar", "html": "<...>", "mode": "replace" }
```
- `region: "modal"` — client sets `#astral-modal` innerHTML (replace only in 027; `mode` reserved).
  Empty `html` clears the modal (equivalent to close).
- `region: "topbar"` — re-render of `#astral-topbar` (used after role/availability changes; rare).
- HTML is trusted server-rendered chrome output (escape-by-default applied server-side at every
  text interpolation via `esc()`); client inserts verbatim and runs `processSideEffects` (Plotly,
  theme banners) on the inserted subtree.

### Existing messages reused
- `user_preferences` (connect-time theme), `chat_status`, `ui_render(target="chat")` for
  creation-flow cards, `audit_append` (live audit surface refresh hint).

## Client → server (`ui_event` envelope, unchanged shape)

```json
{ "type": "ui_event", "action": "<action>", "payload": { ... }, "session_id": "<chat id|undefined>" }
```

### Navigation
| action | payload | server behavior |
|---|---|---|
| `chrome_open` | `{surface, params?}` | render surface → `chrome_render {region:"modal"}`; unknown surface → error notice modal (never silent) |
| `chrome_close` | `{}` | `chrome_render {region:"modal", html:""}` (client may also close locally; server message is authoritative no-op) |

`surface` ∈ `agents | drafts | llm | personalization | audit | theme | tour | guide |
admin_tools` (+ `params` e.g. `{agent_id}` for the permissions detail, `{tab}` for
personalization, `{cursor}` for audit paging).

### Generic client delegation
Any element with `data-ui-action="<action>"` (+ optional `data-ui-payload='<json>'`) sends the
corresponding `ui_event` on click — single document-level delegated listener. Existing
`.astral-action`, param-picker, pagination, color-picker, upload handlers remain.

Inputs inside a chrome form are collected by the nearest `[data-ui-form]` container when a
`data-ui-action` button with `data-ui-collect="true"` is clicked: payload gains
`{fields: {name: value}}` from `input/select/textarea[name]` descendants (checkbox → bool).

### Keyboard / a11y (client-local, FR-017)
- Settings trigger: `aria-haspopup="menu"`, `aria-expanded`; Enter/Space opens; ArrowUp/Down
  navigate `role="menuitem"`s; Home/End jump; Escape closes and restores focus; outside click closes.
- Modal: Escape and backdrop click close (sends `chrome_close`); focus moves into the modal on
  open and returns to the trigger on close.

## Failure contract

- Handler exceptions render an in-modal error notice (`chrome_error` block with a retry of the
  same `chrome_open`) and structured-log (`logger.exception`, Constitution X). Never a silent drop.
- Unknown `chrome_*`/creation action: explicit error notice modal + warning log (the legacy
  if/elif silently fell through; the 027 dispatcher must not).
