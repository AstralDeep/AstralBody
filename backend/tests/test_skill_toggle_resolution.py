"""027 click-through fix: skill toggles must write the permission row that
``is_tool_allowed`` actually honors (per-kind first, legacy NULL outranked)."""
import types

from orchestrator.tool_permissions import VALID_SCOPES, ToolPermissionManager


class FakeDB:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))
        return types.SimpleNamespace(rowcount=1)

    def fetch_one(self, sql, params=()):
        return None

    def fetch_all(self, sql, params=()):
        return []


def _manager(scope_map):
    tp = ToolPermissionManager.__new__(ToolPermissionManager)
    tp.db = FakeDB()
    tp._tool_scope_map = scope_map
    return tp


def test_valid_scopes_include_files():
    """tools:files tools were uncontrollable — the scope now exists."""
    assert "tools:files" in VALID_SCOPES


def test_set_skill_enabled_writes_per_kind_row_and_clears_legacy():
    tp = _manager({"general-1": {"search_wikipedia": "tools:search"}})
    tp.set_skill_enabled("u1", "general-1", "search_wikipedia", False)
    sqls = [sql for sql, _ in tp.db.executed]
    assert any("INSERT INTO tool_overrides" in s for s in sqls), "per-kind upsert missing"
    insert_params = next(p for s, p in tp.db.executed if "INSERT INTO tool_overrides" in s)
    assert "tools:search" in insert_params  # the kind row, not NULL
    assert any("DELETE FROM tool_overrides" in s and "permission_kind IS NULL" in s
               for s in sqls), "legacy NULL row not cleared"


def test_set_skill_enabled_falls_back_for_unknown_scope():
    tp = _manager({"weird-1": {"odd_tool": "tools:quantum"}})
    tp.set_skill_enabled("u1", "weird-1", "odd_tool", True)
    sqls = [sql for sql, _ in tp.db.executed]
    # unknown scope -> legacy tool-wide path only (no invalid kind insert)
    assert not any("'tools:quantum'" in s for s in sqls)
