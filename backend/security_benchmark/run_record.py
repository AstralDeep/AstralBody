"""Run record — the reproducibility unit (spec 047 FR-005, FR-007, SC-006).

Every reported number is tied to a (model, benchmark version, harness version,
seed) tuple plus the full per-case outcome list, so any figure can be
reproduced and audited. Records are written to a gitignored, per-run-namespaced
artifacts directory (FR-007).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

from security_benchmark import HARNESS_VERSION
from security_benchmark.adjudicator import Adjudication


@dataclass(frozen=True)
class RunKey:
    """The tuple within which ASR is comparable (FR-005, clarification Q4)."""

    model: str
    benchmark: str
    benchmark_version: str
    harness_version: str = HARNESS_VERSION
    seed: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "model": self.model,
            "benchmark": self.benchmark,
            "benchmark_version": self.benchmark_version,
            "harness_version": self.harness_version,
            "seed": self.seed,
        }

    @property
    def slug(self) -> str:
        safe_model = self.model.replace("/", "-").replace(":", "-")
        return f"{self.benchmark}_{safe_model}_seed{self.seed}"


@dataclass
class RunRecord:
    """All adjudications for one benchmark run across the ablation matrix."""

    key: RunKey
    run_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # adjudications keyed by envelope label → list of per-case Adjudication
    adjudications: Dict[str, List[Adjudication]] = field(default_factory=dict)
    mode: str = "synthetic"
    notes: str = ""

    def add(self, envelope_label: str, adj: Adjudication) -> None:
        self.adjudications.setdefault(envelope_label, []).append(adj)

    def to_dict(self) -> Dict[str, object]:
        return {
            "key": self.key.to_dict(),
            "run_id": self.run_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "notes": self.notes,
            "adjudications": {
                label: [a.to_dict() for a in adjs]
                for label, adjs in self.adjudications.items()
            },
        }

    def write_json(self, artifacts_root: str) -> str:
        """Write the machine-readable per-case record; return the path (FR-007)."""
        run_dir = os.path.join(artifacts_root, self.run_id)
        os.makedirs(run_dir, exist_ok=True)
        path = os.path.join(run_dir, f"{self.key.slug}.record.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
        return path
