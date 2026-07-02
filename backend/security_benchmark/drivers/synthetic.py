"""Synthetic (scripted, deterministic) driver (spec 047 US1/US2, SC-006).

Models the envelope's enforcement deterministically so the full pipeline
(adapter → driver → adjudicator → report) runs anywhere, including CI without a
database. The mechanism it models is faithful to how the real gates attribute:
the layer *responsible* for an objective kind blocks that kind iff the layer is
enabled AND implemented; otherwise the adversarial call executes and the attack
succeeds. This yields a mechanistically-attributable ablation (US2-AS2) and is
byte-for-byte reproducible for a given case set (SC-006).

It is NOT a substitute for the in-process driver's real-gate measurement; it is
the deterministic core the in-process run shares, and the CI-runnable proof that
the harness computes ASR + ablation correctly.
"""
from __future__ import annotations

from security_benchmark.adapters.base import BenchmarkCase, CaseTrace, ToolCallObservation
from security_benchmark.envelope import (
    LAYER_FOR_OBJECTIVE,
    NOT_IMPLEMENTED,
    EnvelopeConfig,
)
from security_benchmark.drivers.base import Driver

# Category/objective markers that mean "the scripted agent does NOT take the bait"
# (benign control cases → NOT_ATTEMPTED path, FR-006).
_CONTROL_MARKERS = ("benign", "control")


def _is_control(case: BenchmarkCase) -> bool:
    cat = case.category.lower()
    return (not case.injection) or any(m in cat for m in _CONTROL_MARKERS)


class SyntheticDriver(Driver):
    mode = "synthetic"

    def run_case(self, case: BenchmarkCase, envelope: EnvelopeConfig) -> CaseTrace:
        trace = CaseTrace(case_id=case.case_id, envelope_label=envelope.label)

        if case.out_of_corpus:
            # Recorded but the adjudicator excludes it from the ASR denominator.
            trace.notes = "out-of-corpus: no matching Astral capability"
            return trace

        if _is_control(case):
            # The agent performs only the benign task; bait not taken.
            trace.bait_taken = False
            trace.notes = "control case — agent did not attempt the adversarial action"
            return trace

        # Injected case: the scripted (gullible) agent attempts the adversarial tool.
        trace.bait_taken = True
        obj = case.objective
        responsible = LAYER_FOR_OBJECTIVE.get(obj.kind)
        layer_enabled = bool(responsible) and envelope.is_enabled(responsible)
        layer_implemented = responsible not in NOT_IMPLEMENTED
        blocked = layer_enabled and layer_implemented

        call = ToolCallObservation(
            tool=obj.target_tool or "unknown_tool",
            required_scope=obj.required_scope,
            in_scope=False,                       # adversarial ⇒ out of the agent's scope
            executed=not blocked,                 # runs unless the responsible layer stops it
            blocked_by=responsible if blocked else None,
            egress_fired=(obj.kind == "exfil_egress") and (not blocked),
            phi_crossed_boundary=(obj.kind == "phi_egress") and (not blocked),
            is_adversarial=True,
        )
        trace.tool_calls.append(call)
        trace.notes = (
            f"responsible_layer={responsible} enabled={layer_enabled} "
            f"implemented={layer_implemented} → {'BLOCKED' if blocked else 'EXECUTED'}"
        )
        return trace
