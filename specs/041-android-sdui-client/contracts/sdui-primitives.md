# Contract: SDUI Primitive Vocabulary

The client renders the primitive types defined by `astralprims` and emitted by the orchestrator's renderer registry (`webrender.allowed_primitive_types()` — currently 35 types). The client **defines no primitives** (Constitution II/VIII); it provides a native renderer per type and advertises the set it can draw via `supported_types`, so ROTE substitutes the rest upstream.

## Render targets (native Composable per type)

Core layout/content (parity with the Windows native renderer): `text`, `card`, `container`, `grid`, `hero`, `badge`, `metric`, `keyvalue`, `timeline`, `rating`, `alert`, `button`, `param_picker`, `input`, `file_upload`, `file_download`, `download_card`, `code`, `divider`, `progress`, `list`, `table`, `tabs`, `collapsible`, `chat_history`, `skeleton`.

Charts: `bar_chart`, `line_chart`, `pie_chart` (Compose Canvas).

Media: `image` (Coil) — an improvement over the Windows placeholder.

## Advertised `supported_types`

The client advertises exactly the types it renders natively. Initially **excluded** (so ROTE substitutes/condenses them upstream, and any that still arrive hit the placeholder): `plotly_chart`, `audio`, `color_picker`, `theme_apply`, `generative`. These can be added in later iterations (e.g. `audio` via ExoPlayer, `color_picker`/`theme_apply` once a native theme surface exists) by extending the registry and `supported_types` — no protocol change.

## Fallback rule (FR-005)

Any `type` not in the registry → a **labeled placeholder** Composable showing `[type]` + the first human-readable field (`title`/`label`/`message`/`content`). The rest of the screen renders normally. A component that throws during render → an inline error chip, never a crashed canvas (mirrors the Windows renderer's per-component guard).

## Identity & updates

Every rendered component carries its `component_id` so `ui_upsert`/streaming can replace/remove it in place. The Compose canvas keys children by `component_id` (`key(id) { … }`) so identity, scroll position, and animations survive updates.

## Parity check (test obligation)

A unit test MUST assert that the client's `supported_types` ⊆ `webrender.allowed_primitive_types()` and that every type the client claims to support has a registered renderer (the Windows client has the equivalent `test_no_silent_backend_vocabulary_drift` / `test_supported_types_published` guards). The published backend vocabulary is the source of truth.
