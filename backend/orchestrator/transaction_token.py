"""Single-use transaction tokens.

A transaction token is a short-lived, single-use authorization that BINDS one
specific call: ``(agent, user, tool, hash(args))``. It is HMAC-signed with
``TXN_TOKEN_KEY`` (falling back to ``MEMORY_HMAC_KEY``) so it is unforgeable,
carries its own expiry, and a process-local :class:`ConsumedStore` makes it
one-shot — a replayed token is refused.

This backs the policy engine's ``require_token`` effect: a rule can require that
a sensitive call carry a valid token (minted by a confirm/admin path), turning
"deny unless confirmed" into "deny unless *this exact call* was authorized." It
closes the confused-deputy / replay gap — a token for ``transfer(amount=5)``
cannot be reused, nor retargeted to ``amount=500`` or to a different
tool/agent/user, because any of those changes the signed binding.

Posture: **fail-CLOSED**. The effect is strictly opt-in (an operator must write
a ``require_token`` rule AND the policy engine is OFF by default), so a missing
key / missing / tampered / mismatched / expired / replayed token all DENY — the
control can't be silently bypassed. A process restart clears the consumed set
(tokens are short-lived by design); a shared multi-process store is a documented
follow-on.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("orchestrator.transaction_token")

_DEFAULT_TTL_S = 300


def _key() -> Optional[bytes]:
    raw = os.getenv("TXN_TOKEN_KEY") or os.getenv("MEMORY_HMAC_KEY")
    return raw.encode("utf-8") if raw else None


def _now_ms(now_ms: Optional[int]) -> int:
    return now_ms if now_ms is not None else int(time.time() * 1000)


def args_hash(args: Optional[Dict[str, Any]]) -> str:
    """Stable hash of the *intent* args. System-injected keys (anything starting
    with ``_`` — e.g. the embedded ``_txn_token`` itself, or ``_credentials``)
    are excluded so the mint side (clean args) and the verify side (args still
    carrying the token) agree on the binding."""
    clean = {k: v for k, v in (args or {}).items() if not str(k).startswith("_")}
    blob = json.dumps(clean, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sign(body: str, key: bytes) -> str:
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def mint(agent: str, user: str, tool: str, args: Optional[Dict[str, Any]], *,
         ttl_s: int = _DEFAULT_TTL_S, now_ms: Optional[int] = None,
         nonce: Optional[str] = None) -> Optional[str]:
    """Mint a single-use token binding ``(agent, user, tool, hash(args))``.
    Returns ``None`` when no signing key is configured (the caller treats that as
    "cannot authorize")."""
    key = _key()
    if not key:
        return None
    now = _now_ms(now_ms)
    payload = {
        "a": str(agent), "u": str(user), "t": str(tool),
        "h": args_hash(args), "e": now + max(1, int(ttl_s)) * 1000,
        "n": nonce or secrets.token_hex(8),
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{body}.{_sign(body, key)}"


def _decode(token: Any, key: bytes) -> Optional[Dict[str, Any]]:
    if not isinstance(token, str) or "." not in token:
        return None
    body, _, sig = token.rpartition(".")
    if not body or not sig or not hmac.compare_digest(_sign(body, key), sig):
        return None
    try:
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def verify(token: Any, agent: str, user: str, tool: str,
           args: Optional[Dict[str, Any]], *, now_ms: Optional[int] = None
           ) -> Tuple[bool, Any]:
    """Check signature, expiry and binding. Returns ``(True, payload)`` or
    ``(False, reason)``. Does NOT consume — see :func:`verify_and_consume`."""
    key = _key()
    if not key:
        return False, "signing disabled"
    payload = _decode(token, key)
    if payload is None:
        return False, "invalid token"
    if int(payload.get("e", 0)) < _now_ms(now_ms):
        return False, "expired"
    if (payload.get("a") != str(agent) or payload.get("u") != str(user)
            or payload.get("t") != str(tool)):
        return False, "binding mismatch"
    if payload.get("h") != args_hash(args):
        return False, "args mismatch"
    return True, payload


class ConsumedStore:
    """Process-local single-use nonce store. :meth:`consume` returns ``True`` the
    first time a nonce is seen and ``False`` on replay; expired nonces are pruned
    lazily so the set stays bounded by the live TTL window."""

    def __init__(self) -> None:
        self._seen: Dict[str, int] = {}

    def consume(self, nonce: str, exp_ms: int, *, now_ms: Optional[int] = None) -> bool:
        now = _now_ms(now_ms)
        if self._seen:
            self._seen = {n: e for n, e in self._seen.items() if e > now}
        if nonce in self._seen:
            return False
        self._seen[nonce] = int(exp_ms)
        return True


def verify_and_consume(store: ConsumedStore, token: Any, agent: str, user: str,
                       tool: str, args: Optional[Dict[str, Any]], *,
                       now_ms: Optional[int] = None) -> Tuple[bool, str]:
    """Verify the token AND atomically consume its nonce (single-use). Returns
    ``(ok, reason)``. A replayed token verifies but fails to consume →
    ``(False, "already used")``."""
    ok, detail = verify(token, agent, user, tool, args, now_ms=now_ms)
    if not ok:
        return False, str(detail)
    if not store.consume(str(detail.get("n")), int(detail.get("e", 0)), now_ms=now_ms):
        return False, "already used"
    return True, "ok"


_PROCESS_STORE = ConsumedStore()


def default_store() -> ConsumedStore:
    """The process-wide consumed-nonce store used by the dispatch enforcement
    (so single-use holds across calls within a running orchestrator)."""
    return _PROCESS_STORE
