"""Feature 027 — LLM settings surface (key ``llm``, contract settings-surfaces.md).

Form for the user's personal, session-scoped LLM credentials (feature 006
storage model unchanged — A6): ``base_url`` (text), ``api_key`` (password,
write-only display — a "saved" placeholder is shown when session credentials
exist and the key itself is NEVER echoed back into markup), and ``model``
(text input, upgraded to a ``<select>`` after ``chrome_llm_models`` loads the
endpoint's advertised ids).

Actions (all explicit-save, FR-016):

* ``chrome_llm_models`` — reuse the ``POST /api/llm/list-models`` endpoint
  internals (:func:`llm_config.api.list_models`) and re-render with a model
  ``<select>``.
* ``chrome_llm_test`` — reuse the ``POST /api/llm/test`` probe internals
  (:func:`llm_config.api.test_connection`; emits the same ``tested`` audit
  event) and render the verdict (ok/latency or error_class + upstream
  message).
* ``chrome_llm_save`` / ``chrome_llm_clear`` — persist to / clear from the
  per-session store via the SAME WS handlers the ``llm_config_set`` /
  ``llm_config_clear`` messages use (:mod:`llm_config.ws_handlers`), with the
  live websocket, the orchestrator's ``_session_llm_creds`` store and audit
  recorder — audit/ack behavior preserved verbatim.

Credentials live in memory keyed by ``id(websocket)`` and die with the
socket; they are never persisted, never logged, and never placed in a
re-render ``params`` dict or HTML attribute.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

from pydantic import ValidationError

from webrender.chrome import esc, notice_block

logger = logging.getLogger("Orchestrator.Chrome.LLM")

TITLE = "LLM settings"

SURFACE_KEY = "llm"

# Max characters of the upstream error message surfaced into a notice.
_UPSTREAM_SNIPPET_LEN = 300

_INPUT_CLS = (
    "rounded-lg bg-white/10 border border-white/10 px-3 py-2 text-sm "
    "text-astral-text w-full focus:outline-none focus:border-astral-primary/50"
)
_LABEL_CLS = "flex flex-col gap-1 text-sm"
_LABEL_TEXT_CLS = "text-astral-text font-medium"


# ---------------------------------------------------------------------------
# Internals plumbing
# ---------------------------------------------------------------------------

def _fields(payload: Any) -> Dict[str, str]:
    """Extract the stripped-string field map from a ``ui_event`` payload.

    Args:
        payload: The raw ``ui_event`` payload; ``payload["fields"]`` is the
            ``{name: value}`` map collected from the ``data-ui-form``
            container (chrome-ws-protocol.md).

    Returns:
        ``{name: stripped string value}`` for every string-able field.
    """
    raw = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and v is not None and not isinstance(v, (dict, list)):
            out[k] = str(v).strip()
    return out


def _claims(orch: Any, websocket: Any) -> Dict[str, Any]:
    """Return the JWT claims registered for ``websocket`` (empty dict if none)."""
    try:
        return (getattr(orch, "ui_sessions", None) or {}).get(websocket) or {}
    except Exception:
        return {}


def _actor(orch: Any, websocket: Any, user_id: str) -> Tuple[str, str]:
    """Mirror the orchestrator's ``llm_config_*`` actor attribution.

    Returns:
        ``(actor_user_id, auth_principal)`` exactly as the WS
        ``llm_config_set`` / ``llm_config_clear`` branch derives them.
    """
    claims = _claims(orch, websocket)
    actor_user_id = claims.get("sub") or user_id or "legacy"
    auth_principal = claims.get("preferred_username") or claims.get("sub") or "unknown"
    return actor_user_id, auth_principal


def _store(orch: Any):
    """The orchestrator's per-session credential store (``_session_llm_creds``)."""
    return getattr(orch, "_session_llm_creds", None)


def _socket_creds(orch: Any, websocket: Any):
    """Session credentials saved on THIS websocket, or ``None``."""
    store = _store(orch)
    if store is None or websocket is None:
        return None
    try:
        return store.get(id(websocket))
    except Exception:
        return None


def _user_creds(orch: Any, user_id: str):
    """Most recent session credentials on any of the user's live sockets.

    ``render`` does not receive the websocket, so the "saved" state is
    resolved by scanning ``orch.ui_sessions`` for sockets whose claims
    ``sub`` matches ``user_id`` and checking the per-session store. With
    multiple tabs the most recently set entry wins.

    Returns:
        A ``SessionCreds``-shaped object or ``None``.
    """
    store = _store(orch)
    if store is None:
        return None
    best = None
    try:
        for ws, claims in list((getattr(orch, "ui_sessions", None) or {}).items()):
            if ((claims or {}).get("sub") or "legacy") != user_id:
                continue
            creds = store.get(id(ws))
            if creds is None:
                continue
            if best is None or getattr(creds, "set_at", 0.0) >= getattr(best, "set_at", 0.0):
                best = creds
    except Exception:
        logger.exception("llm surface: session-credential scan failed")
        return None
    return best


def _resolve_api_key(orch: Any, websocket: Any, fields: Dict[str, str]) -> Tuple[str, bool]:
    """Resolve the API key for an action: submitted value or the saved one.

    The password field is write-only — a blank submission means "keep the key
    already saved for this session" (the form's hint says so).

    Returns:
        ``(api_key, used_saved)`` — ``api_key`` may be ``""`` when neither
        a submitted nor a saved key exists.
    """
    submitted = fields.get("api_key", "")
    if submitted:
        return submitted, False
    saved = _socket_creds(orch, websocket)
    if saved is not None and getattr(saved, "api_key", ""):
        return saved.api_key, True
    return "", False


def _request_shim(orch: Any) -> Any:
    """Minimal stand-in for the FastAPI ``Request`` the probe endpoints take.

    :func:`llm_config.api.test_connection` only uses the request to reach
    ``request.app.state.orchestrator``; this shim provides exactly that.
    """
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(orchestrator=orch)))


def _validation_message(exc: ValidationError) -> str:
    """First pydantic validation error as a short ``field: message`` string."""
    try:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in (first.get("loc") or ())) or "input"
        return f"{loc}: {first.get('msg', 'invalid value')}"
    except Exception:
        return "Invalid input."


def _failure_notice(prefix: str, error_class: Optional[str], upstream_message: Optional[str]) -> str:
    """Error notice carrying the probe taxonomy class + upstream snippet."""
    detail = (upstream_message or "")[:_UPSTREAM_SNIPPET_LEN]
    msg = f"{prefix} ({error_class or 'unknown'})"
    if detail:
        msg = f"{msg}: {detail}"
    return notice_block("error", msg)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _model_field(model: str, models: Optional[list]) -> str:
    """The model input — a ``<select>`` once models are loaded, else text."""
    if models:
        listed = list(dict.fromkeys(str(m) for m in models if str(m).strip()))
        if model and model not in listed:
            listed.insert(0, model)
        opts = []
        for m in listed:
            sel = " selected" if m == model else ""
            opts.append(f'<option value="{esc(m)}"{sel}>{esc(m)}</option>')
        return f'<select name="model" class="{_INPUT_CLS}">{"".join(opts)}</select>'
    return (
        f'<input type="text" name="model" value="{esc(model)}" '
        f'placeholder="e.g. gpt-4o-mini" autocomplete="off" class="{_INPUT_CLS}">'
    )


def _button(action: str, label: str, primary: bool = False, collect: bool = True) -> str:
    """A chrome action button (``data-ui-action`` + optional field collection)."""
    if primary:
        cls = ("bg-astral-primary/20 text-astral-primary border border-astral-primary/30 "
               "hover:bg-astral-primary/30")
    else:
        cls = "bg-white/5 text-astral-text border border-white/10 hover:bg-white/10"
    collect_attr = ' data-ui-collect="true"' if collect else ""
    return (
        f'<button type="button" class="px-3 py-2 rounded-lg text-sm font-medium {cls}" '
        f'data-ui-action="{esc(action)}"{collect_attr}>{esc(label)}</button>'
    )


async def render(orch: Any, user_id: str, roles: Any, params: Any) -> str:
    """Render the LLM settings form body.

    Args:
        orch: The orchestrator (session-credential store + UI sessions).
        user_id: Authenticated user id (claims ``sub``).
        roles: Session roles (unused — surface is available to everyone).
        params: Optional server-side re-render state from handlers:
            ``base_url`` / ``model`` (submitted values to preserve, FR-016)
            and ``models`` (list of ids → model ``<select>``). NEVER carries
            an API key.

    Returns:
        Body HTML (every dynamic interpolation through ``esc()``).
    """
    _ = roles
    params = params if isinstance(params, dict) else {}
    saved = _user_creds(orch, user_id)
    base_url = str(params.get("base_url") or (getattr(saved, "base_url", "") if saved else "") or "")
    model = str(params.get("model") or (getattr(saved, "model", "") if saved else "") or "")
    models = params.get("models") if isinstance(params.get("models"), list) else None

    if saved is not None:
        key_placeholder = "Saved for this session — leave blank to keep"
        key_hint = (
            '<p class="text-xs text-astral-muted">An API key is saved for this session. '
            "It is never displayed; leave the field blank to keep using it.</p>"
        )
        saved_badge = (
            '<span class="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 '
            'rounded-full bg-green-500/10 text-green-400 border border-green-500/20">'
            "saved this session</span>"
        )
        clear_btn = _button("chrome_llm_clear", "Clear saved config", collect=False)
    else:
        key_placeholder = "sk-..."
        key_hint = ""
        saved_badge = (
            '<span class="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 '
            'rounded-full bg-white/5 text-astral-muted border border-white/10">'
            "not configured</span>"
        )
        clear_btn = ""

    return (
        '<p class="text-xs text-astral-muted">Your personal LLM credentials are held in memory '
        "for this session only — they are never persisted server-side and are discarded when "
        "the connection closes.</p>"
        '<div data-ui-form class="space-y-4">'
        '<div class="bg-white/5 border border-white/10 rounded-lg p-4 space-y-3">'
        f'<div class="flex items-center justify-between">'
        f'<span class="{_LABEL_TEXT_CLS}">Personal LLM configuration</span>{saved_badge}</div>'
        f'<label class="{_LABEL_CLS}"><span class="{_LABEL_TEXT_CLS}">Base URL</span>'
        f'<input type="text" name="base_url" value="{esc(base_url)}" '
        f'placeholder="https://api.openai.com/v1" autocomplete="off" class="{_INPUT_CLS}"></label>'
        f'<label class="{_LABEL_CLS}"><span class="{_LABEL_TEXT_CLS}">API key</span>'
        f'<input type="password" name="api_key" value="" placeholder="{esc(key_placeholder)}" '
        f'autocomplete="off" class="{_INPUT_CLS}">'
        f"</label>{key_hint}"
        f'<label class="{_LABEL_CLS}"><span class="{_LABEL_TEXT_CLS}">Model</span>'
        f"{_model_field(model, models)}</label>"
        "</div>"
        '<div class="flex flex-wrap gap-2">'
        f'{_button("chrome_llm_models", "Load models")}'
        f'{_button("chrome_llm_test", "Test connection")}'
        f'{_button("chrome_llm_save", "Save", primary=True)}'
        f"{clear_btn}"
        "</div></div>"
    )


async def components(orch: Any, user_id: str, roles: Any, params: Any):
    """Feature 043 — the LLM settings surface as native SDUI components.

    A single ``ParamPicker`` action-submit form (base_url / api_key [password,
    write-only] / model [text or select]) with Load-models / Test / Save action
    buttons that all submit the collected fields to the SAME ``chrome_llm_*``
    handlers the web uses, plus a Clear button when a config is saved.
    """
    from webrender.chrome.surfaces import _sdui
    params = params if isinstance(params, dict) else {}
    saved = _user_creds(orch, user_id)
    base_url = str(params.get("base_url") or (getattr(saved, "base_url", "") if saved else "") or "")
    model = str(params.get("model") or (getattr(saved, "model", "") if saved else "") or "")
    models = params.get("models") if isinstance(params.get("models"), list) else None

    if models:
        listed = list(dict.fromkeys(str(m) for m in models if str(m).strip()))
        if model and model not in listed:
            listed.insert(0, model)
        model_field = _sdui.field("model", "Model", "select", default=model, options=listed)
    else:
        model_field = _sdui.field("model", "Model", "text", default=model, help="e.g. gpt-4o-mini")

    key_help = ("An API key is saved for this session; it is never displayed — leave blank to keep it."
                if saved is not None else "Held in memory for this session only; never persisted.")
    out = [
        _sdui.text("Your personal LLM credentials are held in memory for this session only — "
                   "never persisted server-side, discarded when the connection closes.", "caption"),
        _sdui.badge("saved this session" if saved is not None else "not configured",
                    "success" if saved is not None else "default"),
        _sdui.form(
            [_sdui.field("base_url", "Base URL", "text", default=base_url,
                         help="https://api.openai.com/v1"),
             _sdui.field("api_key", "API key", "password", help=key_help),
             model_field],
            actions=[
                {"label": "Load models", "action": "chrome_llm_models"},
                {"label": "Test connection", "action": "chrome_llm_test"},
                {"label": "Save", "action": "chrome_llm_save", "variant": "primary"},
            ],
        ),
    ]
    if saved is not None:
        out.append(_sdui.button("Clear saved config", "chrome_llm_clear", variant="secondary"))
    return out


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _handle_models(orch: Any, websocket: Any, user_id: str, roles: Any, payload: Any):
    """``chrome_llm_models {fields}`` — list the endpoint's advertised models.

    Reuses :func:`llm_config.api.list_models` (the ``POST /api/llm/list-models``
    endpoint body) and re-renders the surface with a model ``<select>``.
    """
    _ = roles
    from llm_config.api import ListModelsRequest, list_models

    fields = _fields(payload)
    keep: Dict[str, Any] = {"base_url": fields.get("base_url", ""), "model": fields.get("model", "")}
    api_key, _used_saved = _resolve_api_key(orch, websocket, fields)
    if not keep["base_url"] or not api_key:
        return (SURFACE_KEY, keep, notice_block(
            "error",
            "Base URL and API key are required to load models "
            "(the key may be left blank only when one is already saved).",
        ))
    try:
        body = ListModelsRequest(api_key=api_key, base_url=keep["base_url"])
    except ValidationError as exc:
        return (SURFACE_KEY, keep, notice_block("error", _validation_message(exc)))

    resp = await list_models(
        body=body,
        request=_request_shim(orch),
        user_id=user_id,
        user_payload=_claims(orch, websocket),
    )
    if not resp.ok:
        return (SURFACE_KEY, keep, _failure_notice(
            "Couldn't load models", resp.error_class, resp.upstream_message))
    if not resp.models:
        return (SURFACE_KEY, keep, notice_block(
            "info", "The endpoint advertises no models — enter a model id manually."))
    keep["models"] = list(resp.models)
    return (SURFACE_KEY, keep, notice_block(
        "success", f"Loaded {len(resp.models)} models from {body.base_url}."))


async def _handle_test(orch: Any, websocket: Any, user_id: str, roles: Any, payload: Any):
    """``chrome_llm_test {fields}`` — probe the configuration, render verdict.

    Reuses :func:`llm_config.api.test_connection` (the ``POST /api/llm/test``
    endpoint body), which performs the 1-token probe AND emits the same
    ``llm_config_change(action="tested")`` audit event via
    ``orch.audit_recorder``.
    """
    _ = roles
    from llm_config.api import TestConnectionRequest, test_connection

    fields = _fields(payload)
    keep: Dict[str, Any] = {"base_url": fields.get("base_url", ""), "model": fields.get("model", "")}
    api_key, _used_saved = _resolve_api_key(orch, websocket, fields)
    if not keep["base_url"] or not keep["model"] or not api_key:
        return (SURFACE_KEY, keep, notice_block(
            "error",
            "Base URL, API key, and model are all required to test the connection "
            "(the key may be left blank only when one is already saved).",
        ))
    try:
        body = TestConnectionRequest(api_key=api_key, base_url=keep["base_url"], model=keep["model"])
    except ValidationError as exc:
        return (SURFACE_KEY, keep, notice_block("error", _validation_message(exc)))

    resp = await test_connection(
        body=body,
        request=_request_shim(orch),
        user_id=user_id,
        user_payload=_claims(orch, websocket),
    )
    if resp.ok:
        latency = f" in {int(resp.latency_ms)} ms" if resp.latency_ms is not None else ""
        return (SURFACE_KEY, keep, notice_block(
            "success", f"Connection OK — model {resp.model} responded{latency}."))
    return (SURFACE_KEY, keep, _failure_notice(
        "Connection test failed", resp.error_class, resp.upstream_message))


async def _handle_save(orch: Any, websocket: Any, user_id: str, roles: Any, payload: Any):
    """``chrome_llm_save {fields}`` — persist to the per-session store.

    Delegates to :func:`llm_config.ws_handlers.handle_llm_config_set` — the
    EXACT function the WS ``llm_config_set`` branch calls — with the live
    websocket, ``orch._session_llm_creds``, ``orch.audit_recorder`` and the
    same actor attribution, so validation, audit
    (``llm_config_change created|updated``) and the ``llm_config_ack`` reply
    are preserved verbatim.
    """
    _ = roles
    from llm_config.ws_handlers import handle_llm_config_set

    fields = _fields(payload)
    keep: Dict[str, Any] = {"base_url": fields.get("base_url", ""), "model": fields.get("model", "")}
    api_key, used_saved = _resolve_api_key(orch, websocket, fields)
    missing = [name for name, val in (
        ("base URL", keep["base_url"]), ("API key", api_key), ("model", keep["model"]),
    ) if not val]
    if missing:
        return (SURFACE_KEY, keep, notice_block(
            "error", "Cannot save — missing: " + ", ".join(missing) + "."))

    store = _store(orch)
    if store is None:
        return (SURFACE_KEY, keep, notice_block(
            "error", "Session credential store unavailable — try reloading the page."))

    actor_user_id, auth_principal = _actor(orch, websocket, user_id)
    await handle_llm_config_set(
        safe_send=orch._safe_send,
        websocket=websocket,
        config={"api_key": api_key, "base_url": keep["base_url"], "model": keep["model"]},
        actor_user_id=actor_user_id,
        auth_principal=auth_principal,
        creds_store=store,
        recorder=orch.audit_recorder,
    )
    if id(websocket) not in store:
        # handle_llm_config_set rejected the payload (it already sent the
        # llm_config_invalid error over the socket); mirror it in the modal.
        return (SURFACE_KEY, keep, notice_block(
            "error", "Save rejected — all three fields must be non-empty."))
    suffix = " (kept the previously saved API key)" if used_saved else ""
    return (SURFACE_KEY, keep, notice_block(
        "success", f"LLM settings saved for this session{suffix}."))


async def _handle_clear(orch: Any, websocket: Any, user_id: str, roles: Any, payload: Any):
    """``chrome_llm_clear`` — drop this session's saved credentials.

    Delegates to :func:`llm_config.ws_handlers.handle_llm_config_clear` (the
    WS ``llm_config_clear`` branch's function) with the live websocket —
    pop + conditional ``llm_config_change(cleared)`` audit + ack preserved.
    """
    _ = roles
    _ = payload
    from llm_config.ws_handlers import handle_llm_config_clear

    store = _store(orch)
    if store is None:
        return (SURFACE_KEY, {}, notice_block(
            "error", "Session credential store unavailable — try reloading the page."))
    had_creds = id(websocket) in store
    actor_user_id, auth_principal = _actor(orch, websocket, user_id)
    await handle_llm_config_clear(
        safe_send=orch._safe_send,
        websocket=websocket,
        actor_user_id=actor_user_id,
        auth_principal=auth_principal,
        creds_store=store,
        recorder=orch.audit_recorder,
    )
    message = (
        "Session LLM credentials cleared." if had_creds
        else "No session LLM credentials were saved."
    )
    return (SURFACE_KEY, {}, notice_block("success" if had_creds else "info", message))


HANDLERS = {
    "chrome_llm_models": _handle_models,
    "chrome_llm_test": _handle_test,
    "chrome_llm_save": _handle_save,
    "chrome_llm_clear": _handle_clear,
}
