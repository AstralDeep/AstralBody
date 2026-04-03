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
import uuid
import logging
from typing import Optional, Dict, List

import aiohttp
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from shared.crypto import build_jwk, compute_jwk_thumbprint

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

        # RFC 9449 DPoP: Generate ephemeral EC P-256 key pair for
        # cryptographic binding of delegation tokens to this Orchestrator instance.
        self._dpop_private_key = ec.generate_private_key(
            ec.SECP256R1(), default_backend()
        )
        self._dpop_public_key = self._dpop_private_key.public_key()
        self._dpop_jwk = build_jwk(self._dpop_public_key)
        self._dpop_thumbprint = compute_jwk_thumbprint(self._dpop_jwk)

        if self.mock_auth:
            logger.info("DelegationService running in MOCK mode (DPoP enabled)")
        else:
            logger.info(
                f"DelegationService configured for Keycloak: {self.authority} (DPoP enabled)"
            )

    # -----------------------------------------------------------------
    # RFC 9449 DPoP — Demonstrating Proof of Possession
    # -----------------------------------------------------------------
    # JWK utilities (build_jwk, compute_jwk_thumbprint) are in shared.crypto

    def _create_dpop_proof(
        self, htm: str, htu: str, access_token: Optional[str] = None
    ) -> str:
        """Create a DPoP proof JWT per RFC 9449 §4.

        Args:
            htm: HTTP method (e.g. "POST", "GET").
            htu: HTTP target URI of the request.
            access_token: If provided, the access token hash (ath) is included
                          for token-bound proof verification.

        Returns:
            A compact-serialized DPoP proof JWT (ES256-signed).
        """
        header = {
            "typ": "dpop+jwt",
            "alg": "ES256",
            "jwk": self._dpop_jwk,
        }
        payload = {
            "jti": str(uuid.uuid4()),
            "htm": htm,
            "htu": htu,
            "iat": int(time.time()),
        }
        if access_token:
            # RFC 9449 §4.2: ath = base64url(SHA-256(access_token))
            ath_digest = hashlib.sha256(access_token.encode()).digest()
            payload["ath"] = base64.urlsafe_b64encode(ath_digest).rstrip(b"=").decode()

        # Sign with the ephemeral private key using ES256
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
        signing_input = f"{header_b64}.{payload_b64}".encode()

        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        from cryptography.hazmat.primitives.hashes import SHA256
        from cryptography.hazmat.primitives.asymmetric import ec as ec_module

        der_sig = self._dpop_private_key.sign(
            signing_input, ec_module.ECDSA(SHA256())
        )
        r, s = decode_dss_signature(der_sig)
        # Convert to fixed-width R||S format (32 bytes each for P-256)
        r_bytes = r.to_bytes(32, byteorder="big")
        s_bytes = s.to_bytes(32, byteorder="big")
        sig_b64 = (
            base64.urlsafe_b64encode(r_bytes + s_bytes).rstrip(b"=").decode()
        )

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def get_dpop_proof_for_request(
        self, method: str, url: str, access_token: str
    ) -> str:
        """Generate a DPoP proof for presenting a delegation token to an agent.

        This proof demonstrates that the Orchestrator possesses the private key
        bound to the delegation token's ``cnf.jkt`` claim.

        Args:
            method: HTTP method of the request (e.g. "GET", "POST").
            url: Target URL of the request.
            access_token: The delegation token being presented.

        Returns:
            A DPoP proof JWT string to include as a ``DPoP`` header.
        """
        return self._create_dpop_proof(method, url, access_token)

    async def exchange_token_for_agent(
        self,
        user_token: str,
        agent_id: str,
        allowed_tools: List[str],
        user_id: Optional[str] = None,
        enabled_scopes: Optional[List[str]] = None,
    ) -> Dict:
        """Exchange a user's access token for a scoped delegation token.

        Per RFC 8693 §2.1, performs a token exchange request with:
        - grant_type = urn:ietf:params:oauth:grant-type:token-exchange
        - subject_token = user's access token
        - audience = agent service client
        - scope = scope-level claims (tools:read, etc.) + tool-level claims

        Args:
            user_token: The user's access token (subject_token).
            agent_id: The agent identifier (becomes the actor).
            allowed_tools: List of tool names the user has allowed.
            user_id: Optional user ID for mock mode.
            enabled_scopes: List of enabled scope names (e.g. ["tools:read", "tools:search"]).

        Returns:
            Dict with 'access_token', 'token_type', 'expires_in',
            'scope', and 'issued_token_type' on success.
            Dict with 'error' and 'error_description' on failure.
        """
        if self.mock_auth:
            return self._create_mock_delegation_token(
                agent_id, allowed_tools, user_id, enabled_scopes
            )

        return await self._exchange_via_keycloak(
            user_token, agent_id, allowed_tools, enabled_scopes
        )

    async def _exchange_via_keycloak(
        self,
        user_token: str,
        agent_id: str,
        allowed_tools: List[str],
        enabled_scopes: Optional[List[str]] = None,
    ) -> Dict:
        """Perform the actual RFC 8693 token exchange with Keycloak."""
        if not self.authority or not self.client_id or not self.client_secret:
            return {
                "error": "server_error",
                "error_description": "Keycloak not configured for delegation",
            }

        token_url = f"{self.authority}/protocol/openid-connect/token"

        # Build scope string: scope-level claims + tool-level claims
        scope_parts = list(enabled_scopes or [])
        scope_parts.extend(f"tool:{t}" for t in allowed_tools)
        combined_scopes = " ".join(scope_parts)

        # RFC 8693 §2.1 — Token Exchange Request parameters
        form_data = {
            "grant_type": GRANT_TYPE_TOKEN_EXCHANGE,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "subject_token": user_token,
            "subject_token_type": TOKEN_TYPE_ACCESS,
            "requested_token_type": TOKEN_TYPE_ACCESS,
            "audience": self.agent_service_client_id,
            "scope": combined_scopes,
        }

        logger.info(
            f"Exchanging token for agent '{agent_id}' with "
            f"{len(allowed_tools)} tool scopes"
        )

        # RFC 9449: Include DPoP proof header to bind the resulting token
        dpop_proof = self._create_dpop_proof("POST", token_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    token_url, data=form_data, headers={"DPoP": dpop_proof}
                ) as resp:
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
                        "scope": body.get("scope", combined_scopes),
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
        enabled_scopes: Optional[List[str]] = None,
    ) -> Dict:
        """Create a mock delegation token for development/testing.

        Generates a JWT-like token with the RFC 8693 `act` claim
        identifying the agent as the actor.
        """
        now = int(time.time())
        # Build scope string: scope-level claims + tool-level claims
        scope_parts = list(enabled_scopes or [])
        scope_parts.extend(f"tool:{t}" for t in allowed_tools)
        combined_scopes = " ".join(scope_parts)

        # Build the JWT payload per RFC 8693 §4.1
        payload = {
            "sub": user_id or "dev-user-id",
            "preferred_username": "DevUser",
            "act": {"sub": f"agent:{agent_id}"},  # RFC 8693 §4.1 Actor Claim
            "scope": combined_scopes,
            "iss": "mock-astral-delegation",
            "aud": self.agent_service_client_id,
            "iat": now,
            "exp": now + 300,  # 5 minute expiry
            "azp": self.client_id or "astral-frontend",
            "realm_access": {"roles": ["user"]},
            "delegation": True,  # Custom flag for easy identification
            "cnf": {"jkt": self._dpop_thumbprint},  # RFC 9449 §6: DPoP binding
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
            f"with {len(allowed_tools)} tools (DPoP-bound)"
        )

        return {
            "access_token": mock_token,
            "token_type": "DPoP",
            "expires_in": 300,
            "scope": combined_scopes,
            "issued_token_type": TOKEN_TYPE_ACCESS,
            "agent_id": agent_id,
            "dpop_bound": True,
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
    def is_tool_in_scope(tool_name: str, scopes: List[str], required_scope: str = "") -> bool:
        """Check if a tool is allowed by the delegation token's scopes.

        Checks both scope-level claims (tools:read, tools:write, etc.)
        and tool-level claims (tool:<name>).

        Args:
            tool_name: The MCP tool name (e.g., 'modify_data').
            scopes: List of scope strings from the delegation token.
            required_scope: The scope required by this tool (e.g., 'tools:write').

        Returns:
            True if the tool is in scope.
        """
        # Check scope-level claim first (e.g., "tools:read" in scopes)
        if required_scope and required_scope in scopes:
            # Also verify the specific tool is listed (belt-and-suspenders)
            tool_scopes = [s for s in scopes if s.startswith("tool:")]
            if not tool_scopes:
                return True  # No tool-level constraints, scope-level is sufficient
            return f"tool:{tool_name}" in tool_scopes

        # Fallback: check tool-level claim directly
        tool_scopes = [s for s in scopes if s.startswith("tool:")]
        if not tool_scopes:
            return True
        return f"tool:{tool_name}" in tool_scopes
