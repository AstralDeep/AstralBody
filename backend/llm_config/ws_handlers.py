"""WebSocket message handlers for feature 006-user-llm-config.

Two handlers:

* :func:`handle_llm_config_set` — the user has saved or updated their
  personal LLM configuration. Validates the trio, populates the
  per-WebSocket :class:`SessionCredentialStore`, emits an
  ``llm_config_change`` audit event, and acks back to the client.
* :func:`handle_llm_config_clear` — the user has cleared their personal
  configuration. Pops the entry, emits an audit event (only if there
  WAS a prior entry — clearing an already-empty slot is a silent no-op),
  and acks back.

Both handlers are no-ops on unauthenticated sockets — the orchestrator's
:meth:`handle_ui_message` ungates non-register messages with the
existing ``_registered_events`` mechanism, so by the time we land here
the socket is authenticated.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from audit.recorder import Recorder

from .audit_events import record_llm_config_change
from .session_creds import SessionCredentialStore

logger = logging.getLogger("LLMConfig.WSHandlers")

SafeSend = Callable[[Any, str], Awaitable[None]]


async def handle_llm_config_set(
    *,
    safe_send: SafeSend,
    websocket: Any,
    config: Dict[str, Any],
    actor_user_id: str,
    auth_principal: str,
    creds_store: SessionCredentialStore,
    recorder: Recorder,
) -> None:
    """Handle a ``llm_config_set`` WS message.

    Args:
        config: The dict from ``LLMConfigSet.config`` — must carry
            ``api_key``, ``base_url``, ``model``, all non-empty strings.
        creds_store: The orchestrator's ``_session_llm_creds`` store.

    Behaviour:

    * Validates the payload. On failure, sends back an ``error`` message
      with code ``llm_config_invalid`` and DOES NOT mutate state.
    * Determines whether this is a creation (no prior entry on this
      socket) or an update (entry already present); the determination
      happens BEFORE the swap so the action label is correct.
    * Replaces the entry; emits ``llm_config_change(action=<created|updated>)``.
    * Sends ``llm_config_ack(ok=True)``.
    """
    api_key = (config.get("api_key") or "").strip() if isinstance(config, dict) else ""
    base_url = (config.get("base_url") or "").strip() if isinstance(config, dict) else ""
    model = (config.get("model") or "").strip() if isinstance(config, dict) else ""

    if not (api_key and base_url and model):
        await safe_send(websocket, json.dumps({
            "type": "error",
            "code": "llm_config_invalid",
            "message": (
                "llm_config_set requires non-empty api_key, base_url, and model"
            ),
        }))
        return

    ws_id = id(websocket)
    prior_present = ws_id in creds_store
    try:
        creds_store.set(ws_id, api_key, base_url, model)
    except ValueError as exc:
        # SessionCredentialStore.set re-validates and may reject; surface
        # the same error code so the client can correct it.
        await safe_send(websocket, json.dumps({
            "type": "error",
            "code": "llm_config_invalid",
            "message": str(exc),
        }))
        return

    action = "updated" if prior_present else "created"
    try:
        await record_llm_config_change(
            recorder,
            actor_user_id=actor_user_id,
            auth_principal=auth_principal,
            action=action,
            base_url=base_url,
            model=model,
            transport="ws",
        )
    except Exception as exc:  # pragma: no cover — audit is best-effort
        logger.warning(f"llm_config_change audit failed (non-fatal): {exc}")

    await safe_send(websocket, json.dumps({"type": "llm_config_ack", "ok": True}))


async def handle_llm_config_clear(
    *,
    safe_send: SafeSend,
    websocket: Any,
    actor_user_id: str,
    auth_principal: str,
    creds_store: SessionCredentialStore,
    recorder: Recorder,
) -> None:
    """Handle a ``llm_config_clear`` WS message.

    Pops the entry; emits ``llm_config_change(action="cleared")`` only if
    there was an entry to begin with (avoids audit-log noise from
    duplicate or speculative clears); acks unconditionally.
    """
    ws_id = id(websocket)
    removed = creds_store.clear(ws_id)
    if removed:
        try:
            await record_llm_config_change(
                recorder,
                actor_user_id=actor_user_id,
                auth_principal=auth_principal,
                action="cleared",
                base_url=None,
                model=None,
                transport="ws",
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"llm_config_change audit failed (non-fatal): {exc}")
    await safe_send(websocket, json.dumps({"type": "llm_config_ack", "ok": True}))


async def populate_from_register_ui(
    *,
    websocket: Any,
    llm_config: Optional[Dict[str, Any]],
    actor_user_id: str,
    auth_principal: str,
    creds_store: SessionCredentialStore,
    recorder: Recorder,
) -> None:
    """Apply an optional ``llm_config`` payload from a ``register_ui``
    message. No client reply is sent (register_ui has its own ack via
    ``rote_config`` etc.); malformed payloads are silently ignored
    rather than rejecting the entire registration.
    """
    if not isinstance(llm_config, dict):
        return
    api_key = (llm_config.get("api_key") or "").strip()
    base_url = (llm_config.get("base_url") or "").strip()
    model = (llm_config.get("model") or "").strip()
    if not (api_key and base_url and model):
        # Partial / malformed payload — silently ignore. The user's
        # browser will not have stored a partial config in the first
        # place; this is defensive only.
        return
    ws_id = id(websocket)
    prior_present = ws_id in creds_store
    try:
        creds_store.set(ws_id, api_key, base_url, model)
    except ValueError:
        return
    action = "updated" if prior_present else "created"
    try:
        await record_llm_config_change(
            recorder,
            actor_user_id=actor_user_id,
            auth_principal=auth_principal,
            action=action,
            base_url=base_url,
            model=model,
            transport="ws",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning(f"llm_config_change audit failed (non-fatal): {exc}")
