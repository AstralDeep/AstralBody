# 041 Android client — known issues & remaining work

**Status: functional but WORK IN PROGRESS.** The client signs in (mock/dev-token),
connects, lists/toggles agents, and renders many primitives natively. But the core
SDUI canvas experience is **not yet solid** and needs significant further work.
This note is intentionally honest so the next session (or reviewer) has the real
state, not an optimistic one.

## Top priority — SDUI canvas rendering & persistence (NOT fixed)
The headline problem is still open: **generated UI components do not reliably
persist / render correctly on the native canvas.**

What's understood so far:
- The orchestrator's per-turn UI lifecycle mixes `ui_upsert` (merge), full
  `ui_render` (replace), `ui_stream_data`, AND a long-narrative "Document" card —
  and the native client's flat `state.canvas` model can't faithfully reproduce the
  intended canvas from that stream. A later render can still clobber earlier rich
  components.
- The feature-029 **web UI-designer is now skipped for native device profiles**
  (server fix, `_deliver_round_components`) — this removed the ~150 s latency and
  the "designed web layout tree the native client can't draw" failure mode. It is
  an improvement but did **not** fully fix persistence; components still get
  replaced/disappear in some flows.

What likely needs to happen (design work, not a one-line fix):
- Define a **native canvas model** that treats the per-chat workspace as the source
  of truth (feature 028 `saved_components` / `ui_upsert` ops keyed by
  `component_id`) and **stops honoring full-canvas `ui_render` replaces** that drop
  identified components — i.e., reconcile by component identity rather than
  wholesale replace.
- Decide where the **narrative "Document" card** belongs (canvas vs the chat panel)
  so it doesn't visually compete with / replace the real tool output.
- Verify the materialized component **data** (chart series, table rows) actually
  arrives in a shape the native renderers parse — confirm charts/tables aren't
  rendering empty.
- Handle `ui_stream_data` terminal/finalize so streamed components settle into the
  same identity-keyed canvas.

## Other known gaps
- **Native layout is flat.** With the designer skipped, the client just stacks
  components. A native arrangement layer (grids/sections/responsive grouping) would
  make dashboards look intentional rather than a vertical list.
- **Chat model rough edges.** Empty/duplicate assistant turns in some flows; the
  chat-vs-canvas split of a turn's output needs a cleaner contract.
- **Renderers are first-pass.** Charts (Canvas-drawn) and several primitives
  (param_picker, file_upload/download, keyvalue/timeline/rating) are minimal; tables
  don't paginate; many need visual polish to match web/Windows.
- **Real Keycloak on-device unverified.** Only the debug `dev-token` (mock auth)
  path has been exercised end-to-end on the emulator. The real OIDC PKCE browser
  flow (`astral-mobile`) compiles and is wired but hasn't been run through to a live
  session on a device.
- **Reconnect/auth-required UX** is minimal; no surfaced loading/empty/error states.
- **Instrumented (Compose UI) tests are thin** and run only on emulator/nightly.
- **No physical-device pass** (emulator only; a real device needs the orchestrator
  bound to `0.0.0.0` + LAN IP, not `127.0.0.1`/`10.0.2.2`).

## Server-side notes (touched during this work, belong on `main`)
- `fix(orchestrator): in-process built-in agents invisible to tool-availability
  filter` — feature-040 regression; affected ALL clients (chat was text-only even
  with scopes enabled). Worth landing/verifying independently of the Android client.
- `fix(orchestrator): skip the web UI-designer for native clients` — see above.

## Environment notes for the next session
- Local run uses the emulator → orchestrator at `ws://10.0.2.2:8001/ws`
  (debug build auto-targets this; release targets `wss://sandbox.ai.uky.edu/ws`).
- `.env` has `USE_MOCK_AUTH=true` so the debug Dev sign-in (`dev-token` → mock
  `test_user`, admin) works; flip to `false` for the real Keycloak flow.
- All feature flags are currently ON in `.env`, which makes turns slow (designer,
  MoA debate, runtime supervisor, etc.) and `FF_HITL_HIGHRISK` can pause on egress.
