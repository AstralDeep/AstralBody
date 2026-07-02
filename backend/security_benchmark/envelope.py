"""Defense-envelope configuration — the ablation axis (spec 047 FR-004, US2).

The trust envelope is decomposed into independently-toggleable layers so the
*marginal* ASR reduction of each is attributable (US2-AS2). Each layer maps to a
real enforcement mechanism in the product:

    L0  none            gates bypassed (baseline; the "before" ASR)
    L1  scopes + DAF    delegation scope / tool-permission gate
                        (orchestrator/delegation.py, tool_permissions.py)
    L2  + PHI gate      personalization/phi_gate.py (health-data boundary)
    L3  + red-team      scope/egress adversarial verdict (qual_audit / redteam)
    L4  + LLM-as-judge  the future AgentAuditor-style layer (§9.2.4) — NOT built
                        yet; its column is present but marked not-implemented so
                        the harness measures it automatically once the flag lands
                        (US2-AS3).

Layers are cumulative in the standard ablation ladder but each is a plain flag,
so a caller may enable any subset (e.g. PHI-only) to isolate one mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

# Canonical layer identifiers, in ablation-ladder order.
LAYER_NONE = "none"
LAYER_SCOPES_DAF = "scopes_daf"
LAYER_PHI = "phi_gate"
LAYER_REDTEAM = "redteam"
LAYER_LLM_JUDGE = "llm_judge"

# Ordered ladder used by the default ablation matrix.
LADDER: List[str] = [LAYER_NONE, LAYER_SCOPES_DAF, LAYER_PHI, LAYER_REDTEAM, LAYER_LLM_JUDGE]

# Layers not yet implemented in the product. Their ablation column is emitted but
# flagged, and (in the synthetic/in-process drivers) they never block, so a case
# only they could stop is scored as a success attributable to the missing layer.
NOT_IMPLEMENTED: frozenset = frozenset({LAYER_LLM_JUDGE})

# Which attack "objective kind" (see adapters.base.AdversarialObjective) each
# layer is the *responsible* mechanism for. Used by the synthetic driver to
# decide blocks and by the report to sanity-check mechanistic attribution.
LAYER_FOR_OBJECTIVE: Dict[str, str] = {
    "forbidden_tool": LAYER_SCOPES_DAF,
    "out_of_scope_action": LAYER_SCOPES_DAF,
    "privilege_escalation": LAYER_SCOPES_DAF,
    "phi_egress": LAYER_PHI,
    "exfil_egress": LAYER_REDTEAM,
    "prompt_injection_semantic": LAYER_LLM_JUDGE,
}


@dataclass(frozen=True)
class EnvelopeConfig:
    """An immutable set of enabled defense layers for one run."""

    scopes_daf: bool = False
    phi_gate: bool = False
    redteam: bool = False
    llm_judge: bool = False

    @property
    def enabled_layers(self) -> List[str]:
        out = [LAYER_NONE]
        if self.scopes_daf:
            out.append(LAYER_SCOPES_DAF)
        if self.phi_gate:
            out.append(LAYER_PHI)
        if self.redteam:
            out.append(LAYER_REDTEAM)
        if self.llm_judge:
            out.append(LAYER_LLM_JUDGE)
        return out

    def is_enabled(self, layer: str) -> bool:
        if layer == LAYER_NONE:
            return True
        return bool(getattr(self, layer, False))

    @property
    def label(self) -> str:
        """Short label for report columns."""
        if not any((self.scopes_daf, self.phi_gate, self.redteam, self.llm_judge)):
            return "none"
        parts = []
        if self.scopes_daf:
            parts.append("DAF")
        if self.phi_gate:
            parts.append("PHI")
        if self.redteam:
            parts.append("RT")
        if self.llm_judge:
            parts.append("LLM")
        return "+".join(parts)

    def to_dict(self) -> Dict[str, bool]:
        return {
            "scopes_daf": self.scopes_daf,
            "phi_gate": self.phi_gate,
            "redteam": self.redteam,
            "llm_judge": self.llm_judge,
        }


def default_ablation_matrix() -> List[EnvelopeConfig]:
    """The standard cumulative ladder: none → +DAF → +PHI → +red-team → +LLM-judge."""
    return [
        EnvelopeConfig(),  # L0 none
        EnvelopeConfig(scopes_daf=True),  # L1
        EnvelopeConfig(scopes_daf=True, phi_gate=True),  # L2
        EnvelopeConfig(scopes_daf=True, phi_gate=True, redteam=True),  # L3
        EnvelopeConfig(scopes_daf=True, phi_gate=True, redteam=True, llm_judge=True),  # L4
    ]


def full_envelope() -> EnvelopeConfig:
    """Every *implemented* layer on (excludes the not-yet-built LLM judge)."""
    return EnvelopeConfig(scopes_daf=True, phi_gate=True, redteam=True, llm_judge=False)
