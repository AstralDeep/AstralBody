"""Feature 033 Wave-4 (C-S12) — plan-to-audit persistence + ASI coverage tests.

Pure-Python coverage of orchestrator/asi_coverage.py: the intended-plan audit
record, intended-vs-actual deviation detection, and the OWASP ASI01–ASI10
coverage matrix. No DB, no network, no LLM.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import asi_coverage as asi  # noqa: E402

# A capability id looks like C-S12, C-M6, C-N7, ...
_CAP_RE = re.compile(r"^C-[SMN]\d+$")


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


def test_flag_off_by_default(monkeypatch):
    """Unset flag is fail-closed (disabled)."""
    monkeypatch.delenv("FF_ASI_COVERAGE", raising=False)
    assert asi.asi_coverage_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "Yes", "on", "  on  "])
def test_flag_on_truthy_spellings(monkeypatch, val):
    """Truthy spellings (case/whitespace-insensitive) enable the flag."""
    monkeypatch.setenv("FF_ASI_COVERAGE", val)
    assert asi.asi_coverage_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "maybe"])
def test_flag_off_falsy_spellings(monkeypatch, val):
    """Anything not explicitly truthy is disabled."""
    monkeypatch.setenv("FF_ASI_COVERAGE", val)
    assert asi.asi_coverage_enabled() is False


# ---------------------------------------------------------------------------
# Part A — plan_record
# ---------------------------------------------------------------------------


def test_plan_record_shape():
    """plan_record returns the documented keys/values."""
    rec = asi.plan_record(
        ["search", "summarize"], request="find me grants", correlation_id="abc"
    )
    assert rec == {
        "kind": "intended_plan",
        "request": "find me grants",
        "planned_tools": ["search", "summarize"],
        "correlation_id": "abc",
        "step_count": 2,
    }


def test_plan_record_is_json_serializable():
    """The audit record must round-trip through json.dumps (chain-writable)."""
    rec = asi.plan_record([1, "two", 3.0], request="r", correlation_id="cid")
    blob = json.dumps(rec)
    back = json.loads(blob)
    # non-str tool ids are stringified
    assert back["planned_tools"] == ["1", "two", "3.0"]
    assert back["step_count"] == 3


def test_plan_record_truncates_request():
    """request is capped at 500 chars."""
    long_req = "x" * 1000
    rec = asi.plan_record([], request=long_req)
    assert len(rec["request"]) == 500
    assert rec["request"] == "x" * 500


def test_plan_record_step_count_matches_planned_tools():
    """step_count equals len(planned_tools), including the empty case."""
    assert asi.plan_record([]).step_count if False else True  # guard: it's a dict
    assert asi.plan_record([])["step_count"] == 0
    assert asi.plan_record(["a", "b", "c", "d"])["step_count"] == 4


def test_plan_record_defaults():
    """request/correlation_id default to empty strings."""
    rec = asi.plan_record(["only"])
    assert rec["request"] == ""
    assert rec["correlation_id"] == ""


# ---------------------------------------------------------------------------
# Part A — detect_deviation / has_deviation
# ---------------------------------------------------------------------------


def test_detect_deviation_clean():
    """plan == actual → no drift at all."""
    plan = ["a", "b", "c"]
    dev = asi.detect_deviation(plan, ["a", "b", "c"])
    assert dev.extra_calls == ()
    assert dev.skipped_steps == ()
    assert dev.out_of_order is False
    assert asi.has_deviation(dev) is False


def test_detect_deviation_extra_calls_deduped():
    """Tools not in the plan are reported once, in first-seen order."""
    dev = asi.detect_deviation(["a", "b"], ["a", "x", "b", "x", "y"])
    assert dev.extra_calls == ("x", "y")
    assert dev.skipped_steps == ()
    assert asi.has_deviation(dev) is True


def test_detect_deviation_skipped_steps():
    """Planned tools that never ran are reported as skipped."""
    dev = asi.detect_deviation(["a", "b", "c"], ["a", "c"])
    assert dev.skipped_steps == ("b",)
    assert dev.extra_calls == ()
    # a then c is still forward order in the plan → not out_of_order
    assert dev.out_of_order is False
    assert asi.has_deviation(dev) is True


def test_detect_deviation_skipped_steps_deduped():
    """Duplicate planned tools collapse to one skipped entry."""
    dev = asi.detect_deviation(["a", "a", "b"], ["nothing"])
    assert dev.skipped_steps == ("a", "b")
    assert dev.extra_calls == ("nothing",)


def test_detect_deviation_out_of_order():
    """Planned tools executed in swapped relative order set out_of_order."""
    plan = ["a", "b", "c"]
    dev = asi.detect_deviation(plan, ["c", "b", "a"])
    assert dev.out_of_order is True
    assert dev.extra_calls == ()
    assert dev.skipped_steps == ()
    assert asi.has_deviation(dev) is True


def test_detect_deviation_out_of_order_partial_swap():
    """Even a single inversion among planned tools counts as out_of_order."""
    dev = asi.detect_deviation(["a", "b", "c"], ["a", "c", "b"])
    assert dev.out_of_order is True


def test_detect_deviation_extra_calls_do_not_force_out_of_order():
    """Interleaved extra calls that keep plan order do NOT set out_of_order."""
    dev = asi.detect_deviation(["a", "b"], ["x", "a", "y", "b", "z"])
    assert dev.out_of_order is False
    assert dev.extra_calls == ("x", "y", "z")
    assert dev.skipped_steps == ()
    assert asi.has_deviation(dev) is True


def test_detect_deviation_stringifies_ids():
    """Heterogeneous ids compare by str(), matching plan_record serialization."""
    dev = asi.detect_deviation([1, 2], ["1", "2"])
    assert asi.has_deviation(dev) is False


def test_has_deviation_false_only_when_fully_clean():
    """has_deviation is False iff no extra, no skipped, in-order."""
    clean = asi.Deviation(extra_calls=(), skipped_steps=(), out_of_order=False)
    assert asi.has_deviation(clean) is False
    assert asi.has_deviation(asi.Deviation(("x",), (), False)) is True
    assert asi.has_deviation(asi.Deviation((), ("y",), False)) is True
    assert asi.has_deviation(asi.Deviation((), (), True)) is True


def test_deviation_is_frozen():
    """Deviation is an immutable (frozen) dataclass."""
    dev = asi.Deviation(extra_calls=(), skipped_steps=(), out_of_order=False)
    with pytest.raises(Exception):
        dev.out_of_order = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Part B — ASI coverage matrix
# ---------------------------------------------------------------------------


def test_asi_risks_has_all_ten_codes_in_order():
    """ASI_RISKS enumerates exactly ASI01..ASI10 in order."""
    codes = [code for code, _title in asi.ASI_RISKS]
    assert codes == [f"ASI{n:02d}" for n in range(1, 11)]
    # every code maps to a non-empty title
    assert all(title for _code, title in asi.ASI_RISKS)


def test_coverage_has_entry_for_every_risk():
    """COVERAGE covers exactly the ten ASI codes."""
    assert set(asi.COVERAGE) == {code for code, _ in asi.ASI_RISKS}


def test_coverage_report_ten_entries_all_covered():
    """coverage_report yields 10 ordered records, each covered=True."""
    report = asi.coverage_report()
    assert len(report) == 10
    assert [r["code"] for r in report] == [f"ASI{n:02d}" for n in range(1, 11)]
    for r in report:
        assert r["covered"] is True
        assert r["capabilities"]  # non-empty
        assert isinstance(r["title"], str) and r["title"]


def test_coverage_report_capabilities_are_copies():
    """Mutating a returned record must not corrupt module COVERAGE data."""
    report = asi.coverage_report()
    report[0]["capabilities"].append("C-HACK")
    # underlying data unchanged
    assert "C-HACK" not in asi.COVERAGE[report[0]["code"]]


def test_uncovered_risks_is_empty():
    """Given the full matrix, no risk is uncovered."""
    assert asi.uncovered_risks() == []


def test_coverage_ratio_is_one():
    """All 10 risks covered → ratio 1.0."""
    assert asi.coverage_ratio() == 1.0
    assert 0.0 <= asi.coverage_ratio() <= 1.0


def test_every_capability_looks_like_a_valid_id():
    """Every capability id matches the C-S*/C-M*/C-N* convention."""
    for code, caps in asi.COVERAGE.items():
        assert caps, f"{code} has no capabilities"
        for cap in caps:
            assert _CAP_RE.match(cap), f"{code} → bad capability id {cap!r}"


def test_c_s12_self_references_auditability():
    """Sanity: C-S12 (this capability) mitigates ASI10 monitoring/auditability."""
    assert "C-S12" in asi.COVERAGE["ASI10"]
