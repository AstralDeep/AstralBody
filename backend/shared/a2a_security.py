"""
A2A Security — Authentication and authorization for incoming A2A JSON-RPC requests.

Extracts Bearer tokens from Authorization headers, validates them via
Keycloak JWKS (production) or mock decode (development), and enforces
RFC 8693 delegation scopes on tool execution.
"""
import os
import base64
import json
import logging
from typing import Optional, Dict, List, Any

import aiohttp
from jose import jwt as jose_jwt

logger = logging.getLogger("A2ASecurity")


class A2ASecurityValidator:
    """Validates Bearer tokens on incoming A2A requests.

    Reuses the same validation logic as orchestrator/auth.py but
    decoupled from FastAPI Depends() so it can be called from the
    AgentExecutor context.
    """

    def __init__(self):
        self.mock_auth = os.getenv("VITE_USE_MOCK_AUTH", "false").lower() == "true"
        self.authority = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")
        self.client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "")
        self._jwks_cache: Optional[dict] = None

    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a Bearer token and return the decoded payload.

        Returns None if the token is invalid or missing.
        """
        if not token:
            return None

        if self.mock_auth:
            return self._validate_mock_token(token)

        return await self._validate_keycloak_token(token)

    def _validate_mock_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode a mock JWT without cryptographic verification."""
        if token == "dev-token":
            return {
                "sub": "test_user",
                "preferred_username": "test_user",
                "email": "test_user@local",
                "realm_access": {"roles": ["admin", "user"]},
                "resource_access": {"astral-frontend": {"roles": ["admin", "user"]}},
            }
        try:
            parts = token.split(".")
            if len(parts) == 3:
                payload_b64 = parts[1]
                payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                payload_json = base64.b64decode(payload_b64).decode("utf-8")
                return json.loads(payload_json)
        except Exception as e:
            logger.debug(f"A2A mock JWT decode failed, falling back to default test_user: {e}")
        return {
            "sub": "test_user",
            "preferred_username": "test_user",
            "email": "test_user@local",
            "realm_access": {"roles": ["admin", "user"]},
            "resource_access": {"astral-frontend": {"roles": ["admin", "user"]}},
        }

    async def _validate_keycloak_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a token against Keycloak JWKS."""
        if not self.authority or not self.client_id:
            logger.error("Keycloak not configured for A2A token validation")
            return None

        try:
            jwks = await self._get_jwks()
            payload = jose_jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_at_hash": False},
            )
            azp = payload.get("azp")
            if azp and azp != self.client_id:
                # Also allow the agent service client
                agent_client = os.getenv("AGENT_SERVICE_CLIENT_ID", "astral-agent-service")
                if azp != agent_client:
                    logger.warning(f"A2A token rejected: invalid azp={azp}")
                    return None
            return payload
        except Exception as e:
            logger.error(f"A2A token validation failed: {e}")
            return None

    async def _get_jwks(self) -> dict:
        """Fetch and cache Keycloak JWKS."""
        if self._jwks_cache:
            return self._jwks_cache

        jwks_url = f"{self.authority}/protocol/openid-connect/certs"
        async with aiohttp.ClientSession() as session:
            async with session.get(jwks_url) as resp:
                self._jwks_cache = await resp.json()
        return self._jwks_cache

    def extract_user_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract user_id from a validated token payload."""
        return payload.get("sub")

    def extract_scopes(self, payload: Dict[str, Any]) -> List[str]:
        """Extract scope list from token payload."""
        scope_str = payload.get("scope", "")
        return scope_str.split() if scope_str else []

    def is_delegation_token(self, payload: Dict[str, Any]) -> bool:
        """Check if the token is an RFC 8693 delegation token (has 'act' claim)."""
        return "act" in payload

    def get_actor(self, payload: Dict[str, Any]) -> Optional[str]:
        """Get the actor identity from a delegation token's 'act' claim."""
        act = payload.get("act", {})
        return act.get("sub") if act else None
