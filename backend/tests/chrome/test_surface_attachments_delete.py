"""Feature 031 US3 — attachment deletion via the library surface (T044).

Deleting removes the attachment from the list and makes it unreferenceable;
a non-owner delete is refused. Covers FR-022.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
_TESTS = os.path.join(_BACKEND, "tests")
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

from attachments.conftest import StubDatabase  # noqa: E402
from orchestrator.attachments.repository import AttachmentRepository  # noqa: E402
from webrender.chrome.surfaces import attachments as surface  # noqa: E402


def _seed(repo, *, user_id, attachment_id):
    repo.insert(attachment_id=attachment_id, user_id=user_id,
                filename=f"{attachment_id}.pdf", content_type="application/pdf",
                category="document", extension="pdf", size_bytes=10, sha256="0" * 64,
                storage_path=f"{user_id}/{attachment_id}/{attachment_id}.pdf")


def _orch(db):
    return types.SimpleNamespace(history=types.SimpleNamespace(db=db))


@pytest.mark.asyncio
async def test_delete_removes_attachment_and_unreferenceable():
    db = StubDatabase()
    repo = AttachmentRepository(db)
    _seed(repo, user_id="u1", attachment_id="a1")
    orch = _orch(db)

    result = await surface._h_attachment_delete(orch, object(), "u1", [], {"attachment_id": "a1"})
    assert result[0] == "attachments"  # re-render the surface
    # Gone from the owner's view, and no longer resolvable.
    assert repo.get_by_id("a1", "u1") is None
    html = await surface.render(orch, "u1", [], {})
    assert "a1.pdf" not in html


@pytest.mark.asyncio
async def test_delete_foreign_attachment_is_refused():
    db = StubDatabase()
    repo = AttachmentRepository(db)
    _seed(repo, user_id="owner", attachment_id="a1")
    orch = _orch(db)
    # A different user cannot delete it.
    result = await surface._h_attachment_delete(orch, object(), "mallory", [], {"attachment_id": "a1"})
    assert result[0] == "attachments"
    assert "not found" in result[2].lower()
    # Still present for the real owner.
    assert repo.get_by_id("a1", "owner") is not None


@pytest.mark.asyncio
async def test_delete_missing_id_is_handled():
    db = StubDatabase()
    orch = _orch(db)
    result = await surface._h_attachment_delete(orch, object(), "u1", [], {})
    assert result[0] == "attachments"
    assert "no attachment" in result[2].lower()
