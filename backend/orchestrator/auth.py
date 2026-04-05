"""
BFF (Backend for Frontend) Auth Proxy.

Proxies OIDC token exchange requests to Keycloak, injecting the
client_secret server-side so it never reaches the browser.

Accepts requests in application/x-www-form-urlencoded format
(as sent by oidc-client-ts) and forwards them to Keycloak with
the client_secret appended.

Also provides the /auth/callback endpoint for SDUI-driven OAuth flow
where the backend handles the entire Keycloak redirect.
"""
import os
import logging
import json
import time
from typing import Optional

import aiohttp
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from jose import jwt as jose_jwt
import shutil

logger = logging.getLogger("AuthProxy")

# =============================================================================
# APIRouter for Auth & File endpoints (included in main app for OpenAPI docs)
# =============================================================================

auth_router = APIRouter()


@auth_router.post(
    "/auth/login",
    tags=["Auth"],
    summary="Username/password login",
    description=(
        "Authenticate using username and password. When MOCK_AUTH is enabled, "
        "accepts test credentials and returns a mock JWT. When disabled, "
        "validates against Keycloak using Resource Owner Password Credentials."
    ),
)
async def login(request: Request):
    """
    Username/password login endpoint.

    Returns access_token and user profile on success (200),
    or 401 on invalid credentials.
    """
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    if not username:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid credentials"},
        )

    if os.getenv("VITE_USE_MOCK_AUTH", "false").lower() == "true":
        # Mock auth: accept any credentials and return a dev token
        import base64 as _b64
        import time as _time
        header = _b64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        payload_data = {
            "sub": "dev-user-id",
            "preferred_username": username,
            "realm_access": {"roles": ["admin", "user"]},
            "resource_access": {"astral-frontend": {"roles": ["admin", "user"]}},
            "exp": int(_time.time()) + 7200,
            "iat": int(_time.time()),
        }
        payload = _b64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
        mock_jwt = f"{header}.{payload}.mock-signature"
        return JSONResponse(content={
            "user": {
                "id": "dev-user-id",
                "username": username,
                "roles": ["admin", "user"],
            },
            "access_token": mock_jwt,
            "token_type": "Bearer",
        })

    # Real auth: use Keycloak Resource Owner Password Credentials grant
    authority, client_id, client_secret = _get_keycloak_config()
    if not authority or not client_id or not client_secret:
        return JSONResponse(
            status_code=500,
            content={"detail": "Keycloak not configured"},
        )

    token_url = f"{authority}/protocol/openid-connect/token"
    form_data = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
        "scope": "openid profile email",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=form_data) as resp:
            body = await resp.json()
            if resp.status != 200:
                logger.warning(f"Login failed for user {username}: {resp.status}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid credentials"},
                )
            # Decode JWT for user info
            access_token = body.get("access_token", "")
            user_info = {"id": "", "username": username, "roles": []}
            try:
                parts = access_token.split(".")
                if len(parts) == 3:
                    import base64 as _b64
                    pad = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                    jwt_payload = json.loads(_b64.urlsafe_b64decode(pad).decode())
                    user_info = {
                        "id": jwt_payload.get("sub", ""),
                        "username": jwt_payload.get("preferred_username", username),
                        "roles": jwt_payload.get("realm_access", {}).get("roles", []),
                    }
            except Exception:
                pass
            return JSONResponse(content={
                "user": user_info,
                "access_token": access_token,
                "refresh_token": body.get("refresh_token"),
                "token_type": "Bearer",
            })


def _get_keycloak_config():
    """Read Keycloak settings from environment."""
    authority = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")
    client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "")
    client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
    return authority, client_id, client_secret


@auth_router.post(
    "/auth/token",
    tags=["Auth"],
    summary="Proxy token request to Keycloak",
    description=(
        "Proxies OIDC token exchange requests to Keycloak's token endpoint, "
        "injecting the client_secret server-side so it never reaches the browser. "
        "Supports authorization_code and refresh_token grant types."
    ),
)
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


# =============================================================================
# Shared token exchange + session authentication logic
# =============================================================================

async def exchange_and_authenticate(orch, websocket, code: str, code_verifier: str) -> tuple:
    """Exchange authorization code for tokens, authenticate the WS session, send dashboard.

    Returns (success: bool, error_message: str | None).
    On success, the websocket session is authenticated and the dashboard SDUI is sent.
    """
    import asyncio
    from shared.protocol import UIAction
    from orchestrator.login_ui import build_login_page

    authority, client_id, client_secret = _get_keycloak_config()
    backend_port = int(os.getenv("ORCHESTRATOR_PORT", 8001))
    backend_host = os.getenv("BACKEND_PUBLIC_URL", f"http://127.0.0.1:{backend_port}")
    redirect_uri = f"{backend_host}/auth/callback"
    token_url = f"{authority}/protocol/openid-connect/token"

    form_data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=form_data) as resp:
                body = await resp.json()
                if resp.status != 200:
                    err_msg = body.get("error_description", body.get("error", "Token exchange failed"))
                    logger.error(f"Token exchange failed: {resp.status} {body}")
                    await orch.send_ui_render(websocket, build_login_page(error=err_msg))
                    return False, err_msg

                access_token = body.get("access_token", "")
                refresh_token = body.get("refresh_token", "")
                expires_in = body.get("expires_in", 300)
    except Exception as e:
        logger.error(f"Token exchange request failed: {e}")
        await orch.send_ui_render(websocket, build_login_page(error="Failed to connect to identity provider."))
        return False, "Could not reach identity provider."

    # Validate the token and extract user data
    user_data = await orch.validate_token(access_token)
    if not user_data:
        await orch.send_ui_render(websocket, build_login_page(error="Token validation failed."))
        return False, "Token validation failed."

    # Authenticate the WebSocket session
    user_data["_raw_token"] = access_token
    user_data["_refresh_token"] = refresh_token
    user_data["_token_expires_at"] = time.time() + expires_in
    orch.ui_sessions[websocket] = user_data
    orch._save_user_profile(user_data)

    # Send store_token action to the client
    store_action = UIAction(action="store_token", payload={
        "token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
    })
    await orch._safe_send(websocket, store_action.to_json())

    # Send dashboard
    await orch.send_dashboard(websocket)

    # Schedule background token refresh
    asyncio.create_task(orch._schedule_token_refresh(websocket))

    logger.info(f"Auth successful for user '{user_data.get('preferred_username', 'unknown')}'")
    return True, None


# =============================================================================
# SDUI OAuth Callback (backend-handled redirect from Keycloak — HTTP fallback)
# =============================================================================

@auth_router.get(
    "/auth/callback",
    tags=["Auth"],
    summary="OAuth callback from Keycloak",
    description=(
        "Receives the authorization code from Keycloak after the user authenticates "
        "in the browser. Exchanges the code for tokens, associates the session with "
        "the originating WebSocket client, and pushes tokens + dashboard over WS. "
        "This endpoint serves as a fallback — the primary flow intercepts the redirect "
        "client-side and sends the code over WebSocket."
    ),
    response_class=HTMLResponse,
)
async def oauth_callback(request: Request, code: str = None, state: str = None, error: str = None, error_description: str = None):
    """Handle Keycloak OAuth redirect back to the backend."""
    from orchestrator.login_ui import build_login_page

    orch = getattr(request.app.state, "orchestrator", None)
    if not orch:
        return HTMLResponse("<html><body><h2>Server error: orchestrator not available.</h2></body></html>", status_code=500)

    # Validate state
    if not state or state not in orch.pending_auth_sessions:
        return HTMLResponse(
            "<html><body><h2>Login failed</h2><p>Invalid or expired session. Please try again in the app.</p></body></html>",
            status_code=400,
        )

    pending = orch.pending_auth_sessions[state]
    websocket = pending["websocket"]
    code_verifier = pending["code_verifier"]

    # Handle Keycloak error
    if error:
        del orch.pending_auth_sessions[state]
        err_msg = error_description or error
        logger.warning(f"OAuth callback error: {err_msg}")
        await orch.send_ui_render(websocket, build_login_page(error=f"Login failed: {err_msg}"))
        return HTMLResponse(
            f"<html><body><h2>Login failed</h2><p>{err_msg}</p><p>You can close this tab and try again.</p></body></html>"
        )

    if not code:
        del orch.pending_auth_sessions[state]
        return HTMLResponse(
            "<html><body><h2>Login failed</h2><p>No authorization code received.</p></body></html>",
            status_code=400,
        )

    # Use shared exchange logic
    success, err_msg = await exchange_and_authenticate(orch, websocket, code, code_verifier)
    del orch.pending_auth_sessions[state]

    if not success:
        return HTMLResponse(
            f"<html><body><h2>Login failed</h2><p>{err_msg}</p><p>You can close this tab.</p></body></html>"
        )

    return HTMLResponse(
        "<html><body style='font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #0F1221; color: #fff;'>"
        "<div style='text-align: center;'>"
        "<h2>Login successful</h2>"
        "<p>You can close this tab and return to the app.</p>"
        "</div></body></html>"
    )


# =============================================================================
# Auth Dependencies (used by REST API and file endpoints)
# =============================================================================

security = HTTPBearer(auto_error=False)

async def get_current_user_payload(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    if request.method == "OPTIONS":
        return {}
        
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Check for token in query parameter (for SSE endpoints where EventSource can't set headers)
        token_param = request.query_params.get("token")
        if token_param:
            token = token_param
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if os.getenv("VITE_USE_MOCK_AUTH") == "true":
        # Accept any token for mock auth (for testing)
        # Check if it's the old dev-token or new JWT format
        if token == "dev-token":
            return {
                "sub": "dev-user-id",
                "preferred_username": "DevUser",
                "realm_access": {"roles": ["admin", "user"]}
            }
        else:
            # Try to decode as JWT for mock
            try:
                import base64
                import json
                # Extract payload from JWT
                parts = token.split('.')
                if len(parts) == 3:
                    # Decode payload
                    payload_b64 = parts[1]
                    # Add padding if needed
                    payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
                    payload_json = base64.b64decode(payload_b64).decode('utf-8')
                    payload = json.loads(payload_json)
                    # Check token expiry even in mock mode
                    exp = payload.get("exp")
                    if exp is not None and exp < time.time():
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token expired",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                    return payload
            except HTTPException:
                raise
            except:
                # If decoding fails, return default mock user
                pass
            # Default mock user
            return {
                "sub": "dev-user-id",
                "preferred_username": "DevUser",
                "realm_access": {"roles": ["admin", "user"]},
                "resource_access": {
                    "astral-frontend": {"roles": ["admin", "user"]}
                }
            }
    
    authority, client_id, _ = _get_keycloak_config()
    if not authority or not client_id:
        raise HTTPException(status_code=500, detail="Auth not configured")
        
    try:
        jwks_url = f"{authority}/protocol/openid-connect/certs"
        async with aiohttp.ClientSession() as session:
            async with session.get(jwks_url) as resp:
                jwks = await resp.json()
                
        payload = jose_jwt.decode(
            token, jwks, algorithms=["RS256"],
            options={"verify_aud": False, "verify_at_hash": False}
        )
        azp = payload.get("azp")
        if azp and azp != client_id:
             raise HTTPException(status_code=401, detail="Invalid client")
        return payload
    except Exception as e:
        logger.error(f"Token validation failed in auth wrapper: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user_id(payload: dict = Depends(get_current_user_payload)) -> Optional[str]:
    """Extract user_id from JWT token."""
    if not payload:
        return None
    return payload.get("sub")  # Keycloak sub claim


async def require_user_id(
    request: Request,
    payload: dict = Depends(get_current_user_payload),
) -> str:
    """Require a valid user_id or raise 401. Also persists user profile to DB."""
    user_id = payload.get("sub") if payload else None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    # Persist user profile on each authenticated request (upsert is cheap)
    try:
        orch = getattr(request.app.state, "orchestrator", None)
        if not orch:
            root_app = getattr(request.app, "_root_app", None) or request.app
            orch = getattr(root_app.state, "orchestrator", None)
        if orch:
            orch._save_user_profile(payload)
    except Exception:
        pass  # Never block a request for profile persistence
    return user_id


def _extract_roles(user_data: dict) -> list:
    logger.debug(f"Extracting roles from user_data: {json.dumps(user_data, indent=2)}")
    roles = user_data.get("realm_access", {}).get("roles", [])
    if "resource_access" in user_data:
        client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend")
        logger.debug(f"Client ID: {client_id}")
        if client_id in user_data["resource_access"]:
            client_roles = user_data["resource_access"][client_id].get("roles", [])
            roles.extend(client_roles)
            logger.debug(f"Client roles: {client_roles}")
        if "account" in user_data["resource_access"]:
            account_roles = user_data["resource_access"]["account"].get("roles", [])
            roles.extend(account_roles)
            logger.debug(f"Account roles: {account_roles}")
    logger.debug(f"Final extracted roles: {roles}")
    return roles

async def verify_user(user_data: dict = Depends(get_current_user_payload)):
    if not user_data:
        return {}
    roles = _extract_roles(user_data)
        
    if "user" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Not authorized (Requires 'user' or 'admin' role)")
    return user_data

async def verify_admin(user_data: dict = Depends(get_current_user_payload)):
    if not user_data:
        logger.warning("verify_admin: user_data is empty")
        return {}
    roles = _extract_roles(user_data)
    logger.debug(f"verify_admin: extracted roles = {roles}")
    if "admin" not in roles:
        logger.warning(f"verify_admin: admin role missing, roles = {roles}")
        raise HTTPException(status_code=403, detail="Not authorized (Requires 'admin' role)")
    logger.debug("verify_admin: admin role present")
    # Add is_admin flag for downstream use
    user_data["is_admin"] = True
    return user_data


# =============================================================================
# File Upload/Download Endpoints
# =============================================================================

@auth_router.post(
    "/api/upload",
    tags=["Files"],
    summary="Upload a file",
    description="Upload a file to the backend, associated with a session ID. Returns the file path.",
)
async def upload_file(file: UploadFile = File(...), session_id: str = Form("default"), user_id: str = Depends(require_user_id)):
    """
    Handle file uploads and save them to a temporary directory under the session id.
    Returns the absolute file path.
    """
    try:
        # Create tmp directory if it doesn't exist
        # We go up one level from orchestrator to backend root
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # User-specific upload directory
        upload_dir = os.path.join(backend_dir, "tmp", user_id, session_id)
        os.makedirs(upload_dir, exist_ok=True)

        # Remove UUID renaming and instead use original filename (sanitize to avoid path traversal)
        safe_filename = os.path.basename(file.filename)
        file_path = os.path.join(upload_dir, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"File uploaded by user {user_id}: {file.filename} -> {file_path}")
        return JSONResponse(content={
            "status": "success",
            "filename": file.filename,
            "file_path": file_path,
            "user_id": user_id
        })
    except Exception as e:
        logger.error(f"Upload failed for user {user_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@auth_router.get(
    "/api/download/{session_id}/{filename}",
    tags=["Files"],
    summary="Download a file",
    description="Download a previously uploaded or generated file by session ID and filename.",
)
async def download_file(session_id: str, filename: str, user_id: str = Depends(require_user_id)):
    """
    Serve files from the downloads directory for a specific session.
    """
    try:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # User-specific download directory
        download_dir = os.path.join(backend_dir, "tmp", user_id, session_id)
        file_path = os.path.join(download_dir, filename)

        if not os.path.exists(file_path):
            logger.error(f"File not found for user {user_id}: {file_path}")
            return JSONResponse(status_code=404, content={"error": "File not found"})

        # Security: check that the file is actually inside the download_dir
        if not os.path.abspath(file_path).startswith(os.path.abspath(download_dir)):
            logger.error(f"Security violation: path traversal attempt by user {user_id} for {filename}")
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"Download failed for user {user_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# =============================================================================
# A2A Agent Authentication
# =============================================================================

def validate_agent_api_key(api_key: str) -> bool:
    """
    Validate an API key for Agent-to-Agent (A2A) communication.
    
    Remote agents connecting to the orchestrator can authenticate
    using an API key configured in the AGENT_API_KEY environment variable.
    This is used for server-to-server communication between the
    orchestrator and agents running on remote servers.
    """
    configured_key = os.getenv("AGENT_API_KEY", "")
    if not configured_key:
        # No key configured — allow unauthenticated agent connections
        # (backwards-compatible with local dev)
        return True
    return api_key == configured_key
