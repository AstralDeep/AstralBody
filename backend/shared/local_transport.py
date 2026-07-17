"""Feature 040 — in-process loopback transport for built-in agents.

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


class TunnelSocket:
    """Feature 058 — agent-connection adapter for a user agent whose frames
    tunnel over the owner's authenticated UI WebSocket (Mode 1 transport).

    To the orchestrator's agent dispatch it looks like a normal agent WebSocket
    (``.send``); each outbound frame is wrapped in an ``agent_tunnel`` envelope
    (tagged with ``agent_id`` so a host running several agents demuxes correctly)
    and delivered to the client over its UI socket via ``send_fn``. Inbound frames
    from the client are unwrapped by the orchestrator's ``agent_tunnel`` handler
    and fed to ``handle_agent_message`` with this same socket.

    Carries the AUTHENTICATED owner ``sub`` (from the UI session) so registration
    owner-binding derives authority from the orchestrator's own record, never from
    anything the agent presents.
    """

    def __init__(self, ui_websocket: Any, owner_sub: str, agent_id: str,
                 send_fn: Any) -> None:
        self.ui_websocket = ui_websocket
        self.owner_sub = owner_sub
        self.agent_id = agent_id
        self._send_fn = send_fn  # async fn(ui_ws, text) — e.g. Orchestrator._safe_send
        self.client = ("tunnel", 0)
        self.is_user_agent_tunnel = True

    async def send(self, text: str) -> None:
        """Deliver an outbound agent frame (a tool-call request) TO the client
        host, wrapped in an agent_tunnel envelope tagged with this agent's id."""
        await self._send_fn(self.ui_websocket, json.dumps({
            "type": "agent_tunnel", "agent_id": self.agent_id, "frame": text,
        }))

    async def send_text(self, text: str) -> None:  # parity with FastAPI sockets
        await self.send(text)

    async def close(self, *args: Any, **kwargs: Any) -> None:  # parity no-op
        return None


class FencedTunnelSocket:
    """Projection of one durably promoted personal-agent runtime.

    Unlike the feature-058 compatibility adapter, this socket never invents a
    route from ``agent_id`` alone. Every outbound request is supplied with the
    exact runtime/request fence already committed by the server repository and
    is pushed only to the selected server-acknowledged host session.
    """

    def __init__(
        self,
        ui_websocket: Any,
        owner_sub: str,
        runtime_fence: Any,
        send_fn: Any,
    ) -> None:
        self.ui_websocket = ui_websocket
        self.owner_sub = owner_sub
        self.runtime_fence = runtime_fence
        self.agent_id = runtime_fence.agent_id
        self.host_session_id = runtime_fence.host_session_id
        self._send_fn = send_fn
        self.client = ("fenced-tunnel", 0)
        self.is_user_agent_tunnel = True
        self.is_fenced_user_agent_tunnel = True

    async def send_fenced(self, frame: dict[str, Any]) -> None:
        """Push one already-validated v2 request to this exact host/runtime."""

        if frame.get("fence") != self.runtime_fence.to_dict():
            raise ValueError("personal-agent request runtime fence is stale")
        await self._send_fn(
            self.ui_websocket,
            json.dumps(
                {
                    "type": "agent_tunnel",
                    "fence": self.runtime_fence.to_dict(),
                    "frame": frame,
                },
                separators=(",", ":"),
            ),
        )

    async def send(self, _text: str) -> None:
        """Refuse the unfenced legacy dispatch path."""

        raise RuntimeError("v2 personal-agent calls require a durable request fence")

    async def send_text(self, text: str) -> None:
        await self.send(text)

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None
