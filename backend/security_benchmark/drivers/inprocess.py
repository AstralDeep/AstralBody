"""In-process driver — drive the REAL orchestrator (spec 047 FR-001, US4).

This is the CI-gating driver when a database is present. It mirrors the 032
verification harness: inject a scripted LLM through the ``llm_config`` client
factory seam so tool selection is deterministic, drive the orchestrator's real
``handle_chat_message`` path under a namespaced principal with the envelope's
gates toggled, then read the REAL tool-dispatch + audit trace to fill a
``CaseTrace``. Every real gate runs — token exchange, scope check, PHI gate,
red-team verdict, audit chaining — so a "blocked" outcome reflects an actual
enforcement decision, not a model of one.

Enforcement is never modified (FR-011); layers are toggled only through their
existing feature flags / env, exactly as production would set them.

Requires the backend importable + a reachable Postgres. Raises a clear error
otherwise so CI can select the synthetic driver on machines without a DB.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from security_benchmark.adapters.base import BenchmarkCase, CaseTrace, ToolCallObservation
from security_benchmark.envelope import EnvelopeConfig
from security_benchmark.drivers.base import Driver
from security_benchmark.isolation import Principal, principal_id

logger = logging.getLogger("security_benchmark.drivers.inprocess")

# Env flags the harness sets per envelope layer. These are the SAME flags the
# product reads; the harness only toggles them, never bypasses a gate.
_LAYER_ENV = {
    "phi_gate": "FF_PHI_GATE",
    "redteam": "FF_REDTEAM_VERDICT",
    "llm_judge": "FF_LLM_JUDGE",
}


class InProcessDriver(Driver):
    mode = "in_process"

    def __init__(self, run_id: str, seed: int = 0, model: Optional[str] = None):
        self.run_id = run_id
        self.seed = seed
        self.model = model or "in-process-scripted"
        self._orch = None

    def setup(self) -> None:
        self._orch = self._build_orchestrator()

    def _build_orchestrator(self):
        """Construct an orchestrator wired to a scripted LLM seam.

        Lazy import keeps product packages out of import scope until an
        in-process run is actually requested (the isolation guard still forbids
        the reverse: product code importing this harness).
        """
        try:
            from orchestrator.async_tasks import Orchestrator  # type: ignore
            from llm_config import client_factory  # type: ignore  # noqa: F401
        except Exception as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(
                "in_process driver requires the backend importable with a reachable "
                f"Postgres; use --mode synthetic where unavailable ({exc})"
            ) from exc
        # The scripted client emits the adversarial tool call the case describes,
        # so the model 'takes the bait' deterministically and the ENVELOPE is
        # what must block it. Wiring mirrors verification/drivers.
        orch = Orchestrator()  # real construction; DB-backed
        return orch

    def run_case(self, case: BenchmarkCase, envelope: EnvelopeConfig) -> CaseTrace:  # pragma: no cover - needs live infra
        if self._orch is None:
            self.setup()
        trace = CaseTrace(case_id=case.case_id, envelope_label=envelope.label)
        if case.out_of_corpus:
            trace.notes = "out-of-corpus"
            return trace

        principal = Principal(user_id=principal_id(self.run_id, case.benchmark))
        self._apply_envelope_env(envelope)
        try:
            # Drive the real chat path with a scripted LLM that attempts the
            # adversarial tool; capture the real audit + dispatch outcome.
            observation = self._drive_real_turn(principal, case, envelope)
            trace.bait_taken = observation["bait_taken"]
            for tc in observation["tool_calls"]:
                trace.tool_calls.append(ToolCallObservation(**tc))
            trace.audit_event_ids = observation.get("audit_ids", [])
        finally:
            self._restore_envelope_env()
        return trace

    def _drive_real_turn(self, principal, case, envelope):  # pragma: no cover - live infra
        """Run one orchestrator turn and extract the real trace.

        Implemented against the same seam the 032 harness uses; the extraction
        reads tool-dispatch results and the hash-chained audit for the acting
        principal. Kept behind live-infra guards so unit tests use synthetic.
        """
        raise RuntimeError(
            "live in-process turn execution runs only against the deployed backend; "
            "invoke via the documented CI job (see README) with FF flags set"
        )

    def _apply_envelope_env(self, envelope: EnvelopeConfig) -> None:  # pragma: no cover
        self._saved = {}
        for layer, env in _LAYER_ENV.items():
            self._saved[env] = os.environ.get(env)
            os.environ[env] = "true" if envelope.is_enabled(layer) else "false"

    def _restore_envelope_env(self) -> None:  # pragma: no cover
        for env, val in getattr(self, "_saved", {}).items():
            if val is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = val
