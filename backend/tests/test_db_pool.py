"""Connection-pool behavior of shared.database.Database (feature 052).

Covers pool reuse across calls, zero borrowed-connection leakage (success
and error paths), the DB_POOL_DISABLE kill switch, and stale-connection
recovery. Requires a reachable Postgres (the docker-compose dev database);
skipped where unreachable.
"""
from __future__ import annotations

import pytest

try:
    import psycopg2  # noqa: F401
    from shared import database as database_module
    from shared.database import Database
except Exception:  # pragma: no cover - import guard
    Database = None  # type: ignore
    database_module = None  # type: ignore


def _db_or_skip():
    """Return a connected Database or skip the test."""
    if Database is None:
        pytest.skip("psycopg2/shared.database unavailable")
    try:
        return Database()
    except Exception as exc:  # pragma: no cover - no DB in this env
        pytest.skip(f"database unreachable: {exc}")


@pytest.fixture(autouse=True)
def _fresh_pools():
    """Reset shared pool state around every test."""
    if Database is not None:
        Database.close()
    yield
    if Database is not None:
        Database.close()


def _entry(db):
    """Return the shared pool entry for the test database URL."""
    return database_module._POOLS[db.database_url]


def test_pool_reuses_backend_connection():
    db = _db_or_skip()
    pid1 = db.fetch_one("SELECT pg_backend_pid() AS pid")["pid"]
    pid2 = db.fetch_one("SELECT pg_backend_pid() AS pid")["pid"]
    assert pid1 == pid2


def test_no_borrowed_connections_leak_on_success():
    db = _db_or_skip()
    for _ in range(5):
        assert db.fetch_one("SELECT 1 AS x")["x"] == 1
        assert db.fetch_all("SELECT 1 AS x")[0]["x"] == 1
        db.execute("SELECT 1")
    assert len(_entry(db)["pool"]._used) == 0


def test_no_borrowed_connections_leak_on_error():
    db = _db_or_skip()
    for method in (db.fetch_one, db.fetch_all, db.execute):
        with pytest.raises(Exception):
            method("SELECT * FROM definitely_missing_table_052")
    assert len(_entry(db)["pool"]._used) == 0


def test_get_connection_close_returns_to_pool():
    db = _db_or_skip()
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 AS x")
    assert cursor.fetchone()["x"] == 1
    assert len(_entry(db)["pool"]._used) == 1
    conn.close()
    conn.close()
    assert len(_entry(db)["pool"]._used) == 0


def test_kill_switch_restores_connect_per_call(monkeypatch):
    db = _db_or_skip()
    Database.close()
    monkeypatch.setenv("DB_POOL_DISABLE", "1")
    assert db.fetch_one("SELECT 1 AS x")["x"] == 1
    db.execute("SELECT 1")
    conn = db._get_connection()
    conn.close()
    assert db.database_url not in database_module._POOLS


def test_stale_pooled_connection_recovers():
    db = _db_or_skip()
    assert db.fetch_one("SELECT 1 AS x")["x"] == 1
    entry = _entry(db)
    assert entry["pool"]._pool, "expected an idle pooled connection"
    entry["pool"]._pool[-1].close()
    assert db.fetch_one("SELECT 2 AS x")["x"] == 2
    assert len(entry["pool"]._used) == 0


def test_close_classmethod_clears_pools():
    db = _db_or_skip()
    db.fetch_one("SELECT 1 AS x")
    assert db.database_url in database_module._POOLS
    Database.close()
    assert database_module._POOLS == {}
    assert db.fetch_one("SELECT 3 AS x")["x"] == 3
