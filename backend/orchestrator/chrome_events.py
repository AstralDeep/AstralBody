"""Feature 027 — chrome ui_event dispatcher.

Routes the settings-menu / surface / creation actions that arrive as
``{type:"ui_event", action, payload}`` from the web shell. Hooked from
``Orchestrator.handle_ui_message`` AFTER the legacy if/elif chain so the
026 actions are untouched; returns ``True`` when the action was handled
(including handled-with-error) and ``False`` for actions outside the
chrome/creation namespace.

Contract (contracts/chrome-ws-protocol.md): every failure renders an
in-modal error notice and structured-logs the exception — never a silent
drop. Admin-only surfaces/actions re-check the role server-side here
regardless of what the menu rendered (FR-014).
"""
import json
import logging

logger = logging.getLogger("Orchestrator.Chrome")

# Lazily aggregated {action: (surface_key, handler)} — surfaces register via
# their module-level HANDLERS dicts; agentic_creation contributes the
# draft/revision decision actions through the same mechanism.
_HANDLERS = None


def _handlers():
    global _HANDLERS
    if _HANDLERS is None:
        from webrender.chrome.surfaces import collect_handlers
        _HANDLERS = collect_handlers()
        try:
            from orchestrator import agentic_creation
            for action, fn in agentic_creation.HANDLERS.items():
                _HANDLERS[action] = ("drafts", fn)
        except Exception:
            logger.exception("chrome: agentic_creation handlers unavailable")
    return _HANDLERS


def _is_chrome_action(action: str) -> bool:
    return bool(action) and (
        action.startswith("chrome_")
        or action in ("draft_approve", "draft_refine", "draft_discard",
                      "revision_apply", "revision_discard")
    )


def _roles(orch, websocket) -> list:
    """Roles from the validated register_ui JWT claims (mock auth ⇒ admin)."""
    claims = orch.ui_sessions.get(websocket) or {}
    roles = list((claims.get("realm_access") or {}).get("roles") or [])
    for client in (claims.get("resource_access") or {}).values():
        roles.extend(client.get("roles") or [])
    return roles


async def _push_modal(orch, websocket, html: str):
    from shared.protocol import ChromeRender
    await orch._safe_send(websocket, ChromeRender(region="modal", html=html).to_json())


async def _render_surface(orch, websocket, user_id, roles, surface_key: str,
                          params: dict, notice_html: str = ""):
    """Render a surface into the modal (admin-gated; error block on failure)."""
    from webrender.chrome import chrome_error_block, render_modal_shell
    from webrender.chrome.surfaces import get_surface

    mod = get_surface(surface_key)
    if mod is None:
        logger.warning("chrome: unknown surface %r requested", surface_key)
        await _push_modal(orch, websocket, render_modal_shell(
            "Not available", chrome_error_block(f"Unknown settings surface: {surface_key}")))
        return
    if getattr(mod, "ADMIN_ONLY", False) and "admin" not in roles:
        logger.warning("chrome: non-admin %s denied surface %s", user_id, surface_key)
        await _audit_admin_rejection(orch, websocket, user_id, surface_key)
        await _push_modal(orch, websocket, render_modal_shell(
            "Not authorized", chrome_error_block("This area requires the admin role.")))
        return
    try:
        body = await mod.render(orch, user_id, roles, params or {})
    except Exception:
        logger.exception("chrome: surface %s render failed", surface_key)
        await _push_modal(orch, websocket, render_modal_shell(
            getattr(mod, "TITLE", surface_key),
            chrome_error_block("This surface failed to load. Please retry.", surface_key)))
        return
    await _push_modal(orch, websocket, render_modal_shell(
        getattr(mod, "TITLE", surface_key), (notice_html or "") + body, surface_key))


async def _audit_admin_rejection(orch, websocket, user_id: str, what: str):
    """US4 scenario 3 — audit a server-side admin rejection (best-effort)."""
    try:
        from datetime import datetime, timezone

        from audit.recorder import get_recorder, make_correlation_id
        from audit.schemas import AuditEventCreate
        rec = get_recorder()
        if rec is None:
            return
        await rec.record(AuditEventCreate(
            actor_user_id=user_id or "unknown",
            auth_principal=user_id or "unknown",
            event_class="settings",
            action_type="settings.admin_denied",
            description=f"Non-admin attempted admin surface/action: {what}",
            correlation_id=make_correlation_id(),
            outcome="failure",
            started_at=datetime.now(timezone.utc),
        ))
    except Exception:
        logger.debug("chrome: admin-rejection audit failed", exc_info=True)


async def handle_chrome_event(orch, websocket, action: str, payload: dict,
                              user_id: str) -> bool:
    """Dispatch one chrome/creation ui_event. Returns True if handled."""
    if not _is_chrome_action(action):
        return False
    payload = payload or {}
    roles = _roles(orch, websocket)

    try:
        if action == "chrome_close":
            await _push_modal(orch, websocket, "")
            return True

        if action == "chrome_open":
            surface = str(payload.get("surface") or "")
            params = payload.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}
            await _render_surface(orch, websocket, user_id, roles, surface, params)
            return True

        entry = _handlers().get(action)
        if entry is None:
            logger.warning("chrome: unknown chrome action %r", action)
            from webrender.chrome import chrome_error_block, render_modal_shell
            await _push_modal(orch, websocket, render_modal_shell(
                "Not available", chrome_error_block(f"Unknown action: {action}")))
            return True

        surface_key, fn = entry
        # Admin re-check for actions owned by admin-only surfaces (FR-014).
        from webrender.chrome.surfaces import get_surface
        owner = get_surface(surface_key)
        if owner is not None and getattr(owner, "ADMIN_ONLY", False) and "admin" not in roles:
            logger.warning("chrome: non-admin %s denied action %s", user_id, action)
            await _audit_admin_rejection(orch, websocket, user_id, action)
            from webrender.chrome import chrome_error_block, render_modal_shell
            await _push_modal(orch, websocket, render_modal_shell(
                "Not authorized", chrome_error_block("This action requires the admin role.")))
            return True

        result = await fn(orch, websocket, user_id, roles, payload)
        if result is not None:
            re_surface, re_params, notice_html = result
            await _render_surface(orch, websocket, user_id, roles, re_surface,
                                  re_params or {}, notice_html or "")
        return True

    except Exception:
        logger.exception("chrome: action %s failed", action)
        try:
            from webrender.chrome import chrome_error_block, render_modal_shell
            await _push_modal(orch, websocket, render_modal_shell(
                "Something went wrong",
                chrome_error_block("The action failed. Please retry.")))
        except Exception:
            logger.debug("chrome: error-notice push failed", exc_info=True)
        return True
