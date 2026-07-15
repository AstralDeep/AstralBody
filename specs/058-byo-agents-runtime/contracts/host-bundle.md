# Contract: BYO host bundle + parent↔child transport (T008 / T012)

**Status**: authoritative for feature 058. Resolves the 057 `_bundle_files` TODO
("the exact shape is finalized against the live generator during host integration").

This contract is the seam between two independently-built halves:

- the **orchestrator** (`agent_generator.py` → `agent_authoring.py` → `agent_bundle_deliver`), and
- the **desktop host** (`windows-client/` supervisor + worker child process).

Both build to *this document*, not to each other.

---

## 1. Why the bundle is NOT a `BaseA2AAgent`

Today's generator emits three files that hard-target the **backend package layout**:
`sys.path.insert(0, ../..)` → `from shared.base_agent import BaseA2AAgent`.

That is unusable on a desktop host, for two independent reasons:

1. **Dependency mass.** `BaseA2AAgent` transitively imports fastapi, uvicorn, the a2a-sdk
   (×3 modules), pydantic and `cryptography`. The Windows client ships none of them
   (`windows-client/requirements.txt`), and Constitution V forbids adding them.
2. **Inverted topology.** `BaseA2AAgent.run()` *starts a uvicorn server* and waits for the
   orchestrator to dial **in** (`base_agent.py:712`). A desktop host behind NAT must dial
   **out**. It is the wrong shape, not merely a heavy one.

The repo already contains the proof that the real protocol surface is small:
`windows-client/win_agent/agent.py` ("No dependency on the backend package") implements the
whole agent contract in ~140 lines of plain dicts.

**Decision (T008):** the generator emits a **self-contained bundle**. The only third-party
import is `astralprims` (first-party, pip-installable, added to the client as a client-only
dependency — same posture as `sigstore`).

---

## 2. Bundle shape

`agent_bundle_deliver.files` is a flat `{filename: source}` dict containing **exactly**:

| File | Author | Purpose |
|---|---|---|
| `mcp_tools.py` | LLM (unchanged from today's generator) | `TOOL_REGISTRY = {name: {"function", "description", "input_schema", "scope"}}`, optional `REQUIRED_CREDENTIALS`. Imports `astralprims`. |
| `agent_main.py` | deterministic template | self-contained stdio runner (§3). Imports `mcp_tools` as a **sibling module**, never `shared.*`, never `agents.*`. |
| `manifest.json` | deterministic | `{"agent_id", "agent_name", "description", "constitution_version", "generated_at"}` — the host's record of what it was handed. |

**Hard rules** (assert these in tests):

- No file in the bundle may contain `from shared` , `import shared`, `from agents.` or
  `sys.path.insert`.
- `agent_main.py` bakes the **owner-namespaced** `agent_id` handed down from
  `agent_authoring.slug_agent_id()` — i.e. `ua-<name>-<ownerhash>`, **not** `<slug>-1`.
  A mismatch here is refused fail-closed by `user_agents.authorize_registration()` and is
  invisible on the wire (see §6).

---

## 3. Parent ↔ child transport: **JSON lines over stdio**

The child process does **not** hold a socket. The authenticated UI WebSocket belongs to the
client; the client is a **dumb pipe**.

```
orchestrator  ──ws(agent_tunnel)──►  Qt client  ──stdin(json lines)──►  child process
              ◄─ws(agent_tunnel)───             ◄─stdout(json lines)──
```

- **child → parent**: one JSON object per line on **stdout**, `flush=True`. These are the
  *agent-channel frames the orchestrator already speaks*: `register_agent`, `mcp_response`,
  and optionally `tool_progress` / `tool_stream_data` / `tool_stream_end`.
- **parent → child**: one JSON object per line on **stdin** — `mcp_request` frames unwrapped
  from the tunnel envelope.
- **stderr** is diagnostics only. The parent captures it for the log; it is never relayed.

Anything on stdout that is not valid JSON is **discarded with a warning** (a stray `print()`
in LLM-written tool code must not corrupt the channel).

The parent relays verbatim — it does not parse, rewrite, or validate agent frames. This keeps
the trust boundary honest: re-verification happens at the **orchestrator** (untrusted-at-the-
boundary), not on the user's own machine.

### `agent_main.py` behavior

1. On start: emit `register_agent` (card built from `TOOL_REGISTRY`).
2. Loop over `sys.stdin`: parse an `mcp_request`, dispatch, emit an `mcp_response` echoing
   `request_id` **verbatim** (an unknown id is dropped server-side, `orchestrator.py:1486`).
3. `tools/list` → the skills array. `tools/call` → the tool fn; unknown tool → JSON-RPC
   `-32601`, raised exception → `-32603` (mirrors `win_agent/agent.py:98-139`).
4. A tool returning `{"_ui_components": [...], "_data": ...}` maps to
   `mcp_response.ui_components` + `result`.
5. EOF on stdin → exit 0. The child dies with its parent; there is no server-side fallback.

---

## 4. Worker entry (frozen-safe)

T012 requires a **separate, client-supervised child process** — not a thread.

The parent re-invokes **itself**:

```python
subprocess.Popen([sys.executable, "--byo-worker", <agent_dir>], ...)
```

- Under plain python `sys.executable` is `python.exe` — so `main.py` must accept the flag.
- Under PyInstaller onefile (`AstralDeep.spec`: `console=False`) `sys.executable` **is
  `AstralDeep.exe`**. The flag branch must therefore be handled in `main.py`
  **before Qt is imported or a QApplication is constructed**, or every worker spawns a GUI.

`main.py`:

```python
if "--byo-worker" in sys.argv:
    from win_agent.byo_worker import run_worker   # no Qt import on this path
    raise SystemExit(run_worker(sys.argv[sys.argv.index("--byo-worker") + 1]))
```

`astralprims` must be listed in `AstralDeep.spec` `hiddenimports` (the frozen exe is the
worker's interpreter, so the bundle's imports must resolve inside it).

---

## 5. Host lifecycle

| Event | Host action |
|---|---|
| `agent_bundle_deliver` | write files under `%LOCALAPPDATA%/AstralDeep/agents/<agent_id>/`, then spawn the worker |
| child emits `register_agent` | wrap in `agent_tunnel` ui_event, send over the UI socket |
| `agent_tunnel` push (mcp_request) | write the inner frame to the child's stdin |
| `agent_stop` push | terminate the child, remove routing |
| UI socket reconnect | **re-send each running child's `register_agent`** — the server pops `self.agents[agent_id]` on teardown |
| client close (`closeEvent`) | terminate every child; agents go honest-offline |
| child exits unexpectedly | log; do **not** auto-respawn in v1 (offline is honest) |

---

## 6. The silence trap (must be designed around)

A refused registration is **total silence to the host**. On refusal the orchestrator calls
`websocket.close(1008, ...)`, but that `websocket` is a `TunnelSocket` whose `close()` is a
**parity no-op returning `None`** (`shared/local_transport.py:88`). Over-cap frames are
likewise dropped with a server-side log only. **There is no NAK frame in the protocol.**

Therefore the host **must** treat "no `agent_registered` within N seconds of tunnelling
`register_agent`" as a failure, surface it to the user, and reap the child. Do not wait
forever on a frame that will never come.

(Adding a `host_status` / NAK frame is deferred: it requires a `ui_protocol.json` entry in the
same PR or the cross-client drift guards fail. Tracked with T004's unfinished heartbeat half.)

---

## 7. Envelope reference (server, already implemented)

- **C→S** is a `ui_event` **action**:
  `{"type":"ui_event","action":"agent_tunnel","payload":{"agent_id":"…","frame":"<JSON string>","host_session_id":"…"}}`
- **S→C** is a bare **push**:
  `{"type":"agent_tunnel","agent_id":"…","frame":"<JSON string>"}`
- `frame` is a JSON **string** in both directions (the server tolerates a nested object inbound).
- `AGENT_API_KEY` is **not** used on this path. Authority is the owner's authenticated UI
  session (`TunnelSocket.owner_sub`), never anything the frame presents.
- Ingress cap: 50 frames/owner/second (`BYO_TUNNEL_MAX_FRAMES_PER_S`); over-cap frames are
  silently dropped. Do not chatty-poll.
