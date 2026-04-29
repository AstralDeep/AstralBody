"""Per-WebSocket in-memory credentials (feature 006-user-llm-config).

These are the user's personal LLM credentials, lifted from their browser
on ``register_ui`` / ``llm_config_set`` and held only for the lifetime of
the WebSocket connection. Cleared on ``llm_config_clear`` and on socket
disconnect. NEVER persisted to disk, NEVER copied into a log line,
NEVER returned by any API. The only legitimate consumer is
:func:`backend.llm_config.client_factory.build_llm_client`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(slots=True)
class SessionCreds:
    """A user's personal LLM credentials, scoped to one WebSocket connection.

    Attributes:
        api_key: The user's API key. NEVER logged, NEVER serialized into
            any audit-event payload. The custom ``__repr__`` below elides
            this field so accidental ``logger.debug(creds)`` calls do not
            leak it.
        base_url: The OpenAI-compatible endpoint URL, e.g.
            ``"https://api.openai.com/v1"``.
        model: The model name to pass as ``model=`` in
            ``chat.completions.create``.
        set_at: ``time.monotonic()`` snapshot at the moment the entry
            was created or last updated. Diagnostic only — not exposed
            outside this module.
    """
    api_key: str
    base_url: str
    model: str
    set_at: float

    def __repr__(self) -> str:
        # Elide api_key. Even if someone wires this dataclass into a log
        # formatter or an exception traceback, the key never appears.
        return (
            f"SessionCreds(api_key=<redacted>, base_url={self.base_url!r}, "
            f"model={self.model!r})"
        )


class SessionCredentialStore:
    """Thin typed wrapper around ``Dict[int, SessionCreds]``.

    Keyed by ``id(websocket)`` — the same identity scheme used elsewhere
    in :class:`backend.orchestrator.orchestrator.Orchestrator` (e.g.
    ``_chat_locks``, ``ui_sessions``, ``cancelled_sessions``). The store
    is process-local memory only; it is not pickled, not persisted, and
    not copied across processes.

    Concurrency: all access is single-threaded within the orchestrator's
    asyncio event loop; no locking is needed.
    """

    def __init__(self) -> None:
        self._creds: Dict[int, SessionCreds] = {}

    def get(self, ws_id: int) -> Optional[SessionCreds]:
        """Return the credentials for ``ws_id``, or ``None`` if unset."""
        return self._creds.get(ws_id)

    def set(self, ws_id: int, api_key: str, base_url: str, model: str) -> SessionCreds:
        """Store or replace credentials for ``ws_id``.

        Validates all three fields are non-empty strings; raises
        :class:`ValueError` otherwise. Returns the stored ``SessionCreds``.
        """
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        creds = SessionCreds(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            set_at=time.monotonic(),
        )
        self._creds[ws_id] = creds
        return creds

    def clear(self, ws_id: int) -> bool:
        """Remove the entry for ``ws_id``. Returns ``True`` iff something was removed."""
        return self._creds.pop(ws_id, None) is not None

    def __contains__(self, ws_id: int) -> bool:
        return ws_id in self._creds

    def __len__(self) -> int:
        return len(self._creds)
