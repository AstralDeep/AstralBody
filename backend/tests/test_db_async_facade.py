"""Async facade equivalence tests for shared.database.Database (feature 052).

afetch_one/afetch_all/aexecute must produce results, placeholder
translation, and exceptions identical to their sync twins while executing
off the event loop via asyncio.to_thread. Sync twins are exercised from
sync test code (never on a running loop) so the suite's event-loop guard
stays quiet. Requires a reachable Postgres; skipped where unreachable.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

try:
    import psycopg2  # noqa: F401
    from shared.database import Database
except Exception:  # pragma: no cover - import guard
    Database = None  # type: ignore


def _db_or_skip():
    """Return a connected Database or skip the test."""
    if Database is None:
        pytest.skip("psycopg2/shared.database unavailable")
    try:
        return Database()
    except Exception as exc:  # pragma: no cover - no DB in this env
        pytest.skip(f"database unreachable: {exc}")


def test_afetch_one_matches_fetch_one():
    db = _db_or_skip()
    query = "SELECT 42 AS answer, 'hello' AS greeting"
    assert asyncio.run(db.afetch_one(query)) == db.fetch_one(query)


def test_afetch_all_matches_fetch_all():
    db = _db_or_skip()
    query = "SELECT g AS n FROM generate_series(1, 3) AS g ORDER BY n"
    rows = asyncio.run(db.afetch_all(query))
    assert rows == db.fetch_all(query)
    assert [r["n"] for r in rows] == [1, 2, 3]


def test_aexecute_matches_execute():
    db = _db_or_skip()
    sync_cursor = db.execute("SELECT 1")
    async_cursor = asyncio.run(db.aexecute("SELECT 1"))
    assert async_cursor.rowcount == sync_cursor.rowcount == 1


def test_facade_translates_placeholders_like_sync():
    db = _db_or_skip()
    query = "SELECT ? AS v, '100%' AS pct"
    sync_row = db.fetch_one(query, ("val",))
    async_row = asyncio.run(db.afetch_one(query, ("val",)))
    assert async_row == sync_row
    assert async_row["v"] == "val"
    assert async_row["pct"] == "100%"


def test_facade_raises_identical_exception_types():
    db = _db_or_skip()
    query = "SELECT * FROM missing_table_052_async"
    with pytest.raises(Exception) as sync_exc:
        db.fetch_one(query)
    with pytest.raises(Exception) as afetch_exc:
        asyncio.run(db.afetch_one(query))
    with pytest.raises(Exception) as aexec_exc:
        asyncio.run(db.aexecute(query))
    assert type(afetch_exc.value) is type(sync_exc.value)
    assert type(aexec_exc.value) is type(sync_exc.value)


def test_facade_runs_sync_twin_off_the_loop_thread(monkeypatch):
    db = _db_or_skip()
    seen_threads = []
    real_fetch_one = Database.fetch_one

    def spy(self, query, params=()):
        seen_threads.append(threading.current_thread())
        return real_fetch_one(self, query, params)

    monkeypatch.setattr(Database, "fetch_one", spy)

    async def run():
        return await db.afetch_one("SELECT 7 AS x")

    row = asyncio.run(run())
    assert row["x"] == 7
    assert seen_threads and all(
        t is not threading.main_thread() for t in seen_threads
    )
