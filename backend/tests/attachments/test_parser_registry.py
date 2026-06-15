"""Feature 031 — parser coverage map (parser_registry).

Covers the "is this type parseable today?" decision: built-in coverage for the
feature-002 categories, global coverage via a live attachment_parser row, and
uncovered for the data/archive categories that drive auto-creation (US2).
"""

from __future__ import annotations

from orchestrator import parser_registry as pr


class _FakeParserRepo:
    """Minimal stand-in exposing get_by_gap for global-coverage tests."""

    def __init__(self, rows_by_gap):
        self._rows = dict(rows_by_gap)

    def get_by_gap(self, gap):
        return self._rows.get(gap)


def test_builtin_coverage_for_feature002_categories():
    for cat, tool in [
        ("document", "read_document"),
        ("spreadsheet", "read_spreadsheet"),
        ("presentation", "read_presentation"),
        ("text", "read_text"),
        ("image", "read_image"),
    ]:
        cov = pr.coverage("anything", cat)
        assert cov == {"covered": True, "tool": tool, "source": "builtin"}


def test_medical_is_covered_builtin():
    assert pr.is_covered("dcm", "medical") is True


def test_data_and_archive_are_uncovered_without_global_parser():
    assert pr.is_covered("parquet", "data") is False
    assert pr.is_covered("zip", "archive") is False
    assert pr.covering_tool("parquet", "data") is None


def test_gap_fingerprint_is_stable_and_format_scoped():
    fp1 = pr.gap_fingerprint("data", "parquet")
    fp2 = pr.gap_fingerprint("data", "parquet")
    assert fp1 == fp2 and len(fp1) == 32
    # Different extension/category → different fingerprint.
    assert pr.gap_fingerprint("data", "avro") != fp1
    assert pr.gap_fingerprint("archive", "parquet") != fp1
    # Case/whitespace-insensitive.
    assert pr.gap_fingerprint("DATA", " parquet ") == fp1


def test_global_live_parser_provides_coverage():
    fp = pr.gap_fingerprint("data", "parquet")
    repo = _FakeParserRepo({fp: {"status": "live", "tool_name": "parse_parquet"}})
    cov = pr.coverage("parquet", "data", parser_repo=repo)
    assert cov == {"covered": True, "tool": "parse_parquet", "source": "global"}
    assert pr.covering_tool("parquet", "data", parser_repo=repo) == "parse_parquet"


def test_pending_or_failed_global_row_is_not_coverage():
    fp = pr.gap_fingerprint("archive", "zip")
    for status in ("pending", "failed", "discarded"):
        repo = _FakeParserRepo({fp: {"status": status, "tool_name": "parse_zip"}})
        assert pr.is_covered("zip", "archive", parser_repo=repo) is False
