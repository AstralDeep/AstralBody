# Contract: SDUI Settings Surface Delivery

Extends the feature-042 chrome contract (`specs/042-cross-client-chrome-parity/contracts/chrome-menu.md`). 042 delivered the **menu** to native clients; 043 delivers the **surface content**. The web path (`chrome_render` HTML) is unchanged; native gains `chrome_surface`.

Single source per surface: that surface module's `components(orch, user_id, roles, params)` in `backend/webrender/chrome/surfaces/*.py`. The orchestrator renders/adapts it; every client is a thin consumer.

## 1. Opening a surface — `chrome_open` (client → server), existing action

Unchanged request shape (already implemented, `chrome_events.py:129-138`):
```json
{"type": "ui_event", "action": "chrome_open", "payload": {"surface": "<key>", "params": { }}}
```

**Response depends on the connecting device target** (`orch.ui_sessions[websocket].device_type`):

- **Web (`browser`)** → existing `chrome_render` HTML modal (unchanged):
  ```json
  {"type": "chrome_render", "region": "modal", "html": "<…>", "mode": "replace"}
  ```
- **Native SDUI (`windows`, `android`)** → new `chrome_surface` components frame:
  ```json
  {"type": "chrome_surface", "region": "modal", "surface_key": "llm", "title": "LLM settings",
   "admin_only": false,
   "components": [ {"type": "card", "attributes": {…}, "children": [ … ]} ]}
  ```
  `components` are `astralprims` `.to_dict()` nodes, **ROTE-adapted** for the device's `supported_types`. The client renders them with its existing component renderer (Windows `renderer.py`; Android `render/Renderer.kt`) into a modal/sheet, and wires component actions back over the existing `ui_event` path.

**Not-yet-converted surface** (a surface without `components()`): native `chrome_open` returns a `chrome_surface` carrying a **single labeled placeholder component** (an `Alert`/`Text` "coming soon" node), never the retired text placeholder — so the delivery path is exercised from day one and each surface flips to real content as it lands.

**Server-side authorization (unchanged, authoritative)**: if the surface's `ADMIN_ONLY` is true and `"admin" not in roles`, the server refuses (no render) and audits, regardless of client type (`chrome_events.py:74-79, 149-158`). The four in-scope surfaces set no `ADMIN_ONLY`.

## 2. WS frame `chrome_surface` (server → client)

```json
{"type": "chrome_surface", "region": "modal", "surface_key": "…", "title": "…",
 "admin_only": false, "components": [ … ], "mode": "replace"}
```
- Pushed on `chrome_open` (native target) and re-pushed after any handler that returns `(surface, params, notice)` (§4).
- Web clients never receive it (their modal is `chrome_render` HTML) but MUST ignore it if received.
- Closing the modal reuses the existing `chrome_close` / an empty-body push.

## 3. Surface module contract (additive)

Each surface module in `webrender/chrome/surfaces/` keeps its existing `TITLE`, `render(orch, user_id, roles, params) -> str` (HTML, web), and `HANDLERS`, and **adds**:

```python
async def components(orch, user_id, roles, params) -> list[dict]:
    """Return astralprims component dicts for this surface (SDUI path).
    Same data + same chrome_* actions as render(); no new handler keys."""
```

- Built with the `_sdui.py` helpers (form via `ParamPicker` action-submit, per-row `Button`, notice → `Alert`).
- A converted surface's `render()` MAY delegate to `components()` + the orchestrator renderer **only where the resulting HTML is unchanged** (D6); otherwise `render()` stays as-is and `components()` serves native only.
- Action bindings use the SAME action strings as today, so `collect_handlers()` and every handler are unchanged.
- Audience/role filtering inside `components()` mirrors `render()` (guide admin sections). `tour` is not ported (web-only, D5) — no `components()`.

## 4. Action round-trip (settings save/toggle/edit)

Interactive components post the existing frame `{type:"ui_event", action, payload, session_id}`:

- **Button** (`astralprims.Button`) → `emit(action, payload)` on both clients (Windows `renderer.py` `ctx.emit`→`_emit`→`send_event`; Android `Emit`→`vm.sendEvent`→`Wire.encodeUiEvent`). Used for theme presets, per-row actions, TOC nav, tour lifecycle.
- **ParamPicker action-submit** (D2 extension) → on submit posts `{action: submit_action, payload: {fields:{…}, …submit_payload}}`. `fields` is collected with web-parity typing (checkbox→bool, number→Number, else string) so it matches the shape existing handlers parse (`_fields`, `llm.py:60-78`).

Server: `handle_chrome_event` resolves `HANDLERS[action]` → `fn(orch, websocket, user_id, roles, payload)` → **persist** (e.g. `set_user_preferences`, `svc.repo.*`, `tool_permissions.*`, `ScheduledJobStore.*`) → return `(surface_key, params, notice_html)`. The dispatcher re-renders that surface; on a native session the re-render is a fresh `chrome_surface` with the notice as a prepended **`Alert`**; on web it is `chrome_render` HTML (unchanged). A handler returning `None` (e.g. `chrome_tour_event`) pushes its own effect and triggers no re-render.

**Same gates as the web**: permission/scope checks (skills scope-bounding, `chrome_skill_toggle`), PHI gating (profile/memory), and audit all run inside the handlers — identical on native and web, no client bypass (Constitution VII).

## 5. Per-surface action inventory (unchanged handlers)

| Surface | Actions | Persistence / effect |
|---------|---------|----------------------|
| `guide` | *(none)* — `chrome_open` re-open with `section` param | none (static content) |
| `theme` | `chrome_theme_preset{preset}` | `set_user_preferences({"theme":{"preset"}})` + `theme_apply` re-render |
| `llm` | `chrome_llm_models`, `chrome_llm_test`, `chrome_llm_save`, `chrome_llm_clear` (all read `payload.fields`) | reuses feature-006 `llm_config.*` (list/test/set/clear) + its audit |
| `personalization` | `chrome_profile_save`, `chrome_memory_update{id}`, `chrome_memory_delete{id}`, `chrome_skill_toggle{agent_id,tool_name,enabled}`, `chrome_job_pause/resume/delete/run_now{job_id}`, `chrome_dreaming_toggle{enabled}`, `chrome_dreaming_trigger` | personalization service repo, `tool_permissions`, `ScheduledJobStore`, consolidation sweep; PHI-gated; each audits |

## 6. Invariants (tested)

- `chrome_open` on a `windows`/`android` session returns a `chrome_surface` with valid `astralprims` component dicts; the same session key on a `browser` session still returns `chrome_render` HTML.
- Every `surface_key` in a `chrome_surface` resolves to a real key in `surfaces/__init__.py::SURFACE_MODULES`, and every action string emitted by its components resolves in `collect_handlers()`.
- A converted surface's `components()` uses only types in `webrender.allowed_primitive_types()` (+ the extended `param_picker`); an unknown type degrades (ROTE ladder → client placeholder), never crashes.
- A `ParamPicker` action-submit produces a `payload.fields` shape the target handler accepts (contract test per form surface).
- Admin gating: a non-admin `chrome_open{surface:"admin_tools"}` on a native session is refused + audited (unchanged from 042); the four in-scope surfaces render for any `user`.
- Web-only tour: the native menu channels (`chrome_menu` frame + `GET /api/chrome/menu`) omit the `tour` item (per spec FR-009/D5), so a native client never sees it and `chrome_open{surface:"tour"}` does not originate natively; the web menu + tour surface are unchanged.
- Web parity: a converted surface's web modal HTML + behavior are unchanged before/after (SC-006), whether `render()` stays as-is or delegates to `components()`.
- Handler reuse: no `chrome_*` handler signature or persistence path changes; only the render/re-render output branches on device target.
