"""Feature 068 — in-process loopback transport for built-in agents.

Lets a :class:`~shared.base_agent.BaseA2AAgent` run *inside* the orchestrator
process with no network hop. The agent's normal ``handle_mcp_request`` writes
frames via ``send_text``/``send_json`` exactly as it would over a real
WebSocket; this loopback feeds each frame straight back into the orchestrator's
inbound agent-message router (``Orchestrator.handle_agent_message``), which
resolves the pending request future and routes ``ToolProgress`` /
``ToolStreamData`` identically to the networked path.

Because the agent's own handler runs unchanged, every agent-side behavior is
preserved automatically: E2E credential decryption inside the agent boundary
(the orchestrator never sees plaintext), ``_runtime`` injection, per-server
kwarg filtering, streaming, and long-running job pollers.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("LoopbackSocket")


class LoopbackSocket:
    """A minimal WebSocket-shaped object that loops frames back to the orchestrator.

    Only the surface the agent side actually uses is implemented:
    ``send_text``/``send_json`` (frame emission) plus ``accept``/``close`` and a
    ``client`` attribute for parity with callers that read them.
    """

    def __init__(self, orchestrator: Any, agent_id: str) -> None:
        self._orch = orchestrator
        self.agent_id = agent_id
        # A loopback has no network peer; some audit-shaped callers read .client.
        self.client = ("inprocess", 0)

    async def send_text(self, text: str) -> None:
        """Route an outbound agent frame back into the orchestrator's router."""
        await self._orch.handle_agent_message(self, text)

    async def send_json(self, obj: Any) -> None:
        await self._orch.handle_agent_message(self, json.dumps(obj))

    async def accept(self) -> None:  # parity no-op (no handshake in-process)
        return None

    async def close(self, *args: Any, **kwargs: Any) -> None:  # parity no-op
        return None
