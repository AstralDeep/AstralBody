"""Tests for the idempotent chat_steps schema delta in shared/database.py.

Feature 014, T012 — verifies Constitution IX:

* The new ``chat_steps`` table exists after ``Database._init_db()`` runs.
* The ``messages.step_count`` column exists after init.
* Calling ``_init_db`` a second time is a no-op (does not raise, does not
  duplicate columns).
* Required indexes exist.
* Foreign-key relationships are wired correctly.
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
        import psycopg2  # noqa: F401
        from shared.database import _build_database_url

        import psycopg2 as _pg
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
    row = db.fetch_one(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = ?",
        (name,),
    )
    return row is not None


def _column_exists(db, table: str, column: str) -> bool:
    row = db.fetch_one(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        (table, column),
    )
    return row is not None


def _index_exists(db, name: str) -> bool:
    row = db.fetch_one(
        "SELECT 1 FROM pg_indexes WHERE indexname = ?",
        (name,),
    )
    return row is not None


class TestSchemaPresent:
    def test_chat_steps_table_exists(self, db):
        assert _table_exists(db, "chat_steps")

    def test_messages_step_count_column_exists(self, db):
        assert _column_exists(db, "messages", "step_count")

    @pytest.mark.parametrize(
        "column",
        [
            "id",
            "chat_id",
            "user_id",
            "turn_message_id",
            "kind",
            "name",
            "status",
            "args_truncated",
            "args_was_truncated",
            "result_summary",
            "result_was_truncated",
            "error_message",
            "started_at",
            "ended_at",
        ],
    )
    def test_chat_steps_has_required_columns(self, db, column):
        assert _column_exists(db, "chat_steps", column)

    def test_required_indexes_exist(self, db):
        assert _index_exists(db, "idx_chat_steps_chat_id")
        assert _index_exists(db, "idx_chat_steps_turn")


class TestIdempotency:
    def test_calling_init_again_is_safe(self, db):
        # Re-running the init should NOT raise and should NOT duplicate the
        # step_count column.
        db._init_db()
        # Postgres would raise on duplicate ALTER TABLE ADD COLUMN; if the
        # init still succeeded, the guard worked.
        assert _column_exists(db, "messages", "step_count")
        # And the chat_steps table is still exactly one entry in
        # information_schema.
        row = db.fetch_one(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'chat_steps'"
        )
        assert row["n"] == 1

    def test_calling_init_three_times_is_safe(self, db):
        db._init_db()
        db._init_db()
        assert _table_exists(db, "chat_steps")
        assert _column_exists(db, "messages", "step_count")


class TestForeignKeys:
    def test_chat_steps_chat_id_fk_cascade(self, db):
        row = db.fetch_one(
            """
            SELECT confdeltype
            FROM pg_constraint
            WHERE conrelid = 'chat_steps'::regclass
              AND confrelid = 'chats'::regclass
            """,
        )
        assert row is not None, "chat_steps has no FK to chats"
        # 'c' = ON DELETE CASCADE
        assert row["confdeltype"] == "c"

    def test_chat_steps_turn_message_id_fk_set_null(self, db):
        row = db.fetch_one(
            """
            SELECT confdeltype
            FROM pg_constraint
            WHERE conrelid = 'chat_steps'::regclass
              AND confrelid = 'messages'::regclass
            """,
        )
        assert row is not None, "chat_steps has no FK to messages"
        # 'n' = ON DELETE SET NULL
        assert row["confdeltype"] == "n"


class TestDefaults:
    def test_step_count_default_is_zero(self, db):
        # Insert a row, read it back; default must be 0.
        from datetime import datetime

        chat_id = f"pytest-{datetime.utcnow().timestamp()}"
        try:
            db.execute(
                "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, "pytest-user", "test", 0, 0),
            )
            db.execute(
                "INSERT INTO messages (chat_id, user_id, role, content, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, "pytest-user", "user", "hi", 0),
            )
            row = db.fetch_one(
                "SELECT step_count FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
                (chat_id,),
            )
            assert row["step_count"] == 0
        finally:
            db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
