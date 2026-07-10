"""WebSocket message handlers for LLM configuration (features 006 + 054).

Feature 054 re-keyed these from the per-WebSocket in-memory store to the
persisted per-USER store (:class:`~llm_config.user_store.UserLLMConfigStore`):

* :func:`handle_llm_config_set` — validates the submission field-by-field,
  derives the base URL server-side for catalog presets, RE-RUNS the real
  connection probe (a save that has not just passed a probe is refused —
  spec FR-008), persists the record (API key Fernet-encrypted), audits, and
  acks. Returns ``True`` iff a configuration was persisted so the caller
  can run the first-run-gate unlock fan-out.
* :func:`handle_llm_config_clear` — deletes the user's record, audits, and
  acks. Returns ``True`` iff a record existed, so the caller can re-gate
  every one of the user's sockets (spec FR-009/FR-013).
* :func:`populate_from_register_ui` — RETIRED to accept-and-ignore: the
  server-persisted record is authoritative, but old clients may still send
  the field, so rejecting it would break wire compatibility.

Both mutating handlers are no-ops on unauthenticated sockets — the
orchestrator's ``_registered_events`` gating guarantees authentication
before dispatch.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from audit.recorder import Recorder

from .audit_events import record_llm_config_change
from .probe import probe_chat_completion
from .providers import get_preset, resolve_base_url
from .user_store import UserLLMConfigStore

logger = logging.getLogger("LLMConfig.WSHandlers")

SafeSend = Callable[[Any, str], Awaitable[None]]


def validate_config_submission(config: Dict[str, Any]) -> tuple:
    """Validate an ``llm_config_set``-shaped submission.

    Returns ``(fields, errors)`` where ``fields`` is the normalized
    ``{provider, base_url, model, api_key}`` dict (base URL already
    server-derived for catalog presets) and ``errors`` maps field name →
    human message. A non-empty ``errors`` means nothing may be stored.
    """
    if not isinstance(config, dict):
        return {}, {"config": "malformed payload"}
    provider = (config.get("provider") or "custom").strip().lower()
    api_key = (config.get("api_key") or "").strip()
    model = (config.get("model") or "").strip()
    submitted_url = (config.get("base_url") or "").strip()

    errors: Dict[str, str] = {}
    preset = get_preset(provider)
    if preset is None:
        errors["provider"] = f"unknown provider {provider!r}"
        return {}, errors
    base_url = resolve_base_url(provider, submitted_url)
    if not base_url:
        errors["base_url"] = "endpoint address is required"
    elif not (base_url.startswith("http://") or base_url.startswith("https://")):
        errors["base_url"] = "endpoint address must start with http:// or https://"
    if not model:
        errors["model"] = "model is required"
    if preset.key_required and not api_key:
        errors["api_key"] = f"an API key is required for {preset.label}"

    fields = {
        "provider": provider,
        "base_url": base_url or "",
        "model": model,
        "api_key": api_key,
    }
    return fields, errors


async def _send_invalid(safe_send: SafeSend, websocket: Any,
                        message: str, *, fields: Optional[Dict[str, str]] = None,
                        error_class: Optional[str] = None) -> None:
    payload: Dict[str, Any] = {
        "type": "error",
        "code": "llm_config_invalid",
        "message": message,
    }
    if fields:
        payload["fields"] = fields
    if error_class:
        payload["error_class"] = error_class
    await safe_send(websocket, json.dumps(payload))


async def handle_llm_config_set(
    *,
    safe_send: SafeSend,
    websocket: Any,
    config: Dict[str, Any],
    actor_user_id: str,
    auth_principal: str,
    store: UserLLMConfigStore,
    recorder: Recorder,
) -> bool:
    """Handle a ``llm_config_set`` WS message (persisted, probe-gated).

    Behaviour:

    * Field-level validation (per-field messages; nothing partial stored).
    * Server-side probe against the EXACT triple being saved; a failing
      probe refuses the save with its ``error_class``.
    * Persists via the store (upsert; API key encrypted at rest), emits
      ``llm_config_change(action=<created|updated>)``, acks
      ``llm_config_ack {ok:true}``.

    Returns ``True`` iff a configuration was persisted.
    """
    fields, errors = validate_config_submission(config)
    if errors:
        await _send_invalid(
            safe_send, websocket,
            "; ".join(f"{k}: {v}" for k, v in errors.items()),
            fields=errors,
        )
        return False

    ok, error_class, upstream = await probe_chat_completion(
        api_key=fields["api_key"], base_url=fields["base_url"], model=fields["model"])
    try:
        await record_llm_config_change(
            recorder,
            actor_user_id=actor_user_id,
            auth_principal=auth_principal,
            action="tested",
            base_url=fields["base_url"],
            model=fields["model"],
            transport="ws",
            result="success" if ok else "failure",
            error_class=error_class if not ok else None,
        )
    except Exception as exc:  # pragma: no cover — audit is best-effort
        logger.warning(f"llm_config_change(tested) audit failed (non-fatal): {exc}")
    if not ok:
        await _send_invalid(
            safe_send, websocket,
            f"Connection test failed ({error_class}): {upstream or 'no details'}",
            error_class=error_class,
        )
        return False

    prior = await store.get(actor_user_id)
    try:
        await store.set(
            actor_user_id,
            provider=fields["provider"],
            base_url=fields["base_url"],
            model=fields["model"],
            api_key=fields["api_key"],
        )
    except ValueError as exc:
        await _send_invalid(safe_send, websocket, str(exc))
        return False

    action = "updated" if prior is not None else "created"
    try:
        await record_llm_config_change(
            recorder,
            actor_user_id=actor_user_id,
            auth_principal=auth_principal,
            action=action,
            base_url=fields["base_url"],
            model=fields["model"],
            transport="ws",
        )
    except Exception as exc:  # pragma: no cover — audit is best-effort
        logger.warning(f"llm_config_change audit failed (non-fatal): {exc}")

    await safe_send(websocket, json.dumps({"type": "llm_config_ack", "ok": True}))
    return True


async def handle_llm_config_clear(
    *,
    safe_send: SafeSend,
    websocket: Any,
    actor_user_id: str,
    auth_principal: str,
    store: UserLLMConfigStore,
    recorder: Recorder,
) -> bool:
    """Handle a ``llm_config_clear`` WS message.

    Deletes the persisted record; emits ``llm_config_change(action="cleared")``
    only if there was a record (avoids audit noise); acks unconditionally.
    Returns ``True`` iff a record was removed — the caller uses this to
    re-gate all of the user's connected sockets immediately (there is no
    longer any default to revert to).
    """
    removed = await store.clear(actor_user_id)
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
    return removed


async def populate_from_register_ui(
    *,
    websocket: Any,
    llm_config: Optional[Dict[str, Any]],
    actor_user_id: str,
    auth_principal: str,
    recorder: Recorder,
    store: Optional[UserLLMConfigStore] = None,
) -> None:
    """RETIRED (feature 054): ``register_ui.llm_config`` is accepted and
    ignored for wire compatibility with pre-054 clients. The server-persisted
    per-user record is authoritative; seeding transient creds from a client
    payload would bypass the probe-gated save path.
    """
    if llm_config:
        logger.debug(
            "register_ui.llm_config ignored (feature 054: server-persisted "
            "config is authoritative)")
    return None
