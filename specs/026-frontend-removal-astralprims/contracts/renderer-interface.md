# Contract: Web Renderer Interface (`backend/webrender/`)

The renderer turns the ROTE-adapted astralprims structured representation into a web HTML fragment. It is the
single seam a future client target plugs into (FR-011, SC-005).

## Public interface

```python
# backend/webrender/renderer.py
def render(components: list[dict], profile: "DeviceProfile") -> str:
    """Render a list of astralprims primitive dicts (already ROTE-adapted) into an
    HTML fragment string. Escapes all text by default (FR-017). Never raises on an
    unknown/unsupported primitive type — emits a readable placeholder (FR-014)."""

def render_one(component: dict, profile: "DeviceProfile") -> str:
    """Render a single primitive dict (recurses into children/content/tabs)."""
```

```python
# backend/webrender/registry.py
RENDERERS: dict[str, Callable[[dict, "DeviceProfile"], str]]   # type -> pure-Python render fn
def get_renderer(type_name: str) -> Callable | None
```

## Rules

1. **Coverage**: every catalog `type` (25) has a renderer. Parity target = the removed
   `frontend/src/registry.tsx` / `DynamicRenderer.tsx` output (visual + interactive behavior).
2. **Escape-by-default (FR-017/SC-008)**: every render fn passes text through `html.escape` (`esc()`). Text fields (`text.content`, `alert.message`,
   table cells, list items, labels, …) are HTML-escaped. Raw HTML only via the explicit opt-in path
   (markdown/`code`), routed through `webrender/sanitize.py` (tag/attr allowlist; strips scripts/handlers).
3. **Interactivity hooks**: interactive primitives emit DOM that `client.js` binds — e.g. a `button` carries
   its `action`/`payload` as data-attributes; `param_picker` renders a form whose submit interpolates
   `submit_message_template`; `table` pagination controls carry `source_tool`/`source_agent`/`source_params`;
   `file_upload`/`file_download`/`theme_apply` map to their existing action round-trips (FR-012).
4. **Children**: `container`/`card`/`grid`/`collapsible`/`tabs` recurse via `render_one`. `grid` honors
   `columns` (already ROTE-clamped). Charts: bar/line/pie/plotly render via the self-hosted Plotly asset fed
   from the dict; ROTE may have already degraded charts→`metric` for small devices (render whatever dict it
   receives).
5. **Determinism**: `render(components, profile)` is a pure function of its inputs (no global state) so it is
   golden-testable and a future renderer is a drop-in sibling.
6. **Theme**: Astral visual language lives in `webrender/static/astral.css` + template classes (ported from
   the old Tailwind/registry styling). `css`/`class`/`id`/`tooltip` base fields are applied to the root
   element of each fragment.

## Test contract (golden HTML)
For each primitive type and a representative nested tree, `render_one(dict, profile)` produces stable HTML
asserted against a golden fixture; escaping is asserted by feeding markup/script in text fields and checking
it renders inertly (SC-008).
