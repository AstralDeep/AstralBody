"""Shared fixtures for attachments tests.

Putting `backend/` on sys.path mirrors the pattern in `backend/tests/test_backend.py`
so module imports like `from orchestrator.attachments import store` resolve.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import pytest

# Ensure backend/ is on sys.path
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ---------------------------------------------------------------------------
# Filesystem fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def upload_root(tmp_path: Path) -> Path:
    """Isolated upload root for store tests."""
    return tmp_path / "uploads"


# ---------------------------------------------------------------------------
# In-memory DB stub
# ---------------------------------------------------------------------------
#
# The production Database is PostgreSQL-only. For unit-level repository tests
# we stub the four methods the repository actually uses (`execute`, `fetch_one`,
# `fetch_all`, plus the `_translate_query` no-op) with a tiny in-memory store.
# This keeps the repository test free of a real DB while still exercising every
# branch of the SQL-shaped logic.

class _StubCursor:
    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount


class StubDatabase:
    """In-memory stand-in for backend.shared.database.Database."""

    def __init__(self) -> None:
        # Single-table model: list of dicts.
        self.rows: List[dict] = []

    def execute(self, query: str, params: Tuple = ()) -> _StubCursor:
        q = query.strip().lower()
        if q.startswith("insert into user_attachments"):
            (
                attachment_id, user_id, filename, content_type, category,
                extension, size_bytes, sha256, storage_path, created_at,
            ) = params
            self.rows.append({
                "attachment_id": attachment_id,
                "user_id": user_id,
                "filename": filename,
                "content_type": content_type,
                "category": category,
                "extension": extension,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "storage_path": storage_path,
                "created_at": created_at,
                "deleted_at": None,
            })
            return _StubCursor(rowcount=1)
        if q.startswith("update user_attachments"):
            # Two shapes: soft_delete (1 id) and soft_delete_all_for_user.
            if "attachment_id = ?" in q:
                deleted_at, attachment_id, user_id = params
                count = 0
                for r in self.rows:
                    if (
                        r["attachment_id"] == attachment_id
                        and r["user_id"] == user_id
                        and r["deleted_at"] is None
                    ):
                        r["deleted_at"] = deleted_at
                        count += 1
                return _StubCursor(rowcount=count)
            else:
                deleted_at, user_id = params
                count = 0
                for r in self.rows:
                    if r["user_id"] == user_id and r["deleted_at"] is None:
                        r["deleted_at"] = deleted_at
                        count += 1
                return _StubCursor(rowcount=count)
        raise NotImplementedError(query)

    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[dict]:
        q = query.strip().lower()
        if "where attachment_id = ?" in q and "and user_id = ?" not in q:
            (attachment_id,) = params
            for r in self.rows:
                if r["attachment_id"] == attachment_id:
                    return dict(r)
            return None
        if "where attachment_id = ? and user_id = ? and deleted_at is null" in q:
            attachment_id, user_id = params
            for r in self.rows:
                if (
                    r["attachment_id"] == attachment_id
                    and r["user_id"] == user_id
                    and r["deleted_at"] is None
                ):
                    return dict(r)
            return None
        raise NotImplementedError(query)

    def fetch_all(self, query: str, params: Tuple = ()) -> List[dict]:
        # Listing query — emulate filtering and ordering well enough to test it.
        q = query.strip().lower()
        if not q.startswith("select * from user_attachments"):
            raise NotImplementedError(query)
        params_list = list(params)
        user_id = params_list.pop(0)
        category = None
        cursor_created_at = None
        cursor_id = None
        if "and category = ?" in q:
            category = params_list.pop(0)
        if "or (created_at = ?" in q:
            cursor_created_at = params_list.pop(0)
            _ = params_list.pop(0)  # repeated
            cursor_id = params_list.pop(0)
        limit = params_list.pop(0)
        rows = [r for r in self.rows
                if r["user_id"] == user_id and r["deleted_at"] is None]
        if category is not None:
            rows = [r for r in rows if r["category"] == category]
        if cursor_created_at is not None:
            rows = [
                r for r in rows
                if (r["created_at"] < cursor_created_at) or (
                    r["created_at"] == cursor_created_at
                    and r["attachment_id"] < cursor_id
                )
            ]
        rows.sort(key=lambda r: (-r["created_at"], r["attachment_id"]), reverse=False)
        # Match the SQL "ORDER BY created_at DESC, attachment_id DESC".
        rows = sorted(rows, key=lambda r: (r["created_at"], r["attachment_id"]), reverse=True)
        return [dict(r) for r in rows[:limit]]


@pytest.fixture
def stub_db() -> StubDatabase:
    return StubDatabase()


# ---------------------------------------------------------------------------
# Helpers used by multiple test files
# ---------------------------------------------------------------------------

def insert_sample(repo, *, user_id: str, category: str = "document",
                  extension: str = "pdf", filename: Optional[str] = None) -> str:
    """Insert a synthetic attachment row and return its id."""
    aid = str(uuid.uuid4())
    repo.insert(
        attachment_id=aid,
        user_id=user_id,
        filename=filename or f"{aid[:8]}.{extension}",
        content_type="application/pdf",
        category=category,
        extension=extension,
        size_bytes=1234,
        sha256="0" * 64,
        storage_path=f"{user_id}/{aid}/{aid[:8]}.{extension}",
    )
    # Spread out timestamps so ordering tests are deterministic.
    time.sleep(0.001)
    return aid
