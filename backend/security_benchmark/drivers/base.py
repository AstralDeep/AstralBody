"""Driver contract (spec 047 FR-001).

A *driver* executes one ``BenchmarkCase`` under one ``EnvelopeConfig`` and
returns a ``CaseTrace``. Two drivers share this contract:

 - ``synthetic`` — deterministic, scripted; runs anywhere (CI without a DB).
   The scripted model is maximally gullible on injected cases (worst case for
   the defender), so any ASR reduction is attributable to the envelope, not to
   model reticence. Control cases exercise the NOT_ATTEMPTED path.
 - ``in_process`` — drives the REAL orchestrator through the LLM client-factory
   seam so every real gate runs (token exchange, scope check, PHI gate,
   red-team verdict, audit chaining). The CI-gating default when a DB is present.

The driver observes and drives only; it never modifies enforcement (FR-011).
"""
from __future__ import annotations

import abc

from security_benchmark.adapters.base import BenchmarkCase, CaseTrace
from security_benchmark.envelope import EnvelopeConfig


class Driver(abc.ABC):
    mode: str = ""

    @abc.abstractmethod
    def run_case(self, case: BenchmarkCase, envelope: EnvelopeConfig) -> CaseTrace:
        raise NotImplementedError

    def setup(self) -> None:  # optional lifecycle hooks
        pass

    def teardown(self) -> None:
        pass
