# Contract: Chrome Menu Delivery & SDUI Surfaces

Single source of truth: `backend/webrender/chrome/menu_model.py::build_menu_model(roles, *, pulse_enabled) -> ChromeModel`. The web renderer, the WS frame, and the REST endpoint all serialize the **same** model.

## 1. `GET /api/chrome/menu`

Role-aware fetch of the caller's chrome model. Bearer-JWT authenticated (same auth as `GET /api/audit`).

**Response 200** (`application/json`):
```json
{
  "version": 1,
  "topbar": [
    {"key": "brand", "kind": "brand"},
    {"key": "status", "kind": "status"},
    {"key": "timeline", "kind": "action", "label": "Workspace timeline", "icon": "history",
     "action": {"surface": "workspace_timeline", "params": {}}},
    {"key": "settings", "kind": "menu", "label": "Settings", "icon": "gear"}
  ],
  "menu": [
    {"key": "account", "label": "Account", "admin_only": false, "items": [
      {"key": "agents", "label": "Agents & permissions", "surface": "agents", "params": {}, "admin_only": false},
      {"key": "llm", "label": "LLM settings", "surface": "llm", "params": {}, "admin_only": false},
      {"key": "personalization", "label": "Personalization", "surface": "personalization", "params": {}, "admin_only": false},
      {"key": "audit", "label": "Audit log", "surface": "audit", "params": {}, "admin_only": false},
      {"key": "theme", "label": "Theme", "surface": "theme", "params": {}, "admin_only": false}
    ]},
    {"key": "help", "label": "Help", "admin_only": false, "items": [
      {"key": "tour", "label": "Take the tour", "surface": "tour", "params": {}, "admin_only": false},
      {"key": "guide", "label": "User guide", "surface": "guide", "params": {}, "admin_only": false}
    ]}
  ],
  "signout": {"key": "signout", "label": "Sign out", "style": "danger", "action": "logout"}
}
```

- For an **admin** caller, `menu` additionally includes the `admin` group:
  ```json
  {"key": "admin", "label": "Admin tools", "admin_only": true, "items": [
    {"key": "tool-quality", "label": "Tool quality", "surface": "admin_tools", "params": {"tab": "quality"}, "admin_only": true},
    {"key": "tutorial-admin", "label": "Tutorial admin", "surface": "admin_tools", "params": {"tab": "tutorial"}, "admin_only": true}
  ]}
  ```
- When `FF_PULSE_DIGEST` is enabled, a `{"key":"pulse","kind":"action","label":"Pulse digest","icon":"sparkle","action":{"surface":"pulse","params":{}}}` control is inserted **before** `timeline`.
- **401** when unauthenticated. The endpoint never returns admin items to a non-admin.

## 2. WS frame `chrome_menu` (server → client)

Pushed to native clients immediately after the `register_ui` acknowledgment, and re-pushed on role/flag change.

```json
{"type": "chrome_menu", "model": { /* identical ChromeModel.to_dict() as above */ }}
```

Clients replace their rendered chrome from `model` verbatim. Web clients do **not** need this frame (their shell is server-rendered from the same builder) but MUST ignore it if received.

## 3. Opening a surface — `chrome_open` (client → server), existing action

Unchanged request shape (already implemented):
```json
{"type": "ui_event", "action": "chrome_open", "payload": {"surface": "<key>", "params": { }}}
```

**Response depends on the connecting device target:**

- **Web (`browser`)** → existing `chrome_render` HTML modal:
  ```json
  {"type": "chrome_render", "region": "modal", "html": "<...>"}
  ```
- **Native SDUI (`windows`, `android`)** → new `chrome_surface` components frame:
  ```json
  {"type": "chrome_surface", "region": "modal", "surface_key": "theme", "title": "Theme",
   "admin_only": false, "components": [ { "type": "card", "attributes": { }, "children": [ ] } ]}
  ```
  `components` are `astralprims` `.to_dict()` nodes, ROTE-adapted for the device's `supported_types`. The client renders them with its existing component renderer into a modal/sheet, and wires component actions (`chrome_*`) back over the existing `ui_event` path.

**Server-side authorization (unchanged, authoritative):** if the surface module sets `ADMIN_ONLY = True` and `"admin" not in roles`, the server refuses (no render) and writes an audit event (`settings.*.denied`), regardless of client type. A `chrome_surface` for a surface not yet converted returns a single labeled placeholder component (FR-013) on native targets while the web keeps its HTML.

## 4. Surface module contract (additive)

Each surface module in `webrender/chrome/surfaces/` keeps its existing `TITLE`, `render(...)` (HTML, web), and `HANDLERS`, and **adds**:

```python
ADMIN_ONLY: bool          # already present on admin_tools
def components(orch, user_id, roles, params) -> list[dict]:
    """Return astralprims component dicts for this surface (SDUI path).
    Same data/actions as render(); actions use the existing chrome_* keys."""
```

- A converted surface's `render()` MAY delegate to `components()` + the orchestrator renderer, so web and native share one source (target of P2).
- Action bindings inside components use the SAME action strings the HTML uses today (`chrome_perms_save`, `chrome_theme_preset`, `chrome_audit_page`, …) so handlers are unchanged.

## 5. Invariants (tested)

- `GET /api/chrome/menu` and the `chrome_menu` frame serialize byte-identical models for the same session.
- The web `render_topbar` output is generated from the same `build_menu_model` (no second menu definition anywhere).
- Non-admin sessions never receive an `admin` group or any `admin_only` item in either channel.
- Item/group **order** is fixed and identical across the REST body, the WS frame, and the web HTML.
- Every `MenuItem.surface` resolves to a real key in `surfaces/__init__.py::SURFACE_MODULES`.
