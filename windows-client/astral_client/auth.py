"""Native desktop OIDC login that REUSES the web's `astral-frontend` client.

`astral-frontend` is a *confidential* Keycloak client (it has a client_secret),
so the desktop can't exchange the auth code directly — it would have to embed the
secret. Instead it does Authorization-Code + PKCE with a loopback redirect (RFC
8252) for the browser step, then exchanges the code through the orchestrator's
existing **BFF token proxy** (`POST {base}/auth/token`), which injects the secret
server-side. No new Keycloak client and no azp change are needed; the only realm
change is adding the loopback redirect URI (`http://127.0.0.1/*`) to
`astral-frontend`'s allowed redirects.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("astral.auth")

_DEFAULT_SCOPES = "openid profile email offline_access"
_DONE_HTML = (b"<html><body style='font-family:sans-serif;background:#0F1221;color:#F3F4F6;"
              b"text-align:center;padding-top:80px'><h2>AstralBody</h2>"
              b"<p>Login complete - you can close this window.</p></body></html>")


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _post_form(url: str, fields: dict, timeout: int = 20) -> dict:
    data = urlencode(fields).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.load(urlopen(req, timeout=timeout))


@dataclass
class Session:
    """A logged-in session — current access token + silent refresh, both routed
    through the orchestrator's BFF token proxy (``token_url``)."""
    access_token: str
    refresh_token: Optional[str]
    token_url: str
    client_id: str

    def refresh(self) -> Optional[str]:
        if not self.refresh_token:
            return None
        try:
            r = _post_form(self.token_url, {"grant_type": "refresh_token",
                                            "refresh_token": self.refresh_token,
                                            "client_id": self.client_id}, timeout=15)
            self.access_token = r["access_token"]
            self.refresh_token = r.get("refresh_token", self.refresh_token)
            return self.access_token
        except Exception:  # noqa: BLE001
            logger.warning("token refresh failed", exc_info=True)
            return None


def oidc_login(authority: str, bff_base: str, client_id: str = "astral-frontend",
               scopes: str = _DEFAULT_SCOPES, timeout: int = 300) -> Session:
    """Interactive PKCE loopback login that exchanges through the BFF.

    ``authority`` — the Keycloak realm URL (used only to find the *authorize*
    endpoint for the browser step). ``bff_base`` — the orchestrator HTTP origin
    (e.g. ``http://127.0.0.1:8001``); the code/refresh exchange POSTs to
    ``{bff_base}/auth/token``.
    """
    conf = json.load(urlopen(f"{authority.rstrip('/')}/.well-known/openid-configuration", timeout=15))
    auth_ep = conf["authorization_endpoint"]
    token_url = f"{bff_base.rstrip('/')}/auth/token"

    verifier = _b64u(secrets.token_bytes(32))
    challenge = _b64u(hashlib.sha256(verifier.encode("ascii")).digest())
    state = _b64u(secrets.token_bytes(16))
    captured: dict = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = parse_qs(urlparse(self.path).query)
            captured["code"] = q.get("code", [None])[0]
            captured["state"] = q.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_DONE_HTML)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    params = urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
        "scope": scopes, "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state,
    })
    logger.info("opening browser for OIDC login (client=%s)", client_id)
    webbrowser.open(f"{auth_ep}?{params}")

    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    t.join(timeout)
    server.server_close()

    code = captured.get("code")
    if not code:
        raise RuntimeError("OIDC login did not complete (no authorization code).")
    if captured.get("state") != state:
        raise RuntimeError("OIDC state mismatch — aborting.")

    tok = _post_form(token_url, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "code_verifier": verifier,
    })
    return Session(access_token=tok["access_token"], refresh_token=tok.get("refresh_token"),
                   token_url=token_url, client_id=client_id)
