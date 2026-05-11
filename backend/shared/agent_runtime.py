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
