# Phase 0 Research: FastAPI-Delivered UI & `astralprims`

All decisions below were resolved from the codebase, the published `astralprims` 0.1.0 package, and the
user's plan directive ("use astralprims as the primitives; replace the frontend with FastAPI; use ROTE to
adapt to the device"). No open `NEEDS CLARIFICATION` remain.

## D1 — Adopt `astralprims` as the primitive/structured layer

**Decision**: `pip install astralprims` (0.1.0) and delete `backend/shared/primitives.py`. astralprims is the
canonical structured representation (the primitive dict/JSON tree — FR-003, FR-018).

**Rationale**: The published package (authored by the project owner; Apache-2.0) is a near field-for-field
port of the current catalog. Verified parity of all 25 types and their fields:
- Layout: `Container`, `Card`, `Grids`/`Grid`, `Tabs`(+`TabItem`), `Collapsible`, `Divider`
- Content: `Text`, `Button`(+`payload`), `Input`, `ParamPicker`(fields/submit_message_template), `Image`,
  `CodeBlock`(type `code`), `Alert`, `ProgressBar`(type `progress`), `MetricCard`(type `metric`), `List_`, `Table`
- `Table` carries the full pagination + re-invocation set: `total_rows`, `page_size`, `page_offset`,
  `page_sizes`, `source_tool`, `source_agent`, `source_params` ✅
- Charts: `BarChart`, `LineChart`, `PieChart`, `PlotlyChart`(+`ChartDataset`)
- Media/IO: `Audio`(src/contentType/autoplay/loop/showControls/…), `FileUpload`, `FileDownload`
- Theming: `ColorPicker`, `ThemeApply`
- `create_ui_response(...)` returns the **identical** envelope `{"_ui_components": [...], "_data": None}`.

**Wire-format differences to reconcile** (the only migration friction):
- Base styling field is **`css`** (astralprims) vs **`style`** (old). `style=` is used in exactly **one**
  agent file (`agents/connectors/mcp_tools_creative.py`) → mechanical change to `css=`. ROTE's adapter does
  **not** reference `style` at all, so device adaptation is unaffected.
- astralprims adds `class_name`→`class` and a free-form `attributes` escape hatch (additive; safe).
- astralprims is **Pydantic-based** and uses **Pydantic v2** APIs (`model_serializer`, `ConfigDict`). Pydantic
  v2 is already present transitively via FastAPI (`fastapi>=0.100`) — no new dependency — but the migration
  MUST confirm the resolved `pydantic` is v2 and that no other dependency (e.g., `a2a-sdk`) pins v1; a v1/v2
  clash would break astralprims at import. Construction now raises on malformed primitives (a correctness
  improvement; watch for tests that built invalid primitives).

**Alternatives considered**: Keep `shared/primitives.py` (rejected — contradicts the explicit goal); fork the
package in-repo (rejected — duplicates a maintained first-party package).

## D2 — Web renderer lives in the FastAPI backend (`backend/webrender/`)

**Decision** (user-selected): Build the HTML renderer as a new backend module that consumes ROTE-adapted
astralprims dicts and emits HTML/CSS/JS. astralprims stays schema-only.

**Rationale**: 0.1.0 ships no renderer by design. The user directed "replace the frontend with FastAPI on the
backend." Keeping the renderer + Astral theme in-repo co-locates it with ROTE and the orchestrator, and
avoids coupling delivery to a separate package release. Implemented as **pure-Python render functions** with explicit `html.escape` (escape-by-default) —
one render function per primitive type in `backend/webrender/renderer.py`, mirroring the old `frontend/src/registry.tsx` mapping. Visual parity uses self-hosted Tailwind + Plotly.

**Constitution note**: Matches **Principle II as amended in v2.0.1** — astralprims **defines**, the
orchestrator **renders** (`backend/webrender/`), ROTE **adapts**. No deviation. Renderer is isolated so a
future target is a sibling renderer (FR-011, SC-005).

**Alternatives considered**: Renderer inside astralprims 0.2.0 (rejected for this feature — cross-repo
release coupling); hybrid render-interface-in-package + web-renderer-in-app (viable future path, deferred).

## D3 — Reuse the existing WebSocket protocol; server sends rendered HTML fragments

**Decision**: Keep the orchestrator WebSocket protocol (`shared/protocol.py`): `register_ui` (with `device`),
`ui_render`, `ui_update`, `ui_append`, `ui_stream_data`/`tool_stream_end`, action/`chat` messages,
`chat_step`, `tool_progress`, `audit_append`, etc. The server-side change is *what* travels: instead of the
client mapping dicts to React, the server renders dicts → HTML fragments (after ROTE) and sends those; the
client swaps them into the DOM.

**Rationale**: The protocol, ROTE integration (`send_ui_render` → `rote.adapt`), streaming-by-`stream_id`,
auto-save, chat-steps, audit streaming, and device re-adaptation on viewport change are all already built and
tested. Re-rendering server-side is the smallest change that preserves every surface at parity (FR-008).
Fragments may be sent as HTML strings (new field) alongside or instead of `components`; the structured
`components` dicts remain on the wire for programmatic/non-web consumers (FR-018).

**Alternatives considered**: Full HTTP page-per-turn (rejected — loses streaming/no-reload, SC-007);
HTMX-over-WebSocket library (rejected — new dependency; a ~150-line vanilla client suffices).

## D4 — Thin browser client (vanilla JS), no build step

**Decision**: A small hand-written `client.js` (served via FastAPI `StaticFiles`) opens the WebSocket, detects
+ reports device capabilities in `register_ui` (porting `detectDeviceType`/`detectDeviceCapabilities` from the
old `useWebSocket.ts`), swaps incoming HTML fragments into canvas/chat regions, merges streamed chunks by
`stream_id`, and posts user actions (button/form/pagination/upload/theme) back over the socket. A static
`shell.html` (served with the session token substituted in) is the only full page.

**Rationale**: Preserves interactivity round-trips (FR-012) and streaming (SC-007) without React or a bundler
(FR-001, SC-004). Charts use self-hosted Plotly (already used today) loaded as a static asset.

**Alternatives considered**: React kept "just for interactivity" (rejected — defeats the feature); zero-JS
(rejected — cannot meet streaming/interaction parity).

## D5 — Device adaptation: ROTE unchanged

**Decision**: Reuse `backend/rote/` as-is. `Orchestrator.send_ui_render()` calls `ROTE.adapt(ws, dicts)`
before rendering; the renderer consumes the adapted dicts. `register_ui.device` still builds the
`DeviceProfile`; viewport-change re-adaptation still works (re-render the cached adapted dicts).

**Rationale**: ROTE already adapts dicts per device (browser/tablet/mobile/watch/tv/voice) and has no `style`
coupling. This is exactly "use ROTE to adapt the output to whatever device is connected." Ordering is
**adapt → render** so each target renders from its already-appropriate dict tree.

## D6 — Authentication moves server-side (Keycloak OIDC code flow)

**Decision**: Replace the SPA `oidc-client-ts`/`react-oidc-context` flow with a server-side OIDC
Authorization-Code flow in FastAPI (login/callback/logout routes + a server session), preserving the WS
`register_ui.token`/`session_id` contract and the 365-day persistent-login semantics + audit events from
feature 016 (`auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed`).

**Rationale**: Removing the SPA removes its client-side auth module (FR-009). Keycloak is retained
(Constitution VII). Server-side code flow is the standard replacement and keeps tokens out of the browser.

**Alternatives considered**: Keep client-side OIDC in `client.js` (rejected — reintroduces SPA-style auth and
token handling in the browser; server-side is safer and simpler for a server-rendered app).

## D7 — Output safety: escape-by-default (FR-017)

**Decision**: explicit `html.escape` on all primitive text by default (pure-Python renderer). Raw HTML only via a narrow opt-in: the
markdown/code path runs through `webrender/sanitize.py` (allowlist sanitizer). No primitive injects
unescaped untrusted content by default.

**Rationale**: Implements the clarified security posture (SC-008); matches React's prior auto-escaping. The
project is HIPAA-adjacent, so default-safe rendering is mandatory.

## D8 — Build/deploy simplification & test migration

**Decision**: Delete `frontend/`; drop the Node/Vite build stage from `Dockerfile`; remove the `:5173`
static server (`start-docker.sh`) and its compose mapping; serve the shell + static assets + WS from `:8001`.
Add `astralprims` to `backend/requirements.txt`. Re-express the React/Vitest parity intent as backend
renderer golden-HTML tests + protocol tests + a real-browser end-to-end parity pass (FR-016, Constitution X).

**Rationale**: One deployable, no build step (SC-004). Removing the SPA also removes its test suite; parity
must be re-proven against the new delivery path.

## D9 — Install via pip; update Docker/compose; test-gated `frontend/` deletion (operator directives)

**Decision**:
- **pip**: add `astralprims` to `backend/requirements.txt` (so `pip install -r backend/requirements.txt`
  pulls it in dev and in the Docker image, line 53 of `Dockerfile`). No vendoring.
- **Dockerfile**: remove **Stage 1 (frontend-builder, Node 20)** entirely, the `COPY --from=frontend-builder
  /app/frontend/dist …` (line 67), and `EXPOSE … 5173` (keep 8001). The final image is backend-only.
- **docker-compose.yml**: remove the `"127.0.0.1:5173:5173"` port mapping (line 54); keep `8001`. No other
  service changes (postgres unchanged).
- **start-docker.sh**: remove the `python3 -m http.server 5173 --directory /app/frontend/dist &` line
  (lines 5–6). The shell + static assets are now served by the orchestrator on `:8001`.
- **Cutover ordering**: `frontend/` and `backend/shared/primitives.py` are deleted **only after** the full
  test suite + real-browser parity pass are green (Phase 3 gate in plan.md). Until then both remain for safe
  rollback. The Docker/compose edits land with the cutover so no image ever expects a missing `dist/`.

**Rationale**: Directly implements the operator's instructions; one deployable on `:8001` (SC-004); the
test-gate honors "if tests pass then you can delete the frontend directory" and keeps the branch revertible
until parity is proven (Constitution X).

**Alternatives considered**: Delete `frontend/` up front (rejected — removes the rollback path before parity
is proven); keep `:5173` serving a placeholder (rejected — pointless once the UI is on `:8001`).

## Open risks (carried into tasks)

- **Charts/Plotly fidelity** server-rendered: PlotlyChart still renders client-side via the self-hosted
  Plotly asset fed by the dict — verify parity for all 4 chart types and the ROTE chart→metric degradation.
- **Streaming DOM merge**: replicating fiber-stable chunk merging (`useWebSocket.ts` stream merge) in
  `client.js` without React identity — design the fragment swap to key by `stream_id`/component index.
- **Auth session edge cases**: persistent-login resume + offline sign-out queue semantics (016) must be
  re-validated under the server-side flow.
- **Pydantic strictness**: primitives that previously accepted loose input now validate — audit agent call
  sites and tests.
