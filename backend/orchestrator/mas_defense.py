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
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

#: Inter-agent payload markers that suggest a prompt-injection / exfil /
#: escalation relayed between agents (composes with C-S4 datamarking on prompt
#: ingress). Each entry is ``(label, pattern)``. The patterns are DIRECTIVE-
#: framed, not bare substrings: a page or digest that merely *mentions* "system
#: prompt", carries a "send to a friend" button, or documents an ``api_key``
#: field is benign and must NOT be flagged — otherwise, now that the scan
#: ENFORCES a quarantine on inter-agent hop results and sub-task digests (056
#: FR-007), legitimate web-research/summarization output silently vanishes.
#: An INJECTION says "ignore your instructions", "reveal your system prompt",
#: "send it to <url>" — an imperative aimed at the model — and those still fire.
_ATTACK_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("ignore previous",
     re.compile(r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|earlier|preceding|above)\b", re.I)),
    ("disregard instructions",
     re.compile(r"\bdisregard\s+(?:your|all|the|any|previous|prior|preceding)?\s*"
                r"(?:instructions?|prompts?|rules?|guidelines?|directions?)\b", re.I)),
    ("new instructions",
     re.compile(r"\bnew\s+instructions?\s*[:\-]", re.I)),
    ("you are now",
     re.compile(r"\byou\s+are\s+now\s+(?:a\s+|an\s+|in\s+)?"
                r"(?:dan\b|jailbroken|jailbreak|unrestricted|developer\s+mode|"
                r"admin(?:istrator)?\b|root\b|god\s+mode|do\s+anything\s+now)", re.I)),
    ("act as admin",
     re.compile(r"\bact\s+as\s+(?:an?\s+)?(?:admin(?:istrator)?|root|superuser|system|developer\s+mode)\b", re.I)),
    ("exfiltrate",
     re.compile(r"\bexfiltrat(?:e|es|ing|ion)\b", re.I)),
    ("system prompt",
     re.compile(r"\b(?:reveal|show|print|repeat|display|output|leak|share|expose|dump|"
                r"ignore|forget|reset|override|disclose)\b[^.\n]{0,40}?\bsystem\s+prompt\b", re.I)),
    ("reveal your",
     re.compile(r"\breveal\s+your\s+(?:system|instructions?|prompt|api|secret|password|"
                r"token|key|credentials?|config(?:uration)?)\b", re.I)),
    ("api_key",
     re.compile(r"\b(?:reveal|leak|send|exfiltrate|share|show|print|give|output|return|"
                r"dump|expose|steal|email|post|upload|your)\b[^.\n]{0,25}?\bapi[_\s-]?keys?\b", re.I)),
    ("database_url",
     re.compile(r"\b(?:reveal|leak|send|exfiltrate|share|show|print|give|output|return|"
                r"dump|expose|steal|email|post|upload)\b[^.\n]{0,25}?\bdatabase[_\s-]?url\b", re.I)),
    ("send to",
     re.compile(r"\bsend\b[^.\n]{0,40}?\bto\s+(?:https?://|[\w.+-]+@[\w.-]+|"
                r"the\s+(?:attacker|following\s+(?:url|address|email|endpoint)))", re.I)),
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
    / escalation DIRECTIVES. Returns the findings (empty == clean). Matches
    imperative injection framing, not topical mentions, so benign retrieved
    content is not quarantined (see ``_ATTACK_PATTERNS``)."""
    text = (payload if isinstance(payload, str)
            else json.dumps(payload, default=str))
    out: List[ScanFinding] = []
    for label, pattern in _ATTACK_PATTERNS:
        if pattern.search(text):
            out.append(ScanFinding(label))
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
