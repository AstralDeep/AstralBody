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
import re

from shared.perf import perf_span

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


# --- Feature 043: device-target-aware surface delivery -----------------------
# Web (browser) → ChromeRender HTML modal (feature 027, unchanged). Native SDUI
# (windows/android) → ChromeSurface: a ROTE-adapted astralprims component list
# the client renders through its EXISTING renderer (contracts/chrome-surface.md).

_TAG_RE = re.compile(r"<[^>]+>")


def _device_type(orch, websocket) -> str:
    """The connecting client's ROTE device type ('browser'|'windows'|'android')."""
    try:
        prof = orch.rote.get_profile(websocket)
        return getattr(prof.device_type, "value", str(prof.device_type))
    except Exception:
        return "browser"


def _strip_html(html: str) -> str:
    """Best-effort plain text from a chrome notice's HTML (native has no HTML).

    Tags become SPACES (then whitespace collapses) so adjacent blocks don't
    fuse into one word — the theme notice used to read
    "Daylight theme saved.Theme applied" on native clients."""
    import html as _htmlmod
    return " ".join(_htmlmod.unescape(_TAG_RE.sub(" ", html or "")).split())


def _notice_components(notice_html: str) -> list:
    """Map a handler's re-render notice (HTML) to a leading Alert component."""
    text = _strip_html(notice_html)
    if not text:
        return []
    low = (notice_html or "").lower()  # infer kind from the notice_block color class
    variant = "error" if "red-" in low else "success" if "green-" in low else "info"
    return [{"type": "alert", "variant": variant, "message": text}]


async def _push_surface(orch, websocket, surface_key, title, admin_only, components):
    from shared.protocol import ChromeSurface
    await orch._safe_send(websocket, ChromeSurface(
        region="modal", surface_key=surface_key, title=title,
        admin_only=bool(admin_only), components=list(components or []),
    ).to_json())


# Feature 051: iOS/macOS join Windows/Android as chrome-model SDUI natives
# (the watch is deliberately chrome-free — no surfaces on the wrist).
_NATIVE_SDUI_DEVICE_TYPES = ("windows", "android", "ios", "macos")


async def _push_error_notice(orch, websocket, title: str, message: str,
                             surface_key: str = ""):
    """Device-aware error notice (feature 044, FR-002/FR-017).

    Web keeps the feature-027 HTML modal; native SDUI clients get a
    ``chrome_surface`` carrying an error Alert — an HTML frame would be
    invisible to them (the pre-044 gap)."""
    if _device_type(orch, websocket) in _NATIVE_SDUI_DEVICE_TYPES:
        from webrender.chrome.surfaces import _sdui
        await _push_surface(orch, websocket, surface_key or "error", title, False,
                            [_sdui.alert(message, "error")])
    else:
        from webrender.chrome import chrome_error_block, render_modal_shell
        await _push_modal(orch, websocket, render_modal_shell(
            title, chrome_error_block(message, surface_key or None)))


async def _push_close(orch, websocket):
    """Device-aware modal close: web clears the HTML modal region; native SDUI
    clients receive the documented empty-components ``chrome_surface`` form."""
    if _device_type(orch, websocket) in _NATIVE_SDUI_DEVICE_TYPES:
        await _push_surface(orch, websocket, "", "", False, [])
    else:
        await _push_modal(orch, websocket, "")


async def _render_surface(orch, websocket, user_id, roles, surface_key: str,
                          params: dict, notice_html: str = ""):
    """Render a surface into the modal, adapting to the connecting client.

    Web → ChromeRender HTML (unchanged). Native SDUI (windows/android) →
    ChromeSurface (ROTE-adapted astralprims components). Admin-gated and
    gracefully-degrading on either path (Constitution X/XII, FR-014).
    """
    with perf_span("surface.render." + surface_key, surface=surface_key):
        if _device_type(orch, websocket) in _NATIVE_SDUI_DEVICE_TYPES:
            await _render_surface_sdui(orch, websocket, user_id, roles,
                                       surface_key, params, notice_html)
        else:
            await _render_surface_html(orch, websocket, user_id, roles,
                                       surface_key, params, notice_html)


async def _render_surface_html(orch, websocket, user_id, roles, surface_key: str,
                               params: dict, notice_html: str = ""):
    """Web path — server-rendered HTML modal (feature 027; behavior unchanged)."""
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


async def _render_surface_sdui(orch, websocket, user_id, roles, surface_key: str,
                               params: dict, notice_html: str = ""):
    """Native SDUI path (feature 043) — a ROTE-adapted ChromeSurface frame."""
    from webrender.chrome.surfaces import _sdui, get_surface

    mod = get_surface(surface_key)
    if mod is None:
        logger.warning("chrome: unknown surface %r requested (native)", surface_key)
        await _push_surface(orch, websocket, surface_key, "Not available", False,
                            [_sdui.alert(f"Unknown settings surface: {surface_key}", "error")])
        return
    title = getattr(mod, "TITLE", surface_key)
    if getattr(mod, "ADMIN_ONLY", False) and "admin" not in roles:
        logger.warning("chrome: non-admin %s denied surface %s (native)", user_id, surface_key)
        await _audit_admin_rejection(orch, websocket, user_id, surface_key)
        await _push_surface(orch, websocket, surface_key, "Not authorized", True,
                            [_sdui.alert("This area requires the admin role.", "error")])
        return
    builder = getattr(mod, "components", None)
    if builder is None:
        # Not yet converted to SDUI → a single labeled placeholder (FR-014),
        # never the retired text placeholder and never a blank screen.
        await _push_surface(orch, websocket, surface_key, title, False, [_sdui.placeholder(title)])
        return
    try:
        comps = list(await builder(orch, user_id, roles, params or {}) or [])
    except Exception:
        logger.exception("chrome: surface %s components() failed", surface_key)
        await _push_surface(orch, websocket, surface_key, title, False,
                            [_sdui.alert("This surface failed to load. Please retry.", "error")])
        return
    payload = _notice_components(notice_html) + comps
    # ROTE-adapt for this device. Use ComponentAdapter directly (not
    # orch.rote.adapt) so surface components don't clobber the canvas
    # re-adaptation cache (orch.rote._last_components).
    try:
        from rote.adapter import ComponentAdapter
        payload = ComponentAdapter.adapt(payload, orch.rote.get_profile(websocket))
    except Exception:
        logger.debug("chrome: ROTE adapt failed; sending unadapted components", exc_info=True)
    await _push_surface(orch, websocket, surface_key, title,
                        getattr(mod, "ADMIN_ONLY", False), payload)


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
    # Resolved before the handler runs so an exception's error notice carries
    # the acting surface key (feature 044 — native key-matched reducers).
    err_surface = ""

    try:
        if action == "chrome_close":
            await _push_close(orch, websocket)
            return True

        if action == "chrome_open":
            surface = str(payload.get("surface") or "")
            params = payload.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}
            if isinstance(params, dict) and not params.get("chat_id"):
                # Feature 044: native clients don't inject chat_id client-side
                # (web's client.js does) — default to the socket's active chat
                # so per-chat surfaces (workspace_timeline) work everywhere.
                # Same fallback the timeline's _live handler already uses.
                chat_id = getattr(orch, "_ws_active_chat", {}).get(id(websocket), "")
                if chat_id:
                    params["chat_id"] = chat_id
            await _render_surface(orch, websocket, user_id, roles, surface, params)
            return True

        entry = _handlers().get(action)
        if entry is None:
            logger.warning("chrome: unknown chrome action %r", action)
            await _push_error_notice(orch, websocket, "Not available",
                                     f"Unknown action: {action}")
            return True

        surface_key, fn = entry
        err_surface = surface_key
        # Admin re-check for actions owned by admin-only surfaces (FR-014).
        from webrender.chrome.surfaces import get_surface
        owner = get_surface(surface_key)
        if owner is not None and getattr(owner, "ADMIN_ONLY", False) and "admin" not in roles:
            logger.warning("chrome: non-admin %s denied action %s", user_id, action)
            await _audit_admin_rejection(orch, websocket, user_id, action)
            await _push_error_notice(orch, websocket, "Not authorized",
                                     "This action requires the admin role.",
                                     surface_key)
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
            await _push_error_notice(orch, websocket, "Something went wrong",
                                     "The action failed. Please retry.",
                                     err_surface)
        except Exception:
            logger.debug("chrome: error-notice push failed", exc_info=True)
        return True
