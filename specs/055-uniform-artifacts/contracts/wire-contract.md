# Wire Contract Deltas: 055-uniform-artifacts

All changes ride the existing WS protocol; `backend/shared/ui_protocol.json` is
edited in the same PR as every item below (drift guards on all three native
clients + backend assert against it). No new push frame types. No new component
types.

## 1. Welcome identity + turn-start lifecycle (US1, `FF_FIRST_TURN_CONTRACT`)

**Server**:
- Welcome components carry BOTH `id` and `component_id` set to the same
  ephemeral `wel_` value (`wel_hero`, `wel_enable`, `wel_ex_<slug>`,
  `wel_hint`), stamped inside `welcome_components()` so every send site
  (register_ui, 054 gate-unlock, `enable_recommended_agents` refresh) carries
  them. `component_id` is what makes the web identity wrapper
  (`data-component-id`) fire and matches the natives' `component_id ?? id`
  read — one uniform purge key. The workspace layer refuses `wel_` identities
  (never persisted).
- ROTE identity preservation: fallback-ladder rebuilds and grid→container
  collapse carry over `id`/`component_id` (today they drop them — on watch the
  degraded Hero/Grids would be unmatchable `anon-N` entries).
- The turn-start welcome-blanking frame — `ui_render {target:'canvas',
  components: [], html:'<wrapper/>'}` sent on the first `chat_message` of a
  welcome-flagged socket — is **no longer sent** (flag on). ONLY the send is
  removed; the `_ws_welcome` bookkeeping stays (the enable-recommended-agents
  refresh reads it). All other empty canvas renders (authoritative out-of-turn
  clears) are unchanged.

**Clients (uniform rule)**: on turn start (the same moment each client arms its
loading state — web `sendChat`, Windows `_send`/`_emit`, Android/Apple send-time
`pendingReplace` arming; watch: unconditional filter at every `ui_upsert` apply,
it has no turn state):
1. Remove all components whose `component_id ?? id` starts with `wel_` from the
   visible/committed canvas state. Web: SELECTIVE removal of
   `[data-component-id^="wel_"]` nodes only — never a blanket canvas clear
   (mid-chat the canvas holds client-side workspace nodes a clear would lose).
2. Never include `wel_` components in any canvas-history archive or snapshot.
3. (Unchanged) out-of-turn empty `ui_render` remains an authoritative clear;
   in-turn semantics per client are otherwise untouched.

**Sequencing**: client purges land with/before the server change — Windows has
no in-turn buffer and is the one client for which the blanking frame still does
real work today.

**Pinned contracts that MUST keep passing**: Android `CanvasClobberTest`
(out-of-turn empty clears; in-turn accumulate-then-commit), Apple/Windows
equivalents, web `chat_status done`/error skeleton-resolution paths.

## 2. `ui_stream_data` additive field (US2, `FF_STREAM_ARTIFACTS`)

New `additive_fields` manifest entry:

```json
{
  "field": "component_id",
  "shape": "string",
  "carried_on": ["ui_stream_data", "stream_subscribed"],
  "scope": "present when the stream is bridged to a workspace component identity; absent on legacy/narrative streams",
  "introduced_by": "055-uniform-artifacts (FR-010)",
  "contract": "specs/055-uniform-artifacts/contracts/wire-contract.md"
}
```

Semantics:
- **Keying rule (double-render guard)**: when frames carry `component_id`,
  clients key the streamed node/canvas entry by it FROM THE FIRST FRAME —
  including the `stream_subscribed` placeholder — and never create a
  `stream-<stream_id>` node for that stream. The terminal persist `ui_upsert`
  under the same identity then replaces in place. (Without this, the retained
  last-chunk content plus the persist upsert would render twice.) Frames
  WITHOUT the field keep today's `stream-<stream_id>` behavior exactly.
- Web `mergeStream` reuses the `applyUpsert` morph mechanics (CSS.escape'd
  selector, fragment unwrap/replaceWith — the server fragment is itself
  `data-component-id`-wrapped — and side-effect re-init) plus `Plotly.purge`
  before replacing chart nodes; chart-bearing interim frames re-plot at most
  1/s, final state on terminal.
- Android's typed decode gains the field (`Wire.kt`/`Messages.kt`
  `Inbound.UiStreamData.componentId`); Apple/Windows read it dynamically.
- watchOS keeps its status-text treatment of stream frames; the terminal
  persist `ui_upsert` is how streamed content reaches the watch canvas.
- `stream_id`, `seq` (monotonic, dedup key — still keyed on `stream_id`),
  `session_id` (chat filter), and terminal/done chunk semantics are UNCHANGED.
- Narrative streams (`narrative-*`) and legacy polling streams never carry the
  field.
- Subscription is established SERVER-SIDE at streaming-tool dispatch (the
  orchestrator auto-subscribes the originating socket and co-viewing sockets);
  the client `stream_subscribe` action remains valid for reattach.
- On terminal, the server persists the retained last content-bearing chunk to
  the workspace under this identity (source-tagged) and fans a normal
  `ui_upsert`.
- Rollout caveat: pre-055 native binaries ignore the field and may show a
  transient duplicate on terminal until updated (all first-party clients ship
  in the same PR).

## 3. Accept actions (US4, `FF_COMPONENT_REFINE`)

`accept_actions` additions (manifest + three native disposition tables + web
handler, same PR):

| Action | Payload | Server behavior |
|--------|---------|-----------------|
| `component_refine` | `{component_id, instruction}` | Full component_action-equivalent gate stack (timeline read-only guard, security flags, per-user permission on source agent/tool, per-user LLM gate, audit) → bounded LLM edit constrained to same component type → force-upsert onto `component_id` → prior dict archived to `component_version` → `ui_upsert` fan-out |
| `component_restore` | `{component_id, version_no}` | Same gates (no LLM) → archive current → restore archived dict → `ui_upsert` fan-out |

Refusals are per-action `error` frames (existing shape), never socket teardown.
Watch: both actions are out of scope (no affordance rendered; server refuses
with honest error if received) — declared ROTE-capability divergence recorded in
the parity matrix.

## 4. Disposition promotions (US3) — no wire change

The 8 existing `component_verbs` push frames (`component_saved`,
`component_save_error`, `saved_components_list`, `component_deleted`,
`combine_status`, `combine_error`, `components_combined`,
`components_condensed`) move from **ignored → handled** on Windows, Android, and
iOS/macOS:
- `component_deleted` → identity-keyed remove op on the canvas.
- `components_combined` / `components_condensed` → apply the carried result
  component(s) + remove the consumed identities (mirroring the web morph).
- `component_saved` / `component_save_error` / `combine_status` /
  `combine_error` → status/toast surface updates.
- `saved_components_list` → refresh of the native saved-components surface.

watchOS: stays ignored-with-reason (bounded scope). Parity-matrix rows updated;
all drift-guard tables (`protocol_manifest.py`, `ProtocolManifest.kt`,
`Dispositions.swift`) edited in the same PR.

## 5. Designed-canvas delivery to natives (US3, `FF_DESIGNER_ALL_DEVICES`) — no wire change

Native sockets (Windows/Android/iOS/macOS/watch) receive the designed canvas as
a **materialized, ROTE-adapted, out-of-turn full `ui_render`** — ONE coalesced
designer pass over the turn's final canvas, pushed inline in the turn handler
AFTER the `chat_status done` send and before the handler returns (per-socket
chat lock + TCP ordering ⇒ done → designed render → next ack is race-free on
the originating socket). Rules:
- Flat `ui_upsert` delivery (upsert-first) remains exactly as today and always
  precedes it; designer failure ⇒ the render simply never arrives.
- Designer progress `chat_status` frames are SUPPRESSED on this post-done pass
  (they would flip natives back to turn-active with a stuck status line).
- The push carries the turn marker and is skipped server-side when a newer turn
  has started on the chat (cross-socket/async stale guard). Async-mode turns
  sequence the push before `task_completed`.
- The materialized canvas for native delivery EXCLUDES `doc_` narrative cards
  and Reasoning collapsibles (native reducers divert/drop them).
- `speak=False` is threaded through the push — watch deliveries of
  re-presented content never speak (this also fixes the latent co-viewed
  designed-canvas re-speak today).
Web delivery is unchanged (mid-turn `_push_canvas`, which also gains
`speak=False` and the stale guard).

## 6. Provenance field (US4) — component dict field, no manifest type change

Every delivered/persisted component dict carries
`provenance: "grounded"|"estimated"|"generated"` (top-level field, stamped
server-side post-designer; agent-supplied values overwritten). Renderers:
- web: existing footer, now driven by the field;
- Windows/Android/iOS/macOS: compact badge in the component chrome;
- watch: inherited through list/text degradation.
ROTE: `provenance` is a preserved field (host bounds never strip it).
Parity-matrix note added; no `component_types` change.

## 7. Flags-off byte equivalence (SC-009)

With `FF_FIRST_TURN_CONTRACT`, `FF_STREAM_ARTIFACTS`, `FF_DESIGNER_ALL_DEVICES`,
`FF_COMPONENT_REFINE`, `FF_ARTIFACT_EXPORT`, `FF_ARTIFACT_SHARING` all off:
welcome ships id-less, the blanking frame returns, `ui_stream_data` carries no
`component_id`, the designer skip tuple returns, refine/restore refuse, export/
share endpoints 404, and no `provenance` field is stamped. Wire behavior is
byte-identical to pre-055; the existing suites + drift guards prove it in a
dedicated CI variant.
