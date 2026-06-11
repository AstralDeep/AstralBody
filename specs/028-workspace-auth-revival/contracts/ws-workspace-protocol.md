# Contract: Workspace WebSocket protocol (028 Part B)

All additions are **additive** to the 026 wire contract (FR-024). Existing message types keep their exact shapes. Structured component dicts always accompany rendered HTML so non-web targets consume the structured layer.

## `ui_upsert` (server→client, NEW)

Partial workspace update. Sent on: new/updated component during a turn, component-action results, workspace removals, legacy combine/condense effects.

```json
{
  "type": "ui_upsert",
  "chat_id": "…",
  "ops": [
    { "op": "upsert", "component_id": "wc_ab12…", "component": { …astralprims dict incl. component_id… }, "html": "<div class=\"astral-component\" data-component-id=\"wc_ab12…\">…</div>" },
    { "op": "remove", "component_id": "wc_cd34…" }
  ]
}
```

- `component` is the ROTE-adapted structured dict **for the receiving socket**; `html` is the web renderer's projection of exactly that dict.
- Client morph: for each op, `querySelector('[data-component-id="…"]')` → replace node (upsert) / remove node; missing target on upsert ⇒ append to canvas; missing on remove ⇒ no-op. Re-run `processSideEffects` (Plotly/theme) on inserted subtrees only.
- Ordering: ops within one message apply in order; messages apply in arrival order (server serializes per chat).
- Broadcast: delivered to every socket of the owning user whose active chat is `chat_id`, each with per-socket adaptation (FR-040).
- A client in timeline mode buffers/skips DOM application and shows the "live has moved on" indicator; server state is unaffected.

## `ui_render` (existing — semantics clarified)

- `target:'canvas'` full renders now always carry the **entire live workspace** (every top-level component wrapped in `<div class="astral-component" data-component-id="…">`), used for: re-hydration after `chat_loaded`, device-profile re-adapt, timeline views ("historical" flagged via accompanying chrome banner), and back-to-live.
- `target:'chat'` unchanged (append bubble).

## `chat_loaded` (existing — additive field)

Each message object MAY now carry `html`: server-rendered transcript representation for component-bearing content (compact card list). Client renders `html` when `content` is not a string — eliminating empty bubbles (FR-028). String content behavior unchanged.

## Re-hydration sequence (on `load_chat`)

1. `chat_loaded {chat}` (messages incl. `html` fields)
2. `ui_render {target:'canvas', components, html}` — full live workspace for this socket (FR-027). Empty workspace ⇒ no message (canvas stays clear).
3. stream resume messages (existing)

(Workspace render precedes stream resume so resumed streams merge into already-present components.) Entering a chat from a historical timeline view also emits `workspace_timeline_mode {active:false}` first — `load_chat` always lands live.

## Timeline (chrome-driven; messages reused)

- Entry: topbar/chrome → `ui_event {action:'chrome_open', payload:{surface:'workspace_timeline', params:{chat_id, page?}}}` (the 027 generic chrome-surface opener) → `chrome_render {region:'modal', html}` (snapshot list, paginated 50/turn-page).
- Select: `ui_event {action:'chrome_workspace_timeline_view', payload:{chat_id, snapshot_id}}` → server audits `workspace.timeline_viewed` → `ui_render {target:'canvas', …historical components…}` + `chrome_render` banner ("Viewing turn N — read-only · Back to live"). Client sets `timelineMode=true` (canvas actions inert; live upserts deferred with indicator).
- Back to live: `ui_event {action:'chrome_workspace_timeline_live', payload:{chat_id}}` → full live `ui_render` + banner cleared; `timelineMode=false`.
- Server-side defense: while a socket is in timeline mode, `component_action` from it is refused (`workspace.action_denied`, reason `timeline_readonly`).

## Renderer obligations (web target)

- `webrender.render()` wraps every **top-level** component in `<div class="astral-component" data-component-id="…">` (id from the structured dict). Nested children are not wrapped.
- Fragment rendering for `ui_upsert.html` uses the identical wrapper so morph targets match.
- Escape-by-default (`esc()`) everywhere, including the new transcript `html` and snapshot renders (026 FR-017).

## Legacy compatibility (D18)

- `components_replaced`, `component_saved`, `components_combined`, `components_condensed` continue to be emitted unchanged for non-web consumers; the web flow is driven by `ui_upsert`/`ui_render`.
- `ui_append` remains untouched (dormant); its semantics are not reused.
- `save_component` ws/REST verbs remain but are deprecated aliases (auto-persistence makes them redundant); `delete_saved_component` triggers `ui_upsert op:'remove'` + snapshot (`cause:'remove'`).
