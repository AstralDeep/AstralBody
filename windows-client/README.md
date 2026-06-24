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

- **Dev**: `dev-token` against a mock-auth orchestrator (`--token dev-token`, the
  default when no authority is configured).
- **Real Keycloak (OIDC)**: set `--authority <realm-url>` (or `KEYCLOAK_AUTHORITY`)
  and the app runs **Authorization-Code + PKCE with a loopback redirect** (RFC
  8252) — it opens the system browser, you log in, and the token is used for
  `register_ui`; it silently refreshes on expiry. An explicit `--token` always
  wins.

By default the desktop uses its own **dedicated public Keycloak client**,
`astral-desktop` (the by-the-book native-app posture, RFC 8252 / OAuth 2.0 for
Native Apps): the browser does PKCE, then the app exchanges the auth code and
refreshes tokens **directly against Keycloak** — it holds no secret and does not
depend on the orchestrator's BFF, and the web/desktop auth surfaces stay
isolated. The orchestrator accepts the desktop client's `azp` via its
`KEYCLOAK_ALLOWED_AZP` allow-list. Override the client id with `--client-id` /
`ASTRAL_CLIENT_ID`.

**One-time Keycloak setup** (create the public client + add it to the
allow-list): see [`docs/keycloak-windows-client-setup.md`](../docs/keycloak-windows-client-setup.md).

```bash
.venv/Scripts/python main.py --authority https://iam.example.com/realms/Astral
# (uses client astral-desktop, direct token exchange)
```

**Legacy BFF reuse** (no dedicated client): pass `--bff` (or `ASTRAL_AUTH_BFF=1`)
to reuse the web's confidential `astral-frontend` client by proxying the token
exchange through the orchestrator's `POST /auth/token`. This requires the
`http://127.0.0.1/*` loopback redirect on the `astral-frontend` client and is
kept only for environments that have not provisioned `astral-desktop` yet.

```bash
.venv/Scripts/python main.py --authority https://iam.example.com/realms/Astral \
    --client-id astral-frontend --bff
```

## Windows tools agent (client-hosted)

The app hosts a small **A2A agent in-process** (`win_agent/`) that exposes
Windows-specific tools to the orchestrator, so the assistant can act on this PC:
`get_system_info`, `read_clipboard`, `write_clipboard`, `notify` (native toast),
`open_path` (file/folder/URL), `list_directory`. Results render natively.

On connect, the client registers the agent at `http://host.docker.internal:8771`
(the orchestrator runs in Docker and reaches the host that way). Override with
`ASTRAL_AGENT_HOST` / `WIN_AGENT_PORT`; disable with `ASTRAL_WIN_AGENT=0`. The
agent can also run standalone: `python -m win_agent.agent --port 8771`.

The agent registers with the orchestrator's `AGENT_API_KEY` when set (required
outside dev; dev mode is keyless).

## Scope / status

Working: real Keycloak OIDC (dedicated public client, silent refresh) → chat →
agents → native SDUI canvas, in-place `ui_upsert` updates, button/history
interactions, client-hosted Windows tools agent. **In progress**: app *chrome*
(settings/modals/agent management). The web app renders these as server HTML
(`chrome_render`); this client reimplements them as **native Qt widgets** —
see "Native-only" below. Streaming primitives are still TODO.

## Native-only (no embedded web browser)

This client is 100% native: every surface is a Qt widget. There is **no
WebView2 / QtWebEngine** anywhere (the PyInstaller build even excludes those
modules), and we do not embed the web app's HTML.

- **SDUI canvas + chat** → native widgets via `renderer.py`.
- **App chrome** (settings, agent management, modals) → native Qt
  reimplementation driven by the same WS events as the web chrome — *not* an
  embedded HTML view.
- **OIDC login** → the **system** browser (RFC 8252 external user-agent), which
  is the correct, more secure native pattern; it is the OS browser, **not** an
  in-app embedded web view. The app never sees your Keycloak password.
