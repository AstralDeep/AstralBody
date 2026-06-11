# Contract: Adaptive UI Designer LLM Pass

**Module**: `backend/orchestrator/ui_designer.py` · **Consumer**: `Orchestrator.handle_chat_message` (replaces the flat append at the post-`_tag_source` choke point) · **Flag**: `FF_UI_DESIGNER` (default on) · **Budget**: `UI_DESIGNER_TIMEOUT_SECONDS` per pass (default 8) × `UI_DESIGNER_MAX_ROUNDS` passes (default 3; 1 == legacy single pass)

## Invocation predicate

```text
designer runs  ⇔  FF_UI_DESIGNER ∧ round_components ≥ 2 ∧ not timeline_mode
```

`round_components` counts rich top-level components produced by the round's tools after `_tag_source` and after `WorkspaceManager.upsert` has assigned each its `component_id` (the designer needs final identities to reference).

## Prompt inputs

1. The user's request for the round (verbatim, truncated to a bounded length).
2. Per-component digest, one entry per round component: `component_id`, `type`, `title` (if any), `_source_agent`/`_source_tool`, and a size-bounded JSON excerpt of the component body.
3. Canvas context digest (existing live components NOT in this round — id/title/type only) so the designer can choose complementary, non-duplicative garnish.
4. The allowed palette: the registered type names (31 including the dashboard primitives) **imported from `webrender.renderer.PRIMITIVE_RENDERERS`** (never hand-copied) plus the `ref` pseudo-node, with one-line usage notes and layout guidance (grids ≤ 3 columns preferred, meaningful titles mandatory on composites for watch/voice survival).

## Required output (assistant message, JSON only)

```json
{
  "layout": [
    {
      "type": "grid",
      "columns": 2,
      "children": [
        { "type": "ref", "component_id": "wc_a1b2c3d4e5f60708" },
        {
          "type": "card",
          "title": "Portfolio pulse",
          "content": [
            { "type": "metric", "title": "S&P 500", "value": "+0.8%", "variant": "success" },
            { "type": "ref", "component_id": "au_watchlist" }
          ]
        }
      ]
    },
    { "type": "text", "content": "Cold front Thursday may pressure ag futures.", "variant": "body" }
  ]
}
```

### Node rules

| Rule | Enforcement stage |
|---|---|
| `layout` is a non-empty array of nodes | structural validation |
| `ref` nodes carry only `component_id`; that id exists among the round's components or the live canvas | ref validation (unknown → node dropped) |
| Each round component referenced **exactly once** | dedupe (first occurrence wins) + omission repair (missing components appended flat at the end, in dispatch order) |
| Non-`ref` node types ∈ renderer registry | type validation (unknown type → node rewritten to `container`, children preserved — existing `_validate_component_tree` behavior, widened to the registry) |
| Garnish nodes never duplicate a tool component's data wholesale | prompt instruction (not mechanically enforced; garnish is additive narrative/metrics/grouping) |
| Composites (card/tabs/grid/collapsible) carry a meaningful `title`/labels | prompt instruction + validation warning log |
| `ERROR: <reason>` is a permitted refusal output | treated as fallback trigger, logged |

### Multi-round refinement

The designer is a bounded conversation, not a single shot. Pass 1 drafts the
arrangement from the prompt above. While passes remain
(`UI_DESIGNER_MAX_ROUNDS`, default 3):

- **Refine** — the model is shown its own current arrangement (an indented
  structural sketch with refs resolved to component type/title — canvas refs
  labelled "(canvas)" — plus the bounded layout JSON) and a review checklist
  (anchor, hierarchy, balance, scannability, texture). It replies with a
  complete improved `{"layout": [...]}` (same node rules, re-validated per
  pass) or exactly `DONE` to finish early.
- **Converge** — a refinement identical to the current arrangement ends the
  loop (`outcome=stable`).
- **Keep-best** — any refine-pass failure (timeout, LLM error, refusal,
  unparseable/invalid output) keeps the best arrangement so far; refinement
  can never lose a good draft.
- **Stand-alone refinements** — a refinement must itself reference every
  component the current arrangement places (round AND canvas refs); omission
  repair runs only on draft passes, because repair-appending a refinement's
  omissions would silently demote good placements to flat refs and launder
  ref-free meta-replies into "layouts". Incomplete refinements are rejected
  (`outcome=rejected:incomplete`, keep-best).
- **Format retry** — a *draft* pass producing unusable JSON (`parse`/`invalid`)
  is retried with the failure reason fed back, while passes remain. A draft
  `ERROR:` refusal is respected immediately (no retry). First-pass
  timeout/LLM-error/refusal semantics are identical to the legacy single pass.

Garnish ids are stamped once, on the final arrangement, so determinism per
`(chat_id, layout_key, ordinal)` is unaffected by how many passes ran.

### Garnish identity stamping (post-validation)

Every non-`ref` node that is a *renderable component* (not pure structure inside another's `content`) at the top level of `layout` receives `id = "dg_" + sha1(chat_id|layout_key|ordinal)[:12]` and `attributes["data-component-id"] = id` — deterministic across re-designs of the same round (FR-019).

## Materialization (server-side, pre-ROTE)

`materialize(layout, components_by_id) -> List[component_dict]`: substitutes each `ref` with the live component dict (stamping `attributes["data-component-id"] = component_id`), returns the layout as an ordinary astralprims component list. From here the existing pipeline applies untouched: `rote.adapt(websocket, components)` → server HTML render → `ui_render` (canvas target). The renderer and client have **no knowledge of `ref`** — it never crosses the materializer.

## Failure semantics (FR-022 — all fail-open to legacy append)

| Failure | Detection | Result |
|---|---|---|
| LLM unavailable / non-200 | client exception | fallback, log `fallback{reason:"llm_error"}` |
| Budget exceeded | `asyncio.wait_for` timeout | fallback, log `fallback{reason:"timeout", budget_s}` |
| Unparseable output | JSON extraction fails | fallback, log `fallback{reason:"parse"}` |
| `ERROR:` refusal | prefix check | fallback, log `fallback{reason:"refusal"}` |
| Empty/invalid structure | structural validation | fallback, log `fallback{reason:"invalid"}` |
| Partial validity | per-node drops + omission repair | designed render proceeds (repair is not failure) |

Fallback = exactly today's `_send_or_replace_components` flat path. No user-visible error, ever.

## Persistence & downstream contracts

- Validated layout upserts into `workspace_layout` (`layout_key` deterministic per round); the round's full-canvas `ui_render` is pushed per socket with ROTE adaptation (existing path).
- `workspace_snapshot.layouts` captures live layouts each turn; timeline materializes historical layouts read-only.
- `load_chat` re-renders canvas via `render_workspace(live_components, live_layouts)`.
- Canvas-context for the chat LLM continues to list every component row individually (FR-026); layouts add no entries and hide none.
- `ui_upsert` morphs of a referenced component require no layout change (client morphs by `data-component-id` wherever the node sits).

## Observability (FR-030)

Structured log events: `ui_designer.invoked {chat_id, components, budget_s, max_rounds}`, `ui_designer.refine {chat_id, round, outcome: improved|done|stable|empty|timeout|llm_error|rejected:<reason>}` (one per refinement pass), `ui_designer.designed {chat_id, layout_key, refs, garnish, rounds, latency_ms}`, `ui_designer.fallback {chat_id, reason, latency_ms}`. Every pass's LLM call is audited under the existing `llm_call` event class with the round's credential resolution (feature-006 factory, websocket-scoped).
