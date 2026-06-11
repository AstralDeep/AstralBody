# Phase 1 Data Model: FastAPI-Delivered UI & `astralprims`

This feature introduces **no database schema changes**. The "data model" here is the in-memory/over-the-wire
shape of UI and device state. Persistence (chats, saved components, audit, preferences) already stores
primitive dicts and is unchanged.

## 1. UI Primitive (owned by `astralprims`)

The canonical structured unit of UI. Defined as Pydantic models in `astralprims`; serialized to a plain dict
via `to_dict()` / wrapped via `create_ui_response()`. **This dict tree is the canonical structured
representation (FR-018)** that ROTE adapts, the web renderer renders, and programmatic consumers may read.

**Base fields (every primitive)**: `type` (str, first key), `css` (dict, kebab-case props; omitted when
empty), `id` (str?), `class` (from `class_name`), `tooltip` (str?), plus merged free-form `attributes`.

**Catalog (25 types — full parity with the removed `shared/primitives.py`)**:

| Group | Types (and notable fields) |
|-------|----------------------------|
| Layout | `container`(children, direction), `card`(title, content, variant), `grid`(columns, children, gap), `tabs`(tabs:[TabItem], variant), `collapsible`(title, content, default_open), `divider`(variant) |
| Content | `text`(content, variant h1/h2/h3/body/caption), `button`(label, action, payload, variant), `input`(placeholder, name, value), `param_picker`(title, description, fields[], submit_label, submit_message_template), `image`(url, alt, width, height), `code`(code, language, show_line_numbers), `alert`(message, variant, title), `progress`(value, label, variant, show_percentage), `metric`(title, value, subtitle, icon, variant, progress), `list`(items, ordered, variant), `table`(see below) |
| Charts | `bar_chart`/`line_chart`(title, labels, datasets[]), `pie_chart`(title, labels, data, colors), `plotly_chart`(title, data, layout, config) |
| Media/IO | `audio`(src, contentType, autoplay, loop, label, showControls, description), `file_upload`(label, accept, action), `file_download`(label, url, filename) |
| Theming | `color_picker`(label, color_key, value), `theme_apply`(preset, colors, color_key, color_value, message) |

**`table` (pagination + re-invocation — must round-trip intact)**: `headers[]`, `rows[][]`, `variant`,
`total_rows?`, `page_size?`, `page_offset?`, `page_sizes[]`, `source_tool?`, `source_agent?`, `source_params{}`.

**Validation**: Pydantic validates on construction. `Primitive.from_dict(d)` reconstructs the nested tree by
`type`; unknown keys funnel into `attributes`. Children/content/tabs coerce dicts → primitives recursively.

**Non-primitive helpers**: `TabItem`(label, content[], value), `ChartDataset`(label, data[], color).

## 2. UI Response Envelope (unchanged contract)

```json
{ "_ui_components": [ <primitive dict>, ... ], "_data": null }
```
Produced by `astralprims.create_ui_response([...])`; emitted by agent tools as `_ui_components` and carried
through MCP responses to the orchestrator — identical to today, so agent/orchestrator plumbing is unchanged.

## 3. DeviceProfile / DeviceCapabilities (owned by ROTE — unchanged)

Built from `register_ui.device`. `DeviceType` ∈ {browser, tablet, mobile, watch, tv, voice}. Derived
constraints drive adaptation: `max_grid_columns`, `supports_charts|tables|code|file_io|tabs`,
`max_text_chars`, `max_table_rows`, `max_table_cols`. (Source: `backend/rote/capabilities.py`.)

**State transitions**: `register_ui` → `register_device(ws, info)` stores profile; viewport/capability change →
`update_device(ws, info)` rebuilds profile and, if changed, re-adapts the cached dicts; disconnect →
`cleanup(ws)`.

## 4. Structured Representation → Rendered Output (the new seam)

```
agent tool → _ui_components (astralprims dicts)
           → orchestrator.send_ui_render(ws, dicts)
           → ROTE.adapt(ws, dicts)            # dict → dict, per DeviceProfile  (UNCHANGED)
           → webrender.render(adapted, profile) -> HTML fragment(s)            (NEW)
           → WS ui_render/ui_stream_data {components: [...], html: "<...>"}     # both kept
           → client.js swaps HTML into DOM / merges by stream_id
```

- **Adapt-then-render** ordering: each target renders from its already-appropriate dict tree.
- The `components` (dicts) stay on the wire next to `html` so programmatic/non-web consumers keep the
  structured form (FR-018). A future renderer is added at the `webrender.render` seam only (FR-011, SC-005).

## 5. Renderer Registry (new, `backend/webrender/registry.py`)

A `type → render-fn/template` map covering all 25 types (mirrors the removed `frontend/src/registry.tsx`).
A missing/unknown type renders a readable placeholder rather than failing the response (FR-014).

## 6. Browser Client State (`client.js`, ephemeral)

WebSocket connection; reported `device` capabilities; canvas vs chat target regions; in-flight stream buffers
keyed by `stream_id`; pending action payloads. No durable storage beyond what the server already persists.

## Entities explicitly NOT changed

- DB tables (chats, components, audit, user_preferences, personalization, scheduled_job, …).
- MCP request/response shapes; agent tool registries; permissions/scopes; RFC 8693 delegation.
- ROTE adaptation rules.
