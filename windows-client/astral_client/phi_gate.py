"""Client-side PHI pre-filter for the Windows coding agent.

A dependency-light port of the *pure-Python pre-filter* half of
``backend/personalization/phi_gate.py``. It runs on every file read and every
command's stdout/stderr **on the client, before the result is returned to the
orchestrator / model** — so PHI never leaves the user's machine. A hit ⇒ the
result is refused (fail-closed), never silently redacted-and-forwarded.

Why not bundle Presidio/spaCy here: they would bloat the PyInstaller exe and
pull a large model. The orchestrator's full Presidio gate
(``backend/personalization/phi_gate.py``) remains the authoritative PHI
boundary for anything that reaches the backend; this pre-filter is the
client's defense-in-depth so PHI is caught (and refused) locally first.

**Fail-closed:** if the pre-filter raises, treat the input as PHI and refuse.
"""
from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger("astral.phi_gate")

# Mirrors backend/personalization/phi_gate.py::_PREFILTER_PATTERNS exactly so
# the client and server agree on what "looks like PHI".
_PREFILTER_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                      # SSN
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # email
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # phone
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                      # ISO date (possible DOB)
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),                # US date (possible DOB)
    re.compile(r"\bMRN\b[:#\s-]*\d{3,}", re.IGNORECASE),       # MRN context
    re.compile(r"\bmedical record\b", re.IGNORECASE),          # MRN context
    re.compile(r"\b\d{7,}\b"),                                 # long digit run (account/MRN)
]


def looks_like_phi(text: str) -> bool:
    """True if ``text`` matches any PHI pre-filter pattern.

    Fail-closed: if ``text`` is not a string or the check raises, return True
    (refuse — never risk forwarding PHI).
    """
    if not isinstance(text, str) or not text:
        return False
    try:
        return any(p.search(text) for p in _PREFILTER_PATTERNS)
    except Exception:  # noqa: BLE001 — fail-closed
        logger.warning("PHI pre-filter raised; treating input as PHI (fail-closed)", exc_info=True)
        return True


def scan(text: str) -> bool:
    """Alias for :func:`looks_like_phi` — the audit-log-facing name."""
    return looks_like_phi(text)
