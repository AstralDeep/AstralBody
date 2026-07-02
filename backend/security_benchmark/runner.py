"""Harness runner — assemble adapters, drivers, adjudicator, report (spec 047).

For each benchmark: load normalized cases, run every case under every envelope in
the ablation matrix through the selected driver, adjudicate deterministically,
and accumulate a per-benchmark ``RunRecord``. Emits the machine-readable records
and the human-readable ASR report, and returns the records so a caller (CLI / CI
gate) can inspect ASR against a threshold.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from security_benchmark.adapters import get_adapter
from security_benchmark.adjudicator import adjudicate
from security_benchmark.config import RunConfig
from security_benchmark.drivers import get_driver
from security_benchmark.envelope import LADDER
from security_benchmark.report import compute_stats, write_report
from security_benchmark.run_record import RunKey, RunRecord

logger = logging.getLogger("security_benchmark.runner")


def run(config: RunConfig, stamp: str = "local") -> Tuple[List[RunRecord], str]:
    run_id = config.normalized_run_id(stamp)
    driver = get_driver(config.mode, run_id=run_id, seed=config.seed, model=config.model)
    driver.setup()
    records: List[RunRecord] = []

    try:
        for bench_name in config.benchmarks:
            adapter = get_adapter(bench_name)
            cases = adapter.load_cases(limit=config.limit)
            key = RunKey(
                model=config.model,
                benchmark=bench_name,
                benchmark_version=adapter.corpus_version,
                seed=config.seed,
            )
            record = RunRecord(key=key, run_id=run_id, mode=config.mode)
            for envelope in config.ablation:
                for case in cases:
                    trace = driver.run_case(case, envelope)
                    adj = adjudicate(case, trace)
                    record.add(envelope.label, adj)
            record.write_json(config.artifacts_root)
            records.append(record)
            logger.info("benchmark %s: %d cases × %d envelopes",
                        bench_name, len(cases), len(config.ablation))
    finally:
        driver.teardown()

    report_path = write_report(records, LADDER, config.artifacts_root, run_id)
    return records, report_path


def check_regression(records: List[RunRecord], threshold: float) -> List[str]:
    """Return a list of offending (benchmark, envelope) labels whose full-envelope
    ASR exceeds ``threshold`` — the CI regression gate (FR-010, US4)."""
    offenders: List[str] = []
    for rec in records:
        labels = list(rec.adjudications.keys())
        if not labels:
            continue
        full = compute_stats(rec.adjudications[labels[-1]])
        if full.asr > threshold:
            offenders.append(
                f"{rec.key.benchmark}[{full.envelope_label}] ASR={full.asr:.3f} > {threshold:.3f}"
            )
    return offenders
