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
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse
from jose import jwt as jose_jwt
import shutil

logger = logging.getLogger("AuthProxy")

if os.getenv("VITE_USE_MOCK_AUTH", "").lower() == "true":
    logger.info("Mock auth ENABLED — all tokens accepted as test_user with roles [admin, user]")
else:
    logger.info("Mock auth disabled — Keycloak JWKS validation active")

# =============================================================================
# APIRouter for Auth & File endpoints (included in main app for OpenAPI docs)
# =============================================================================

auth_router = APIRouter()


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
    if os.getenv("VITE_USE_MOCK_AUTH", "").lower() == "true":
        # Accept any token for mock auth (for testing)
        if token == "dev-token":
            mock_payload = {
                "sub": "test_user",
                "preferred_username": "test_user",
                "email": "test_user@local",
                "realm_access": {"roles": ["admin", "user"]},
                "resource_access": {
                    "astral-frontend": {"roles": ["admin", "user"]}
                }
            }
            try:
                request.state.audit_claims = mock_payload
            except Exception:
                pass
            return mock_payload
        try:
            import base64
            parts = token.split('.')
            if len(parts) == 3:
                payload_b64 = parts[1]
                payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
                payload_json = base64.b64decode(payload_b64).decode('utf-8')
                decoded = json.loads(payload_json)
                try:
                    request.state.audit_claims = decoded
                except Exception:
                    pass
                return decoded
        except Exception as e:
            logger.debug(f"Mock JWT decode failed, falling back to default test_user: {e}")
        fallback = {
            "sub": "test_user",
            "preferred_username": "test_user",
            "email": "test_user@local",
            "realm_access": {"roles": ["admin", "user"]},
            "resource_access": {
                "astral-frontend": {"roles": ["admin", "user"]}
            }
        }
        try:
            request.state.audit_claims = fallback
        except Exception:
            pass
        return fallback
    
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
        try:
            request.state.audit_claims = payload
        except Exception:
            pass
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

# NOTE: POST /api/upload moved to backend/orchestrator/attachments/router.py
# (feature 002-file-uploads) — supports the expanded type set, 30 MB cap,
# user-scoped storage, and content-type sniffing.

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
