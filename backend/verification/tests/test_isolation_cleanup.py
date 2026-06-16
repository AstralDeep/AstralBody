"""Isolation + cleanup (T030 / SC-013, FR-031). Pure — fake DB, no boot."""
from __future__ import annotations

from verification.isolation import (
    NAMESPACE_PREFIX,
    is_harness_principal,
    make_principal,
    principal_id,
    teardown,
)


def test_principal_namespacing():
    pid = principal_id("__verif__abc123", "everyday", "primary")
    assert pid.startswith(NAMESPACE_PREFIX)
    assert "everyday" in pid and "primary" in pid
    assert is_harness_principal(pid)
    assert not is_harness_principal("real-user-42")


def test_principal_roles_and_claims():
    p = make_principal("__verif__abc", "gov", "admin", roles=["admin", "user"])
    assert p.is_admin
    claims = p.claims()
    assert claims["sub"] == p.user_id
    assert "admin" in claims["realm_access"]["roles"]


class _FakeDB:
    def __init__(self):
        self.deletes = []

    def execute(self, sql, params=None):
        self.deletes.append((sql, params))


def test_teardown_deletes_namespaced_rows_only():
    db = _FakeDB()
    n = teardown(db, "__verif__run9")
    assert n == len(db.deletes) > 0
    # Every DELETE is scoped by the run's namespace LIKE pattern.
    for sql, params in db.deletes:
        assert sql.strip().upper().startswith("DELETE FROM")
        assert params and params[0] == "__verif__run9_%"


def test_teardown_never_raises_on_bad_table():
    class _BoomDB:
        def execute(self, *a, **k):
            raise RuntimeError("no such table")

    # Best-effort: must not propagate.
    assert teardown(_BoomDB(), "__verif__x") == 0
