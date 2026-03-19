"""
Tests for ToolPermissionManager — Scope-based agent authorization.

Verifies:
1. Default scopes (all disabled)
2. Setting/getting scopes per user per agent
3. is_tool_allowed checks scope enablement
4. Tool→scope mapping registration
5. Persistence across instances
6. get_effective_permissions derives from scopes
"""
import os
import sys
import tempfile
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.tool_permissions import ToolPermissionManager, VALID_SCOPES


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test data."""
    d = tempfile.mkdtemp()
    yield d
    import glob
    for f in glob.glob(os.path.join(d, "*")):
        os.remove(f)
    if os.path.exists(d):
        os.rmdir(d)


@pytest.fixture
def manager(tmp_dir):
    m = ToolPermissionManager(data_dir=tmp_dir)
    # Register tool→scope mapping for a test agent
    m.register_tool_scopes("agent1", {
        "get_system_status": "tools:system",
        "get_cpu_info": "tools:system",
        "modify_data": "tools:write",
        "search_wikipedia": "tools:search",
        "search_arxiv": "tools:search",
        "generate_chart": "tools:read",
    })
    return m


TOOLS = ["get_system_status", "get_cpu_info", "modify_data", "search_wikipedia", "search_arxiv", "generate_chart"]


class TestDefaultScopes:
    def test_all_scopes_disabled_by_default(self, manager):
        """By default, all 4 scopes are disabled."""
        scopes = manager.get_agent_scopes("user1", "agent1")
        assert all(v is False for v in scopes.values())
        assert set(scopes.keys()) == set(VALID_SCOPES)

    def test_is_scope_enabled_default_false(self, manager):
        """Default: all scopes disabled."""
        for scope in VALID_SCOPES:
            assert manager.is_scope_enabled("user1", "agent1", scope) is False

    def test_is_tool_allowed_default_false(self, manager):
        """Default: no tools are allowed (scopes disabled)."""
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False
        assert manager.is_tool_allowed("user1", "agent1", "get_system_status") is False
        assert manager.is_tool_allowed("user1", "agent1", "search_wikipedia") is False

    def test_effective_permissions_all_false(self, manager):
        """Effective permissions default to False for all tools."""
        result = manager.get_effective_permissions("user1", "agent1", TOOLS)
        assert all(v is False for v in result.values())
        assert set(result.keys()) == set(TOOLS)


class TestSetGetScopes:
    def test_enable_single_scope(self, manager):
        """Enabling a single scope."""
        manager.set_agent_scopes("user1", "agent1", {"tools:read": True})
        assert manager.is_scope_enabled("user1", "agent1", "tools:read") is True
        assert manager.is_scope_enabled("user1", "agent1", "tools:write") is False

    def test_enable_scope_allows_tools(self, manager):
        """Enabling tools:write allows write tools."""
        manager.set_agent_scopes("user1", "agent1", {"tools:write": True})
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is True
        # Read tools still blocked
        assert manager.is_tool_allowed("user1", "agent1", "generate_chart") is False

    def test_enable_multiple_scopes(self, manager):
        """Enabling multiple scopes."""
        manager.set_agent_scopes("user1", "agent1", {
            "tools:read": True,
            "tools:search": True,
        })
        assert manager.is_tool_allowed("user1", "agent1", "generate_chart") is True
        assert manager.is_tool_allowed("user1", "agent1", "search_wikipedia") is True
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False  # write not enabled
        assert manager.is_tool_allowed("user1", "agent1", "get_system_status") is False  # system not enabled

    def test_different_users_different_scopes(self, manager):
        """Different users have different scope settings."""
        manager.set_agent_scopes("user1", "agent1", {"tools:write": True})
        manager.set_agent_scopes("user2", "agent1", {"tools:write": False, "tools:read": True})
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is True
        assert manager.is_tool_allowed("user2", "agent1", "modify_data") is False
        assert manager.is_tool_allowed("user2", "agent1", "generate_chart") is True

    def test_invalid_scope_ignored(self, manager):
        """Invalid scopes are silently ignored."""
        manager.set_agent_scopes("user1", "agent1", {"tools:invalid": True})
        scopes = manager.get_agent_scopes("user1", "agent1")
        assert "tools:invalid" not in scopes

    def test_disable_scope(self, manager):
        """Disabling a previously enabled scope."""
        manager.set_agent_scopes("user1", "agent1", {"tools:write": True})
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is True
        manager.set_agent_scopes("user1", "agent1", {"tools:write": False})
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False


class TestEffectivePermissions:
    def test_effective_from_scopes(self, manager):
        """Effective permissions are derived from scopes."""
        manager.set_agent_scopes("user1", "agent1", {
            "tools:read": True,
            "tools:system": True,
        })
        result = manager.get_effective_permissions("user1", "agent1", TOOLS)
        assert result["generate_chart"] is True     # read
        assert result["get_system_status"] is True   # system
        assert result["get_cpu_info"] is True        # system
        assert result["modify_data"] is False        # write (not enabled)
        assert result["search_wikipedia"] is False   # search (not enabled)
        assert result["search_arxiv"] is False       # search (not enabled)


class TestGetAllowedTools:
    def test_filter_by_scope(self, manager):
        manager.set_agent_scopes("user1", "agent1", {
            "tools:search": True,
            "tools:system": True,
        })
        allowed = manager.get_allowed_tools("user1", "agent1", TOOLS)
        assert "search_wikipedia" in allowed
        assert "search_arxiv" in allowed
        assert "get_system_status" in allowed
        assert "get_cpu_info" in allowed
        assert "modify_data" not in allowed
        assert "generate_chart" not in allowed


class TestEnabledScopeNames:
    def test_enabled_scope_names(self, manager):
        manager.set_agent_scopes("user1", "agent1", {
            "tools:read": True,
            "tools:write": False,
            "tools:search": True,
        })
        names = manager.get_enabled_scope_names("user1", "agent1")
        assert "tools:read" in names
        assert "tools:search" in names
        assert "tools:write" not in names
        assert "tools:system" not in names


class TestToolScopeMapping:
    def test_get_tool_scope(self, manager):
        assert manager.get_tool_scope("agent1", "modify_data") == "tools:write"
        assert manager.get_tool_scope("agent1", "search_wikipedia") == "tools:search"
        assert manager.get_tool_scope("agent1", "get_system_status") == "tools:system"
        assert manager.get_tool_scope("agent1", "generate_chart") == "tools:read"

    def test_unknown_tool_defaults_to_read(self, manager):
        assert manager.get_tool_scope("agent1", "unknown_tool") == "tools:read"

    def test_unknown_agent_defaults_to_read(self, manager):
        assert manager.get_tool_scope("nonexistent_agent", "some_tool") == "tools:read"

    def test_get_tool_scope_map(self, manager):
        scope_map = manager.get_tool_scope_map("agent1")
        assert scope_map["modify_data"] == "tools:write"
        assert scope_map["search_wikipedia"] == "tools:search"
        assert len(scope_map) == 6


class TestPersistence:
    def test_save_and_reload(self, tmp_dir):
        """Scopes persist across manager instances."""
        m1 = ToolPermissionManager(data_dir=tmp_dir)
        m1.register_tool_scopes("agent1", {"modify_data": "tools:write"})
        m1.set_agent_scopes("user1", "agent1", {"tools:write": True})

        m2 = ToolPermissionManager(data_dir=tmp_dir)
        m2.register_tool_scopes("agent1", {"modify_data": "tools:write"})
        assert m2.is_scope_enabled("user1", "agent1", "tools:write") is True
        assert m2.is_tool_allowed("user1", "agent1", "modify_data") is True

    def test_db_connected(self, tmp_dir):
        m = ToolPermissionManager(data_dir=tmp_dir)
        m.set_agent_scopes("user1", "agent1", {"tools:read": True})
        # Verify data was persisted by reading it back
        assert m.is_scope_enabled("user1", "agent1", "tools:read") is True


class TestCleanup:
    def test_remove_user_permissions(self, manager):
        manager.set_agent_scopes("user1", "agent1", {"tools:write": True})
        manager.remove_user_permissions("user1")
        assert manager.is_scope_enabled("user1", "agent1", "tools:write") is False

    def test_remove_agent_permissions(self, manager):
        manager.set_agent_scopes("user1", "agent1", {"tools:write": True})
        manager.set_agent_scopes("user1", "agent2", {"tools:write": True})
        manager.remove_agent_permissions("user1", "agent1")
        assert manager.is_scope_enabled("user1", "agent1", "tools:write") is False
        assert manager.is_scope_enabled("user1", "agent2", "tools:write") is True


class TestGetAllAgentPermissions:
    def test_returns_all_agents(self, manager):
        manager.set_agent_scopes("user1", "agent1", {"tools:read": True})
        manager.set_agent_scopes("user1", "agent2", {"tools:write": True, "tools:search": True})
        result = manager.get_all_agent_permissions("user1")
        assert "agent1" in result
        assert "agent2" in result
        assert result["agent1"]["tools:read"] is True
        assert result["agent1"]["tools:write"] is False
        assert result["agent2"]["tools:write"] is True
        assert result["agent2"]["tools:search"] is True
