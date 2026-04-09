# Quickstart: Add a Streaming Tool to AstralBody

**Feature**: 001-tool-stream-ui
**Audience**: A developer who wants to make a tool produce real-time updates that show up in a UI component without the user re-asking.

This is the fast path. It assumes the implementation from this feature has already landed (`FF_TOOL_STREAMING=true`). For the design rationale, read [research.md](research.md). For the wire protocol, read [contracts/protocol-messages.md](contracts/protocol-messages.md).

---

## Prerequisites

- A working AstralBody dev environment: `cd backend && .venv/Scripts/python.exe start.py` brings up the orchestrator on `ws://localhost:8001/ws` and at least the agents you care about on 8003+.
- The frontend running via Vite (`cd frontend && npm run dev`).
- An existing agent in `backend/agents/<your_agent>/` with at least one non-streaming tool already working. If you don't have one, copy `backend/agents/weather/` as a template.

---

## Step 1 — Mark a tool function as streaming

Open your agent's `mcp_tools.py` and add a new tool. The minimal change vs. a normal tool is: use `@streaming_tool` (not `@tool`), make the function `async def`, and **`yield`** `StreamComponents` objects in a loop.

```python
# backend/agents/weather/mcp_tools.py
import asyncio
from typing import AsyncIterator
from backend.shared.stream_sdk import streaming_tool, StreamComponents

@streaming_tool(
    name="live_temperature",
    description="Live temperature for a location, updated every few seconds.",
    input_schema={
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "interval_s": {"type": "integer", "minimum": 1, "maximum": 60},
        },
        "required": ["lat", "lon"],
    },
    max_fps=10,   # this tool's natural cadence is well below 10 fps; the cap is conservative
)
async def live_temperature(args: dict, credentials: dict) -> AsyncIterator[StreamComponents]:
    """Yield a Metric component every interval_s seconds with the latest temperature."""
    interval = args.get("interval_s", 5)
    last_temp = None
    try:
        while True:
            reading = await fetch_one_reading(args["lat"], args["lon"], credentials)
            delta = "" if last_temp is None else f"{reading.temp_c - last_temp:+.1f}"
            last_temp = reading.temp_c
            yield StreamComponents(
                components=[{
                    "type": "metric",
                    "label": "Temperature",
                    "value": f"{reading.temp_c:.1f}°C",
                    "delta": delta,
                }],
                raw={"temp_c": reading.temp_c, "ts": reading.ts},
            )
            await asyncio.sleep(interval)
    finally:
        # Cleanup runs on cancellation. Close any upstream subscriptions here.
        pass
```

**You do not set `id` on the components.** The SDK assigns the canonical `stream_id` for the active subscription before the chunk leaves the agent.

---

## Step 2 — Restart the agent (and only the agent)

```bash
# kill the agent process; the orchestrator will reconnect when it comes back
cd backend && .venv/Scripts/python.exe -m agents.weather.weather_agent
```

When the agent re-registers with the orchestrator, the new tool appears in `_streamable_tools` automatically because of the `@streaming_tool` decorator's `metadata.streamable=true` registration. No orchestrator restart needed.

---

## Step 3 — Trigger the tool from a chat

Open the frontend, start (or open) a chat, and ask for live temperature:

> "Show me a live temperature feed for London (51.5, -0.12)."

The orchestrator routes the chat to the weather agent. The agent calls `live_temperature` as a streaming tool. Within ~2 seconds you should see a Metric card appear in the canvas with the first temperature reading. Every few seconds the value updates **in place** — the card does not flicker, no other components on the canvas re-render.

---

## Step 4 — Verify the lifecycle

### 4.a Leave the chat

Click on a different chat in the sidebar (or open a new one). Within 5 seconds the backend should report (in the orchestrator log):

```text
[stream_manager] stream-7c2a1f → DORMANT (reason=load_chat, user=dev-user-id, chat=<old_chat>)
```

If you watch the agent's outbound network activity, it should stop. The metric card is no longer in your canvas (you're in a different chat).

### 4.b Return to the chat

Click back on the original chat. Within 3 seconds the metric card reappears, showing **fresh** data (not the value frozen at the moment you left). In the orchestrator log:

```text
[stream_manager] stream-7c2a1f → STARTING (reason=load_chat_return)
[stream_manager] stream-7c2a1f → ACTIVE (first chunk delivered)
```

### 4.c Disconnect

Close the browser tab. Within 5 seconds:

```text
[stream_manager] stream-7c2a1f → DORMANT (reason=ws_disconnect)
```

Reopen the tab and reload the chat. The stream resumes (same as 4.b).

---

## Step 5 — Verify isolation (manual test of FR-011)

1. Open the app in two browsers as two different users.
2. Both users start the same `live_temperature` tool in their own chats.
3. Confirm in the orchestrator log that **two distinct** `stream_id`s are created, one per user.
4. Confirm each browser only sees its own metric card update.
5. Try to send a `stream_unsubscribe` from user A's browser dev tools console with user B's `stream_id`. The orchestrator MUST respond with `stream_error { code: "unauthorized" }` and not stop user B's stream.

## Step 6 — Verify multi-tab fan-out (manual test of FR-009a)

1. As one user, open the same chat in two browser tabs.
2. In tab A, trigger the `live_temperature` stream.
3. In tab B (which already has the same chat loaded), the metric card should appear and start updating **without a second `stream_subscribe` causing a second upstream call**.
4. Confirm in the orchestrator log:
   - Tab A's subscribe creates a fresh subscription: `[stream_manager] stream-7c2a1f → STARTING`.
   - Tab B's subscribe shows `[stream_manager] stream-7c2a1f attach (subscribers=2)` — no new `stream_id`.
   - Both tabs receive identical chunks at the same time (same `seq`).
5. Close tab B. The orchestrator log shows `[stream_manager] stream-7c2a1f detach (subscribers=1)`. The stream stays active for tab A.
6. Close tab A. The orchestrator log shows `[stream_manager] stream-7c2a1f → DORMANT` (the last subscriber left).
7. Open the chat again. The stream resumes.

## Step 7 — Verify auto-retry on transient failure (manual test of FR-021a)

1. Start `live_temperature` against an upstream you can briefly take offline (e.g., block the upstream API at the firewall, or kill an upstream mock).
2. Wait for the next chunk to fail. The metric card should show a "Reconnecting (1/3)…" overlay within 5 s.
3. Restore the upstream within 5 s. The next retry succeeds; the overlay disappears in a single render and normal updates resume.
4. Repeat, but keep the upstream down. After 1 s + 5 s + 15 s ≈ 21 s of backoff, the card shows a manual retry button (`error.phase == "failed"`, `retryable: true`).
5. Click retry. The orchestrator allocates a new subscription (the previous one is in `STOPPED`) and the cycle restarts.
6. **Auth failure check**: forcibly revoke the user's token (or wait for it to expire). The next chunk should show "Sign in again" — NOT a reconnecting overlay. Verify the orchestrator log shows `RECONNECTING` was bypassed.

---

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Tool function never yields | You wrote `return` instead of `yield` somewhere, so Python never made it a generator. | Make sure the function body contains `yield` somewhere reachable. The decorator will assert this at registration. |
| `TypeError: yielded value must be StreamComponents` | You yielded a bare dict or list. | Wrap it: `yield StreamComponents(components=[my_dict])`. |
| First chunk takes >2 seconds | Your fetch is slow, or you `await asyncio.sleep(interval)` **before** the first yield. | Yield the first reading immediately, then enter the sleep loop. |
| Updates stop after one chunk | Your loop exits early (e.g. `while False`), or an exception is being silently swallowed. | Check the agent log for `[stream_sdk] tool_error in <tool>`. |
| UI card flickers / remounts on every update | The component's `id` is being lost in your `mcp_tools.py` (e.g., you tried to set it manually and the SDK rejected it, then your component had no id at all). | Don't set `id`; let the SDK do it. Verify in the browser dev tools that the rendered DOM element keeps the same React fiber across updates. |
| Cross-chat leak | You're testing against the legacy `_streamable_tools` polling path, not the new push path. | Confirm `metadata.streaming_kind == "push"` for your tool in the agent's registration log. |
| `chunk_too_large` errors | Each chunk's serialized size exceeds 64 KB. | Either reduce the payload (drop large fields from `raw`), or override `max_chunk_bytes` in the decorator and document why. |

---

## Where to look in the code

- **Tool author**: only [backend/agents/<your_agent>/mcp_tools.py](../../backend/agents/) and [backend/shared/stream_sdk.py](../../backend/shared/stream_sdk.py).
- **Agent runtime**: [backend/agents/<your_agent>/mcp_server.py](../../backend/agents/) — request loop branches on `inspect.isasyncgenfunction(fn)`.
- **Orchestrator stream manager**: [backend/orchestrator/stream_manager.py](../../backend/orchestrator/stream_manager.py) — registry, lifecycle, coalescing, ROTE adaptation.
- **Frontend message handler**: [frontend/src/hooks/useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts) — `case "ui_stream_data"`.
- **Frontend rendering**: [frontend/src/components/DynamicRenderer.tsx](../../frontend/src/components/DynamicRenderer.tsx) — stable keys + `React.memo`.

---

## Running the tests for this feature

```bash
# Backend
cd backend
.venv/Scripts/python.exe -m pytest tests/test_stream_*.py -v

# Frontend
cd frontend
npm run test -- stream_
```

The integration tests in `test_stream_lifecycle.py` and `test_stream_isolation.py` exercise the full subscribe → leave → return → unsubscribe path against a mocked agent and a fake browser WebSocket. They are the canonical reference for the behavior the feature promises.

---

## What this quickstart does NOT cover

- Adding a brand new agent (see existing docs for that).
- Persisting stream payloads to the history DB — explicitly out of scope per A-007.
- Sharing one stream across multiple users — explicitly out of scope.
- Mobile background streaming — out of scope.

For any of those, see the spec's "Out of Scope" section.
