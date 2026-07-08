"""schema_meta fast-path and 052 backfill migration tests (feature 052).

A matching schema_meta revision marker must skip the full _init_db
DDL/migration run (only the marker probe executes, within the 250ms
budget); a missing or stale marker must trigger the full run and restore
the marker. Also covers the promoted tool_overrides per-kind backfill
(_migrate_backfill_tool_kinds_052) semantics and idempotency. Requires a
reachable Postgres; skipped where unreachable.
"""
from __future__ import annotations

import time

import pytest

try:
    import psycopg2  # noqa: F401
    from shared.database import Database, SCHEMA_REVISION
except Exception:  # pragma: no cover - import guard
    Database = None  # type: ignore
    SCHEMA_REVISION = None  # type: ignore


def _db_or_skip():
    """Return a connected Database (marker freshly upserted) or skip."""
    if Database is None:
        pytest.skip("psycopg2/shared.database unavailable")
    try:
        return Database()
    except Exception as exc:  # pragma: no cover - no DB in this env
        pytest.skip(f"database unreachable: {exc}")


def test_marker_row_written():
    db = _db_or_skip()
    row = db.fetch_one(
        "SELECT value FROM schema_meta WHERE key = ?", ("revision",)
    )
    assert row is not None and row["value"] == SCHEMA_REVISION


def test_fast_path_skips_full_run(monkeypatch):
    _db_or_skip()

    def fail(self, conn, cursor):
        raise AssertionError("full schema run must be skipped on marker match")

    monkeypatch.setattr(Database, "_apply_full_schema", fail)
    Database()


def test_fast_path_runs_only_marker_statements(monkeypatch):
    _db_or_skip()
    statements = []

    class CountingCursor:
        def __init__(self, cursor):
            self._cursor = cursor

        def execute(self, query, params=None):
            statements.append(query)
            if params is None:
                return self._cursor.execute(query)
            return self._cursor.execute(query, params)

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class CountingConn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self, *args, **kwargs):
            return CountingCursor(self._conn.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._conn, name)

    monkeypatch.setenv("DB_POOL_DISABLE", "1")
    real_borrow = Database._borrow

    def counting_borrow(self):
        conn, pooled = real_borrow(self)
        return CountingConn(conn), pooled

    monkeypatch.setattr(Database, "_borrow", counting_borrow)
    Database()
    assert len(statements) == 2, statements
    assert "schema_meta" in statements[0]
    assert "SELECT value FROM schema_meta" in statements[1]


def test_revision_mismatch_triggers_full_run(monkeypatch):
    db = _db_or_skip()
    db.execute(
        "UPDATE schema_meta SET value = ? WHERE key = ?",
        ("000.000-test-stale", "revision"),
    )
    calls = []
    real_apply = Database._apply_full_schema

    def spy(self, conn, cursor):
        calls.append(1)
        return real_apply(self, conn, cursor)

    monkeypatch.setattr(Database, "_apply_full_schema", spy)
    Database()
    assert calls == [1]
    row = db.fetch_one(
        "SELECT value FROM schema_meta WHERE key = ?", ("revision",)
    )
    assert row["value"] == SCHEMA_REVISION


def test_missing_marker_triggers_full_run(monkeypatch):
    db = _db_or_skip()
    db.execute("DELETE FROM schema_meta WHERE key = ?", ("revision",))
    calls = []
    real_apply = Database._apply_full_schema

    def spy(self, conn, cursor):
        calls.append(1)
        return real_apply(self, conn, cursor)

    monkeypatch.setattr(Database, "_apply_full_schema", spy)
    Database()
    assert calls == [1]
    row = db.fetch_one(
        "SELECT value FROM schema_meta WHERE key = ?", ("revision",)
    )
    assert row["value"] == SCHEMA_REVISION


def test_fast_path_within_budget():
    _db_or_skip()
    durations = []
    for _ in range(3):
        start = time.perf_counter()
        Database()
        durations.append(time.perf_counter() - start)
    assert min(durations) <= 0.25, durations


def _backfill_cleanup(db, user_id):
    db.execute("DELETE FROM tool_overrides WHERE user_id = ?", (user_id,))


def test_backfill_tool_kinds_052_semantics_and_idempotency():
    db = _db_or_skip()
    user, agent, tool = "u-test-052-backfill", "agent-test-052", "tool_x"
    _backfill_cleanup(db, user)
    try:
        db.execute(
            "INSERT INTO tool_overrides "
            "(user_id, agent_id, tool_name, permission_kind, enabled, updated_at) "
            "VALUES (?, ?, ?, NULL, ?, ?)",
            (user, agent, tool, False, 1),
        )
        db.execute(
            "INSERT INTO tool_overrides "
            "(user_id, agent_id, tool_name, permission_kind, enabled, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user, agent, tool, "tools:read", True, 1),
        )
        db.execute(
            "INSERT INTO tool_overrides "
            "(user_id, agent_id, tool_name, permission_kind, enabled, updated_at) "
            "VALUES (?, ?, ?, NULL, ?, ?)",
            (user, agent, "tool_enabled_legacy", True, 1),
        )

        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            db._migrate_backfill_tool_kinds_052(cursor)
            db._migrate_backfill_tool_kinds_052(cursor)
            conn.commit()
        finally:
            conn.close()

        rows = db.fetch_all(
            "SELECT tool_name, permission_kind, enabled FROM tool_overrides "
            "WHERE user_id = ? AND agent_id = ? AND permission_kind IS NOT NULL",
            (user, agent),
        )
        state = {
            (r["tool_name"], r["permission_kind"]): bool(r["enabled"]) for r in rows
        }
        assert state[(tool, "tools:read")] is True
        assert state[(tool, "tools:write")] is False
        assert state[(tool, "tools:search")] is False
        assert state[(tool, "tools:system")] is False
        assert len(state) == 4
        assert not any(name == "tool_enabled_legacy" for name, _kind in state)

        legacy = db.fetch_all(
            "SELECT tool_name FROM tool_overrides "
            "WHERE user_id = ? AND agent_id = ? AND permission_kind IS NULL",
            (user, agent),
        )
        assert {r["tool_name"] for r in legacy} == {tool, "tool_enabled_legacy"}
    finally:
        _backfill_cleanup(db, user)
