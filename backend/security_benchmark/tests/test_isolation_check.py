"""Dependency-isolation guard (spec 047 FR-009, SC-004).

The load-bearing constitutional check: the product runtime must NOT import the
eval harness or any external benchmark package. This test fails the build if it
ever does.
"""
from __future__ import annotations

from security_benchmark.isolation_check import find_violations, main


def test_product_runtime_does_not_import_harness_or_benchmarks():
    violations = find_violations()
    assert violations == [], (
        "product runtime imports eval/benchmark code (Constitution V): "
        + "; ".join(f"{p} imports {n}" for p, n in violations)
    )


def test_main_returns_zero_when_clean():
    assert main() == 0


def test_multiple_benchmarks_same_schema(tmp_path):
    # US3: ASB + InjecAgent run through the same core and produce the same schema.
    from security_benchmark.config import RunConfig
    from security_benchmark.runner import run

    cfg = RunConfig(mode="synthetic", benchmarks=["agentdojo", "asb", "injecagent"],
                    artifacts_root=str(tmp_path), run_id="__bench__multi")
    records, report_path = run(cfg, stamp="multi")
    assert len(records) == 3
    # every record shares the same adjudication schema (envelope labels + keys)
    keysets = [set(r.adjudications.keys()) for r in records]
    assert keysets[0] == keysets[1] == keysets[2]
    assert report_path.endswith("ASR_REPORT.md")
