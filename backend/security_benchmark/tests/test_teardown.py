"""Teardown transaction hygiene (spec 047 FR-008).

A failed per-table DELETE must not poison the run's teardown: each successful
table commits on its own, a failure rolls back, and later tables still purge —
``deleted`` counts only committed work. Modeled on psycopg2 semantics where a
failed statement aborts the shared transaction (subsequent statements raise
InFailedSqlTransaction until a rollback).
"""
from __future__ import annotations

import pytest

from security_benchmark.isolation import (
    _DELETABLE_USER_TABLES,
    assert_namespaced,
    teardown,
)


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        table = sql.split()[2]
        if self._conn.in_failed_tx:
            raise RuntimeError("InFailedSqlTransaction: transaction is aborted")
        if table in self._conn.fail_tables:
            self._conn.in_failed_tx = True
            raise RuntimeError(f"relation {table} does not exist")
        self.rowcount = self._conn.rowcounts.get(table, 0)
        self._conn.pending.append((table, self.rowcount))


class FakeConn:
    """psycopg2-shaped connection: an aborted tx makes commit() a rollback."""

    def __init__(self, rowcounts, fail_tables=()):
        self.rowcounts = dict(rowcounts)
        self.fail_tables = set(fail_tables)
        self.in_failed_tx = False
        self.pending = []           # uncommitted (table, rowcount) work
        self.committed = []         # committed (table, rowcount) work
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        if not self.in_failed_tx:
            self.committed.extend(self.pending)
        self.pending = []
        self.in_failed_tx = False

    def rollback(self):
        self.pending = []
        self.in_failed_tx = False
        self.rollbacks += 1


def test_teardown_counts_and_commits_every_table_when_clean():
    conn = FakeConn(rowcounts={t: 2 for t in _DELETABLE_USER_TABLES})
    deleted = teardown(conn, "run-1")
    assert deleted == 2 * len(_DELETABLE_USER_TABLES)
    assert [t for t, _ in conn.committed] == list(_DELETABLE_USER_TABLES)
    assert conn.pending == []


def test_failed_table_rolls_back_and_later_tables_still_purge():
    fail = _DELETABLE_USER_TABLES[2]  # a mid-loop failure
    conn = FakeConn(rowcounts={t: 3 for t in _DELETABLE_USER_TABLES},
                    fail_tables={fail})
    deleted = teardown(conn, "run-2")
    committed_tables = [t for t, _ in conn.committed]
    # Every OTHER table was still deleted and committed…
    expected = [t for t in _DELETABLE_USER_TABLES if t != fail]
    assert committed_tables == expected
    # …and `deleted` reports ONLY committed work.
    assert deleted == 3 * len(expected)
    assert conn.rollbacks == 1
    assert conn.pending == [] and conn.in_failed_tx is False


def test_assert_namespaced_guards_real_principals():
    assert_namespaced("__bench__run__agentdojo__primary")
    with pytest.raises(ValueError):
        assert_namespaced("real-user-42")
