"""
BFF (Backend for Frontend) Auth Proxy.

Proxies OIDC token exchange requests to Keycloak, injecting the
client_secret server-side so it never reaches the browser.

Accepts requests in application/x-www-form-urlencoded format
(as sent by oidc-client-ts) and forwards them to Keycloak with
the client_secret appended.
"""
import os
import logging

import aiohttp
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("AuthProxy")

app = FastAPI(title="AstralBody Auth Proxy")

# CORS — allow the frontend origin to make token exchange requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_keycloak_config():
    """Read Keycloak settings from environment."""
    authority = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")
    client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "")
    client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
    return authority, client_id, client_secret


@app.post("/auth/token")
async def proxy_token(request: Request):
    """
    Proxy token requests to Keycloak's token endpoint.

    Accepts the same application/x-www-form-urlencoded body that
    oidc-client-ts sends (grant_type, code, redirect_uri, code_verifier,
    client_id, etc.) and injects the client_secret before forwarding.
    Also handles refresh_token grant type.
    """
    authority, client_id, client_secret = _get_keycloak_config()

    if not authority or not client_id or not client_secret:
        return JSONResponse(
            status_code=500,
            content={
                "error": "server_error",
                "error_description": "Keycloak not configured on backend",
            },
        )

    token_url = f"{authority}/protocol/openid-connect/token"

    # Read the form data sent by oidc-client-ts
    form = await request.form()
    form_data = dict(form)

    # Inject client_secret (server-side only)
    form_data["client_secret"] = client_secret

    # Ensure client_id is set
    if "client_id" not in form_data:
        form_data["client_id"] = client_id

    grant_type = form_data.get("grant_type", "unknown")
    logger.info(f"Proxying {grant_type} request to Keycloak")

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=form_data) as resp:
            body = await resp.json()
            if resp.status != 200:
                logger.error(f"Token request failed ({grant_type}): {resp.status} {body}")
                return JSONResponse(status_code=resp.status, content=body)
            logger.info(f"Token request successful ({grant_type})")
            return JSONResponse(content=body)
