"""
WebSocket publisher for ``audit_append`` events.

The orchestrator owns the connection registry (``ui_clients`` plus a
``ui_sessions`` mapping each connection to its authenticated JWT
payload). This module implements the per-user fan-out: given an
``AuditEventDTO`` and the owning ``user_id``, find every connection
whose authenticated subject matches that ``user_id`` and deliver one
``audit_append`` message.

Server-side ``user_id`` filtering is the only filter — there is no
broadcast channel and clients never participate in filtering
(FR-007 / FR-019).
"""
from __future__ import annotations

import logging
from typing import Any

from shared.protocol import AuditAppend

from .schemas import AuditEventDTO

logger = logging.getLogger("Audit.WSPublisher")


class WSPublisher:
    """Publishes ``audit_append`` messages to user-scoped WS connections."""

    def __init__(self, orchestrator: Any):
        self._orch = orchestrator

    async def publish(self, event: AuditEventDTO, actor_user_id: str) -> None:
        """Send ``event`` to every connection whose subject == ``actor_user_id``."""
        if not actor_user_id:
            return
        msg = AuditAppend(event=event.model_dump(mode="json"))
        payload = msg.to_json()
        sessions = getattr(self._orch, "ui_sessions", {})
        targets = [
            ws for ws, claims in list(sessions.items())
            if (claims or {}).get("sub") == actor_user_id
        ]
        if not targets:
            return
        for ws in targets:
            try:
                await self._orch._safe_send(ws, payload)
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("audit_append send failed: %s", exc)


def make_publish_callable(orchestrator: Any):
    """Return the bound publisher coroutine for ``Recorder.set_publisher``."""
    pub = WSPublisher(orchestrator)
    return pub.publish
