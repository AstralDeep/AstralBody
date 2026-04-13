# Contract: Agent SDK for Streaming Tools

**Feature**: 001-tool-stream-ui
**Layer**: The Python interface that tool authors use inside `backend/agents/<agent>/mcp_tools.py` to declare and produce a streaming tool.

This is the contract between the tool author and the project. It is **strictly additive** — every existing tool keeps working unchanged.

---

## 1. Two ways to write a streaming tool

### 1.a Async generator (preferred)

```python
# backend/agents/weather/mcp_tools.py
from typing import AsyncIterator
from backend.shared.stream_sdk import streaming_tool, StreamComponents

@streaming_tool(
    name="live_forecast",
    description="Live weather updates for a location.",
    input_schema={
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "interval_s": {"type": "integer", "minimum": 1, "maximum": 60},
        },
        "required": ["lat", "lon"],
    },
    max_fps=10,
)
async def live_forecast(args: dict, credentials: dict) -> AsyncIterator[StreamComponents]:
    """Yield a Metric component every interval_s seconds."""
    interval = args.get("interval_s", 5)
    while True:
        reading = await fetch_one_reading(args["lat"], args["lon"], credentials)
        yield StreamComponents(
            components=[{
                "type": "metric",
                "label": "Temperature",
                "value": f"{reading.temp_c:.1f}°C",
                "delta": f"{reading.delta:+.1f}",
            }],
            raw=reading.as_dict(),
        )
        await asyncio.sleep(interval)
```

**Rules**:

- The function **MUST** be `async def` and **MUST** be an async generator (i.e., contains `yield`).
- It receives the same `(args, credentials)` signature as today's tools.
- It MUST yield `StreamComponents` instances. A bare dict is rejected at SDK level (defense against accidentally yielding arbitrary objects).
- The `id` field of components in `StreamComponents.components` is **assigned by the SDK** — the tool author MUST NOT set it. The SDK overwrites any author-supplied `id` with the canonical `stream_id` for the active subscription before forwarding to the orchestrator.
- The function MUST clean up resources in a `try/finally` block. The SDK propagates `GeneratorExit` on cancellation; cleanup MUST complete within 1 s.
- The function MUST NOT block the event loop. Blocking I/O MUST go through `asyncio.to_thread` or an async client library.

### 1.b `StreamCtx.emit(...)` (for callback-based upstream APIs)

```python
@streaming_tool(name="watch_inbox", description="Watch a folder for new emails.", input_schema={...})
async def watch_inbox(args: dict, credentials: dict, ctx: StreamCtx):
    """Use ctx.emit() when the upstream API is callback-based."""
    def on_new_email(email):
        ctx.emit(StreamComponents(
            components=[{"type": "list_item", "title": email.subject, "subtitle": email.sender}],
        ))
    subscription = imap_client.watch(args["folder"], on_new_email, credentials)
    try:
        await ctx.until_cancelled()
    finally:
        subscription.close()
```

**Rules** (additional to 1.a):

- The function MUST accept a third positional parameter `ctx: StreamCtx`. The SDK detects the parameter name and signature.
- `ctx.emit(payload)` MAY be called from any coroutine or thread; the SDK uses `asyncio.run_coroutine_threadsafe` internally for thread safety.
- `ctx.until_cancelled()` is an awaitable that resolves when the orchestrator sends `ToolStreamCancel`. The author uses it to keep the function alive while emissions happen via callback.
- The function is NOT a generator in this form (no `yield`); it's a regular `async def`. The decorator detects this and routes through the `StreamCtx` queue internally.

---

## 2. The `StreamComponents` payload type

```python
@dataclass(frozen=True)
class StreamComponents:
    components: list[dict]   # MUST be ≤ 64 KB total when JSON-serialized (or per-tool override)
    raw: Any | None = None   # Optional; counted against the 64 KB cap
    error: StreamError | None = None  # Optional; if set, components MAY be empty
    terminal: bool = False   # If True, the SDK closes the generator after emitting this
```

**Validation** (raised as `StreamPayloadError` at the SDK level, before the chunk leaves the agent process):

- `len(json.dumps(asdict(self))) <= max_chunk_bytes` — default 65536 unless overridden in `@streaming_tool(max_chunk_bytes=...)`.
- Every dict in `components` MUST have a `type` key matching a known primitive in [backend/shared/primitives.py](../../../backend/shared/primitives.py).
- `components` MUST NOT include nested children that themselves have `id` matching the parent's `stream_id` (no recursion ambiguity).

---

## 3. The `@streaming_tool` decorator

```python
def streaming_tool(
    *,
    name: str,
    description: str,
    input_schema: dict,
    max_fps: int = 30,
    min_fps: int = 5,
    max_chunk_bytes: int = 65536,
    scope: str | None = None,
) -> Callable: ...
```

**Behavior**:

1. Validates that `1 <= min_fps <= max_fps <= 60`.
2. Marks the function with attributes the agent's `MCPServer.process_request` reads at runtime: `__streaming_tool__ = True`, `__stream_metadata__ = {...}`.
3. Registers the tool in the agent's `TOOL_REGISTRY` exactly as the existing `@tool` decorator does, but with `metadata.streamable = True` and `metadata.streaming_kind = "push"` so the orchestrator's `_streamable_tools` table picks it up at agent registration time (B5 in [protocol-messages.md](protocol-messages.md)).
4. Returns the original function unchanged for normal callability — the decorator is a marker, not a wrapper. Wrapping happens at the `MCPServer.process_request` layer where the per-call `StreamCtx` is constructed.

**Feature flag interaction**: when `FF_TOOL_STREAMING` is `False`, the decorator is still importable and the function is still registered as a tool, but the agent's request loop ignores the streaming markers and runs the generator to completion, returning the **last** yielded chunk as a single `MCPResponse`. This guarantees that flipping the flag off does not break tools written for the new path — it merely degrades them.

---

## 4. Lifecycle from the tool's perspective

```text
Subscribe message arrives at agent
  │
  ▼
MCPServer.process_request sees _stream=True
  │
  ▼
SDK constructs StreamCtx, calls the function
  │
  ▼
Generator yields chunks (or ctx.emit fires) ────────► sent as ToolStreamData
                                                          │
                                                          ▼
                                                    orchestrator forwards to UI
  │
  ▼
Orchestrator decides user has left ──── ToolStreamCancel ────► SDK closes generator
                                                                         │
                                                                         ▼
                                                                  finally: cleanup
                                                                         │
                                                                         ▼
                                                                  generator returns
                                                                         │
                                                                         ▼
                                                          ToolStreamEnd sent automatically
```

**Guarantees the SDK gives the tool author**:

1. `args` and `credentials` are exactly as in today's single-response tools.
2. Cancellation arrives as `GeneratorExit` (or `ctx.until_cancelled()` resolving) — never as a hard kill mid-statement.
3. `credentials` may contain a delegated token that has not been refreshed yet at chunk N. If refresh fails, the SDK injects an error chunk and cancels — the tool does not need to handle auth refresh itself.
4. Slow yields are fine. Backpressure from the orchestrator never propagates as an exception; chunks are simply dropped at the orchestrator coalescing buffer.
5. Exceptions raised inside the generator are caught at the SDK level, wrapped as a `StreamError` with `code="tool_error"`, and forwarded as a final chunk before transitioning to `STOPPED`.

---

## 5. What the SDK forbids

- Setting `Component.id` manually inside the tool (the SDK overwrites it).
- Yielding a non-`StreamComponents` value (e.g., a bare dict) — `TypeError` at first yield.
- Using `print(...)` or writing to stdout from inside a streaming tool — captured by the existing agent logging convention; not new.
- Spawning unawaited background tasks that outlive the generator — they will leak. Use the existing per-agent task supervisor (out of scope of this feature).
- Calling `ctx.emit` after the generator has been cancelled — silently no-ops (the cancelled context is inert).

---

## 6. Reference implementation

[backend/agents/weather/mcp_tools.py](../../../backend/agents/weather/mcp_tools.py) gains a new tool `live_forecast` as the canonical example. The existing `current_weather` (single-response) tool stays exactly as it is. Tests in [backend/tests/test_stream_protocol.py](../../../backend/tests/test_stream_protocol.py) cover both the round-trip and the "feature flag off → degrades to single response" path.

---

## 7. Migration guidance for existing streamable tools (poll path)

Tools that today use the polling-based `stream_subscribe` (e.g., declaring `metadata.streamable = True` with a `default_interval_s`) **do not need to change**. The orchestrator's `_streamable_tools` registry distinguishes by `streaming_kind` (default `"poll"`). Authors who want to upgrade a polled tool to push semantics:

1. Add `@streaming_tool(...)` to the function.
2. Convert the function from `def fetch(args, creds) -> dict` to `async def fetch(args, creds) -> AsyncIterator[StreamComponents]`.
3. Move the polling loop *inside* the function (or wire it to upstream events directly).
4. Remove `default_interval_s` from `metadata` if no longer relevant.

The migration is per-tool; mixed agents (some pushed, some polled) are explicitly supported.
