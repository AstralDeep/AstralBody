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
        self.authority = os.getenv("KEYCLOAK_AUTHORITY", "")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID", "")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
        self.agent_service_client_id = os.getenv(
            "AGENT_SERVICE_CLIENT_ID", "astral-agent-service"
        )
        self.agent_service_client_secret = os.getenv(
            "AGENT_SERVICE_CLIENT_SECRET", ""
        )
        self.mock_auth = os.getenv("USE_MOCK_AUTH", "false").lower() == "true"

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

        # Keycloak's astral-agent-service client only registers the four
        # scope-level claims (tools:read, tools:write, tools:search,
        # tools:system). Per-tool `tool:<name>` scopes are not pre-registered
        # and Keycloak rejects them with 400 invalid_scope. Per-tool
        # authorization is already enforced by the orchestrator's
        # ``allowed_tools`` filter at dispatch time, and ``is_tool_in_scope``
        # treats the scope-level claim as sufficient when no per-tool claims
        # are present in the JWT — so we send only scope-level claims here.
        combined_scopes = " ".join(enabled_scopes or [])

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
            f"{len(allowed_tools)} allowed tool(s) (scope='{combined_scopes}')"
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


# ===========================================================================
# 048 — Recursive, provenance-bearing delegation chains (behind a flag)
# ===========================================================================
# Extends the single-hop exchange above with nested RFC 8693 `act` child
# delegation tokens for sub-agent fan-out (035) and auto-created-agent
# promotion (027/035). Four enforcement invariants hold at every hop:
# monotonic scope attenuation, no privilege escalation, actor-chain
# completeness (terminating at the human `sub`), and depth-bounding. A child
# never outlives or exceeds its parent. Every hop emits a provenance record
# for the hash-chained audit. Gated by FF_RECURSIVE_DELEGATION (default off,
# fail-closed): with the flag off, callers use the single-hop path unchanged.
# See specs/048-recursive-delegation-chains/. No new runtime dependency
# (Constitution V) -- nested `act` rides the existing JWT/DPoP construction.

# Configurable maximum chain depth (small by default). Depth 0 == the legacy
# single-hop token; each child mint increments by one. Depth N allows N hops.
DEFAULT_MAX_DELEGATION_DEPTH = 3

# JWT claim names carrying the depth counter and the recorded bound, so a
# verifier can reject an over-depth chain it receives (FR-005).
DELEGATION_DEPTH_CLAIM = "delegation_depth"
MAX_DEPTH_CLAIM = "max_delegation_depth"

# Clock-skew tolerance for cross-hop expiry comparison, consistent with the
# repo's existing token handling (spec 048 edge case: skew near expiry).
_DELEGATION_CLOCK_SKEW_SECONDS = 60

# Guard against a pathological/cyclic `act` nesting while walking a chain.
_ACTOR_CHAIN_WALK_CAP = 64


class RecursiveDelegationError(Exception):
    """Base error for the recursive-delegation extension (spec 048)."""


class DelegationDepthExceeded(RecursiveDelegationError):
    """Raised when minting a child would exceed the maximum chain depth."""


def recursive_delegation_enabled() -> bool:
    """Return whether recursive delegation is enabled (FF_RECURSIVE_DELEGATION).

    Fail-closed: any error reading the flag yields False, so the caller falls
    back to the single-hop path (FR-009).
    """
    try:
        from shared.feature_flags import flags
        return bool(flags.is_enabled("recursive_delegation"))
    except Exception:  # pragma: no cover - defensive, fail closed
        return False


def attenuate_scopes(parent_scopes, requested_scopes) -> List[str]:
    """Intersect requested scopes with the parent's -- equal-or-narrower only.

    The child receives exactly the scopes it both requested AND the parent
    already holds; anything the parent lacks is dropped, never widened. This is
    the monotonic-attenuation / no-escalation invariant at the scope level
    (FR-002, FR-004). Returns a sorted list for deterministic tokens.
    """
    parent_set = set(parent_scopes or [])
    requested_set = set(requested_scopes or [])
    return sorted(parent_set & requested_set)


def _token_scopes(token: dict) -> List[str]:
    """Scope list from a token payload's space-delimited `scope` claim."""
    return (token.get("scope", "") or "").split()


def _token_depth(token: dict) -> int:
    """Delegation depth of a token (absent claim == 0, the single-hop root)."""
    try:
        return int(token.get(DELEGATION_DEPTH_CLAIM, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _walk_actor_chain(token: dict):
    """Walk the nested `act` chain outermost -> innermost.

    Returns ``(actors, complete)`` where ``actors`` lists the ``act.sub`` values
    current-first and ``complete`` is False if a link is severed (an ``act``
    present but not a well-formed ``{"sub": ...}`` node) or the cycle guard
    trips. A clean chain terminates at a node with no nested ``act`` (whose
    parent is the human ``sub`` on the top-level token).
    """
    actors: List[str] = []
    node = token.get("act")
    steps = 0
    while isinstance(node, dict) and "sub" in node:
        actors.append(node["sub"])
        steps += 1
        if steps > _ACTOR_CHAIN_WALK_CAP:
            return actors, False
        if "act" in node:
            nxt = node["act"]
            if not isinstance(nxt, dict) or "sub" not in nxt:
                return actors, False  # severed / malformed prior-actor link
            node = nxt
        else:
            return actors, True  # clean termination at the root agent
    return actors, bool(actors)


def actor_chain(token: dict) -> List[str]:
    """Return the actor chain, current delegate first, root agent last (FR-003).

    Every ``act.sub`` from the immediate actor up to the agent the human
    directly authorized. The human principal itself is the top-level ``sub`` and
    terminates the chain.
    """
    return _walk_actor_chain(token)[0]


def mint_child_delegation(parent: dict, child_agent_id: str,
                          requested_scopes, now: Optional[int] = None) -> dict:
    """Mint a further-attenuated child delegation payload (FR-002/003/005/010).

    The child: carries ``attenuate_scopes(parent, requested)`` (a subset of the
    parent's scopes); nests the parent's ``act`` chain under its own actor claim
    so the path back to the human ``sub`` is complete; inherits the human
    ``sub``, ``aud``, ``iss`` and DPoP ``cnf`` binding (audience never widened);
    caps ``exp`` at the parent's (a child never outlives its parent); and sets
    depth = parent depth + 1, refusing beyond the maximum with
    ``DelegationDepthExceeded`` (fail-closed).

    Returns the decoded child payload dict -- the mechanism the enforcement path
    and audit consume. Compact encoding/signing rides the existing construction
    at the transport call site during integration.
    """
    now = int(now if now is not None else time.time())

    child_depth = _token_depth(parent) + 1
    max_depth = min(
        int(parent.get(MAX_DEPTH_CLAIM, DEFAULT_MAX_DELEGATION_DEPTH)),
        DEFAULT_MAX_DELEGATION_DEPTH,
    )
    if child_depth > max_depth:
        raise DelegationDepthExceeded(
            f"minting at depth {child_depth} exceeds maximum {max_depth}"
        )

    child_scopes = attenuate_scopes(_token_scopes(parent), requested_scopes)

    # Nested actor claim: this child is the current actor; the parent's entire
    # actor chain nests beneath it (never re-broadened).
    child_act = {"sub": f"agent:{child_agent_id}"}
    parent_act = parent.get("act")
    if isinstance(parent_act, dict):
        child_act["act"] = parent_act

    parent_exp = int(parent.get("exp", now))
    child: Dict = {
        "sub": parent.get("sub"),                 # human principal, inherited
        "act": child_act,
        "scope": " ".join(child_scopes),
        "iss": parent.get("iss", "mock-astral-delegation"),
        "aud": parent.get("aud"),                 # audience never widened
        "iat": now,
        "exp": parent_exp,                        # capped at parent (never later)
        "delegation": True,
        DELEGATION_DEPTH_CLAIM: child_depth,
        MAX_DEPTH_CLAIM: max_depth,
    }
    if "cnf" in parent:
        child["cnf"] = parent["cnf"]              # RFC 9449 DPoP binding carried
    return child


def verify_delegation_chain(token: dict, now: Optional[int] = None,
                            expected_human_sub: Optional[str] = None):
    """Verify a received (possibly chained) delegation token, fail-closed.

    Checks, in order: depth bound (reject over-depth, FR-005); actor-chain
    completeness terminating at the human ``sub`` (FR-003); chain-of-custody
    expiry within skew (a child cannot outlive its parent, FR-010); and, when
    given, the expected human principal. Returns ``(ok, reason)`` -- ``reason``
    is empty on success and human-readable on failure.
    """
    now = int(now if now is not None else time.time())

    # 1) Depth bound first, so an over-depth forge reports a "depth" reason.
    depth = _token_depth(token)
    try:
        recorded_max = int(token.get(MAX_DEPTH_CLAIM, DEFAULT_MAX_DELEGATION_DEPTH))
    except (TypeError, ValueError):
        recorded_max = DEFAULT_MAX_DELEGATION_DEPTH
    max_depth = min(recorded_max, DEFAULT_MAX_DELEGATION_DEPTH)
    if depth < 0:
        return False, "negative delegation depth"
    if depth > max_depth:
        return False, f"delegation depth {depth} exceeds maximum {max_depth}"

    # 2) Actor-chain completeness + termination at a human principal.
    human_sub = token.get("sub")
    if not human_sub or (isinstance(human_sub, str) and human_sub.startswith("agent:")):
        return False, "chain does not terminate at a human principal"
    actors, complete = _walk_actor_chain(token)
    if not complete:
        return False, "actor chain is broken or incomplete"
    if len(actors) != depth + 1:
        return False, (
            f"actor-chain length {len(actors)} inconsistent with depth {depth}"
        )
    if expected_human_sub is not None and human_sub != expected_human_sub:
        return False, "human principal does not match expected authorizer"

    # 3) Chain-of-custody expiry (child exp was capped at mint; an unexpired
    #    child therefore implies an unexpired parent within skew).
    exp = token.get("exp")
    if exp is not None:
        try:
            if now > int(exp) + _DELEGATION_CLOCK_SKEW_SECONDS:
                return False, "delegation token expired"
        except (TypeError, ValueError):
            return False, "malformed expiry"

    return True, ""


def authorize_chained_tool_call(token: dict, tool_name: str,
                                required_scope: str = "",
                                now: Optional[int] = None):
    """Per-tool-call authorization over the persistent transport (FR-006/007).

    Re-derives authority from the presented (possibly chained) token on every
    call -- no new user-token round trip -- by (1) verifying the whole chain and
    (2) checking the tool against the token's attenuated scopes. Denials are
    per-call and fail-closed; the caller keeps the session/socket open. Returns
    ``(ok, reason)``.
    """
    ok, reason = verify_delegation_chain(token, now=now)
    if not ok:
        return False, reason
    scopes = _token_scopes(token)
    if not DelegationService.is_tool_in_scope(tool_name, scopes, required_scope):
        acting = actor_chain(token)[:1]
        return False, f"tool '{tool_name}' outside delegated scope for {acting}"
    return True, ""


def delegation_chain_audit_record(parent: dict, child: dict,
                                  operation: str = "", tool: str = "",
                                  now: Optional[int] = None) -> dict:
    """Provenance/completion record for one delegation hop (FR-008, SC-007).

    Maps field-by-field onto the HIPAA audit-trail checklist (spec 2.5) so the
    authority path -- human -> parent actor -> acting agent -> tool effect -- is
    reconstructable and tamper-evident once appended to the hash-chained audit
    (``audit/pii.py::chain_hmac`` at the call site). Pure and DB-free by design:
    it builds the record; the caller appends it to the chain.
    """
    now = int(now if now is not None else time.time())
    child_act = child.get("act") or {}
    parent_act = parent.get("act") or {}
    return {
        "event": "delegation_chain_hop",
        "acting_agent": child_act.get("sub"),                     # who acted
        "parent_actor": parent_act.get("sub"),                    # who delegated
        "human_authorizer": child.get("sub") or parent.get("sub"),  # root principal
        "operation": operation or tool,                           # what was done
        "tool": tool or operation,
        "scope": child.get("scope", ""),                          # scope/policy context
        "delegation_depth": _token_depth(child),
        "actor_chain": actor_chain(child),
        "timestamp": now,                                         # tamper-evident once chained
    }
