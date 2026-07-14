"""Feature 055 — idempotent schema deltas (Constitution IX).

component_version (US4 refine/restore history), share_grant (US5 snapshot
share links), and background_task (bg-continuity durable task records) are
additive, guarded, inert while their flags are off, and safe to re-run.
Rollback: DROP TABLE IF EXISTS component_version / share_grant /
background_task (documented in specs/055-uniform-artifacts/data-model.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _can_connect_to_db() -> bool:
    try:
        import psycopg2 as _pg
        from shared.database import _build_database_url
        conn = _pg.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="Postgres unavailable in this environment",
)


@pytest.fixture(scope="module")
def db():
    from shared.database import Database
    return Database()


def _table_exists(db, name: str) -> bool:
    return db.fetch_one(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = ?",
        (name,),
    ) is not None


def _column_exists(db, table: str, column: str) -> bool:
    return db.fetch_one(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        (table, column),
    ) is not None


def _index_exists(db, name: str) -> bool:
    return db.fetch_one(
        "SELECT 1 FROM pg_indexes WHERE indexname = ?", (name,)) is not None


def test_schema_revision_bumped():
    from shared.database import SCHEMA_REVISION
    assert SCHEMA_REVISION == "055.002"


def test_component_version_table_and_index(db):
    assert _table_exists(db, "component_version")
    for col in ("chat_id", "user_id", "component_id", "version_no",
                "component", "reason", "created_at"):
        assert _column_exists(db, "component_version", col), col
    assert _index_exists(db, "idx_component_version_lookup")


def test_share_grant_table_and_index(db):
    assert _table_exists(db, "share_grant")
    for col in ("token_sha256", "user_id", "chat_id", "scope", "component_id",
                "snapshot_html", "snapshot_json", "expires_at", "revoked_at",
                "open_count"):
        assert _column_exists(db, "share_grant", col), col
    assert _index_exists(db, "idx_share_grant_owner")


def test_background_task_table_and_index(db):
    assert _table_exists(db, "background_task")
    for col in ("task_id", "user_id", "chat_id", "kind", "status", "title",
                "summary", "created_at", "completed_at", "notified"):
        assert _column_exists(db, "background_task", col), col
    assert _index_exists(db, "idx_background_task_user")


def test_init_db_reruns_idempotently(db):
    db._init_db()  # second run must not raise or duplicate
    assert _table_exists(db, "component_version")
    assert _table_exists(db, "share_grant")
    assert _table_exists(db, "background_task")
