"""
Delegation Service — RFC 8693 Token Exchange for Agent Authorization.

Implements OAuth 2.0 Token Exchange (RFC 8693) to create delegation tokens
that allow agents to act on behalf of users with restricted scopes.

Key concepts from RFC 8693:
- subject_token: The user's access token (who the agent acts on behalf of)
- actor: The agent identity (who is doing the acting)
- act claim: JWT claim identifying the delegate (§4.1)
- Delegation semantics (§1.1): Agent has its own identity, acts for the user

Reference: https://datatracker.ietf.org/doc/html/rfc8693
"""
import os
import time
import json
import hmac
import hashlib
import base64
import logging
from typing import Optional, Dict, List

import aiohttp

logger = logging.getLogger("DelegationService")


# RFC 8693 constants
GRANT_TYPE_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"


class DelegationService:
    """Manages token exchange for agent delegation per RFC 8693.

    In production mode, exchanges user tokens via Keycloak's token endpoint.
    In mock auth mode, generates self-signed delegation tokens for development.
    """

    def __init__(self):
        self.authority = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")
        self.client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
        self.agent_service_client_id = os.getenv(
            "AGENT_SERVICE_CLIENT_ID", "astral-agent-service"
        )
        self.agent_service_client_secret = os.getenv(
            "AGENT_SERVICE_CLIENT_SECRET", ""
        )
        self.mock_auth = os.getenv("VITE_USE_MOCK_AUTH", "false").lower() == "true"

        if self.mock_auth:
            logger.info("DelegationService running in MOCK mode")
        else:
            logger.info(
                f"DelegationService configured for Keycloak: {self.authority}"
            )

    async def exchange_token_for_agent(
        self,
        user_token: str,
        agent_id: str,
        allowed_tools: List[str],
        user_id: Optional[str] = None,
    ) -> Dict:
        """Exchange a user's access token for a scoped delegation token.

        Per RFC 8693 §2.1, performs a token exchange request with:
        - grant_type = urn:ietf:params:oauth:grant-type:token-exchange
        - subject_token = user's access token
        - audience = agent service client
        - scope = tools the user has enabled for this agent

        Args:
            user_token: The user's access token (subject_token).
            agent_id: The agent identifier (becomes the actor).
            allowed_tools: List of tool names the user has allowed.
            user_id: Optional user ID for mock mode.

        Returns:
            Dict with 'access_token', 'token_type', 'expires_in',
            'scope', and 'issued_token_type' on success.
            Dict with 'error' and 'error_description' on failure.
        """
        if self.mock_auth:
            return self._create_mock_delegation_token(
                agent_id, allowed_tools, user_id
            )

        return await self._exchange_via_keycloak(
            user_token, agent_id, allowed_tools
        )

    async def _exchange_via_keycloak(
        self,
        user_token: str,
        agent_id: str,
        allowed_tools: List[str],
    ) -> Dict:
        """Perform the actual RFC 8693 token exchange with Keycloak."""
        if not self.authority or not self.client_id or not self.client_secret:
            return {
                "error": "server_error",
                "error_description": "Keycloak not configured for delegation",
            }

        token_url = f"{self.authority}/protocol/openid-connect/token"

        # Build tool scopes from allowed tools
        tool_scopes = " ".join(f"tool:{t}" for t in allowed_tools)

        # RFC 8693 §2.1 — Token Exchange Request parameters
        form_data = {
            "grant_type": GRANT_TYPE_TOKEN_EXCHANGE,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "subject_token": user_token,
            "subject_token_type": TOKEN_TYPE_ACCESS,
            "requested_token_type": TOKEN_TYPE_ACCESS,
            "audience": self.agent_service_client_id,
            "scope": tool_scopes,
        }

        logger.info(
            f"Exchanging token for agent '{agent_id}' with "
            f"{len(allowed_tools)} tool scopes"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=form_data) as resp:
                    body = await resp.json()
                    if resp.status != 200:
                        logger.error(
                            f"Token exchange failed: {resp.status} {body}"
                        )
                        return {
                            "error": body.get("error", "exchange_failed"),
                            "error_description": body.get(
                                "error_description",
                                f"Keycloak returned {resp.status}",
                            ),
                        }

                    logger.info(
                        f"Token exchange successful for agent '{agent_id}'"
                    )
                    return {
                        "access_token": body["access_token"],
                        "token_type": body.get("token_type", "Bearer"),
                        "expires_in": body.get("expires_in", 300),
                        "scope": body.get("scope", tool_scopes),
                        "issued_token_type": body.get(
                            "issued_token_type", TOKEN_TYPE_ACCESS
                        ),
                        "agent_id": agent_id,
                    }
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return {
                "error": "exchange_error",
                "error_description": str(e),
            }

    def _create_mock_delegation_token(
        self,
        agent_id: str,
        allowed_tools: List[str],
        user_id: Optional[str] = None,
    ) -> Dict:
        """Create a mock delegation token for development/testing.

        Generates a JWT-like token with the RFC 8693 `act` claim
        identifying the agent as the actor.
        """
        now = int(time.time())
        tool_scopes = " ".join(f"tool:{t}" for t in allowed_tools)

        # Build the JWT payload per RFC 8693 §4.1
        payload = {
            "sub": user_id or "dev-user-id",
            "preferred_username": "DevUser",
            "act": {"sub": f"agent:{agent_id}"},  # RFC 8693 §4.1 Actor Claim
            "scope": tool_scopes,
            "iss": "mock-astral-delegation",
            "aud": self.agent_service_client_id,
            "iat": now,
            "exp": now + 300,  # 5 minute expiry
            "azp": self.client_id or "astral-frontend",
            "realm_access": {"roles": ["user"]},
            "delegation": True,  # Custom flag for easy identification
        }

        # Create a simple mock JWT (not cryptographically secure — dev only)
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode())
            .rstrip(b"=")
            .decode()
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode())
            .rstrip(b"=")
            .decode()
        )
        signing_input = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            b"mock-delegation-secret", signing_input.encode(), hashlib.sha256
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
        mock_token = f"{signing_input}.{sig_b64}"

        logger.info(
            f"Mock delegation token created for agent '{agent_id}' "
            f"with {len(allowed_tools)} tools"
        )

        return {
            "access_token": mock_token,
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": tool_scopes,
            "issued_token_type": TOKEN_TYPE_ACCESS,
            "agent_id": agent_id,
        }

    @staticmethod
    def extract_delegation_info(token_payload: dict) -> Optional[Dict]:
        """Extract delegation information from a decoded JWT payload.

        Per RFC 8693 §4.1, the `act` claim identifies the actor.

        Args:
            token_payload: Decoded JWT payload dict.

        Returns:
            Dict with 'user_id', 'actor', and 'scopes' if this is a
            delegation token, or None if it's a regular user token.
        """
        act_claim = token_payload.get("act")
        if not act_claim:
            return None

        return {
            "user_id": token_payload.get("sub"),
            "actor": act_claim.get("sub"),
            "scopes": (token_payload.get("scope", "")).split(),
            "is_delegation": True,
        }

    @staticmethod
    def is_tool_in_scope(tool_name: str, scopes: List[str]) -> bool:
        """Check if a tool is allowed by the delegation token's scopes.

        Args:
            tool_name: The MCP tool name (e.g., 'modify_data').
            scopes: List of scope strings from the delegation token.

        Returns:
            True if the tool is in scope (or no tool-specific scopes exist).
        """
        tool_scopes = [s for s in scopes if s.startswith("tool:")]
        if not tool_scopes:
            # No tool-specific scopes = all tools allowed at token level
            return True
        return f"tool:{tool_name}" in tool_scopes
