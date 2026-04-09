"""
Streaming Tool SDK for AstralBody agents (001-tool-stream-ui).

This module is the contract between a tool author writing a streaming tool
and the rest of the system. It is **strictly additive** — every existing
single-response tool keeps working unchanged.

Two ways to write a streaming tool:

1. **Async generator (preferred):**

       @streaming_tool(
           name="live_temperature",
           description="...",
           input_schema={...},
           max_fps=10,
       )
       async def live_temperature(args, credentials):
           while True:
               reading = await fetch_one_reading(args["lat"], args["lon"])
               yield StreamComponents(
                   components=[{"type": "metric", "label": "T", "value": ...}],
                   raw=reading.as_dict(),
               )
               await asyncio.sleep(args.get("interval_s", 5))

2. **StreamCtx.emit() (for callback-based upstream APIs):**

       @streaming_tool(name="watch_inbox", ...)
       async def watch_inbox(args, credentials, ctx: StreamCtx):
           sub = imap.watch(args["folder"], on_new=lambda e: ctx.emit(
               StreamComponents(components=[{"type": "list_item", ...}])
           ))
           try:
               await ctx.until_cancelled()
           finally:
               sub.close()

The decorator is a marker — wrapping happens at the agent's
``MCPServer.process_request`` layer, where the per-call ``StreamCtx`` is
constructed and the function is detected via
``inspect.isasyncgenfunction(fn)``.

See specs/001-tool-stream-ui/contracts/agent-sdk.md.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional


# --- Errors --------------------------------------------------------------

class StreamPayloadError(ValueError):
    """Raised when a streaming tool yields a payload that violates the SDK
    contract — e.g. wrong type, oversized chunk, or non-primitive component
    type. The agent's MCPServer wraps this into a final ``ToolStreamData``
    chunk with ``error.code = "tool_error"`` and ``error.phase = "failed"``
    so the user sees a clear failure rather than a silently broken stream.
    """


# --- Payload type --------------------------------------------------------

@dataclass(frozen=True)
class StreamComponents:
    """One emission from a streaming tool — a small subtree of UI components
    plus optional raw data, optional error, and a terminal flag.

    The total JSON-serialized size of this object MUST be at most
    ``max_chunk_bytes`` (default 65536). Larger payloads cause the agent to
    raise ``StreamPayloadError``.

    The tool author MUST NOT set the ``id`` field on any component in
    ``components`` — the SDK overwrites it with the canonical ``stream_id``
    of the active subscription before the chunk leaves the agent process.
    """
    components: List[Dict[str, Any]]
    raw: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    terminal: bool = False

    def serialized_size(self) -> int:
        """Approximate JSON serialized size in bytes (used by the SDK to
        enforce ``max_chunk_bytes`` before sending)."""
        return len(json.dumps(asdict(self), default=str))


# --- StreamCtx -----------------------------------------------------------

class StreamCtx:
    """Per-call context object passed to tools that prefer ``ctx.emit(...)``
    over the async-generator yield form (e.g. for wrapping callback-based
    upstream libraries).

    Internally, ``emit()`` puts the chunk on an ``asyncio.Queue`` that the
    surrounding wrapper drains. ``until_cancelled()`` resolves when the
    orchestrator sends a ``ToolStreamCancel`` for this stream.
    """

    def __init__(self, stream_id: str, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.stream_id = stream_id
        self._loop = loop or asyncio.get_event_loop()
        self._queue: asyncio.Queue[Optional[StreamComponents]] = asyncio.Queue()
        self._cancelled = asyncio.Event()

    def emit(self, payload: StreamComponents) -> None:
        """Schedule ``payload`` for delivery. Safe to call from any coroutine
        or thread (uses ``call_soon_threadsafe`` for the cross-thread path).
        After cancellation, calls become silent no-ops."""
        if self._cancelled.is_set():
            return
        if not isinstance(payload, StreamComponents):
            raise StreamPayloadError(
                f"ctx.emit expects a StreamComponents, got {type(payload).__name__}"
            )
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is self._loop:
            self._queue.put_nowait(payload)
        else:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, payload)

    async def until_cancelled(self) -> None:
        """Awaitable that resolves when the orchestrator cancels this
        stream. Used by ``ctx.emit``-style tools to keep the function alive
        while emissions happen via callback."""
        await self._cancelled.wait()

    def _cancel(self) -> None:
        """Internal: called by the agent's MCPServer wrapper when a
        ``ToolStreamCancel`` arrives."""
        self._cancelled.set()
        # Wake any pending queue.get() so the wrapper can exit cleanly
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:  # pragma: no cover
            pass

    async def _drain(self) -> Optional[StreamComponents]:
        """Internal: called by the agent's MCPServer wrapper to retrieve
        the next emitted chunk. Returns ``None`` on cancellation."""
        item = await self._queue.get()
        return item


# --- Decorator -----------------------------------------------------------

def streaming_tool(
    *,
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    max_fps: int = 30,
    min_fps: int = 5,
    max_chunk_bytes: int = 65536,
    scope: Optional[str] = None,
) -> Callable[[Callable], Callable]:
    """Mark a function as a streaming tool.

    The function MUST be either:

    - an ``async def`` containing at least one ``yield`` (true async
      generator), in which case the agent's MCPServer iterates it directly;
      OR
    - an ``async def`` that takes a third ``ctx: StreamCtx`` parameter and
      uses ``ctx.emit(...)`` from a callback (the wrapper queues those
      emissions).

    Validation occurs at registration time, not at decoration time, because
    the function may be defined before the ``StreamCtx`` parameter inspection
    happens.

    The decorator does NOT wrap the function — it only marks it. Wrapping
    happens in the agent's ``MCPServer.process_request`` where per-call
    state (the ``StreamCtx``, the actual ``stream_id``) is constructed.

    Args:
        name: Tool identifier (matches MCP tool name).
        description: Human-readable description for the tool catalog.
        input_schema: JSON Schema for the tool's input arguments.
        max_fps: Per-stream upper bound for the orchestrator's coalescing
            buffer. Clamped to ``1..60`` per
            ``validate_streaming_metadata``.
        min_fps: Per-stream lower bound. Default 5.
        max_chunk_bytes: Per-chunk size cap. Default 65536. Hard ceiling
            1 MiB enforced by ``validate_streaming_metadata``.
        scope: Optional security scope name (e.g. ``"tools:read"``). Defaults
            to the agent's existing scope if omitted.

    Returns:
        The original function, unchanged, with marker attributes added.
    """
    # Validate decorator arguments early so a malformed @streaming_tool
    # call fails at import time, not at first invocation.
    if not (1 <= min_fps <= max_fps <= 60):
        raise ValueError(
            f"@streaming_tool: must satisfy 1 <= min_fps <= max_fps <= 60, "
            f"got min_fps={min_fps}, max_fps={max_fps}"
        )
    if not isinstance(max_chunk_bytes, int) or max_chunk_bytes <= 0:
        raise ValueError(
            f"@streaming_tool: max_chunk_bytes must be a positive int, "
            f"got {max_chunk_bytes!r}"
        )

    def decorate(fn: Callable) -> Callable:
        # The function must be async (either an async generator OR an async
        # def that takes a StreamCtx). Sync functions are rejected at
        # decoration time so authors get an immediate error.
        if not asyncio.iscoroutinefunction(fn) and not inspect.isasyncgenfunction(fn):
            raise TypeError(
                f"@streaming_tool: {fn.__name__} must be `async def` "
                f"(either an async generator with `yield`, or an async "
                f"function that takes a StreamCtx parameter)"
            )

        # Detect the StreamCtx form by signature inspection.
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        uses_ctx = any(
            p.annotation is StreamCtx
            or (p.name == "ctx" and p.annotation is inspect.Parameter.empty)
            for p in params
        )

        # Marker attributes consumed by the MCPServer dispatch loop and by
        # the orchestrator's _streamable_tools registry.
        fn.__streaming_tool__ = True
        fn.__stream_metadata__ = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "scope": scope,
            "uses_ctx": uses_ctx,
            "metadata": {
                "streamable": True,
                "streaming_kind": "push",
                "max_fps": max_fps,
                "min_fps": min_fps,
                "max_chunk_bytes": max_chunk_bytes,
            },
        }
        return fn

    return decorate


def is_streaming_tool(fn: Any) -> bool:
    """True if ``fn`` was decorated with ``@streaming_tool``."""
    return bool(getattr(fn, "__streaming_tool__", False))


def get_stream_metadata(fn: Any) -> Optional[Dict[str, Any]]:
    """Return the marker dict installed by ``@streaming_tool``, or ``None``
    if ``fn`` is not a streaming tool."""
    return getattr(fn, "__stream_metadata__", None)


# --- Component id assignment helper --------------------------------------

def assign_stream_id_to_components(
    components: List[Dict[str, Any]],
    stream_id: str,
) -> List[Dict[str, Any]]:
    """Walk a list of UI component dicts and overwrite each top-level
    component's ``id`` field with ``stream_id``.

    Tool authors are forbidden from setting ``id`` themselves
    (``contracts/agent-sdk.md §5``). The agent's MCPServer wrapper calls
    this helper on every ``StreamComponents.components`` list before sending
    the chunk so the orchestrator and frontend can merge by id.

    Returns a NEW list (does not mutate the input). Each component dict is
    shallow-copied; nested children are NOT modified — only the top-level
    components carry the stream_id, since fan-out merge in
    ``mergeStreamChunk`` finds the anchor by top-level id.
    """
    out = []
    for c in components:
        if not isinstance(c, dict):
            raise StreamPayloadError(
                f"streaming tool yielded a non-dict component: {type(c).__name__}"
            )
        if "type" not in c:
            raise StreamPayloadError(
                f"streaming tool yielded a component without a 'type' key: {c!r}"
            )
        copy = dict(c)
        copy["id"] = stream_id
        out.append(copy)
    return out


def validate_chunk_size(chunk: StreamComponents, max_chunk_bytes: int) -> None:
    """Raise ``StreamPayloadError`` if the chunk's serialized size exceeds
    ``max_chunk_bytes``. Called by the agent's MCPServer wrapper before
    sending the chunk to the orchestrator. The error code routes to a
    ``chunk_too_large`` failure (non-retryable, deterministic).
    """
    size = chunk.serialized_size()
    if size > max_chunk_bytes:
        raise StreamPayloadError(
            f"streaming tool emitted a {size}-byte chunk, exceeds "
            f"max_chunk_bytes={max_chunk_bytes}"
        )
