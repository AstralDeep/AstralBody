"""Native desktop OIDC login — Authorization Code + PKCE with a loopback
redirect (RFC 8252). Opens the system browser to Keycloak, captures the auth
code on a localhost callback, and exchanges it for an access token. Stdlib only.

Requires a public Keycloak client (default ``astral-desktop``) with Standard
Flow + PKCE (S256) and a loopback redirect URI (http://127.0.0.1:*/callback),
and the orchestrator's KEYCLOAK_ALLOWED_AZP including that client id.
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


@dataclass
class Session:
    """A logged-in session — current access token + silent refresh."""
    access_token: str
    refresh_token: Optional[str]
    token_endpoint: str
    client_id: str

    def refresh(self) -> Optional[str]:
        """Refresh the access token using the refresh token. Returns the new
        access token, or None if refresh isn't possible."""
        if not self.refresh_token:
            return None
        try:
            data = urlencode({"grant_type": "refresh_token", "refresh_token": self.refresh_token,
                              "client_id": self.client_id}).encode()
            r = json.load(urlopen(Request(self.token_endpoint, data=data,
                          headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=15))
            self.access_token = r["access_token"]
            self.refresh_token = r.get("refresh_token", self.refresh_token)
            return self.access_token
        except Exception:  # noqa: BLE001
            logger.warning("token refresh failed", exc_info=True)
            return None


def oidc_login(authority: str, client_id: str = "astral-desktop",
               scopes: str = _DEFAULT_SCOPES, timeout: int = 300) -> Session:
    """Run the interactive PKCE loopback login and return a Session.

    ``authority`` is the Keycloak realm URL, e.g.
    ``https://iam.example.com/realms/Astral``.
    """
    conf = json.load(urlopen(f"{authority.rstrip('/')}/.well-known/openid-configuration", timeout=15))
    auth_ep, token_ep = conf["authorization_endpoint"], conf["token_endpoint"]

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

        def log_message(self, *a):  # silence the dev server
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

    server.timeout = timeout
    # handle a single callback request (the redirect), then close.
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    t.join(timeout)
    server.server_close()

    code = captured.get("code")
    if not code:
        raise RuntimeError("OIDC login did not complete (no authorization code).")
    if captured.get("state") != state:
        raise RuntimeError("OIDC state mismatch — aborting.")

    data = urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "code_verifier": verifier,
    }).encode()
    tok = json.load(urlopen(Request(token_ep, data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=20))
    return Session(access_token=tok["access_token"], refresh_token=tok.get("refresh_token"),
                   token_endpoint=token_ep, client_id=client_id)
