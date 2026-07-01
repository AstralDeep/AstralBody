# 041 Android client — known issues & remaining work

> **UPDATE — feature 044 (2026-07-01):** The headline defects in this note were
> fixed and verified under feature 044 (see `specs/044-native-client-parity/` and
> its `verification/results.md`): the SDUI canvas clobber, reconnect/auth-required
> UX, table pagination, error/empty/loading states, and markdown links. Resolved
> items are marked inline below; genuinely-open items (physical-device pass, a
> native arrangement layer, chat-turn rough edges) are left as-is. Note the
> `DevAuth`/`dev-token` debug path was **removed in 044** — the app now signs in via
> Keycloak OIDC (AppAuth PKCE) only.

**Original 041 status (historical): functional but WORK IN PROGRESS.** The client
connected, listed/toggled agents, and rendered many primitives natively, but the
core SDUI canvas experience was not yet solid. This note is intentionally honest so
the next session (or reviewer) has the real state, not an optimistic one.

## Top priority — SDUI canvas rendering & persistence — RESOLVED (feature 044)

**RESOLVED in feature 044 (T025).** The out-of-turn full `ui_render` now reconciles
by component identity via `Canvas.apply` instead of a wholesale replace, so a later
render no longer clobbers earlier rich components (`CanvasClobberTest`; live scenario
2.5 in the 044 verification results, corroborated by the backend
`test_canvas_full_render` guarantee). The identity-reconciliation design sketched
below is essentially what shipped. Historical analysis retained for context:

~~The headline problem is still open: **generated UI components do not reliably
persist / render correctly on the native canvas.**~~

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
  (param_picker, file_upload/download, keyvalue/timeline/rating) are minimal; many
  need visual polish to match web/Windows. (**Tables now paginate** — resolved in
  044, T027.)
- **Real Keycloak full chat not yet driven autonomously.** `DevAuth`/`dev-token`
  was removed in 044, so Keycloak OIDC PKCE (`astral-mobile`) is now the *only*
  sign-in path. The app screens, chrome, and renderers are verified live on the
  emulator via the 10 instrumented Compose tests, and the identical server contract
  is exercised live on web + Windows. A full logged-in chat over *real* Keycloak on
  the emulator was not driven autonomously (credential entry is out of bounds — see
  044 Defect Register D-032); a manual/physical-device pass remains.
- **Reconnect / auth-required UX + loading/empty/error states — RESOLVED (044).**
  Reconnect uses 1→30 s exponential backoff with a bounded outbound queue and a
  disconnected banner (T014); cold-start / `auth_required` refresh failure routes to
  the sign-in screen (T016; live scenario 1.3); server errors surface a banner and
  fail the turn (T012); settings surfaces show a 10 s bounded skeleton → error+Retry
  (T039).
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
- The Android client no longer has a `dev-token`/mock sign-in (removed in 044), so
  the emulator now signs in via the real Keycloak OIDC browser flow regardless of the
  server's `USE_MOCK_AUTH` (web/Windows still accept `dev-token` under mock auth).
- All feature flags are currently ON in `.env`, which makes turns slow (designer,
  MoA debate, runtime supervisor, etc.) and `FF_HITL_HIGHRISK` can pause on egress.
