"""read_spreadsheet: XLSX, CSV, TSV (XLS/ODS covered structurally)."""

from __future__ import annotations

from agents.general.file_tools.read_spreadsheet import read_spreadsheet
from conftest import _persist, make_csv, make_xlsx


def test_read_xlsx_default_sheet(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="data.xlsx",
                   category="spreadsheet", extension="xlsx",
                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   upload_root=upload_root,
                   payload=make_xlsx([
                       ["patient_id", "age", "diagnosis"],
                       ["P001", 47, "A"],
                       ["P002", 53, "B"],
                   ]))
    out = read_spreadsheet(attachment_id=aid, user_id="alice")
    assert "error" not in out
    assert out["columns"] == ["patient_id", "age", "diagnosis"]
    assert out["rows"][0] == ["P001", 47, "A"]
    assert "Notes" in out["sheet_names"]


def test_read_xlsx_pick_sheet(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="data.xlsx",
                   category="spreadsheet", extension="xlsx",
                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   upload_root=upload_root,
                   payload=make_xlsx([["a", "b"], [1, 2]]))
    out = read_spreadsheet(attachment_id=aid, user_id="alice", sheet_name="Notes")
    assert out["sheet_name"] == "Notes"


def test_read_xlsx_unknown_sheet(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="data.xlsx",
                   category="spreadsheet", extension="xlsx",
                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   upload_root=upload_root,
                   payload=make_xlsx([["a", "b"], [1, 2]]))
    out = read_spreadsheet(attachment_id=aid, user_id="alice", sheet_name="Nope")
    assert out["error"]["code"] == "parse_failed"


def test_read_csv(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="cohort.csv",
                   category="spreadsheet", extension="csv",
                   content_type="text/csv", upload_root=upload_root,
                   payload=make_csv([
                       ["pid", "age"], ["P1", 41], ["P2", 52], ["P3", 33],
                   ]))
    out = read_spreadsheet(attachment_id=aid, user_id="alice")
    assert "error" not in out
    assert out["columns"] == ["pid", "age"]
    assert len(out["rows"]) == 3
    assert out["row_count"] == 3


def test_read_csv_max_rows_truncation(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="big.csv",
                   category="spreadsheet", extension="csv",
                   content_type="text/csv", upload_root=upload_root,
                   payload=make_csv([["a"]] + [[i] for i in range(100)]))
    out = read_spreadsheet(attachment_id=aid, user_id="alice", max_rows=10)
    assert len(out["rows"]) == 10
    assert out["truncated"] is True
    assert out["row_count"] == 100


def test_read_tsv(repo, upload_root):
    payload = b"a\tb\n1\t2\n3\t4\n"
    aid = _persist(repo, user_id="alice", filename="x.tsv",
                   category="spreadsheet", extension="tsv",
                   content_type="text/tab-separated-values", upload_root=upload_root,
                   payload=payload)
    out = read_spreadsheet(attachment_id=aid, user_id="alice")
    assert out["columns"] == ["a", "b"]
    assert out["rows"] == [["1", "2"], ["3", "4"]]
