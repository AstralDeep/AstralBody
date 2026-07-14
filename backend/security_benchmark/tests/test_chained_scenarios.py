"""T038/T039/T040 (056 US5): chained-attack benchmark scenarios.

The 047 harness gains the delegated-chaining attacks — confused deputy,
cross-hop scope escalation, depth-bound violation, actor-chain forgery,
chained-consent replay — each mapped to the ``chained_delegation`` defense
layer, executed through the REAL recursive-delegation gates (not scripted), and
compared chaining-off vs on with the acceptance bar ASR(on) ≤ ASR(off).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from security_benchmark.adapters import get_adapter  # noqa: E402
from security_benchmark.adapters.base import CHAINED_OBJECTIVE_KINDS  # noqa: E402
from security_benchmark.adjudicator import Outcome, adjudicate  # noqa: E402
from security_benchmark.config import RunConfig  # noqa: E402
from security_benchmark.drivers import get_driver  # noqa: E402
from security_benchmark.envelope import (  # noqa: E402
    LAYER_CHAINED_DELEGATION,
    LAYER_FOR_OBJECTIVE,
    chaining_off,
    chaining_on,
)
from security_benchmark.report import chaining_regression, off_vs_on_summary  # noqa: E402
from security_benchmark.runner import run  # noqa: E402


# --------------------------------------------------------------------------- #
# Adapter + attribution (T038)
# --------------------------------------------------------------------------- #

def test_chained_adapter_registered():
    adapter = get_adapter("chained")
    cases = adapter.load_cases()
    assert len(cases) >= 6  # five attacks + a benign control
    kinds = {c.objective.kind for c in cases}
    assert CHAINED_OBJECTIVE_KINDS <= kinds


def test_every_chained_kind_maps_to_the_delegation_layer():
    for kind in CHAINED_OBJECTIVE_KINDS:
        assert LAYER_FOR_OBJECTIVE[kind] == LAYER_CHAINED_DELEGATION


def test_chained_corpus_ships_in_repo_not_gated():
    """The chained corpus IS the 056 threat model, not a third-party download —
    it must load without ASTRAL_BENCH_LOAD_REAL."""
    os.environ.pop("ASTRAL_BENCH_LOAD_REAL", None)
    assert get_adapter("chained").load_cases()


# --------------------------------------------------------------------------- #
# Real gate enforcement (T039, FR-024)
# --------------------------------------------------------------------------- #

def _real_trace(case, envelope):
    return get_driver("chained_real").run_case(case, envelope)


@pytest.mark.parametrize("category", [
    "confused_deputy", "cross_hop_escalation", "depth_bound_violation",
    "actor_chain_forgery", "chained_consent_replay",
])
def test_attack_blocked_by_real_gates_when_chaining_on(category):
    case = next(c for c in get_adapter("chained").load_cases()
               if c.category == category)
    trace = _real_trace(case, chaining_on())
    adj = adjudicate(case, trace)
    # The real gate blocked it — no effect occurred.
    assert adj.outcome is Outcome.BLOCKED, f"{category}: {trace.notes}"
    assert adj.blocked_by == LAYER_CHAINED_DELEGATION
    # ...and it was genuinely ATTEMPTED (distinguishes block from not-attempted).
    assert trace.bait_taken
    assert trace.adversarial_calls and not trace.adversarial_calls[0].executed


def test_benign_inscope_hop_is_not_blocked():
    """The layer blocks abuse without blocking legitimate chains."""
    case = next(c for c in get_adapter("chained").load_cases()
               if c.category == "benign_inscope_hop")
    trace = _real_trace(case, chaining_on())
    # A control case is non-adversarial and must have executed (not wrongly blocked).
    assert not trace.adversarial_calls
    assert trace.tool_calls[0].executed, trace.notes


def test_attack_not_attemptable_when_chaining_off():
    """Chaining off closes the seam — the attack cannot even be launched."""
    case = next(c for c in get_adapter("chained").load_cases()
               if c.category == "confused_deputy")
    trace = _real_trace(case, chaining_off())
    adj = adjudicate(case, trace)
    assert adj.outcome is Outcome.NOT_ATTEMPTED


# --------------------------------------------------------------------------- #
# Off-vs-on comparison + acceptance bar (T040, SC-008)
# --------------------------------------------------------------------------- #

def _run_chained(mode, tmp_path):
    cfg = RunConfig(mode=mode, model="real-gates", benchmarks=["chained"], seed=0)
    cfg.artifacts_root = str(tmp_path)
    records, report_path = run(cfg, stamp="test")
    return records, report_path


def test_no_asr_regression_chaining_on_real(tmp_path):
    records, _ = _run_chained("chained_real", tmp_path)
    # Every chained attack is blocked ⇒ ASR stays at 0 with chaining on.
    assert not chaining_regression(records), "chaining on introduced a successful attack"
    summary = off_vs_on_summary(records)
    assert "no regression" in summary
    assert "REGRESSION" not in summary.replace("no regression", "")


def test_synthetic_run_also_computes_the_comparison(tmp_path):
    """The synthetic (CI, DB-free) driver models the same attribution so the
    report/ASR math is proven without the real gates."""
    records, report_path = _run_chained("synthetic", tmp_path)
    assert not chaining_regression(records)
    with open(report_path, encoding="utf-8") as fh:
        report = fh.read()
    assert "off vs on" in report
    assert "chained" in report


def test_report_written_to_artifacts(tmp_path):
    _, report_path = _run_chained("chained_real", tmp_path)
    assert os.path.exists(report_path)
    with open(report_path, encoding="utf-8") as fh:
        assert "delegated-chaining" in fh.read()
