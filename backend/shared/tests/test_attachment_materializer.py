"""Tests for shared.attachment_materializer.materialize_text_attachment.

Follows the conventions of ``test_attachment_resolver.py``: the DB layer is
mocked (``_open_db`` + ``AttachmentRepository``); the blob store writes to a
real ``tmp_path`` via the ``ATTACHMENT_UPLOAD_ROOT`` override so the on-disk
layout (``{root}/{user}/{attachment_id}/{filename}``) is exercised for real.
"""
import hashlib
from unittest.mock import MagicMock, patch

import pytest

from shared.attachment_materializer import (
    MAX_INLINE_BYTES,
    materialize_text_attachment,
    strip_code_fences,
)


CSV_TEXT = "Week,Enrollment\n1,40\n2,42\n3,45\n"


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    """Point the attachments store at a throwaway root."""
    monkeypatch.setenv("ATTACHMENT_UPLOAD_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_repo():
    """Patch the repository + DB so no Postgres is needed."""
    repo = MagicMock()
    with patch("orchestrator.attachments.repository.AttachmentRepository", return_value=repo), \
         patch("shared.attachment_materializer._open_db", return_value=MagicMock()):
        yield repo


# ---------------------------------------------------------------------------
# strip_code_fences
# ---------------------------------------------------------------------------


def test_strip_fences_csv_info_string() -> None:
    assert strip_code_fences(f"```csv\n{CSV_TEXT}```") == CSV_TEXT.strip()


def test_strip_fences_bare() -> None:
    assert strip_code_fences(f"```\n{CSV_TEXT}\n```") == CSV_TEXT.strip()


def test_strip_fences_other_info_string() -> None:
    """Any info string (```text, ```data, …) is tolerated, not just ```csv."""
    assert strip_code_fences(f"```text\n{CSV_TEXT}\n```") == CSV_TEXT.strip()


def test_strip_fences_passthrough_when_unfenced() -> None:
    assert strip_code_fences(f"  {CSV_TEXT}  ") == CSV_TEXT.strip()


def test_strip_fences_single_line_fence_yields_empty() -> None:
    assert strip_code_fences("```csv") == ""
    assert strip_code_fences("") == ""
    assert strip_code_fences(None) == ""


# ---------------------------------------------------------------------------
# materialize_text_attachment — validation failures
# ---------------------------------------------------------------------------


def test_requires_user_id() -> None:
    with pytest.raises(ValueError, match="user_id is required"):
        materialize_text_attachment(CSV_TEXT, "")


def test_empty_text_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        materialize_text_attachment("```\n```", "alice")


def test_header_without_rows_rejected() -> None:
    with pytest.raises(ValueError, match="no data rows"):
        materialize_text_attachment("Week,Enrollment\n", "alice")


def test_unparseable_csv_rejected() -> None:
    """A field over csv.field_size_limit() makes the stdlib csv reader
    raise csv.Error (still under the 1 MB cap, so the size gate passes)."""
    import csv as _csv
    huge_field = "x" * (_csv.field_size_limit() + 1)
    with pytest.raises(ValueError, match="not valid CSV"):
        materialize_text_attachment(f"Week,Notes\n1,{huge_field}\n", "alice")


def test_over_1mb_rejected() -> None:
    big = "a,b\n" + ("1,2\n" * ((MAX_INLINE_BYTES // 4) + 1))
    with pytest.raises(ValueError, match="inline limit"):
        materialize_text_attachment(big, "alice")


def test_unsupported_extension_rejected(upload_root, fake_repo) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        materialize_text_attachment("anything at all", "alice", extension="exe")


def test_validate_csv_missing_header_rejected() -> None:
    from shared.attachment_materializer import _validate_csv
    with pytest.raises(ValueError, match="no header row"):
        _validate_csv("")


def test_attachments_subsystem_unavailable_surfaces_value_error() -> None:
    """If the orchestrator attachments package can't import (broken sidecar
    deployment), the caller gets an actionable ValueError, not ImportError."""
    import sys
    with patch.dict(sys.modules, {"orchestrator.attachments": None}):
        with pytest.raises(ValueError, match="Attachments subsystem unavailable"):
            materialize_text_attachment(CSV_TEXT, "alice")


def test_db_open_failure_surfaces_value_error(upload_root) -> None:
    with patch("shared.attachment_materializer._open_db", side_effect=RuntimeError("no pg")):
        with pytest.raises(ValueError, match="Could not open attachments database"):
            materialize_text_attachment(CSV_TEXT, "alice")


def test_open_db_constructs_and_caches(monkeypatch) -> None:
    """_open_db builds one Database per process and caches it (same pattern
    as shared.attachment_resolver)."""
    import shared.attachment_materializer as mat
    import shared.database as shared_database
    sentinel = MagicMock()
    monkeypatch.setattr(mat, "_MATERIALIZER_DB", None)
    monkeypatch.setattr(shared_database, "Database", MagicMock(return_value=sentinel))
    try:
        assert mat._open_db() is sentinel
        assert mat._open_db() is sentinel  # cached: constructor called once
        shared_database.Database.assert_called_once()
    finally:
        mat._MATERIALIZER_DB = None


# ---------------------------------------------------------------------------
# materialize_text_attachment — happy paths
# ---------------------------------------------------------------------------


def test_happy_path_writes_blob_and_inserts_row(upload_root, fake_repo) -> None:
    attachment_id = materialize_text_attachment(f"```csv\n{CSV_TEXT}```", "alice")

    fake_repo.insert.assert_called_once()
    kwargs = fake_repo.insert.call_args.kwargs
    assert kwargs["attachment_id"] == attachment_id
    assert kwargs["user_id"] == "alice"
    assert kwargs["extension"] == "csv"
    assert kwargs["category"] == "spreadsheet"
    assert kwargs["content_type"] == "text/csv"
    expected_bytes = CSV_TEXT.strip().encode("utf-8")
    assert kwargs["size_bytes"] == len(expected_bytes)
    assert kwargs["sha256"] == hashlib.sha256(expected_bytes).hexdigest()

    # Blob exists under the canonical layout and matches the fence-stripped text.
    blob = upload_root / kwargs["storage_path"]
    assert blob.read_text(encoding="utf-8") == CSV_TEXT.strip()
    # storage_path is RELATIVE to the upload root (resolver joins it back).
    assert kwargs["storage_path"] == f"alice/{attachment_id}/{kwargs['filename']}"


def test_returned_id_resolves_via_attachment_resolver(upload_root, fake_repo) -> None:
    """End-to-end with the resolver: the row the materializer inserts is
    exactly what resolve_attachment_path needs to find the blob again."""
    from shared.attachment_resolver import resolve_attachment_path

    attachment_id = materialize_text_attachment(CSV_TEXT, "alice")
    storage_path = fake_repo.insert.call_args.kwargs["storage_path"]
    fake_repo.get_by_id.return_value = MagicMock(storage_path=storage_path)
    with patch("orchestrator.attachments.repository.AttachmentRepository", return_value=fake_repo), \
         patch("shared.attachment_resolver._open_db", return_value=MagicMock()):
        path = resolve_attachment_path(attachment_id, "alice")
    fake_repo.get_by_id.assert_called_with(attachment_id, "alice")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == CSV_TEXT.strip()


def test_non_csv_extension_skips_csv_validation(upload_root, fake_repo) -> None:
    attachment_id = materialize_text_attachment("just some prose", "alice", extension="txt")
    kwargs = fake_repo.insert.call_args.kwargs
    assert kwargs["attachment_id"] == attachment_id
    assert kwargs["extension"] == "txt"
    assert kwargs["category"] == "text"
    assert kwargs["content_type"] == "text/plain"


def test_db_insert_failure_rolls_back_blob(upload_root, fake_repo) -> None:
    fake_repo.insert.side_effect = RuntimeError("db down")
    with pytest.raises(ValueError, match="Could not record"):
        materialize_text_attachment(CSV_TEXT, "alice")
    # Mirror of the upload router: no orphaned blob directory is left behind.
    user_dir = upload_root / "alice"
    assert not user_dir.exists() or not any(user_dir.iterdir())
