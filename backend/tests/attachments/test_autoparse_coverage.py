"""Feature 031 US2 — autoparse coverage_status decisions (T033/T036/T037).

The upload endpoint uses coverage_status to set parser_status and decide whether
to enqueue a background parser draft. Covered/built-in or globally-live → no
draft; pending → dedup (awaiting admin); flag off → unavailable; otherwise
preparing.
"""

from __future__ import annotations

import types

from orchestrator import attachment_autoparse, parser_registry
from orchestrator.attachments.parser_repo import AttachmentParserRepository
from shared.feature_flags import flags
from tests.attachments._fake_db_031 import FakeDB


def _orch(db):
    return types.SimpleNamespace(history=types.SimpleNamespace(db=db))


def test_builtin_covered_type_reports_covered():
    db = FakeDB()
    out = attachment_autoparse.coverage_status(_orch(db), extension="pdf", category="document")
    assert out["status"] == "covered"


def test_uncovered_type_reports_preparing(monkeypatch):
    monkeypatch.setitem(flags._flags, "attachment_autoparse", True)
    db = FakeDB()
    out = attachment_autoparse.coverage_status(_orch(db), extension="parquet", category="data")
    assert out["status"] == "preparing"
    assert out["gap_fingerprint"] == parser_registry.gap_fingerprint("data", "parquet")


def test_pending_registry_row_reports_pending_admin_approval(monkeypatch):
    monkeypatch.setitem(flags._flags, "attachment_autoparse", True)
    db = FakeDB()
    fp = parser_registry.gap_fingerprint("archive", "zip")
    AttachmentParserRepository(db).create_pending(
        gap_fingerprint=fp, category="archive", extension="zip",
        draft_agent_id="d1", source_attachment_id="a1", source_chat_id=None,
        requested_by="u1")
    out = attachment_autoparse.coverage_status(_orch(db), extension="zip", category="archive")
    assert out["status"] == "pending_admin_approval"


def test_live_registry_row_reports_covered(monkeypatch):
    monkeypatch.setitem(flags._flags, "attachment_autoparse", True)
    db = FakeDB()
    fp = parser_registry.gap_fingerprint("data", "avro")
    repo = AttachmentParserRepository(db)
    repo.create_pending(gap_fingerprint=fp, category="data", extension="avro",
                        draft_agent_id="d1", source_attachment_id="a1",
                        source_chat_id=None, requested_by="u1")
    repo.mark_live(fp, live_agent_id="avro-parser-1", tool_name="parse_avro", approved_by="admin")
    out = attachment_autoparse.coverage_status(_orch(db), extension="avro", category="data")
    assert out["status"] == "covered"


def test_flag_off_reports_unavailable(monkeypatch):
    monkeypatch.setitem(flags._flags, "attachment_autoparse", False)
    db = FakeDB()
    out = attachment_autoparse.coverage_status(_orch(db), extension="parquet", category="data")
    assert out["status"] == "unavailable"


def test_failed_registry_row_allows_reattempt(monkeypatch):
    monkeypatch.setitem(flags._flags, "attachment_autoparse", True)
    db = FakeDB()
    fp = parser_registry.gap_fingerprint("data", "orc")
    repo = AttachmentParserRepository(db)
    repo.create_pending(gap_fingerprint=fp, category="data", extension="orc",
                        draft_agent_id="d1", source_attachment_id="a1",
                        source_chat_id=None, requested_by="u1")
    repo.mark_status(fp, "failed")
    out = attachment_autoparse.coverage_status(_orch(db), extension="orc", category="data")
    assert out["status"] == "preparing"  # a later upload may re-attempt


def test_tool_name_is_identifier_safe():
    assert attachment_autoparse._tool_name_for("nii.gz") == "parse_nii_gz"
    assert attachment_autoparse._tool_name_for("7z") == "parse_7z"
    assert attachment_autoparse._tool_name_for(None) == "parse_file"
