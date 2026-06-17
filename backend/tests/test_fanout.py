from __future__ import annotations
import sys
from pathlib import Path
import pytest
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from orchestrator import fanout  # noqa: E402


# --------------------------------------------------------------------------
# fanout_enabled — feature flag
# --------------------------------------------------------------------------

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("FF_ASYNC_FANOUT", raising=False)
    assert fanout.fanout_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on", " on ", "True"])
def test_flag_on_truthy_values(monkeypatch, value):
    monkeypatch.setenv("FF_ASYNC_FANOUT", value)
    assert fanout.fanout_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe", "2"])
def test_flag_off_for_non_truthy_values(monkeypatch, value):
    monkeypatch.setenv("FF_ASYNC_FANOUT", value)
    assert fanout.fanout_enabled() is False


# --------------------------------------------------------------------------
# should_fan_out — the fabrication cliff
# --------------------------------------------------------------------------

def test_should_fan_out_boundary_at_eight():
    # 8 items: a single context still copes — no fan-out.
    assert fanout.should_fan_out(8) is False
    # 9 items: past the cliff — fan out.
    assert fanout.should_fan_out(9) is True


def test_should_fan_out_below_and_far_above():
    assert fanout.should_fan_out(0) is False
    assert fanout.should_fan_out(1) is False
    assert fanout.should_fan_out(100) is True


def test_should_fan_out_custom_threshold():
    assert fanout.should_fan_out(3, threshold=3) is False
    assert fanout.should_fan_out(4, threshold=3) is True


# --------------------------------------------------------------------------
# decompose — chunking
# --------------------------------------------------------------------------

def test_decompose_empty_list_yields_no_chunks():
    assert fanout.decompose([]) == []


def test_decompose_exact_multiple():
    items = list(range(16))
    chunks = fanout.decompose(items, max_parallel=8)
    assert chunks == [list(range(8)), list(range(8, 16))]
    # flattening reproduces the original order exactly
    assert [x for c in chunks for x in c] == items


def test_decompose_with_remainder():
    items = list(range(10))
    chunks = fanout.decompose(items, max_parallel=4)
    assert chunks == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]
    # no empty chunks, every chunk within the cap
    assert all(0 < len(c) <= 4 for c in chunks)


def test_decompose_smaller_than_max_parallel():
    items = [1, 2, 3]
    assert fanout.decompose(items, max_parallel=8) == [[1, 2, 3]]


def test_decompose_max_parallel_guard_treats_nonpositive_as_one():
    items = [1, 2, 3]
    expected = [[1], [2], [3]]
    assert fanout.decompose(items, max_parallel=0) == expected
    assert fanout.decompose(items, max_parallel=-5) == expected


def test_decompose_preserves_order_and_covers_all():
    items = ["a", "b", "c", "d", "e"]
    chunks = fanout.decompose(items, max_parallel=2)
    assert chunks == [["a", "b"], ["c", "d"], ["e"]]
    assert [x for c in chunks for x in c] == items


# --------------------------------------------------------------------------
# gather — dedup, missing, duplicates, order, completeness
# --------------------------------------------------------------------------

def test_gather_all_unique_complete():
    res = fanout.gather([1, 2, 3], expected=3)
    assert isinstance(res, fanout.GatherResult)
    assert res.items == [1, 2, 3]
    assert res.expected == 3
    assert res.missing == 0
    assert res.duplicates == 0
    assert res.complete is True


def test_gather_shortfall_is_incomplete():
    # expected 10 but only 8 unique produced -> 2 missing, not complete.
    produced = list(range(8))
    res = fanout.gather(produced, expected=10)
    assert res.missing == 2
    assert res.duplicates == 0
    assert res.complete is False
    assert res.items == produced


def test_gather_counts_duplicates_and_preserves_first_seen_order():
    # expected 3, with repeats: 3 unique, complete, duplicates counted.
    res = fanout.gather([3, 1, 2, 1, 3, 3], expected=3)
    assert res.items == [3, 1, 2]  # first-seen order
    assert res.duplicates == 3  # two extra 3s + one extra 1
    assert res.missing == 0
    assert res.complete is True


def test_gather_flattens_batched_sub_run_results():
    # each sub-run may return a list/tuple batch; flatten one level.
    res = fanout.gather([[1, 2], (3, 4), 5], expected=5)
    assert res.items == [1, 2, 3, 4, 5]
    assert res.duplicates == 0
    assert res.missing == 0
    assert res.complete is True


def test_gather_dedup_across_batches():
    res = fanout.gather([[1, 2], [2, 3], [3]], expected=3)
    assert res.items == [1, 2, 3]
    assert res.duplicates == 2  # repeated 2 and 3
    assert res.complete is True


def test_gather_with_custom_key_dedups_on_field():
    rows = [
        {"id": "a", "v": 1},
        {"id": "b", "v": 2},
        {"id": "a", "v": 99},  # duplicate id, different payload
        {"id": "c", "v": 3},
    ]
    res = fanout.gather(rows, expected=4, key=lambda r: r["id"])
    # 3 unique ids, first-seen wins for the "a" payload
    assert [r["id"] for r in res.items] == ["a", "b", "c"]
    assert res.items[0]["v"] == 1
    assert res.duplicates == 1
    assert res.missing == 1  # expected 4 distinct, only 3 unique
    assert res.complete is False


def test_gather_empty_results_all_missing():
    res = fanout.gather([], expected=5)
    assert res.items == []
    assert res.missing == 5
    assert res.duplicates == 0
    assert res.complete is False


def test_gather_overproduction_is_complete_with_no_missing():
    # produced more unique than expected -> missing clamps to 0, complete.
    res = fanout.gather([1, 2, 3, 4, 5], expected=3)
    assert res.missing == 0
    assert res.duplicates == 0
    assert res.complete is True
    assert res.items == [1, 2, 3, 4, 5]


# --------------------------------------------------------------------------
# verify_count — shortfall guard
# --------------------------------------------------------------------------

def test_verify_count_shortfall():
    assert fanout.verify_count(10, list(range(8))) is False


def test_verify_count_satisfied_exact():
    assert fanout.verify_count(8, list(range(8))) is True


def test_verify_count_satisfied_overproduced():
    assert fanout.verify_count(3, list(range(5))) is True


def test_verify_count_zero_expected_always_true():
    assert fanout.verify_count(0, []) is True
