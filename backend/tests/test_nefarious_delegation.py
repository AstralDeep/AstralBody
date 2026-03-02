"""
Tests for Nefarious Agent — Delegated Token Blast Radius PoC.

Demonstrates that the RFC 8693 delegation system can block a bad actor
tool (exfiltrate_data) while allowing legitimate tools to operate.

Verifies:
1. All 5 tools are registered in TOOL_REGISTRY
2. Delegation token excludes exfiltrate_data when permission is revoked
3. DelegationService.is_tool_in_scope blocks the exfiltration tool
4. The exfiltration tool CAN run directly (proving delegation is the gatekeeper)
5. Toggling permissions changes the delegation token scope
"""
import os
import sys
import json
import base64
import tempfile
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force mock auth for testing
os.environ["VITE_USE_MOCK_AUTH"] = "true"

from agents.nefarious.mcp_tools import TOOL_REGISTRY
from orchestrator.delegation import DelegationService
from orchestrator.tool_permissions import ToolPermissionManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    return DelegationService()


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    perm_file = os.path.join(d, "tool_permissions.json")
    if os.path.exists(perm_file):
        os.remove(perm_file)
    os.rmdir(d)


@pytest.fixture
def perm_manager(tmp_dir):
    return ToolPermissionManager(data_dir=tmp_dir)


ALL_TOOLS = list(TOOL_REGISTRY.keys())
LEGIT_TOOLS = ["read_user_profile", "read_system_logs", "write_user_notes", "update_user_settings"]
BAD_TOOL = "exfiltrate_data"


# ── Test 1: Tool Registry ────────────────────────────────────────────────────

class TestNefariousToolRegistry:
    def test_has_five_tools(self):
        """Nefarious agent registers exactly 5 tools."""
        assert len(TOOL_REGISTRY) == 5

    def test_all_expected_tools_present(self):
        """All 5 tools are in the registry."""
        expected = {"read_user_profile", "read_system_logs",
                    "write_user_notes", "update_user_settings",
                    "exfiltrate_data"}
        assert set(TOOL_REGISTRY.keys()) == expected

    def test_each_tool_has_function(self):
        """Every registered tool has a callable function."""
        for name, info in TOOL_REGISTRY.items():
            assert callable(info["function"]), f"{name} has no callable function"

    def test_each_tool_has_description(self):
        """Every registered tool has a description."""
        for name, info in TOOL_REGISTRY.items():
            assert info.get("description"), f"{name} has no description"

    def test_exfiltrate_tool_is_flagged(self):
        """The exfiltration tool description mentions sending data externally."""
        desc = TOOL_REGISTRY[BAD_TOOL]["description"]
        assert "external endpoint" in desc


# ── Test 2: Delegation Blocks Exfiltration ────────────────────────────────────

class TestDelegationBlocksExfiltration:
    """Core PoC: delegation token EXCLUDES exfiltrate_data when revoked."""

    def test_permission_revoke_removes_from_allowed(self, perm_manager):
        """ToolPermissionManager filters out revoked tools."""
        # Revoke the bad actor tool
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, False)

        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)
        assert BAD_TOOL not in allowed
        for tool in LEGIT_TOOLS:
            assert tool in allowed

    def test_delegation_token_excludes_revoked_tool(self, service, perm_manager):
        """Delegation token scope does NOT contain exfiltrate_data."""
        # Revoke the bad actor tool
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, False)

        # Get allowed tools (what the orchestrator would pass to delegation)
        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)

        # Create delegation token with only allowed tools
        result = service._create_mock_delegation_token(
            agent_id="nefarious-1",
            allowed_tools=allowed,
            user_id="user-001"
        )

        scope = result["scope"]
        # Exfiltrate tool should NOT be in scope
        assert f"tool:{BAD_TOOL}" not in scope
        # Legit tools should be in scope
        for tool in LEGIT_TOOLS:
            assert f"tool:{tool}" in scope

    def test_is_tool_in_scope_blocks_exfiltration(self, service, perm_manager):
        """DelegationService.is_tool_in_scope returns False for blocked tool."""
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, False)
        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)
        result = service._create_mock_delegation_token(
            agent_id="nefarious-1",
            allowed_tools=allowed,
            user_id="user-001"
        )

        # Parse the scopes from the token
        scopes = result["scope"].split()

        # Bad tool is blocked
        assert DelegationService.is_tool_in_scope(BAD_TOOL, scopes) is False

        # Legit tools are allowed
        assert DelegationService.is_tool_in_scope("read_user_profile", scopes) is True
        assert DelegationService.is_tool_in_scope("write_user_notes", scopes) is True

    def test_token_act_claim_identifies_nefarious_agent(self, service, perm_manager):
        """Delegation token act claim identifies the nefarious agent."""
        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)
        result = service._create_mock_delegation_token(
            agent_id="nefarious-1",
            allowed_tools=allowed,
            user_id="user-001"
        )

        # Decode the JWT payload
        token = result["access_token"]
        parts = token.split(".")
        payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        assert payload["act"]["sub"] == "agent:nefarious-1"
        assert payload["sub"] == "user-001"


# ── Test 3: Direct Execution (proves delegation is the gatekeeper) ────────────

class TestExfiltrationToolDirectExecution:
    """Shows the tool CAN run directly — it's the delegation layer that blocks it."""

    def test_exfiltrate_runs_directly(self):
        """Exfiltrate tool executes when called directly (no delegation check)."""
        tool_fn = TOOL_REGISTRY[BAD_TOOL]["function"]
        result = tool_fn(target_user_id="user-001")

        # Tool runs and returns data
        assert "_data" in result
        assert result["_data"]["exfiltration_attempted"] is True
        assert result["_data"]["target_user_id"] == "user-001"
        # GET to example.com — may succeed or fail depending on network
        assert isinstance(result["_data"]["send_success"], bool)

    def test_exfiltrate_collects_data(self):
        """Exfiltrate tool collects sensitive fields."""
        tool_fn = TOOL_REGISTRY[BAD_TOOL]["function"]
        result = tool_fn(target_user_id="user-001")

        fields = result["_data"]["fields_collected"]
        assert "email" in fields
        assert "api_keys" in fields
        assert "ssn_last4" in fields

    def test_read_tools_work(self):
        """Legitimate read tools execute correctly."""
        profile_fn = TOOL_REGISTRY["read_user_profile"]["function"]
        result = profile_fn(target_user_id="user-001")
        assert "_data" in result
        assert result["_data"]["name"] == "Alice Johnson"

        logs_fn = TOOL_REGISTRY["read_system_logs"]["function"]
        result = logs_fn(limit=3)
        assert "_data" in result
        assert result["_data"]["log_count"] == 3

    def test_write_tools_work(self):
        """Legitimate write tools execute correctly."""
        notes_fn = TOOL_REGISTRY["write_user_notes"]["function"]
        result = notes_fn(target_user_id="user-001", note="Test note from PoC")
        assert "_data" in result
        assert result["_data"]["note_saved"] is True

        settings_fn = TOOL_REGISTRY["update_user_settings"]["function"]
        result = settings_fn(target_user_id="user-001", settings={"theme": "dark"})
        assert "_data" in result
        assert "theme" in result["_data"]["updated_keys"]


# ── Test 4: Permission Toggle ─────────────────────────────────────────────────

class TestPermissionToggle:
    """Shows that toggling exfiltrate_data permission changes delegate scope."""

    def test_toggle_off_blocks(self, service, perm_manager):
        """Revoking permission removes tool from delegation scope."""
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, False)
        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)
        result = service._create_mock_delegation_token(
            agent_id="nefarious-1", allowed_tools=allowed, user_id="user-001"
        )
        assert f"tool:{BAD_TOOL}" not in result["scope"]

    def test_toggle_on_allows(self, service, perm_manager):
        """Re-granting permission adds tool back to delegation scope."""
        # First revoke, then re-allow
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, False)
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, True)

        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)
        result = service._create_mock_delegation_token(
            agent_id="nefarious-1", allowed_tools=allowed, user_id="user-001"
        )
        assert f"tool:{BAD_TOOL}" in result["scope"]

    def test_default_permissions_allow_all(self, service, perm_manager):
        """Default: all tools allowed (including the bad one)."""
        allowed = perm_manager.get_allowed_tools("user-001", "nefarious-1", ALL_TOOLS)
        assert len(allowed) == 5
        result = service._create_mock_delegation_token(
            agent_id="nefarious-1", allowed_tools=allowed, user_id="user-001"
        )
        for tool in ALL_TOOLS:
            assert f"tool:{tool}" in result["scope"]

    def test_selective_revoke_only_affects_target(self, service, perm_manager):
        """Revoking exfiltrate_data doesn't affect other tools."""
        perm_manager.set_permission("user-001", "nefarious-1", BAD_TOOL, False)

        # Read tools still allowed
        assert perm_manager.is_tool_allowed("user-001", "nefarious-1", "read_user_profile") is True
        assert perm_manager.is_tool_allowed("user-001", "nefarious-1", "read_system_logs") is True
        # Write tools still allowed
        assert perm_manager.is_tool_allowed("user-001", "nefarious-1", "write_user_notes") is True
        assert perm_manager.is_tool_allowed("user-001", "nefarious-1", "update_user_settings") is True
        # Only bad tool is blocked
        assert perm_manager.is_tool_allowed("user-001", "nefarious-1", BAD_TOOL) is False
