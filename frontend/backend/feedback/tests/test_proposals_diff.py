"""Tests for the proposals diff apply helper.

Round-trip: a diff produced by ``_make_unified_diff`` must always apply
cleanly to its source via ``_apply_unified_diff``. File-creation diffs
(empty source) must work as well.
"""
from __future__ import annotations

import pytest

from feedback.proposals import _apply_unified_diff, _make_unified_diff


def _roundtrip(old: str, new: str):
    diff = _make_unified_diff(old, new, "x.md")
    return _apply_unified_diff(old, diff)


def test_creation_from_empty_source():
    new = "Hello world\nSecond line\n"
    assert _roundtrip("", new) == new


def test_addition_at_end():
    old = "alpha\nbeta\n"
    new = "alpha\nbeta\ngamma\n"
    assert _roundtrip(old, new) == new


def test_insertion_in_middle():
    old = "a\nc\n"
    new = "a\nb\nc\n"
    assert _roundtrip(old, new) == new


def test_replacement_in_middle():
    old = "a\nold\nz\n"
    new = "a\nnew\nz\n"
    assert _roundtrip(old, new) == new


def test_deletion():
    old = "a\nb\nc\n"
    new = "a\nc\n"
    assert _roundtrip(old, new) == new


def test_no_op_diff_is_idempotent():
    old = "alpha\nbeta\n"
    diff = _make_unified_diff(old, old, "x.md")
    # Empty-or-near-empty diff applied to old yields old
    assert _apply_unified_diff(old, diff) == old


def test_malformed_diff_raises():
    with pytest.raises(ValueError):
        _apply_unified_diff("a\n", "@@ this is not a real header @@\n+x\n")
