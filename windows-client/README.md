# AstralBody — Native Windows Client

A native Windows desktop client that renders the AstralBody orchestrator's
**server-driven UI (SDUI)** components as native Qt widgets — not a web view.

It is a real ROTE/webrender *target*: it consumes the structured `components`
that the orchestrator places on every `ui_render` / `ui_upsert` (the non-web wire
layer) and draws native PySide6 widgets for the SDUI primitive vocabulary (text,
card, table, list, tabs, metric, hero, badge, keyvalue, timeline, rating, alert,
button, code, charts, …). Unknown types degrade to a labeled placeholder.

## Architecture

```
Orchestrator (:8001)  ──WebSocket /ws──►  OrchestratorClient (asyncio thread)
   ui_render/ui_upsert {components}            │  Qt signal
   chat_status / chat_created                  ▼
                                          MainWindow  ──►  renderer.render(dict) ─► native QWidget
   ◄── ui_event (chat_message, button       (chat rail + SDUI canvas)
        actions, load_chat, …) ──────────────┘
```

- `astral_client/protocol.py` — WebSocket client (connect, `register_ui` with
  token + device caps, message loop, `ui_event`/`chat_message` out).
- `astral_client/renderer.py` — structured component dict → native `QWidget`.
- `astral_client/charts.py` — bar/line/pie via QtCharts.
- `astral_client/app.py` — main window (chat rail + canvas) and message wiring.
- `astral_client/theme.py` — dark palette mirroring the web app.

## Run (dev)

Requires a running orchestrator. For local dev set the orchestrator to mock auth
(`USE_MOCK_AUTH=true`, `ASTRAL_ENV=development`) so the `dev-token` is accepted.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python main.py                 # connects to ws://127.0.0.1:8001/ws as dev-token
# or:
.venv/Scripts/python main.py --url ws://HOST:8001/ws --token <JWT>
```

Env overrides: `ASTRAL_WS_URL`, `ASTRAL_TOKEN`.

## Build the .exe

```bash
.venv/Scripts/python -m pip install pyinstaller
.venv/Scripts/pyinstaller --noconfirm AstralBody.spec
# → dist/AstralBody.exe  (single-file, no console)
```

## Tests

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m pytest -q tests/test_renderer.py
# live end-to-end against a mock-auth orchestrator:
QT_QPA_PLATFORM=offscreen .venv/Scripts/python tests/e2e_live.py --prompt "roll 3 dice"
```

## Auth

- **Dev**: `dev-token` against a mock-auth orchestrator.
- **Production**: obtain a Keycloak access token via OIDC Authorization-Code +
  PKCE (RFC 8252) with a loopback redirect, and pass it via `--token` /
  `ASTRAL_TOKEN`. This requires a new public Keycloak client (`astral-desktop`)
  and relaxing the orchestrator's single-`azp` check to a configurable
  allow-list. (Not yet implemented — tracked as a follow-up.)

## Scope / status

MVP: chat → keyless agent → native SDUI canvas, in-place `ui_upsert` updates,
button/history interactions. **Not yet**: app *chrome* (settings/modals/agent
management) — those are server-rendered HTML (`chrome_render`) and would need an
embedded WebView2 or native reimplementation; native OIDC; streaming primitives.
