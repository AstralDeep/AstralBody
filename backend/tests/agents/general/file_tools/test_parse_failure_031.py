"""Feature 031 (T023a) — FR-010 / FR-011 parse-failure & vision routing.

These are existing reader behaviors that this feature relies on; pinned here so
the attach→parse path's failure handling stays a clear, non-crashing surface.
"""

from __future__ import annotations

from agents.general.file_tools.read_document import read_document
from conftest import _persist, make_pdf_blank


def test_corrupt_document_returns_structured_result_not_exception(repo, upload_root):
    """FR-010: a supported-type file that can't be parsed yields a structured
    result (no raised exception), so the conversation can continue."""
    aid = _persist(repo, user_id="alice", filename="broken.pdf",
                   category="document", extension="pdf",
                   content_type="application/pdf", upload_root=upload_root,
                   payload=b"%PDF-1.4\nnot actually a valid pdf body \x00\x01\x02")
    out = read_document(attachment_id=aid, user_id="alice")
    # Never raises; always a dict. Either a clear error, or an empty/vision
    # result — but never a silent crash.
    assert isinstance(out, dict)
    assert ("error" in out) or ("text" in out) or ("vision_required" in out)


def test_foreign_owner_is_denied_with_structured_error(repo, upload_root):
    """FR-007 + FR-010: reading another user's attachment returns a structured
    error, not data and not an exception."""
    aid = _persist(repo, user_id="alice", filename="hers.pdf",
                   category="document", extension="pdf",
                   content_type="application/pdf", upload_root=upload_root,
                   payload=b"%PDF-1.4\n...")
    out = read_document(attachment_id=aid, user_id="mallory")
    assert isinstance(out, dict)
    assert "error" in out


def test_no_text_document_routes_to_vision(repo, upload_root, monkeypatch):
    """FR-011: a document with no extractable text routes to the visual path
    (page images) instead of silently returning empty content."""
    from agents.general.file_tools import read_document as rd
    monkeypatch.setattr(rd, "pdf_to_vision_images",
                        lambda _p: [{"content_type": "image/png", "image_base64": "ZmFrZQ=="}])
    aid = _persist(repo, user_id="alice", filename="blank.pdf",
                   category="document", extension="pdf",
                   content_type="application/pdf", upload_root=upload_root,
                   payload=make_pdf_blank())
    out = read_document(attachment_id=aid, user_id="alice")
    assert "error" not in out
    assert out["vision_required"] is True
    assert out["text"] == ""
    assert len(out["images"]) == 1
