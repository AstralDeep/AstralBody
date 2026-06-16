"""Verdicts + deterministic<->LLM-judge reconciliation (T005).

The outcome of a check is decided by a DETERMINISTIC assertion. An optional
LLM-as-judge may add a second opinion, but it can never be the sole basis for a
pass, and any disagreement resolves to ``uncertain`` (FR-003 / FR-004 / D1/D13).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


# Judge results may also be "na" (no LLM available, e.g. in CI).
JUDGE_NA = "na"


@dataclass
class Verdict:
    """A machine-readable result for a check / scenario / property / run."""

    verdict_id: str
    scope: str  # check | scenario | property | run
    outcome: Outcome
    run_mode: str  # real_keycloak | mock_inprocess
    confidence: str = "high"  # high | medium | low
    evidence_ref: Optional[str] = None
    refs: Dict[str, Any] = field(default_factory=dict)
    adversarial: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "scope": self.scope,
            "outcome": self.outcome.value if isinstance(self.outcome, Outcome) else self.outcome,
            "confidence": self.confidence,
            "evidence_ref": self.evidence_ref,
            "refs": self.refs,
            "run_mode": self.run_mode,
            "adversarial": self.adversarial,
            "reason": self.reason,
        }


def reconcile(
    deterministic: Outcome,
    counter_refuted: bool,
    llm_judge: Optional[Outcome] = None,
) -> tuple[Outcome, str, Dict[str, Any]]:
    """Reconcile the deterministic result, its adversarial counter-check, and an
    optional LLM judge into a final outcome (FR-003 / D13).

    Rules:
      1. A ``pass`` requires deterministic == PASS AND the counter-check did NOT
         refute AND the LLM judge is PASS or NA.
      2. Any disagreement (counter refutes a pass, or judge disagrees) -> UNCERTAIN.
      3. A deterministic FAIL is a FAIL regardless of the judge.

    Returns ``(outcome, confidence, adversarial_detail)``.
    """
    judge_val = (
        llm_judge.value if isinstance(llm_judge, Outcome) else (llm_judge or JUDGE_NA)
    )
    detail: Dict[str, Any] = {
        "deterministic": deterministic.value,
        "counter_refuted": counter_refuted,
        "llm_judge": judge_val,
    }

    if deterministic == Outcome.FAIL:
        detail["reconciled"] = Outcome.FAIL.value
        return Outcome.FAIL, "high", detail

    if deterministic == Outcome.UNCERTAIN:
        detail["reconciled"] = Outcome.UNCERTAIN.value
        return Outcome.UNCERTAIN, "low", detail

    # deterministic == PASS
    if counter_refuted:
        detail["reconciled"] = Outcome.UNCERTAIN.value
        return Outcome.UNCERTAIN, "low", detail

    if judge_val not in (Outcome.PASS.value, JUDGE_NA):
        # judge disagrees with a deterministic pass
        detail["reconciled"] = Outcome.UNCERTAIN.value
        return Outcome.UNCERTAIN, "medium", detail

    # corroborated pass; confidence high if a real judge agreed, else medium-high
    confidence = "high" if judge_val == Outcome.PASS.value else "high"
    detail["reconciled"] = Outcome.PASS.value
    return Outcome.PASS, confidence, detail
