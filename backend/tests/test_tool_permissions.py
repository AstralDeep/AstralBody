"""
Tests for ToolPermissionManager — Per-user, per-agent tool authorization.

Verifies:
1. Default permissions (all tools enabled)
2. Setting/getting permissions per user per agent
3. is_tool_allowed returns correct value
4. Bulk permission updates
5. Persistence across instances (write to temp file, reload)
6. get_effective_permissions with available tools
"""
import os
import sys
import json
import tempfile
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.tool_permissions import ToolPermissionManager


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test data."""
    d = tempfile.mkdtemp()
    yield d
    # Cleanup
    perm_file = os.path.join(d, "tool_permissions.json")
    if os.path.exists(perm_file):
        os.remove(perm_file)
    os.rmdir(d)


@pytest.fixture
def manager(tmp_dir):
    return ToolPermissionManager(data_dir=tmp_dir)


TOOLS = ["get_system_status", "modify_data", "search_wikipedia", "search_arxiv"]


class TestDefaultPermissions:
    def test_no_permissions_stored_returns_empty(self, manager):
        """When no permissions stored, get_permissions returns empty dict."""
        result = manager.get_permissions("user1", "agent1")
        assert result == {}

    def test_is_tool_allowed_default_true(self, manager):
        """Default: all tools are allowed (no explicit set)."""
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is True
        assert manager.is_tool_allowed("user1", "agent1", "get_system_status") is True

    def test_get_effective_permissions_all_true(self, manager):
        """Effective permissions default to True for all tools."""
        result = manager.get_effective_permissions("user1", "agent1", TOOLS)
        assert all(v is True for v in result.values())
        assert set(result.keys()) == set(TOOLS)


class TestSetGetPermissions:
    def test_set_single_permission(self, manager):
        """Setting a single permission."""
        manager.set_permission("user1", "agent1", "modify_data", False)
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False
        assert manager.is_tool_allowed("user1", "agent1", "get_system_status") is True

    def test_set_and_get(self, manager):
        manager.set_permission("user1", "agent1", "modify_data", False)
        result = manager.get_permissions("user1", "agent1")
        assert result == {"modify_data": False}

    def test_set_multiple_users(self, manager):
        """Different users have different permissions."""
        manager.set_permission("user1", "agent1", "modify_data", False)
        manager.set_permission("user2", "agent1", "modify_data", True)
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False
        assert manager.is_tool_allowed("user2", "agent1", "modify_data") is True

    def test_set_multiple_agents(self, manager):
        """Different agents under same user have different permissions."""
        manager.set_permission("user1", "agent1", "modify_data", False)
        manager.set_permission("user1", "agent2", "modify_data", True)
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False
        assert manager.is_tool_allowed("user1", "agent2", "modify_data") is True


class TestBulkPermissions:
    def test_set_bulk(self, manager):
        perms = {"modify_data": False, "search_wikipedia": False, "get_system_status": True}
        manager.set_bulk_permissions("user1", "agent1", perms)

        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is False
        assert manager.is_tool_allowed("user1", "agent1", "search_wikipedia") is False
        assert manager.is_tool_allowed("user1", "agent1", "get_system_status") is True
        # Not explicitly set = True
        assert manager.is_tool_allowed("user1", "agent1", "search_arxiv") is True

    def test_effective_permissions_after_bulk(self, manager):
        perms = {"modify_data": False, "search_wikipedia": False}
        manager.set_bulk_permissions("user1", "agent1", perms)

        result = manager.get_effective_permissions("user1", "agent1", TOOLS)
        assert result["modify_data"] is False
        assert result["search_wikipedia"] is False
        assert result["get_system_status"] is True
        assert result["search_arxiv"] is True


class TestGetAllowedTools:
    def test_filter_by_permission(self, manager):
        manager.set_bulk_permissions("user1", "agent1", {
            "modify_data": False,
            "search_wikipedia": False,
        })
        allowed = manager.get_allowed_tools("user1", "agent1", TOOLS)
        assert "modify_data" not in allowed
        assert "search_wikipedia" not in allowed
        assert "get_system_status" in allowed
        assert "search_arxiv" in allowed


class TestPersistence:
    def test_save_and_reload(self, tmp_dir):
        """Permissions persist across manager instances."""
        m1 = ToolPermissionManager(data_dir=tmp_dir)
        m1.set_permission("user1", "agent1", "modify_data", False)
        m1.set_permission("user1", "agent1", "search_arxiv", True)

        # Create new instance from same dir
        m2 = ToolPermissionManager(data_dir=tmp_dir)
        assert m2.is_tool_allowed("user1", "agent1", "modify_data") is False
        assert m2.is_tool_allowed("user1", "agent1", "search_arxiv") is True
        assert m2.is_tool_allowed("user1", "agent1", "get_system_status") is True

    def test_file_created(self, tmp_dir):
        m = ToolPermissionManager(data_dir=tmp_dir)
        m.set_permission("user1", "agent1", "modify_data", False)
        assert os.path.exists(os.path.join(tmp_dir, "tool_permissions.json"))


class TestCleanup:
    def test_remove_user_permissions(self, manager):
        manager.set_permission("user1", "agent1", "modify_data", False)
        manager.remove_user_permissions("user1")
        # Should be back to default
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is True

    def test_remove_agent_permissions(self, manager):
        manager.set_permission("user1", "agent1", "modify_data", False)
        manager.set_permission("user1", "agent2", "modify_data", False)
        manager.remove_agent_permissions("user1", "agent1")
        assert manager.is_tool_allowed("user1", "agent1", "modify_data") is True
        assert manager.is_tool_allowed("user1", "agent2", "modify_data") is False
