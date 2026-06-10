"""Feature 028 — shared JWKS cache (research D8).

Pre-028, ``Orchestrator.validate_token`` and ``orchestrator.auth.
get_current_user_payload`` fetched the Keycloak JWKS document on EVERY
validation, coupling every request's availability to the IdP and adding a
network round-trip per call (``shared.a2a_security`` already cached; this
gives the other two validators the same behavior).

TTL-based with a kid-miss refetch escape hatch: a key rotation invalidates
the cache early instead of failing tokens for the rest of the TTL window.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger("shared.jwks_cache")

_TTL_SECONDS = 600
_cache: Dict[str, Dict[str, Any]] = {}  # url -> {"jwks": dict, "fetched_at": float}


def _kids(jwks: Dict[str, Any]) -> set:
    return {k.get("kid") for k in (jwks or {}).get("keys", []) if isinstance(k, dict)}


def _token_kid(token: str) -> Optional[str]:
    try:
        import base64
        header = token.split(".")[0]
        header += "=" * (-len(header) % 4)
        return json.loads(base64.urlsafe_b64decode(header)).get("kid")
    except Exception:
        return None


async def _fetch(jwks_url: str) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.get(jwks_url) as resp:
            jwks = await resp.json()
    _cache[jwks_url] = {"jwks": jwks, "fetched_at": time.time()}
    return jwks


async def get_jwks(jwks_url: str, *, token: Optional[str] = None) -> Dict[str, Any]:
    """Return the JWKS for ``jwks_url``, cached for up to 10 minutes.

    When ``token`` is supplied and its ``kid`` is absent from the cached set
    (key rotation), the cache is refreshed immediately.
    """
    entry = _cache.get(jwks_url)
    if entry and (time.time() - entry["fetched_at"]) < _TTL_SECONDS:
        jwks = entry["jwks"]
        if token is not None:
            kid = _token_kid(token)
            if kid and kid not in _kids(jwks):
                logger.info("jwks_cache: kid %s not in cached set — refetching (rotation?)", kid)
                return await _fetch(jwks_url)
        return jwks
    return await _fetch(jwks_url)


def clear() -> None:
    """Test helper."""
    _cache.clear()
