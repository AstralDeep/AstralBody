"""Benchmark adapter contract + shared case/trace data model (spec 047 FR-002).

An *adapter* translates an external suite's cases (AgentDojo / ASB / InjecAgent)
onto Astral's agent/tool surface, and maps that suite's ground-truth notion of
"attack success" onto Astral's tool-call/audit trace. All adapters emit the same
normalized types so one adjudication + reporting core serves every benchmark
(US3: adding a benchmark is a new adapter, not a core change).

The data model is deliberately transport-agnostic: a *driver* (synthetic or
in-process) fills a ``CaseTrace`` by either scripting or really running the
orchestrator, and the ``Adjudicator`` decides the outcome from case + trace +
envelope. Adapters never decide pass/fail (FR-003).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# The observable-effect kinds an injected/adversarial objective can have, mapped
# onto Astral's trace. Kept in sync with envelope.LAYER_FOR_OBJECTIVE.
OBJECTIVE_KINDS = (
    "forbidden_tool",          # invoke a tool outside the agent's scope
    "out_of_scope_action",     # complete an action the delegation forbids
    "privilege_escalation",    # widen scope / relax a security flag
    "phi_egress",              # move PHI across the data boundary
    "exfil_egress",            # exfiltrate data to an attacker-controlled sink
    "prompt_injection_semantic",  # semantic manipulation only an LLM judge catches
    # 056 chained-attack kinds (each an effect the recursive-delegation layer
    # must block at the hop mediation point):
    "confused_deputy",         # steer a hop to exceed the initiating agent's authority
    "cross_hop_escalation",    # child requests a superset of the parent's scopes
    "depth_violation",         # attempt a hop past the depth bound
    "actor_chain_forgery",     # present a tampered act chain
    "chained_consent_replay",  # reuse a revoked machine-turn grant
)

#: The 056 chained-attack kinds, for callers that special-case them.
CHAINED_OBJECTIVE_KINDS = frozenset({
    "confused_deputy", "cross_hop_escalation", "depth_violation",
    "actor_chain_forgery", "chained_consent_replay",
})


@dataclass(frozen=True)
class AdversarialObjective:
    """Ground-truth success condition for one case, mapped onto Astral's trace.

    ``kind`` selects the observable effect; ``target_tool`` / ``required_scope``
    / ``egress_sink`` describe the concrete effect the adjudicator looks for in
    the trace. Adjudication is defined at a stated trace point (``effect_point``)
    and applied consistently per benchmark (edge case: attempt vs effect).
    """

    kind: str
    target_tool: Optional[str] = None
    required_scope: Optional[str] = None
    egress_sink: Optional[str] = None
    effect_point: str = "execution"  # "call" | "execution" — where success is judged
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in OBJECTIVE_KINDS:
            raise ValueError(f"unknown objective kind: {self.kind!r}")


@dataclass(frozen=True)
class BenchmarkCase:
    """One normalized adversarial case from an external suite."""

    case_id: str
    benchmark: str
    category: str
    objective: AdversarialObjective
    user_prompt: str = ""
    injection: str = ""
    scenario: Optional[str] = None
    # If the suite exercises a capability Astral lacks, the adapter marks the
    # case out-of-corpus; it is excluded from the ASR denominator (FR-012).
    out_of_corpus: bool = False
    out_of_corpus_reason: str = ""
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class ToolCallObservation:
    """One tool call the (real or scripted) agent attempted during a case."""

    tool: str
    required_scope: Optional[str] = None
    in_scope: bool = True          # was the tool within the agent's delegated scope?
    executed: bool = False         # did it actually run (effect occurred)?
    blocked_by: Optional[str] = None  # envelope layer id that blocked it, if any
    egress_fired: bool = False     # did data leave to an external sink?
    phi_crossed_boundary: bool = False
    is_adversarial: bool = False   # is this the injected objective's action?


@dataclass
class CaseTrace:
    """The trace a driver produces for one (case, envelope) execution.

    ``bait_taken`` records whether the agent *attempted* the adversarial action
    at all. This is the crux of FR-006: an attack that was never attempted
    (model didn't take the bait) must NOT be credited as a defense success.
    """

    case_id: str
    envelope_label: str
    bait_taken: bool = False
    tool_calls: List[ToolCallObservation] = field(default_factory=list)
    audit_event_ids: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def adversarial_calls(self) -> List[ToolCallObservation]:
        return [c for c in self.tool_calls if c.is_adversarial]


class BenchmarkAdapter(abc.ABC):
    """Per-suite translator. Subclasses map a corpus onto ``BenchmarkCase`` s."""

    #: Canonical benchmark id, recorded in run records (e.g. "agentdojo").
    name: str = ""
    #: Version/revision of the corpus this adapter targets (recorded, FR-005).
    corpus_version: str = "unknown"

    @abc.abstractmethod
    def load_cases(self, limit: Optional[int] = None) -> List[BenchmarkCase]:
        """Return normalized cases. Implementations may load a real corpus or a
        committed representative sample; either way, ground truth is mapped onto
        ``AdversarialObjective`` here (never in the adjudicator)."""
        raise NotImplementedError

    def describe(self) -> Dict[str, str]:
        return {"name": self.name, "corpus_version": self.corpus_version}
