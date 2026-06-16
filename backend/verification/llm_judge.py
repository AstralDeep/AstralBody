"""Optional LLM-as-judge enrichment (T025 / FR-003 / D1).

A SECOND opinion only — never the basis for a pass. It runs only when a real LLM
is available (so it resolves to ``na`` in CI / scripted-LLM mode). The deterministic
counter-check remains the gate; a judge that disagrees forces ``uncertain``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from verification.checks.base import Check
from verification.evidence import CapturedEvidence
from verification.verdict import Outcome

logger = logging.getLogger("verification.llm_judge")

_PROMPT = (
    "You are an adversarial verifier. A deterministic check claims a property "
    "holds. Try to REFUTE it from the evidence. Reply with a JSON object "
    '{"verdict": "pass"|"fail", "why": "..."} — "pass" only if the evidence '
    "genuinely supports the claim; default to \"fail\" when in doubt."
)


def interpret_judge_response(text: Optional[str]) -> Optional[Outcome]:
    """Parse a judge model reply into an Outcome (pure / unit-testable).

    Returns ``Outcome.PASS``/``Outcome.FAIL``, or ``None`` (na) when the reply is
    missing or unparseable — never guesses a pass.
    """
    if not text:
        return None
    cleaned = text.strip().strip("`")
    try:
        obj = json.loads(cleaned)
        verdict = str(obj.get("verdict", "")).lower()
    except (json.JSONDecodeError, AttributeError, TypeError):
        low = cleaned.lower()
        if "pass" in low and "fail" not in low:
            return Outcome.PASS
        if "fail" in low:
            return Outcome.FAIL
        return None
    if verdict == "pass":
        return Outcome.PASS
    if verdict == "fail":
        return Outcome.FAIL
    return None


def make_llm_judge(call_llm: Optional[Callable[..., Any]] = None):
    """Build a judge coroutine. With no real ``call_llm``, the judge is ``na``.

    ``call_llm`` matches the orchestrator's ``_call_llm`` contract and returns
    ``(message, usage)`` where ``message.content`` is the model's reply.
    """

    async def _judge(check: Check, evidence: CapturedEvidence, inputs: Dict[str, Any]) -> Optional[Outcome]:
        if call_llm is None:
            return None  # na — no LLM available (CI / scripted mode)
        payload = {
            "check": check.check_id,
            "property": check.property,
            "component_types": sorted({c.get("type") for c in evidence.components if isinstance(c, dict)}),
            "audit_actions": sorted({r.get("action_type") for r in evidence.audit_rows}),
            "audit_chain_ok": evidence.audit_chain_ok,
        }
        messages = [
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ]
        try:
            message, _usage = await call_llm(None, messages, feature="verification_judge")
            return interpret_judge_response(getattr(message, "content", None))
        except Exception:
            logger.debug("llm judge call failed; returning na", exc_info=True)
            return None

    return _judge
