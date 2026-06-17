"""Multi-agent-system attack defenses — 033 Wave-2/4 (C-S14).

The Wave-2 capabilities introduce genuine multi-agent flows (C-N7 dual-ledger
control, C-N8 fan-out, C-N9 MoA/debate) where one agent's output becomes
another's input. Per FR-011 / FR-039 the defenses ship WITH them. Three pure
pieces, composing with the existing crypto (C-S9 signing, C-S8 tokens) and the
taint lattice (C-S2):

* **Inter-agent message provenance / integrity** — :func:`sign_message` /
  :func:`verify_message` HMAC-bind a hop ``(sender → recipient, hash(payload))``
  so a relayed message can't be forged or retargeted between agents.
* **Per-edge scoping** — :func:`edge_allowed` authorizes a specific
  sender→recipient edge against an allow-list, so the agent graph is a
  whitelist, not a clique (a compromised agent can't talk to arbitrary peers).
* **TAMAS-style red-team scan** — :func:`scan_message` flags an inter-agent
  payload carrying injection / exfil / scope-escalation markers before it is
  delivered downstream.

Pure, stdlib only (``hmac``/``hashlib``). **No new dependency.** Flag
``FF_MAS_DEFENSE`` (default OFF). Posture: signing/verification fail CLOSED when
a key is configured and the check fails; with no key, verification reports
"unsigned" and the caller decides (additive — single-agent flows are
unaffected).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

#: Inter-agent payload markers that suggest a prompt-injection / exfil / escalation
#: relayed between agents (composes with C-S4 datamarking on prompt ingress).
_ATTACK_MARKERS = (
    "ignore previous", "ignore all previous", "disregard your instructions",
    "you are now", "new instructions:", "system prompt", "exfiltrate",
    "send to", "reveal your", "api_key", "database_url", "act as admin",
)


def mas_defense_enabled() -> bool:
    """FF_MAS_DEFENSE feature flag (default OFF; feature 033 C-S14)."""
    return os.getenv("FF_MAS_DEFENSE", "false").strip().lower() in ("1", "true", "yes", "on")


def _key() -> Optional[bytes]:
    raw = os.getenv("MAS_MESSAGE_KEY") or os.getenv("MEMORY_HMAC_KEY")
    return raw.encode("utf-8") if raw else None


def _payload_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sign_message(sender: str, recipient: str, payload: Any) -> Optional[str]:
    """HMAC-sign an inter-agent hop, binding sender, recipient and the payload
    hash. Returns None when no key is configured (caller treats as unsigned)."""
    key = _key()
    if not key:
        return None
    body = f"{sender}\x1f{recipient}\x1f{_payload_hash(payload)}"
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_message(sender: str, recipient: str, payload: Any,
                   signature: Optional[str]) -> Tuple[bool, str]:
    """Verify an inter-agent message's provenance + integrity. Returns
    ``(ok, reason)``. Fails CLOSED when a key is set but the signature is
    missing/forged/retargeted; reports ``unsigned`` when no key is configured."""
    key = _key()
    if not key:
        return False, "unsigned"
    if not signature:
        return False, "missing signature"
    expected = sign_message(sender, recipient, payload)
    if expected is None or not hmac.compare_digest(expected, signature):
        return False, "bad signature"
    return True, "ok"


def edge_allowed(sender: str, recipient: str,
                 allowed_edges: Optional[Iterable[Tuple[str, str]]]) -> bool:
    """Per-edge scoping: is the sender→recipient edge on the allow-list? A None
    allow-list means "no graph configured" → allow (additive default); an empty
    list denies everything (locked down). A ``"*"`` recipient wildcard lets a
    sender talk to anyone."""
    if allowed_edges is None:
        return True
    edges = set((str(s), str(r)) for s, r in allowed_edges)
    return (sender, recipient) in edges or (sender, "*") in edges


@dataclass(frozen=True)
class ScanFinding:
    marker: str


def scan_message(payload: Any) -> List[ScanFinding]:
    """TAMAS-style red-team scan of an inter-agent payload for injection / exfil
    / escalation markers. Returns the findings (empty == clean)."""
    text = (payload if isinstance(payload, str)
            else json.dumps(payload, default=str)).lower()
    out: List[ScanFinding] = []
    for marker in _ATTACK_MARKERS:
        if marker in text:
            out.append(ScanFinding(marker))
    return out


def is_safe_message(sender: str, recipient: str, payload: Any, signature: Optional[str],
                    *, allowed_edges: Optional[Iterable[Tuple[str, str]]] = None,
                    require_signature: bool = True) -> Tuple[bool, str]:
    """Combined gate for one inter-agent hop: edge authorized AND (optionally)
    signature valid AND no attack markers. Returns ``(ok, reason)`` — the first
    failure's reason."""
    if not edge_allowed(sender, recipient, allowed_edges):
        return False, f"edge {sender}->{recipient} not allowed"
    if require_signature:
        ok, reason = verify_message(sender, recipient, payload, signature)
        if not ok:
            return False, f"integrity: {reason}"
    findings = scan_message(payload)
    if findings:
        return False, f"attack markers: {', '.join(f.marker for f in findings[:3])}"
    return True, "ok"
