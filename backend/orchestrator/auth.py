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

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt as jose_jwt

security = HTTPBearer(auto_error=False)

async def get_current_user_payload(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    if request.method == "OPTIONS":
        return {}
        
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    if os.getenv("VITE_USE_MOCK_AUTH") == "true" and token == "dev-token":
        return {
            "sub": "dev-user-id",
            "preferred_username": "DevUser",
            "realm_access": {"roles": ["admin", "user"]}
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
    logger.info(f"verify_admin: extracted roles = {roles}")
    if "admin" not in roles:
        logger.warning(f"verify_admin: admin role missing, roles = {roles}")
        raise HTTPException(status_code=403, detail="Not authorized (Requires 'admin' role)")
    logger.info("verify_admin: admin role present")
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

from typing import Optional, Dict
from pydantic import BaseModel

class StartSessionRequest(BaseModel):
    name: str
    persona: str
    toolsDescription: str
    apiKeys: str

class ChatSessionRequest(BaseModel):
    session_id: str
    message: str

class ApproveSessionRequest(BaseModel):
    session_id: str
    code: str
    files: Optional[Dict[str, str]] = None

class ResolveInstallRequest(BaseModel):
    session_id: str
    tool_call_id: str
    approved: bool
    packages: list[str]

class GenerateCodeRequest(BaseModel):
    session_id: str

class TestRequest(BaseModel):
    session_id: str
    code: Optional[str] = None
    files: Optional[Dict[str, str]] = None

@app.post("/api/agent-creator/start")
async def agent_creator_start(req: StartSessionRequest, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    user_id = admin.get('sub', 'legacy')
    result = await agent_generator.start_session(
        name=req.name,
        persona=req.persona,
        tools_desc=req.toolsDescription,
        api_keys=req.apiKeys,
        user_id=user_id
    )
    return JSONResponse(content=result)

@app.post("/api/agent-creator/chat")
async def agent_creator_chat(req: ChatSessionRequest, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    user_id = admin.get('sub', 'legacy')
    result = await agent_generator.chat(req.session_id, req.message, user_id=user_id)
    return JSONResponse(content=result)

@app.post("/api/agent-creator/generate")
async def agent_creator_generate(req: GenerateCodeRequest, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    user_id = admin.get('sub', 'legacy')
    result = await agent_generator.generate_code(req.session_id, user_id=user_id)
    return JSONResponse(content=result)

from fastapi.responses import StreamingResponse
import asyncio
from shared.progress import ProgressEvent

@app.post("/api/agent-creator/generate-with-progress")
async def agent_creator_generate_with_progress(req: GenerateCodeRequest, admin=Depends(verify_admin)):
    """Generate code with Server-Sent Events progress streaming."""
    from orchestrator.agent_generator import agent_generator
    user_id = admin.get('sub', 'legacy')
    
    async def progress_stream():
        """Generator that yields SSE progress events during code generation."""
        # Queue to collect progress events
        queue = asyncio.Queue()
        
        def progress_callback(event: ProgressEvent):
            # Convert ProgressEvent to dict and then to SSE format
            queue.put_nowait(f"data: {json.dumps(event.to_dict())}\n\n")
        
        async def generate_and_collect():
            try:
                # Call generate_code with progress callback
                result = await agent_generator.generate_code(
                    req.session_id,
                    progress_callback=progress_callback,
                    user_id=user_id
                )
                # Send final result
                await queue.put(json.dumps({
                    "type": "progress",
                    "phase": "generation",
                    "step": "generation_complete",
                    "percentage": 100,
                    "message": "Generation successful",
                    "data": {"result": result}
                }))
            except Exception as e:
                await queue.put(json.dumps({
                    "type": "progress",
                    "phase": "generation",
                    "step": "error",
                    "percentage": 100,
                    "message": f"Generation failed: {str(e)}",
                    "data": {"error": True, "error_details": str(e)}
                }))
        
        # Start generation in background
        asyncio.create_task(generate_and_collect())
        
        # Yield events from queue
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
                if isinstance(item, str):
                    if item.startswith('{'):
                        # JSON object, wrap as SSE
                        yield f"data: {item}\n\n"
                    else:
                        # Already SSE formatted
                        yield item
                else:
                    # Should be string
                    continue
            except asyncio.TimeoutError:
                # Timeout, send keep-alive
                yield ":keep-alive\n\n"
                continue
            except Exception as e:
                logger.error(f"Progress stream error: {e}")
                break
    
    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@app.post("/api/agent-creator/test")
async def agent_creator_test(req: TestRequest, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    user_id = admin.get('sub', 'legacy')
    
    # Determine what to send to save_and_test_agent
    # Priority: files dict if provided, otherwise code string
    if req.files:
        # Send files dict as JSON string
        files_data = json.dumps(req.files)
        return StreamingResponse(
            agent_generator.save_and_test_agent(req.session_id, files_data, user_id=user_id),
            media_type="text/event-stream"
        )
    elif req.code:
        # Backward compatibility: single code string
        return StreamingResponse(
            agent_generator.save_and_test_agent(req.session_id, req.code, user_id=user_id),
            media_type="text/event-stream"
        )
    else:
        return JSONResponse(
            status_code=400,
            content={"error": "Either 'code' or 'files' must be provided"}
        )

@app.get("/api/agent-creator/drafts")
async def get_draft_agents(admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    # Admin users see all drafts (including legacy)
    user_id = None if admin.get('is_admin') else admin.get('sub', 'legacy')
    return JSONResponse(content={"drafts": agent_generator.get_all_sessions(user_id=user_id)})

@app.get("/api/agent-creator/session/{session_id}")
async def get_draft_session(session_id: str, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    # Admin users can access any session (including legacy)
    user_id = None if admin.get('is_admin') else admin.get('sub', 'legacy')
    details = agent_generator.get_session_details(session_id, user_id=user_id)
    if not details:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return JSONResponse(content=details)

@app.delete("/api/agent-creator/session/{session_id}")
async def delete_draft_session(session_id: str, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    # Admin users can delete any session (including legacy)
    user_id = None if admin.get('is_admin') else admin.get('sub', 'legacy')
    success = agent_generator.delete_session(session_id, user_id=user_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return JSONResponse(content={"status": "success"})

@app.post("/api/agent-creator/resolve-install")
async def agent_creator_resolve_install(req: ResolveInstallRequest, admin=Depends(verify_admin)):
    from orchestrator.agent_generator import agent_generator
    user_id = admin.get('sub', 'legacy')
    result = await agent_generator.resolve_install(req.session_id, req.tool_call_id, req.approved, req.packages, user_id=user_id)
    return JSONResponse(content=result)
