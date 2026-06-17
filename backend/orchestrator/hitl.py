"""Runtime human-in-the-loop for high-risk actions — 033 Wave-4 (C-S11).

A pending tool call is classified by **typed risk codes** — egress (data leaves
this system), cross_principal (the call acts on a different account than the
actor), irreversible (the action can't be undone), and untrusted_tainted (the
call is built from untrusted data). Any risk means the user is shown a
provenance-bearing **confirmation card** before the call runs; the strongest
classes (irreversible / cross_principal) and any *compounded* risk (≥2 codes at
once) mark the call **high-risk**.

When a high-risk action keeps being attempted — the user is repeatedly asked, or
the same risky call is retried past a threshold — that is an **escalation
signal**: hand off warm to a human/operator instead of looping on confirmations.

Pure + deterministic; stdlib only. **No new dependency.** Flag
``FF_HITL_HIGHRISK`` (default OFF) gates the dispatch enforcement; the
classification helpers themselves are side-effect free and always safe to call.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Typed risk codes ─────────────────────────────────────────────────────────
EGRESS, CROSS_PRINCIPAL, IRREVERSIBLE, UNTRUSTED_TAINTED = (
    "egress",
    "cross_principal",
    "irreversible",
    "untrusted_tainted",
)

#: Tools whose name alone marks the call as egress (data leaves the system).
_EGRESS_TOOLS = {
    "send_email",
    "send_message",
    "fetch_page",
    "http_get",
    "http_post",
    "webhook",
}
#: Name prefixes that also indicate egress.
_EGRESS_PREFIXES = ("http_", "send_", "post_", "fetch_", "upload_")
#: Name prefixes that indicate an irreversible (non-undoable) action.
_IRREVERSIBLE_PREFIXES = (
    "delete_",
    "drop_",
    "wipe_",
    "purge_",
    "transfer_",
    "pay_",
    "deploy_",
)

#: Human phrase shown on the confirmation card for each risk code.
_RISK_PHRASES = {
    EGRESS: "send data off this system",
    IRREVERSIBLE: "make an irreversible change",
    CROSS_PRINCIPAL: "act on another account",
    UNTRUSTED_TAINTED: "use untrusted data",
}


def hitl_enabled() -> bool:
    """FF_HITL_HIGHRISK feature flag (default OFF; feature 033 C-S11)."""
    return os.getenv("FF_HITL_HIGHRISK", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _is_egress(tool_name: str) -> bool:
    """Whether ``tool_name`` sends data off the system (exact name or prefix)."""
    name = tool_name or ""
    return name in _EGRESS_TOOLS or name.startswith(_EGRESS_PREFIXES)


def _is_irreversible(tool_name: str) -> bool:
    """Whether ``tool_name`` performs a non-undoable action (prefix match)."""
    return (tool_name or "").startswith(_IRREVERSIBLE_PREFIXES)


def assess_risk(
    tool_name: str,
    args: Optional[dict] = None,
    *,
    actor_principal: Optional[str] = None,
    target_principal: Optional[str] = None,
    trust: str = "trusted",
) -> List[str]:
    """Classify a pending tool call into the sorted list of risk codes that apply.

    Deterministic; an empty list means the call carries no recognized risk.

    - :data:`EGRESS` — the tool sends data off this system (name or prefix).
    - :data:`IRREVERSIBLE` — the tool performs a non-undoable action (prefix).
    - :data:`CROSS_PRINCIPAL` — ``actor_principal`` and ``target_principal`` are
      both set and differ (the call acts on someone else's account).
    - :data:`UNTRUSTED_TAINTED` — ``trust`` is ``"untrusted"`` (the call is built
      from untrusted data).

    ``args`` is accepted for call-site symmetry / future use and does not affect
    the classification today.
    """
    risks: List[str] = []
    if _is_egress(tool_name):
        risks.append(EGRESS)
    if _is_irreversible(tool_name):
        risks.append(IRREVERSIBLE)
    if actor_principal and target_principal and actor_principal != target_principal:
        risks.append(CROSS_PRINCIPAL)
    if trust == "untrusted":
        risks.append(UNTRUSTED_TAINTED)
    return sorted(risks)


def requires_confirmation(risks: List[str]) -> bool:
    """True when *any* risk applies — the user must confirm before the call runs."""
    return bool(risks)


def is_high_risk(risks: List[str]) -> bool:
    """True for the strongest risk classes or any compounded risk.

    The irreversible and cross_principal classes are high-risk on their own; so
    is any call carrying two or more risk codes at once (compounded risk).
    """
    return (
        IRREVERSIBLE in risks
        or CROSS_PRINCIPAL in risks
        or len(risks) >= 2
    )


@dataclass(frozen=True)
class ConfirmationRequest:
    """An immutable, provenance-bearing confirmation prompt for a pending call.

    - ``tool`` — the tool the call would invoke.
    - ``risks`` — the applicable risk codes (as a tuple, so the record is hashable).
    - ``summary`` — a human sentence naming what the call will do.
    - ``provenance`` — supporting context shown on the card (where the data /
      authority came from).
    """

    tool: str
    risks: Tuple[str, ...]
    summary: str
    provenance: Dict = field(default_factory=dict)


def _summarize(risks: List[str]) -> str:
    """A human sentence: 'This will <phrase>[ and <phrase>…] — confirm?'."""
    phrases = [_RISK_PHRASES[r] for r in risks if r in _RISK_PHRASES]
    if not phrases:
        return "This will run a sensitive action — confirm?"
    if len(phrases) == 1:
        joined = phrases[0]
    elif len(phrases) == 2:
        joined = " and ".join(phrases)
    else:
        joined = ", ".join(phrases[:-1]) + ", and " + phrases[-1]
    return f"This will {joined} — confirm?"


def confirmation_request(
    tool_name: str,
    risks: List[str],
    *,
    provenance: Optional[dict] = None,
) -> ConfirmationRequest:
    """Build the confirmation card for a pending high-/any-risk call.

    The ``summary`` names each applicable risk in a human sentence; ``provenance``
    (defaulting to ``{}``) carries the context shown to the user so they can see
    *why* the call is risky before approving it.
    """
    return ConfirmationRequest(
        tool=tool_name,
        risks=tuple(risks),
        summary=_summarize(risks),
        provenance=dict(provenance) if provenance else {},
    )


def escalation_needed(
    risks: List[str],
    *,
    denied_attempts: int = 0,
    denial_threshold: int = 2,
) -> bool:
    """Whether a high-risk action that keeps being attempted should escalate.

    True when the call is high-risk AND it has been denied / re-prompted at least
    ``denial_threshold`` times — i.e. the user keeps being asked or a risky action
    keeps being retried, which is the signal to hand off warm to a human rather
    than loop on confirmations.
    """
    return is_high_risk(risks) and denied_attempts >= denial_threshold
