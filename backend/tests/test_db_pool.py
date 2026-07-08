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


_FAKE_URL = "postgresql://fake:fake@127.0.0.1:1/edge-cases"


def _bare_db():
    """A Database whose __init__ (schema run) is skipped — edge-branch rig."""
    if Database is None:
        pytest.skip("psycopg2/shared.database unavailable")
    db = Database.__new__(Database)
    db.database_url = _FAKE_URL
    return db


class _FakeSem:
    """Semaphore stub with scripted acquire/release behavior."""

    def __init__(self, acquire_result=True, release_error=None):
        self.acquire_result = acquire_result
        self.release_error = release_error
        self.released = 0

    def acquire(self, timeout=None):
        return self.acquire_result

    def release(self):
        if self.release_error is not None:
            raise self.release_error
        self.released += 1


class _FakePool:
    """Pool stub with scripted getconn/putconn/closeall behavior."""

    def __init__(self, getconn_error=None, putconn_error=None,
                 closeall_error=None):
        self.getconn_error = getconn_error
        self.putconn_error = putconn_error
        self.closeall_error = closeall_error

    def getconn(self):
        if self.getconn_error is not None:
            raise self.getconn_error
        return object()

    def putconn(self, conn, key=None, close=False):
        if self.putconn_error is not None:
            raise self.putconn_error

    def closeall(self):
        if self.closeall_error is not None:
            raise self.closeall_error


class _FakeConn:
    """Connection stub that can refuse to close and hand out fake cursors."""

    def __init__(self, close_error=None, cursor_factory=None):
        self.close_error = close_error
        self.cursor_factory = cursor_factory
        self.closed = False
        self.committed = False

    def close(self):
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def cursor(self):
        return self.cursor_factory()

    def commit(self):
        self.committed = True


def test_close_all_pools_swallows_closeall_errors():
    if database_module is None:
        pytest.skip("shared.database unavailable")
    database_module._POOLS[_FAKE_URL] = {
        "pool": _FakePool(closeall_error=RuntimeError("boom")),
        "sem": _FakeSem(),
    }
    database_module._close_all_pools()
    assert database_module._POOLS == {}


def test_proxy_del_swallows_release_errors():
    if database_module is None:
        pytest.skip("shared.database unavailable")

    def _raise(conn):
        raise RuntimeError("release failed")

    proxy = database_module._PooledConnectionProxy(object(), _raise)
    proxy.__del__()
    assert proxy._released is True


def test_borrow_raises_operational_error_when_pool_exhausted():
    db = _bare_db()
    database_module._POOLS[_FAKE_URL] = {
        "pool": _FakePool(), "sem": _FakeSem(acquire_result=False)}
    try:
        with pytest.raises(psycopg2.OperationalError, match="exhausted"):
            db._borrow()
    finally:
        database_module._POOLS.pop(_FAKE_URL, None)


def test_borrow_releases_semaphore_when_getconn_fails():
    db = _bare_db()
    sem = _FakeSem()
    database_module._POOLS[_FAKE_URL] = {
        "pool": _FakePool(getconn_error=RuntimeError("no conn")), "sem": sem}
    try:
        with pytest.raises(RuntimeError, match="no conn"):
            db._borrow()
        assert sem.released == 1
    finally:
        database_module._POOLS.pop(_FAKE_URL, None)


def test_borrow_hands_out_pooled_connection():
    db = _bare_db()
    sem = _FakeSem()
    database_module._POOLS[_FAKE_URL] = {"pool": _FakePool(), "sem": sem}
    try:
        conn, pooled = db._borrow()
        assert pooled is True and conn is not None
    finally:
        database_module._POOLS.pop(_FAKE_URL, None)


def test_build_database_url_normalizes_localhost(monkeypatch):
    if database_module is None:
        pytest.skip("shared.database unavailable")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "normtest")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    assert database_module._build_database_url() == (
        "postgresql://u:p@127.0.0.1:5433/normtest")
    monkeypatch.setenv("DB_HOST", "db.internal")
    assert "@db.internal:" in database_module._build_database_url()


def test_release_nonpooled_swallows_close_error():
    db = _bare_db()
    db._release(_FakeConn(close_error=RuntimeError("already closed")), False)


def test_release_without_pool_entry_closes_connection():
    db = _bare_db()
    conn = _FakeConn()
    db._release(conn, True)
    assert conn.closed is True


def test_release_putconn_failure_falls_back_to_close():
    db = _bare_db()
    database_module._POOLS[_FAKE_URL] = {
        "pool": _FakePool(putconn_error=RuntimeError("pool broken")),
        "sem": _FakeSem(release_error=ValueError("over-released")),
    }
    try:
        db._release(_FakeConn(close_error=RuntimeError("nope")), True)
    finally:
        database_module._POOLS.pop(_FAKE_URL, None)


def test_run_with_retry_never_retries_nonpooled(monkeypatch):
    db = _bare_db()
    conn = _FakeConn()
    monkeypatch.setattr(db, "_borrow", lambda: (conn, False))
    calls = []

    def _op(c):
        calls.append(c)
        raise psycopg2.OperationalError("stale")

    with pytest.raises(psycopg2.OperationalError):
        db._run_with_retry(_op)
    assert len(calls) == 1
    assert conn.closed is True


def test_execute_reraises_stale_error_then_retries(monkeypatch):
    db = _bare_db()

    class _StaleCursor:
        def execute(self, query, params):
            raise psycopg2.OperationalError("server closed the connection")

    class _GoodCursor:
        rowcount = 1

        def execute(self, query, params):
            self.query = query

    stale = _FakeConn(cursor_factory=_StaleCursor)
    good = _FakeConn(cursor_factory=_GoodCursor)
    borrows = iter([(stale, True), (good, True)])
    releases = []
    monkeypatch.setattr(db, "_borrow", lambda: next(borrows))
    monkeypatch.setattr(
        db, "_release",
        lambda conn, pooled, discard=False: releases.append((conn, discard)))

    cursor = db.execute("SELECT 1")
    assert cursor.rowcount == 1
    assert good.committed is True
    assert releases[0] == (stale, True)
    assert releases[1] == (good, False)
