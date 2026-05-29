"""Feature 026 — server-side OIDC Authorization-Code flow (FR-009).

Replaces the removed React client-side auth (oidc-client-ts). The orchestrator
now drives login server-side: ``/auth/login`` → Keycloak authorize (PKCE),
``/auth/callback`` → token exchange (confidential client_secret stays
server-side), ``/auth/session`` → hands the access token to the WS
``register_ui`` handshake, ``/auth/logout`` → Keycloak end-session + offline-
tolerant sign-out. Tokens stay server-side in a signed-cookie session.

Preserves: JWKS validation (via the existing ``validate_token``), the
``openid profile email offline_access`` scope (so feature-025 OfflineGrant still
captures the refresh token), the 365-day persistent-login hard cap (feature 016),
and the ``auth.login_interactive`` / ``auth.session_resumed`` audit action types.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

logger = logging.getLogger("orchestrator.web_auth")

web_auth_router = APIRouter()

# In-memory session store: sid -> {access_token, refresh_token, sub, created_at}.
# Survives the process lifetime; production multi-worker deploys should back this
# with shared storage, but the contract (signed cookie + 365-day cap) is the same.
_SESSIONS: Dict[str, Dict[str, Any]] = {}
# Pending logins: state -> {code_verifier, created_at, next}
_PENDING: Dict[str, Dict[str, Any]] = {}

HARD_MAX_SECONDS = int(os.getenv("OFFLINE_GRANT_MAX_DAYS", "365")) * 24 * 60 * 60
COOKIE_NAME = "astral_session"
_SCOPE = "openid profile email offline_access"

_PROCESS_SECRET = secrets.token_hex(32)


def _is_mock() -> bool:
    return os.getenv("VITE_USE_MOCK_AUTH", "").strip().lower() in ("1", "true", "yes")


def _secret() -> bytes:
    return (os.getenv("WEB_SESSION_SECRET") or os.getenv("OFFLINE_GRANT_ENC_KEY") or _PROCESS_SECRET).encode()


def _sign(sid: str) -> str:
    mac = hmac.new(_secret(), sid.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{sid}.{mac}"


def _unsign(value: str) -> Optional[str]:
    if not value or "." not in value:
        return None
    sid, mac = value.rsplit(".", 1)
    expected = hmac.new(_secret(), sid.encode(), hashlib.sha256).hexdigest()[:32]
    return sid if hmac.compare_digest(mac, expected) else None


def _keycloak_config():
    """Reuse the existing helper (authority, client_id, client_secret)."""
    try:
        from orchestrator.auth import _get_keycloak_config
        return _get_keycloak_config()
    except Exception:
        return (
            os.getenv("VITE_KEYCLOAK_AUTHORITY", ""),
            os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend"),
            os.getenv("KEYCLOAK_CLIENT_SECRET", ""),
        )


def get_session(request: Request) -> Optional[Dict[str, Any]]:
    """Return the live session dict for a request, enforcing the 365-day cap."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    sid = _unsign(raw)
    if not sid:
        return None
    sess = _SESSIONS.get(sid)
    if not sess:
        return None
    if (time.time() - sess.get("created_at", 0)) > HARD_MAX_SECONDS:
        _SESSIONS.pop(sid, None)
        logger.info("web_auth: session %s exceeded 365-day cap — cleared", sid[:8])
        return None
    return sess


def session_token(request: Request) -> str:
    """Access token for the WS register_ui handshake ('' if unauthenticated)."""
    if _is_mock():
        return "dev-token"
    sess = get_session(request)
    return (sess or {}).get("access_token", "") or ""


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _redirect_uri(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/callback"


@web_auth_router.get("/auth/login")
async def auth_login(request: Request):
    """Begin the OIDC Authorization-Code flow (PKCE)."""
    nxt = request.query_params.get("next", "/")
    if _is_mock():
        # Dev/mock: mint a local session immediately, no Keycloak round-trip.
        return _establish_session(request, {"access_token": "dev-token", "refresh_token": "", "sub": "test_user"}, nxt)
    authority, client_id, _secret_unused = _keycloak_config()
    if not authority:
        return JSONResponse({"error": "OIDC not configured"}, status_code=500)
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    _PENDING[state] = {"code_verifier": verifier, "created_at": time.time(), "next": nxt}
    from urllib.parse import urlencode
    params = urlencode({
        "client_id": client_id, "response_type": "code", "scope": _SCOPE,
        "redirect_uri": _redirect_uri(request), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return RedirectResponse(f"{authority}/protocol/openid-connect/auth?{params}")


@web_auth_router.get("/auth/callback")
async def auth_callback(request: Request):
    """Exchange the authorization code for tokens, establish a session, audit
    ``auth.login_interactive``."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    pending = _PENDING.pop(state, None) if state else None
    if not code or not pending:
        return JSONResponse({"error": "invalid_callback"}, status_code=400)
    authority, client_id, client_secret = _keycloak_config()
    data = {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": _redirect_uri(request), "client_id": client_id,
        "code_verifier": pending["code_verifier"],
    }
    if client_secret:
        data["client_secret"] = client_secret
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{authority}/protocol/openid-connect/token", data=data)
        resp.raise_for_status()
        tok = resp.json()
    except Exception:
        logger.exception("web_auth: token exchange failed")
        return JSONResponse({"error": "token_exchange_failed"}, status_code=502)
    sub = _sub_from_jwt(tok.get("access_token", ""))
    _audit_login(request, sub, "login_interactive")
    return _establish_session(
        request,
        {"access_token": tok.get("access_token", ""), "refresh_token": tok.get("refresh_token", ""), "sub": sub},
        pending.get("next", "/"),
    )


@web_auth_router.get("/auth/session")
async def auth_session(request: Request):
    """Report the current session/token for the WS handshake."""
    if _is_mock():
        return JSONResponse({"authenticated": True, "access_token": "dev-token", "resumed": True})
    sess = get_session(request)
    if not sess:
        return JSONResponse({"authenticated": False, "access_token": "", "resumed": False})
    return JSONResponse({"authenticated": True, "access_token": sess.get("access_token", ""), "resumed": True})


@web_auth_router.post("/auth/logout")
@web_auth_router.get("/auth/logout")
async def auth_logout(request: Request):
    """Offline-tolerant sign-out: clear the server session, then best-effort
    Keycloak end-session (never blocks)."""
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        sid = _unsign(raw)
        if sid:
            _SESSIONS.pop(sid, None)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    if not _is_mock():
        authority, client_id, _ = _keycloak_config()
        if authority:
            from urllib.parse import urlencode
            params = urlencode({"client_id": client_id, "post_logout_redirect_uri": str(request.base_url).rstrip("/")})
            resp = RedirectResponse(f"{authority}/protocol/openid-connect/logout?{params}", status_code=303)
            resp.delete_cookie(COOKIE_NAME)
    return resp


def _establish_session(request: Request, payload: Dict[str, Any], nxt: str) -> RedirectResponse:
    sid = secrets.token_urlsafe(24)
    _SESSIONS[sid] = {**payload, "created_at": time.time()}
    safe_next = nxt if (nxt or "").startswith("/") else "/"
    resp = RedirectResponse(safe_next, status_code=303)
    secure = str(request.base_url).startswith("https")
    resp.set_cookie(COOKIE_NAME, _sign(sid), httponly=True, samesite="lax",
                    secure=secure, max_age=HARD_MAX_SECONDS, path="/")
    return resp


def _sub_from_jwt(token: str) -> str:
    """Best-effort, non-validating sub extraction (validation happens via JWKS
    in validate_token when register_ui arrives)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        import json
        return json.loads(base64.urlsafe_b64decode(payload)).get("sub", "anonymous")
    except Exception:
        return "anonymous"


def _audit_login(request: Request, sub: str, action: str) -> None:
    try:
        from audit.hooks import record_auth_event
        record_auth_event(action_type=f"auth.{action}", actor_user_id=sub or "anonymous",
                           detail={"flow": "server_oidc", "feature": "026"})
    except Exception:
        logger.debug("web_auth: audit hook unavailable for %s", action, exc_info=True)
