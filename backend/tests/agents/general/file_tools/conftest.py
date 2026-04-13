"""Fixtures for file_tools tests.

We deliberately *generate* test artifacts at runtime (PDFs via reportlab,
DOCX via python-docx, etc.) so the repo doesn't carry binary fixtures and
tests stay deterministic.
"""

from __future__ import annotations

import io
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Tuple

import pytest

# Make `from orchestrator.X import Y` resolve.
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Make the backend/tests/attachments StubDatabase reusable here.
sys.path.insert(0, os.path.abspath(os.path.join(_BACKEND, "tests")))

from attachments.conftest import StubDatabase  # noqa: E402

from orchestrator.attachments import store  # noqa: E402
from orchestrator.attachments.repository import AttachmentRepository  # noqa: E402
from agents.general.file_tools import set_database_for_testing  # noqa: E402


@pytest.fixture
def upload_root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("ATTACHMENT_UPLOAD_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def stub_db():
    db = StubDatabase()
    set_database_for_testing(db)
    yield db
    set_database_for_testing(None)


@pytest.fixture
def repo(stub_db) -> AttachmentRepository:
    return AttachmentRepository(stub_db)


def _persist(repo: AttachmentRepository, *, user_id: str, filename: str,
             category: str, extension: str, content_type: str,
             upload_root: Path, payload: bytes) -> str:
    """Write *payload* to disk under the canonical layout, insert a row, return id."""
    aid = str(uuid.uuid4())
    path, size, sha = store.write(
        user_id=user_id, attachment_id=aid, filename=filename,
        chunks=iter([payload]), max_bytes=10 * 1024 * 1024, root=upload_root,
    )
    repo.insert(
        attachment_id=aid, user_id=user_id, filename=filename,
        content_type=content_type, category=category, extension=extension,
        size_bytes=size, sha256=sha,
        storage_path=str(path.relative_to(upload_root)),
    )
    return aid


# ---------------------------------------------------------------------------
# Fixture builders for each file type
# ---------------------------------------------------------------------------


def make_pdf_with_text(text: str = "Hello PDF world") -> bytes:
    """Build a tiny PDF whose first page contains *text*."""
    from reportlab.pdfgen import canvas  # type: ignore

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def make_pdf_blank() -> bytes:
    """Build a PDF with no extractable text (single blank page)."""
    from reportlab.pdfgen import canvas  # type: ignore

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    return buf.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    import docx  # python-docx

    doc = docx.Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_xlsx(rows: list[list[object]]) -> bytes:
    import openpyxl  # type: ignore

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)
    wb.create_sheet("Notes").append(["only", "for", "presence"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_pptx(slides: list[tuple[str, str]]) -> bytes:
    from pptx import Presentation  # type: ignore

    prs = Presentation()
    blank_layout = prs.slide_layouts[5]
    title_layout = prs.slide_layouts[0]
    for title, body in slides:
        slide = prs.slides.add_slide(title_layout)
        slide.shapes.title.text = title
        if body:
            slide.placeholders[1].text = body
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def make_png(width: int = 32, height: int = 32) -> bytes:
    from PIL import Image  # type: ignore

    img = Image.new("RGB", (width, height), color=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_rtf(text: str) -> bytes:
    body = (
        r"{\rtf1\ansi\deff0 {\fonttbl{\f0 Courier;}}"
        + text.replace("\n", r"\par ")
        + "}"
    )
    return body.encode("ascii")


def make_odt(text: str) -> bytes:
    from odf.opendocument import OpenDocumentText  # type: ignore
    from odf import text as odftext  # type: ignore

    doc = OpenDocumentText()
    p = odftext.P(text=text)
    doc.text.addElement(p)
    buf = io.BytesIO()
    doc.write(buf)
    return buf.getvalue()


def make_csv(rows: list[list[object]]) -> bytes:
    import csv

    out = io.StringIO()
    w = csv.writer(out)
    for r in rows:
        w.writerow(r)
    return out.getvalue().encode()
