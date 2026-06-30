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
`open_path` (file/folder/URL), `list_directory`, plus the **coding tools**
(`read_file`, `write_file`, `edit_file`, `run_command`, `run_shell`). Results
render natively.

On connect, the client registers the agent at `http://host.docker.internal:8771`
(the orchestrator runs in Docker and reaches the host that way). Override with
`ASTRAL_AGENT_HOST` / `WIN_AGENT_PORT`; disable with `ASTRAL_WIN_AGENT=0`. The
agent can also run standalone: `python -m win_agent.agent --port 8771`.

The agent registers with the orchestrator's `AGENT_API_KEY` when set (required
outside dev; dev mode is keyless).

### Coding agent (feature 067)

The coding tools let the assistant **generate, write, edit, and run code on your
machine**. They are gated by three independent safety layers:

1. **Workspace confinement.** Every file tool operates only inside
   `ASTRAL_WORKSPACE_DIR` (default `~/AstralWorkspace`). Path traversal
   (`../`) and absolute paths outside the workspace are refused; symlinks that
   escape are resolved and refused.
2. **Per-tool permissions.** Each tool declares a scope (`tools:read`,
   `tools:write`, `tools:execute`); you enable them one-by-one under
   **Agents & permissions**, exactly like every other agent. With nothing
   enabled, every coding tool is refused.
   - `read_file` / `list_directory` → `tools:read`
   - `write_file` / `edit_file` → `tools:write`
   - `run_command` → `tools:execute` — runs a **whitelisted** dev command
     (`git`, `python`, `pip`, `npm`, `cargo`, `go`, …) inside the workspace,
     bounded timeout + output cap.
3. **Dangerous bypass (off by default).** `run_shell` gives **full arbitrary
   shell access** (any command, any directory). It is only advertised when
   `ASTRAL_DANGEROUS_BYPASS=1` is set, and each call still requires a native
   confirmation showing the exact command. It is always audited as
   `dangerous_bypass`.

**PHI safety (fail-closed).** Every `read_file` / `list_directory` / `run_command`
/ `run_shell` result is run through a client-side PHI pre-filter
(`astral_client/phi_gate.py`, the same patterns as the orchestrator's gate)
**before** it is returned to the orchestrator/model. If PHI is detected, the
result is refused — it never leaves your machine. If the check itself errors,
the result is treated as PHI and refused (fail-closed).

**Audit (every action).** Each tool call is recorded in an append-only,
hash-chained JSONL log at `%APPDATA%/AstralBody/audit.log` (`astral_client/
audit_log.py`): timestamp, actor, tool, redacted args, outcome
(`success`/`refused`/`phi_blocked`/`error`), and correlation id. The
orchestrator records its own `tool` audit event too, so actions are double-
audited.

### Integrity verification (feature 067)

When you download the app from a GitHub Release, the client verifies it **before
it ever runs** (`astral_client/integrity.py`):

1. resolves the latest release, downloads `AstralBody.exe` + `SHA256SUMS` +
   `cosign.bundle`;
2. checks `sha256(exe) ==` the manifest entry;
3. verifies the **sigstore** (keyless) signature, asserting the signing
   identity is the `AstralDeep/AstralBody` GitHub Actions workflow;
4. only then launches/replaces the binary.

A tampered exe, a bad hash, or an unverifiable signature ⇒ the download is
deleted and refused. Offline on an update check, the current already-verified
binary keeps running (an unverified download is never executed).

Releases are built and signed by [`.github/workflows/release-windows.yml`](../.github/workflows/release-windows.yml)
(fires on `v*` tags).

| Env | Default | Purpose |
|-----|---------|---------|
| `ASTRAL_WORKSPACE_DIR` | `~/AstralWorkspace` | Workspace confinement root |
| `WIN_CMD_TIMEOUT` | `60` | `run_command` timeout (s) |
| `WIN_CMD_MAX_BYTES` | `1048576` | `run_command` output cap |
| `ASTRAL_DANGEROUS_BYPASS` | unset | Enables `run_shell` (full shell) |
| `DESKTOP_RELEASE_REPO` | `AstralDeep/AstralBody` | GitHub repo for releases |

## Scope / status

Working: real Keycloak OIDC (dedicated public client, silent refresh) → chat →
agents → native SDUI canvas, in-place `ui_upsert` updates, **live push
streaming** (`ui_stream_data` frames rendered in place on the canvas),
button/history interactions, client-hosted Windows tools agent, and native app
*chrome* dialogs: Agents & permissions, History, and the **Audit log** (a
read-only `/api/audit` viewer with event-class / outcome / keyword filters and
cursor pagination). The web app renders chrome as server HTML (`chrome_render`,
which this client acknowledges but never embeds — there is no web view); the
native Qt reimplementations are the parity path (see "Native-only" below).
**In progress**: the remaining settings surfaces (LLM, personalization, theme,
attachments, drafts), each driven by its existing REST/WS data action.

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
