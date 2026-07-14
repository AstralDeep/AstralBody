"""Per-request runtime context injected into tool kwargs as ``_runtime``.

Tools that need to do anything beyond a one-shot synchronous response —
emit incremental progress, register a long-running upstream job for
background polling, etc. — pull the runtime out of ``kwargs`` and use its
methods.

The runtime is constructed once per MCP request inside
``BaseA2AAgent.handle_mcp_request`` and discarded after the tool returns.
Existing tools that don't accept ``_runtime`` are unaffected: the MCP
server filters kwargs by signature, so unrecognized keys are dropped.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.protocol import MCPRequest


logger = logging.getLogger("AgentRuntime")


class AgentRuntime:
    """Bridge from a synchronously-running tool back to the agent's event loop."""

    def __init__(
        self,
        ws: Any,
        msg: "MCPRequest",
        agent_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.ws = ws
        self.request_id = msg.request_id
        self.agent_id = agent_id
        self.tool_name = (msg.params or {}).get("name", "")
        args = (msg.params or {}).get("arguments") or {}
        self.cap_job_id: Optional[str] = args.get("_cap_job_id")
        self.user_id: Optional[str] = args.get("user_id")
        self.loop = loop

    async def call_agent_tool(
        self,
        callee_agent_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        timeout: float = 30.0,
    ):
        """Request a MEDIATED hop to a peer agent's tool (056 US1, FR-001).

        Returns the peer's ``MCPResponse`` or an honest error ``MCPResponse``
        — never raises into the tool, never tears down the session (FR-028).
        NEVER talks to a peer directly: it schedules an ``agent_hop_request``
        control frame onto the orchestrator via the same channel the agent
        already uses (the in-process loopback for built-ins, the agent
        WebSocket for networked agents) and awaits the correlated response.
        The initiating agent holds NO token and NO mint capability — the
        orchestrator resolves authority from its OWN record of this request
        (``parent_request_id``), mints a strictly-narrower child delegation,
        and re-enters the full single-path gate stack for the hop.

        Async by design; a synchronous tool bridges with::

            asyncio.run_coroutine_threadsafe(
                runtime.call_agent_tool(...), runtime.loop).result(timeout)
        """
        import uuid as _uuid
        from shared.protocol import AgentHopRequest, MCPResponse

        hop_id = f"hop_{_uuid.uuid4().hex[:12]}"
        fut: "asyncio.Future" = asyncio.get_running_loop().create_future()
        futures = getattr(self.ws, "_hop_futures", None)
        if futures is None:
            futures = {}
            try:
                self.ws._hop_futures = futures
            except Exception:
                return MCPResponse(
                    request_id=hop_id,
                    error={"message": "agent transport cannot correlate hop responses",
                           "retryable": False})
        futures[hop_id] = fut

        frame = AgentHopRequest(
            request_id=hop_id,
            parent_request_id=self.request_id,
            initiator_agent_id=self.agent_id,
            callee_agent_id=callee_agent_id,
            tool_name=tool_name,
            arguments=dict(arguments or {}),
        )
        try:
            await self.ws.send_text(frame.to_json())
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return MCPResponse(
                request_id=hop_id,
                error={"message": f"hop to '{callee_agent_id}.{tool_name}' timed out",
                       "retryable": True})
        except Exception as exc:  # honest error, never a raise into the tool
            logger.warning("call_agent_tool failed: %s", exc)
            return MCPResponse(
                request_id=hop_id,
                error={"message": f"hop request failed: {exc}", "retryable": False})
        finally:
            futures.pop(hop_id, None)

    def start_long_running_job(
        self,
        poll_fn: Callable[[], Dict[str, Any]],
        *,
        poll_interval: float = 5.0,
        failure_threshold: int = 5,
    ) -> None:
        """Schedule a :class:`JobPoller` on the agent's event loop.

        ``poll_fn`` is a synchronous callable invoked from a worker thread on
        each tick; it must return a dict shaped like::

            {
                "status": "started" | "in_progress" | "succeeded" | "failed",
                "percentage": <int|None>,
                "message": "<human-readable>",
                "result": <dict|None>,   # only required on succeeded/failed
            }
        """
        from shared.job_poller import JobPoller  # local import to avoid cycle
        poller = JobPoller(
            ws=self.ws,
            request_id=self.request_id,
            agent_id=self.agent_id,
            tool_name=self.tool_name,
            cap_job_id=self.cap_job_id,
            poll_fn=poll_fn,
            poll_interval=poll_interval,
            failure_threshold=failure_threshold,
        )
        # Tools run in a worker thread; schedule onto the agent's event loop.
        asyncio.run_coroutine_threadsafe(poller.run(), self.loop)
