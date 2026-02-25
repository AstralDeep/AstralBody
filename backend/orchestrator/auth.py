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
import json
from typing import Optional

import aiohttp
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import shutil
import uuid

logger = logging.getLogger("AuthProxy")

app = FastAPI(title="AstralBody Auth Proxy")

# CORS — allow the frontend origin to make token exchange requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
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

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt as jose_jwt

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
                    return payload
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


async def require_user_id(user_id: str = Depends(get_current_user_id)) -> str:
    """Require a valid user_id or raise 401."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
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

@app.post("/api/upload")
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

@app.get("/api/download/{session_id}/{filename}")
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

