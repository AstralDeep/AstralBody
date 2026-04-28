"""Verify the feature-005 tables and indices are created by ``Database._init_db``."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def conn(database):
    c = database._get_connection()
    yield c
    c.close()


def _table_exists(conn, name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (name,),
    )
    return cur.fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def _index_exists(conn, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (name,))
    return cur.fetchone() is not None


def test_tables_exist(conn):
    assert _table_exists(conn, "onboarding_state")
    assert _table_exists(conn, "tutorial_step")
    assert _table_exists(conn, "tutorial_step_revision")


def test_onboarding_state_columns(conn):
    for col in (
        "user_id", "status", "last_step_id", "started_at",
        "updated_at", "completed_at", "skipped_at",
    ):
        assert _column_exists(conn, "onboarding_state", col), col


def test_tutorial_step_columns(conn):
    for col in (
        "id", "slug", "audience", "display_order", "target_kind", "target_key",
        "title", "body", "created_at", "updated_at", "archived_at",
    ):
        assert _column_exists(conn, "tutorial_step", col), col


def test_tutorial_step_revision_columns(conn):
    for col in (
        "id", "step_id", "editor_user_id", "edited_at",
        "previous", "current", "change_kind",
    ):
        assert _column_exists(conn, "tutorial_step_revision", col), col


def test_indexes_exist(conn):
    assert _index_exists(conn, "idx_tutorial_step_user_view")
    assert _index_exists(conn, "idx_tutorial_step_revision_step_time")
    assert _index_exists(conn, "idx_tutorial_step_revision_editor")


def test_init_db_idempotent(database):
    """Calling _init_db a second time must not raise."""
    database._init_db()  # idempotent re-run


def test_status_check_constraint(conn):
    cur = conn.cursor()
    try:
        try:
            cur.execute(
                "INSERT INTO onboarding_state (user_id, status) VALUES (%s, %s)",
                ("pytest-bad-status", "totally_invalid"),
            )
        finally:
            conn.rollback()
    except Exception:
        # The cursor.execute raises on the CHECK violation; rollback already done.
        pass
    else:
        pytest.fail("expected status CHECK constraint to reject invalid value")


def test_target_consistency_constraint(conn):
    cur = conn.cursor()
    # target_kind='none' with non-null target_key must be rejected
    try:
        try:
            cur.execute(
                """
                INSERT INTO tutorial_step (slug, audience, display_order, target_kind, target_key, title, body)
                VALUES ('pytest-bad-target', 'user', 999, 'none', 'should-not-have-key', 'T', 'B')
                """
            )
        finally:
            conn.rollback()
    except Exception:
        pass
    else:
        pytest.fail("expected target_kind='none' with target_key to be rejected")
