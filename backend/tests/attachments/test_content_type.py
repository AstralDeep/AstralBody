"""content_type allow-list and consistency checks."""

from __future__ import annotations

import pytest

from orchestrator.attachments import content_type as ct


@pytest.mark.parametrize("name,ext,category", [
    ("Q4-report.PDF", "pdf", "document"),
    ("notes.docx", "docx", "document"),
    ("data.xlsx", "xlsx", "spreadsheet"),
    ("slides.pptx", "pptx", "presentation"),
    ("config.yaml", "yaml", "text"),
    ("script.py", "py", "text"),
    ("photo.JPEG", "jpeg", "image"),
])
def test_extension_and_category(name, ext, category):
    assert ct.normalise_extension(name) == ext
    assert ct.category_for_extension(ext) == category


def test_unknown_extension_returns_none():
    assert ct.category_for_extension("dwg") is None
    assert ct.category_for_extension("") is None


def test_legacy_binary_formats_are_marked():
    assert "doc" in ct.LEGACY_BINARY_FORMATS
    assert "ppt" in ct.LEGACY_BINARY_FORMATS


@pytest.mark.parametrize("ext,mime,ok", [
    ("pdf", "application/pdf", True),
    ("pdf", "application/octet-stream", False),
    ("docx", "application/zip", True),       # docx is a zip
    ("png", "image/png", True),
    ("png", "image/jpeg", False),
    ("py",  "text/x-python", True),
    ("csv", "text/csv", True),
    ("csv", "image/png", False),
])
def test_is_consistent(ext, mime, ok):
    assert ct.is_consistent(ext, mime) is ok


def test_is_consistent_unknown_extension_is_false():
    assert ct.is_consistent("dwg", "application/octet-stream") is False
