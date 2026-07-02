# Contract — Chrome Parity: Top Bar, Menu, Settings Surfaces (044)

**Satisfies**: FR-015–FR-018, US3 | **Research**: R6, R7, R8

## 1. Top-bar rendering duty (both natives)

The `chrome_menu` model (`{version, topbar[], menu[], signout}` — MODEL_VERSION 1) is the
single chrome source (Constitution II/XII). Native duty per `topbar[].kind`:

| kind | key today | Native rendering duty |
|---|---|---|
| `brand` | `brand` | client brand mark/image (existing) |
| `status` | `status` | **live connection state** (text/dot fed by the client's connection state machine) — this control *is* the connection-status surface; nothing client-invented |
| `action` | `pulse` (flag-gated), `timeline` | icon button (semantic icon map: `sparkle`→pulse, `history`→timeline, `gear`→settings) → emits `ui_event chrome_open {surface, params}` from the control's `action` |
| `menu` | `settings` | anchors the client's settings dropdown, populated **only** from `model.menu` groups/items + `model.signout` (existing on both) |

- Ordering and presence follow the model verbatim; a control the client deliberately will not
  render must instead be **server-omitted** for that channel (none currently — natives render
  all five).
- Chat navigation (Android New/Recent, Windows chat list) is form-factor adaptation of the web
  shell's sidebar, outside the chrome model; recorded `native-equivalent` in the matrix.
- `signout` (`{label, style:"danger", action:"logout"}`) triggers the
  [session-lifecycle](session-lifecycle.md) sign-out ladder.
- Menu items `agents`/`audit` keep opening the clients' existing native screens
  (`native-equivalent`, deliberate); `llm`/`personalization`/`theme`/`guide` open SDUI
  surfaces; admin tools + tour remain server-omitted for native channels (verified:
  `include_admin=False, include_tour=False` at both the WS and REST menu sources) —
  Constitution XII v2.3.1 carve-out.

## 2. Surface lifecycle (both natives)

```
chrome_open {surface, params}  →  chrome_surface {region:"modal", surface_key, title,
                                                  admin_only, components[], mode:"replace"}
```

- **Bounded loading**: skeleton ≤ 10 s after `chrome_open`; then inline error + **Retry**
  (re-emits `chrome_open`). No indefinite skeleton (FR-017); reopening never wedges.
- **Close**: client closes its modal locally; server-side `chrome_close` becomes
  device-aware — native targets receive `chrome_surface {components: []}` (documented
  clear-modal form) instead of the web-only empty-HTML `chrome_render`.
- **Action feedback**: tuple-returning `chrome_*` handlers already re-render device-aware
  with the notice as a leading Alert — the re-pushed `chrome_surface` IS the success/failure
  feedback. Clients show an in-flight state on submit until the re-push (≤10 s bound → Retry).
- **Error paths become device-aware** (today web-only HTML): unknown action, admin-denied
  action, uncaught handler exception → native targets get `chrome_surface` with an error
  Alert (`title:"Something went wrong"`); web keeps its HTML modal. Forced-failure feedback
  (SC-003) rides this path.

## 3. Surfaces gaining `components()` (server-side)

All composed from existing astralprims vocabulary via `_sdui` helpers; ROTE-adapted per
device; web `render()` HTML **unchanged** in all three cases.

### 3.1 `workspace_timeline`
- List of snapshots (newest first): `#n · <cause> · <timestamp>` rows; **Newer/Older**
  buttons → existing `chrome_workspace_timeline_view` handler; **Back to live** →
  `chrome_workspace_timeline_live`. Both handlers (which push their own output today) become
  device-aware.
- While a snapshot is open the server's `workspace_timeline_mode {on: true}` frame applies:
  natives disable mutating affordances (send, component actions, save/delete) until
  `{on: false}` — matching web (FR-007).

### 3.2 `pulse` (only reachable when `FF_PULSE_DIGEST` on)
- Digest cards from the existing `build_digest` primitives + intro text; flag-off state = a
  single notice Alert. No new handlers.

### 3.3 `attachments` (the library — US4 entry point)
- Rows per upload: filename, category, uploaded-at, parser status; per-row **Attach** button
  with client-local action `attach_existing {attachment_id, filename, category}`; per-row
  **Delete** → existing `chrome_attachment_delete`; empty state text.
- **`attach_existing` semantics (new, client-local)**: the client intercepts this action
  instead of sending it — it stages a composer chip from the payload (the SDUI twin of the
  web's `astral-attach-existing` behavior) and closes/keeps the modal per client idiom. It
  MUST NOT be forwarded to the server (the server treats it as unknown).
- Reached from each native composer's paperclip menu: *Choose from your files* →
  `chrome_open {surface:"attachments"}` — same entry the web paperclip offers.

### 3.4 Deliberately not ported (recorded in matrix + Defect Register)
- `drafts` — in no client's menu (web included); draft decisions arrive as in-chat cards that
  already round-trip everywhere. Equal reachability = no gap.
- `agents`, `audit` — native-equivalent screens stay (042/043 disposition); convergence
  deferred with rationale.
- `admin_tools`, `tour` — sanctioned web-only (server-omitted for native channels).

## 4. Settings round-trips in scope (SC-003 — 8/8 surface-client pairs)

Theme, User guide, LLM settings, Personalization × {Windows, Android}: load current values →
change → Save/Test where offered → visible success **and** forced-failure feedback via §2's
re-push. (Theme's apply additionally live-restyles per
[theme-restyle.md](theme-restyle.md).)
