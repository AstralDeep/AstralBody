"""Check framework: typed, pure, replayable assertions (T006).

A ``Check`` makes one structural/authority assertion (``run``) and an adversarial
counter-assertion that tries to falsify a pass (``counter``). Both are PURE over
``(evidence, inputs)`` so a check replays identically from a persisted run record
(FR-002 / FR-003).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from verification.evidence import CapturedEvidence
from verification.verdict import Outcome


@dataclass
class CheckResult:
    """The typed result of a single check (or counter-check) run."""

    check_id: str
    outcome: Outcome
    observed: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "outcome": self.outcome.value if isinstance(self.outcome, Outcome) else self.outcome,
            "observed": self.observed,
            "reason": self.reason,
        }


@dataclass
class Check:
    """A named, replayable assertion plus its adversarial counter-check.

    Attributes:
        check_id: Stable identifier (e.g. ``us1.component_from_file``).
        property: ``tangible_ui`` | ``delegated_authority`` | ``backend_only_ui``.
        run_fn: Pure ``(evidence, inputs) -> CheckResult`` asserting the property.
        counter_fn: Pure ``(evidence, inputs) -> CheckResult`` attempting to
            FALSIFY a positive ``run_fn`` result. ``outcome=PASS`` means "the
            counter found grounds to doubt" (i.e. it refuted). Optional.
    """

    check_id: str
    property: str
    run_fn: Callable[[CapturedEvidence, Dict[str, Any]], CheckResult]
    counter_fn: Optional[Callable[[CapturedEvidence, Dict[str, Any]], CheckResult]] = None
    is_deterministic: bool = True

    def run(self, evidence: CapturedEvidence, inputs: Dict[str, Any]) -> CheckResult:
        return self.run_fn(evidence, inputs)

    def counter(self, evidence: CapturedEvidence, inputs: Dict[str, Any]) -> CheckResult:
        if self.counter_fn is None:
            # No adversarial counter defined: treat as "did not refute".
            return CheckResult(self.check_id + ".counter", Outcome.FAIL, reason="no counter-check")
        return self.counter_fn(evidence, inputs)

    def counter_refutes(self, evidence: CapturedEvidence, inputs: Dict[str, Any]) -> bool:
        """True iff the counter-check found grounds to doubt a pass."""
        if self.counter_fn is None:
            return False
        return self.counter(evidence, inputs).outcome == Outcome.PASS


_REGISTRY: Dict[str, Check] = {}


def register(check: Check) -> Check:
    """Register a check by id (idempotent; last registration wins)."""
    _REGISTRY[check.check_id] = check
    return check


def get(check_id: str) -> Optional[Check]:
    return _REGISTRY.get(check_id)


def all_checks() -> List[Check]:
    return list(_REGISTRY.values())


def by_property(prop: str) -> List[Check]:
    return [c for c in _REGISTRY.values() if c.property == prop]


# ---------------------------------------------------------------------------
# Small assertion helpers shared by check modules (kept pure + deterministic).
# ---------------------------------------------------------------------------

def ok(check_id: str, reason: str = "", **observed: Any) -> CheckResult:
    return CheckResult(check_id, Outcome.PASS, observed=observed, reason=reason)


def no(check_id: str, reason: str = "", **observed: Any) -> CheckResult:
    return CheckResult(check_id, Outcome.FAIL, observed=observed, reason=reason)


def unsure(check_id: str, reason: str = "", **observed: Any) -> CheckResult:
    return CheckResult(check_id, Outcome.UNCERTAIN, observed=observed, reason=reason)
