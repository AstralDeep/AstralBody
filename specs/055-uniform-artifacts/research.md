# Phase 0 Research: Uniform Cross-Device Artifacts & First-Turn Loading Contract

**Feature**: 055-uniform-artifacts | **Date**: 2026-07-13

Evidence base: the 2026-07-13 13-agent research audit (subsystem readers over
webrender/client.js, ROTE, astralprims, dispatch, native clients + three targeted
probes, adversarially verified with file:line citations) plus a live browser
reproduction of the first-query skeleton failure. Verified facts below cite the
current tree; each decision lists alternatives considered.

---

## D1 — Welcome lifecycle: stable `wel_` identities + client-side turn-start purge; retire the blanking frame

**Decision**: Give every welcome component a stable, namespaced identity
(`wel_hero`, `wel_ex_<slug>`, `wel_enable`, `wel_hint`, stamped in
`backend/orchestrator/welcome.py` via `Primitive.id`). Clients treat `wel_`
components as *ephemeral pre-turn content*: each client purges them from its
canvas state when a turn starts (web: at `sendChat`; Windows: at `_send`/`_emit`;
Android/Apple: at send-time arming alongside `pendingReplace`; watch: at first
in-turn `ui_upsert`), and never archives them into canvas history. The server
**stops sending** the turn-start blanking `send_ui_render(websocket, [])`
(orchestrator.py:1495-1501).

**Rationale** (per-client verified behavior, probe 1):
- The blanking frame is what kills the web skeleton (client.js:330-333 does
  `hideSkeleton(); setHTML(...)` on it) — removing it fixes web outright.
- The frame was already a no-op on Android/iOS/macOS (in-turn empty render
  returns state unchanged, AppViewModel.kt:604-609 / AppModel.swift:548-549) and
  is dropped in *every* state on watchOS (WatchModel.swift:326-328) — so it never
  performed its welcome-cleanup job on 3 of 6 targets. Only client-side purge
  reaches all six.
- `wel_` ids also fix the two Android/Apple leaks the empty frame never could:
  welcome snapshots archived as "Canvas 1" (AppViewModel.kt:879-887) and welcome
  resurrection after text-only turns (commitTurn with empty pendingCanvas keeps
  the old canvas) — both become "skip/drop `wel_`-identified components".
- Welcome components are currently id-less on the wire (`Primitive.id=None` is
  serialized away, base.py:101-115; welcome.py:79-105), so clients cannot
  distinguish them today.

**Constraints honored**: the out-of-turn "empty `ui_render` == authoritative
clear" contract is untouched (pinned by CanvasClobberTest.kt:54-61 and relied on
by chat_loaded/timeline flows). `wel_` is a new namespace disjoint from
`wc_`/`au_`/`dg_`/`ly_`; welcome components remain never-persisted
(welcome.py:70-71 contract unchanged). `_ws_welcome` flag lifecycle
(re-render on `enable_recommended_agents` orchestrator.py:2143-2149, pop on
load_chat 1721-1724, re-arm after 054 gate unlock llm_gate.py:148) is preserved —
only the blanking side-effect of the pop is removed.

**Alternatives considered**:
- *Server-side targeted `ui_upsert remove` ops for `wel_` ids at turn start* —
  rejected as the sole mechanism: on Android/Apple, in-turn ops buffer into
  `pendingCanvas` (commit-on-done), so remove ops against the committed canvas
  are no-ops exactly when needed; the history/text-only leaks would remain.
- *Keep the blanking frame, re-show skeleton after it* (client-only web fix) —
  rejected: leaves watch broken (content under welcome), leaves the Android/Apple
  leaks, and keeps paying an extra frame + full-canvas HTML render per first turn.
- *Wholesale replace welcome canvas on `user_message_acked`* — rejected: ack is
  too late (blank window), and arming on ack was explicitly flagged as opening a
  race (probe 1 constraint: skeleton arming must stay optimistic at send).

**Verification amendments (adversarial pass, 2026-07-13)**:
1. Welcome dicts get **`component_id`** (the `wel_` value) stamped alongside
   `id`, inside `welcome_components()` itself — the single source both send
   sites consume (register_ui path orchestrator.py:1301-1315 AND the 054
   gate-unlock re-render llm_gate.py:146-148, plus the
   `enable_recommended_agents` refresh at 2143-2148). Rationale: the web
   identity wrapper keys on `component_id`, not `id`
   (renderer.py:1287-1302), and every native reads `component_id ?? id`
   (Component.kt:27-29, Components.swift:30-32, windows app.py:399) — one
   uniform purge key (`[data-component-id^="wel_"]` on web) instead of two.
   The workspace guard (data-model) makes `wel_` unpersistable regardless.
2. **ROTE identity preservation**: the fallback-ladder rebuild
   (rote/adapter.py:62-76) and the grid→container collapse (adapter.py:408-410)
   currently DROP ids — on watch, the welcome Hero (hero→text) and Grids lose
   their identities and key as `anon-N`. Fix: degraded/collapsed rebuilds carry
   over `id`/`component_id` from the source component (generally correct — it
   also lets upsert morphs target degraded components).
3. **Watch purge shape**: WatchModel has no turn state (no pendingReplace) —
   the purge is an unconditional `wel_` filter applied at every `ui_upsert`
   apply (welcome components only ever exist pre-first-turn, so this is free).
4. **Web purge is selective, never a blanket clear**: mid-chat the canvas holds
   client-side-only workspace nodes that `ui_upsert` morphs/appends — a full
   clear at `sendChat` would permanently lose them. Remove
   `[data-component-id^="wel_"]` (and legacy `[id^="wel_"]`) nodes only.
5. **Sequencing**: client purges land with/before the server change — Windows
   is a live consumer of the blanking frame (no in-turn buffer; without its
   purge, first-turn upserts stack under the welcome). The server change drops
   ONLY the send at orchestrator.py:1497-1499; the `_ws_welcome` bookkeeping
   stays (the enable-recommended-agents re-render reads it).
6. **Bonus pre-existing bug to fix here** (skeleton safety net): the
   all-tools-denied `break` exits the ReAct loop without ever sending
   `chat_status done` (orchestrator.py:4120-4125 falls past the max-turns
   block) — one of the residual "stuck skeleton" causes. US1 fixes it.

## D2 — Windows loading parity: arm the skeleton on typed sends; suppress the idle hint mid-turn

**Decision**: `app.py::_send` (typed composer path, app.py:1905-1924) arms the
same `Canvas.show_skeleton()` as `_emit('chat_message')` already does
(app.py:1932-1940 — whose comment already *claims* twin parity); the
empty-state hint ("Your generated interface appears here") is suppressed while a
turn is active (turn-active flag mirrors the Android `turnActive` state).
Existing removal paths (first content, `chat_status` done, error, timeline mode,
app.py:2251-2263) unchanged.

**Rationale**: probe 1 verified typed Windows sends never show any loading state
and the mid-turn empty hint reads as a final state. This is a two-site client
fix with existing offscreen-Qt test coverage patterns.

**Alternatives**: server-driven `skeleton` primitive push at turn start —
rejected: no other client needs it (all arm locally), it adds a frame to a hot
path, and Windows already renders a local skeleton on the `_emit` path.

## D3 — Web empty-canvas honesty: key the empty-state on components, not HTML truthiness

**Decision**: the web canvas `ui_render` branch decides "empty" from the
structured `components` array (already on the wire per the 026 dual-shape
contract), not from `data.html` truthiness — fixing the `render_workspace([])`
non-empty-wrapper defect (renderer.py:1305-1313) that suppresses
`showCanvasEmpty()` today.

**Rationale**: with D1 the turn-start blank frame is gone, but out-of-turn
authoritative clears (chat deleted elsewhere, empty chat loaded) still arrive as
empty renders and currently leave a bare wrapper div instead of the idle hint.
Client-side check avoids changing `render_workspace` semantics for its other
callers (canvas export D11 wants the wrapper).

**Alternatives**: make `render_workspace([])` return `""` — rejected: other call
sites (chat_loaded hydration, export) treat the wrapper as canvas scaffolding.

## D4 — Stream→artifact bridge: workspace identity at subscribe, additive wire field, persist-on-terminal

**Decision** (four bounded deltas, per probe 2's "rename-plus" verdict):
1. **Identity at subscribe**: populate the already-existing
   `StreamSubscription.component_id` (stream_manager.py:168, today a hardcoded
   alias of `stream_id`) with the workspace rule-2 fingerprint
   `workspace.fingerprint(agent_id, tool_name, params)` (workspace.py:80-82).
2. **Wire**: add `component_id` to the two `ui_stream_data` frame builders
   (stream_manager.py:676-686, 1193-1203) as a manifest `additive_fields` entry
   (same vehicle as 051's `speech` field; ui_protocol.json:75-84). `stream_id`,
   `seq`, and `session_id` semantics unchanged (client dedup contract intact).
3. **Client keying**: web `mergeStream` targets `[data-component-id="…"]` inside
   the workspace tree when the frame carries `component_id` (falling back to
   today's `#stream-<id>` append otherwise); the existing
   `render_component_fragment` wrapper (renderer.py:1274-1302) is the anchor.
   Native reducers apply stream frames as in-place component content updates by
   the same id (their canvases are already identity-keyed).
4. **Persist-on-terminal** (the genuinely new code): the orchestrator's
   `handle_agent_end` wrapper (orchestrator.py:1106-1111) retains the last
   non-empty chunk's components per subscription, `_tag_source`-stamps them
   (today stream components are never stamped — orchestrator.py:4009-4054 runs
   only on chat-loop tool results), and writes them through `workspace.upsert`
   + snapshot + audit under the pre-assigned identity. StreamManager itself
   stays storage-free (its documented contract, stream_manager.py:304-306); the
   orchestrator layer owns persistence.

**Stream vs. full-render precedence** (spec FR-012): a designed/authoritative
`ui_render` repaints the component's last persisted state into a fresh
`[data-component-id]` anchor; subsequent stream frames keep morphing that anchor.
No suppression logic — the anchor IS the precedence mechanism. An abandoned
stream (agent death/timeout) resolves via `handle_agent_end`'s error path to an
honest failed-state alert persisted under the same identity.

**Scope**: the push-stream subsystem only (the one with `stream_id`s); the
legacy interval-polling path (orchestrator.py:7112-7182) is explicitly out of
scope (candidate for later retirement). The 052 narrative stream
(`narrative-<hex>` ids, orchestrator.py:4977) deliberately keeps its
identity-less ephemeral form — the turn's final render is its authoritative
replacement (5091-5098).

**Flag**: `FF_STREAM_ARTIFACTS` (default on, fail-open): any bridge failure
degrades to today's terminal-only delivery.

**Alternatives**: unify the stream and workspace dedup keys — rejected: they are
intentionally different spaces (sha256-raw vs sha1-canonical, probe 2
constraint); the bridge maps between them at subscribe without conflating them.

**Verification amendments (adversarial pass, 2026-07-13)**:
1. **Double-render refuted → keying rule**: today's terminal chunk is empty and
   natives keep the last streamed content under the `stream-<sid>` node
   (Streaming.kt:86, Streaming.swift:97, streaming.py:105-107), so a terminal
   `ui_upsert` under the workspace identity would render a SECOND copy. Fix:
   when a frame carries `component_id`, clients key the stream node by it FROM
   THE FIRST FRAME (no `stream-<sid>` node is ever created) — the terminal
   persist upsert then replaces in place. `stream_subscribed` also carries
   `component_id` so the placeholder is keyed the same way (else it orphans).
   Stale pre-055 native binaries would show a transient duplicate — acceptable:
   all first-party clients ship in the same PR (Constitution XII); noted as a
   rollout caveat.
2. **Android typed decode**: `Wire.kt:51-60`/`Messages.kt:73-81`
   (`Inbound.UiStreamData`) drop unknown fields — Android needs the
   `componentId` field added to its typed frames (Apple reads payload
   dynamically; Windows reads raw dicts; web reads JSON directly).
3. **Web morph mechanics**: `mergeStream` reuses `applyUpsert`'s machinery —
   `CSS.escape`d selector, fragment unwrap/`replaceWith` (the server fragment
   is itself wrapped in `data-component-id`, renderer.py:1296-1302 — naïve
   `innerHTML` would nest duplicate anchors), `processSideEffects` — plus
   `Plotly.purge` before replacing chart nodes; chart-bearing interim frames
   re-plot at most once per second (leak/flicker guard), final state on
   terminal.
4. **Subscription reality check**: no client sends `stream_subscribe` today —
   the only live `ui_stream_data` producer is the single-socket narrative path.
   The bridge therefore includes SERVER-SIDE subscription: the orchestrator
   auto-subscribes the originating socket (and co-viewing sockets of the same
   chat) when it dispatches a streaming-capable tool
   (`_dispatch_stream_request`, orchestrator.py:6878-6930 adjacency). The
   client `stream_subscribe` vocabulary stays for reattach.
5. **Third frame builder**: `_emit_narrative_frame` (orchestrator.py:5091-5128)
   deliberately does NOT gain `component_id` — narrative streams stay ephemeral
   with the final render as their authoritative replacement (their `doc_`
   routing on natives diverts to the chat rail, AppViewModel.kt:631-643).
6. **Watch**: renders stream frames as status text only (WatchModel.swift:
   344-347) — the terminal persist `ui_upsert` is the watch's delivery of
   streamed content; no watch client change needed.
7. **Retention state**: `handle_agent_end` receives an empty ToolStreamEnd —
   the bridge adds per-subscription retention of the last content-bearing chunk
   (new field on the subscription record) as the persist payload.

## D5 — Mid-stream narrative honesty: boundary-buffered incremental markdown

**Decision**: the FF_LLM_STREAMING narrative path renders each outbound chunk
server-side through the existing markdown pipeline, holding back a small tail
buffer up to the last "safe boundary" (whitespace outside unclosed `**`/`*`/
`` ` ``/`[` spans) so no frame ever ships a dangling markup token. The terminal
chunk flushes the buffer. Pure-Python tokenizer scan (~30 lines), no new deps.

**Rationale**: observed live — narrative rendered raw `You rolled **` mid-turn.
Spec FR-013: every visible frame is rendered-or-withheld. Buffering at most a few
words adds no perceptible latency at LLM token rates.

**Alternatives**: client-side incremental markdown — rejected (ES5 no-build web
layer has no markdown renderer; natives would need three more); render-partial-
as-literal — rejected (that is precisely the observed defect).

## D6 — Leaked tool-call stripping: extend the existing stripper to every delivery surface

**Decision**: the existing leak stripper + diagnostic (orchestrator.py:4152-4165)
becomes a shared `_strip_toolcall_leakage()` applied to (a) the chat narrative,
(b) the long-answer canvas doc-card promotion path (orchestrator.py:4334-4385 —
the path the observed `update_component<arg_key>…NEW_PAGE@true` leak rode into a
rendered Document card), and (c) `_generate_tool_summary` output. Patterns
extended to cover XML-ish pseudo-call syntax (`<arg_key>`, `<arg_value>`,
`NAME@true` attribute trains) alongside the current patterns. When stripping
empties the response, an honest fallback line replaces it and the incident is
logged with the raw payload for diagnosis (never rendered).

**Rationale**: observed live in this exact system; the model was attempting a
component update — the affordance D4/D10 make real — so leakage frequency should
drop, but the render surface must still never echo protocol syntax.

## D7 — Origin-independent designed canvases: design by content, deliver post-commit to natives

**Decision**: remove the originating-device gate on the designer
(orchestrator.py:7450-7461). The design pass runs whenever the *turn content*
qualifies (≥2 rich components, existing trigger), regardless of which device
sent the message. Delivery becomes per-receiver:
- **Web sockets**: unchanged (mid-turn `_push_canvas` full render, morph anchors).
- **Native sockets** (Windows/Android/iOS/macOS): the designed canvas is
  materialized server-side pre-ROTE (`_canvas_components`, orchestrator.py:
  7381-7416 — already produces plain container/card trees natives render) and
  pushed as an **out-of-turn authoritative full `ui_render` after
  `chat_status done`** — the one frame shape all native reducers treat as
  wholesale replace (AppViewModel.kt:610-621, AppModel.swift:551-553,
  app.py:362-444). This sidesteps the Android/Apple in-turn additive-overlay
  branch entirely.
- **Watch**: receives the same materialized canvas through its existing
  degradation profile; re-presented content stays speech-free (speak=False on
  re-pushes, preserving the no-re-speak contract).
Flat components still upsert FIRST on every target (fail-open invariant 052
FR-013/FR-022 untouched); designer failure = the refinement never arrives.

**Rationale**: the audit found the skip is latency-motivated, not structural —
natives already render materialized designed canvases on every `load_chat`
re-hydration (orchestrator.py:1786-1795) and via `_push_canvas` co-viewing
fan-out (7418-7431). The asymmetry violates Constitution XII(b) (layout parity
must key on ROTE capability, never on which client sent the message) and makes
persisted chat state origin-dependent (workspace_layout rows exist only for
web-origin turns).

**Flag**: `FF_DESIGNER_ALL_DEVICES` (default on; off restores the skip tuple).

**Alternatives**: teach native clients to resolve `ref` layout trees — rejected
(three client implementations + drift-guard surface for something the server
already materializes); standardize on flat-everywhere — rejected (regresses the
web experience and the thesis Direction C story).

**Verification amendments (adversarial pass, 2026-07-13)**:
1. **One coalesced pass at turn end for natives**: `_deliver_round_components`
   runs per tool round mid-loop; the native designed push is instead ONE
   designer pass over the turn's final canvas state, executed INLINE in
   `handle_chat_message` after the `chat_status done` send (orchestrator.py:
   4410-4414) and before the handler returns. Because turns are serialized
   per-socket under `_chat_locks` (2810-2821) and the next turn's ack is
   emitted inside the next handler, single-socket TCP ordering makes the
   done → designed-render → next-ack sequence race-free on the originating
   socket. (Also cheaper: one designer pass per native turn, not per round.)
2. **Suppress designer chatter on the post-done pass**: each designer pass
   emits `chat_status thinking "Designing your layout…"` (7488-7494) — sent
   after done this would flip natives back to turn-active with a stuck status.
   The post-done pass runs with progress frames suppressed (log-only).
3. **speak=False must be threaded**: `_push_canvas` calls `send_ui_render`
   without `speak=False` (7430-7431) — today this already latently speaks
   co-viewed designed canvases to watch sockets. The designed push (and
   `_push_canvas` generally) passes `speak=False` for re-presented content.
4. **Cross-socket/async stale guard**: the designed push carries the turn
   marker and is skipped server-side when a newer turn has started on that
   chat (the cross-socket race exists unsuppressed today; async-mode turns
   close via `task_completed`, not `done` — the async path sequences the
   designed push before `task_completed` is emitted).
5. **Doc-card exclusion**: Android/Apple reducers divert/drop `doc_` cards and
   Reasoning collapsibles from canvas frames (AppViewModel.kt:589-596,
   AppModel.swift:542-547) — the materialized designed canvas for native
   delivery excludes them server-side (never silently dropped client-side).
6. **Reinforcing evidence**: natives already receive designed canvases today
   via cross-socket `_push_canvas` fan-out and `load_chat` re-hydration
   (7423-7431, 1786-1793) — the skip tuple only ever guarded the originating
   socket, confirming origin-independence is a bug fix, not a capability leap.

## D8 — Workspace verb reconcile on natives: promote the 8 ack frames to handled

**Decision**: Windows, Android, and iOS/macOS promote the eight
`component_verbs` frames (`component_saved`, `component_save_error`,
`saved_components_list`, `component_deleted`, `combine_status`, `combine_error`,
`components_combined`, `components_condensed` — ui_protocol.json:20-34) from
*ignored* to *handled*: deletion/combine/condense results apply to the canvas as
identity-keyed remove/replace ops; list/status frames update the existing
native surfaces. Watch keeps them ignored (bounded scope, spec FR-020).
Disposition tables ×3 + parity-matrix rows updated in the same PR (drift guards
stay green).

**Rationale**: today an edit on one device reconciles on others only at the next
`load_chat` (natives reader, verified) — spec US3/FR-018 requires live
reconcile. The server already fans these frames to every socket; only client
dispositions change, no wire change.

## D9 — Provenance as a structured component field, stamped server-side

**Decision**: `_tag_source` (orchestrator.py:4009-4054) additionally stamps a
top-level `provenance` field on every delivered/persisted component dict:
`"grounded"` (subtree carries tool-sourced data — same derivation the web-only
footer uses today, renderer.py:1180-1251), `"estimated"`, or `"generated"`
(default when no source attribution). Stamping happens AFTER agent/designer
output is fixed, and the stamper overwrites any agent-supplied value — agents
and the designer structurally cannot upgrade trust (spec FR-026). Renderers:
web keeps its footer (now reading the field); Windows/Android/iOS/macOS add a
compact badge derived from the same field; watch inherits it through its list
degradation (text badge). ROTE treats `provenance` as a preserved field (never
stripped by host bounds). No manifest `component_types` change (it is a field,
not a type); parity-matrix note + client renderer updates ship in the same PR.

**Alternatives**: a `provenance` column on `saved_components` — rejected: the
value must travel the wire to natives and live in snapshots/exports; the
component dict already does all three. New badge primitive type — rejected:
`badge` exists; this is a field rendered within each component's chrome.

## D10 — Component-scoped refine + bounded version history

**Decision**:
- New accept action **`component_refine`** `{component_id, instruction}`
  (manifest `accept_actions` + three client disposition tables). Server handler
  lives beside `component_action` (orchestrator.py:7599-7733) and inherits its
  full gate sequence: timeline read-only guard, security-flag block, per-user
  permissions on the component's source agent/tool, per-user LLM gate (a refine
  is an LLM turn billed to the user), audit. Execution: a bounded single-purpose
  LLM call given the component's current dict + source context + the user's
  instruction, constrained to emit a same-type component (validated against
  `allowed_primitive_types()`), then force-upserted onto the same
  `component_id` (existing `force_component_id` pinning, workspace.py:264-278).
  Provenance re-stamps as `estimated` unless the refine re-ran the source tool.
- New table **`component_version`**: before any refine/restore overwrite, the
  prior component dict is archived (retain the most recent **5** versions per
  component; older rows pruned). New accept action **`component_restore`**
  `{component_id, version_no}` restores an archived version (archiving the
  current one first); same gates, audited.
- Affordances: web — footer buttons on the component chrome; natives — an
  overflow/context affordance on the component card. ROTE hosts with
  `supports_interactivity=False` never see the affordance (existing stripping).

**Rationale**: spec US4; `component_action` deliberately refuses free-form kinds
(orchestrator.py:7624-7636) — refine is a new, separately-gated verb, not a
loosening of the deterministic contract. Version history cannot ride
`workspace_snapshot` (whole-canvas, per-turn, read-only timeline semantics);
a small per-component table is the additive migration.

**Flag**: `FF_COMPONENT_REFINE` (default on; off = affordance absent, action
refused with honest error).

## D11 — Export + share: snapshot renditions, fail-closed sharing

**Decision**:
- **Table CSV export**: `GET /api/export/component/{component_id}.csv`
  (session-authed). Serves the stored rows when complete; when
  `total_rows > len(rows)` (paginated tables store one page), re-invokes the
  source tool through the existing deterministic `component_action` pipeline
  with full-range params — inheriting every permission gate — and streams the
  result as CSV (stdlib `csv`).
- **Canvas HTML export**: `GET /api/export/canvas/{chat_id}.html`
  (session-authed) — `render_workspace(components, layouts)` output embedded in
  a self-contained page (inline `astral.css` subset, no WS/JS, charts as static
  tables via the existing chart→table fallback ladder), stamped with provenance
  badges and generation date.
- **Share links**: new table **`share_grant`** (see data-model). Minting
  (`POST /api/share`) snapshots the rendition at mint time (component dict(s) +
  rendered standalone HTML) — a share NEVER reads live workspace rows.
  Token: 256-bit urlsafe secret; only its SHA-256 stored. Public route
  `GET /share/{token}` (no auth) serves the snapshot with
  `X-Robots-Tag: noindex` + `Cache-Control: private`; owner routes list/revoke
  (`GET/DELETE /api/share`). **PHI gate at mint, fail-closed**: the mint handler
  runs the existing PHI gate against the snapshot content and refuses on any
  hit. Audit events `share.minted`/`share.opened`/`share.revoked` (class
  `conversation`). Revocation is immediate (row flag checked per request).
- **Flags**: `FF_ARTIFACT_EXPORT` default **on** (authed, local download);
  `FF_ARTIFACT_SHARING` default **off** (fail-closed until the operator enables
  public serving).

**Rationale**: snapshot-scoped sharing bounds the public surface to token
validity (spec assumption); `render_workspace` already produces the HTML
(prims reader GAP-6: "nothing exposes it").

**Alternatives**: live share views — rejected (drags per-user workspace reads
behind an unauthenticated route); signed-URL blob storage — rejected (no object
store in the stack; Postgres row + rendered text is well within bounds).

## D12 — Feature flags, rollout, and byte-equivalence

| Flag | Default | Off-state |
|------|---------|-----------|
| `FF_FIRST_TURN_CONTRACT` | on | blanking frame + id-less welcome restored (byte-identical wire) |
| `FF_STREAM_ARTIFACTS` | on (fail-open) | today's `stream-<id>` ephemeral behavior |
| `FF_DESIGNER_ALL_DEVICES` | on | native skip tuple restored |
| `FF_COMPONENT_REFINE` | on | affordance absent; action refused honestly |
| `FF_ARTIFACT_EXPORT` | on | endpoints 404 |
| `FF_ARTIFACT_SHARING` | off (fail-closed) | mint/serve refused |

SC-009 (all-flags-off byte equivalence) is enforced by running the existing
suite + drift guards with every 055 flag forced off in one CI-visible test job
variant. Schema deltas (D10/D11 tables) are idempotent `_init_db` migrations
with documented rollback; they are inert when their flags are off.

## Resolved spec assumptions

- Six targets confirmed in scope; voice/AOM untouched except watch speech
  preservation (D1/D7).
- Artifact identity = existing four-rule contract, extended not altered
  (D4 assigns rule-2 fingerprints early; D10 pins via `force_component_id`).
- Version history = new bounded table (workspace_snapshot unsuitable — D10).
- Share = snapshot renditions (D11).
- Refine = normal LLM turn under the user's provider config (D10).
- Push-stream subsystem only (D4).
- Native manifest/disposition updates enumerated: 1 additive field
  (`component_id` on `ui_stream_data`), 2 accept actions (`component_refine`,
  `component_restore`), 8 disposition promotions ×3 clients, provenance
  render note — all same-PR with drift guards (Constitution XII).
