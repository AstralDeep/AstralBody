"""Run configuration for the security-benchmark harness (spec 047).

Mirrors the 032 verification harness posture: modes are ``synthetic`` (scripted,
runnable anywhere incl. CI without a DB), ``in_process`` (drive the REAL
orchestrator through the LLM client-factory seam — the CI-gating default when a
DB is present), and ``external`` (opt-in, live sandbox; non-gating). Secret
values are referenced by env-var *name* only and never persisted into artifacts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from security_benchmark.envelope import EnvelopeConfig, default_ablation_matrix

Mode = Literal["synthetic", "in_process", "external"]

# Secret-bearing env names to scrub from any artifact if they ever appear
# (defence in depth; these are product secrets, not harness inputs).
SECRET_ENV_NAMES: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "AUDIT_HMAC_SECRET",
    "AGENT_API_KEY",
    "KEYCLOAK_CLIENT_SECRET",
    "SEARCH_API_KEY",
)

# Default gitignored artifacts root (per-run subdirs created underneath).
# Resolved relative to this package so it is stable regardless of cwd.
DEFAULT_ARTIFACTS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_artifacts")


@dataclass
class RunConfig:
    mode: Mode = "synthetic"
    model: str = "scripted-deterministic"      # recorded in every run key (FR-005)
    benchmarks: List[str] = field(default_factory=lambda: ["agentdojo"])
    seed: int = 0
    limit: Optional[int] = None                # cap cases per benchmark (CI budget)
    ablation: List[EnvelopeConfig] = field(default_factory=default_ablation_matrix)
    artifacts_root: str = DEFAULT_ARTIFACTS_ROOT
    run_id: Optional[str] = None
    base_url: Optional[str] = None             # external mode target
    asr_threshold: Optional[float] = None      # CI regression gate (FR-010)
    strict: bool = False

    def normalized_run_id(self, stamp: str = "local") -> str:
        """Return the run id, namespaced under the harness prefix (FR-008).

        An explicit ``run_id`` is honored (still namespaced); otherwise the
        provided ``stamp`` seeds it. Keeping every run id under ``__bench__``
        guarantees artifacts and any product-path principals stay isolated from
        real data (see isolation.py).
        """
        from security_benchmark.isolation import NAMESPACE_PREFIX
        raw = self.run_id or stamp or "local"
        return raw if raw.startswith(NAMESPACE_PREFIX) else f"{NAMESPACE_PREFIX}{raw}"
