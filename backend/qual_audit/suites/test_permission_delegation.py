"""Category 4: Permission & Delegation Validation Tests.

Validates scope enforcement, RFC 8693 token attenuation, immediate
permission changes, per-tool overrides, and cross-user isolation.
6 test cases.
"""

import base64
import json

import pytest


AGENT_ID = "test-nefarious-agent"
USER_ID = "researcher-001"


@pytest.fixture
def configured_perm_manager(perm_manager):
    """ToolPermissionManager with nefarious-style tool scopes registered."""
    tool_scope_map = {
        "read_user_profile": "tools:read",
        "read_system_logs": "tools:read",
        "write_user_notes": "tools:write",
        "update_user_settings": "tools:write",
        "exfiltrate_data": "tools:system",
    }
    perm_manager.register_tool_scopes(AGENT_ID, tool_scope_map)
    return perm_manager


def _decode_mock_jwt_payload(token: str) -> dict:
    """Decode the payload from a mock JWT (base64url, no verification)."""
    parts = token.split(".")
    payload_b64 = parts[1]
    # Pad if needed
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    return json.loads(base64.urlsafe_b64decode(payload_b64))


class TestPermissionDelegation:
    """Verify scope-based authorization and delegation token constraints."""

    def test_scope_enforcement_blocks_unauthorized(self, configured_perm_manager):
        """PD-001: Agent with only tools:read cannot access tools:write tools."""
        pm = configured_perm_manager
        # Grant only tools:read
        pm.set_agent_scopes(USER_ID, AGENT_ID, {"tools:read": True})

        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "read_user_profile") is True
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "read_system_logs") is True
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "write_user_notes") is False
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "exfiltrate_data") is False

    def test_token_attenuation_scopes(self, configured_perm_manager, delegation_service):
        """PD-002: Delegation token contains only granted scopes."""
        pm = configured_perm_manager
        pm.set_agent_scopes(USER_ID, AGENT_ID, {
            "tools:read": True,
            "tools:write": False,
            "tools:system": False,
        })

        enabled = pm.get_enabled_scope_names(USER_ID, AGENT_ID)
        allowed = pm.get_allowed_tools(
            USER_ID, AGENT_ID,
            ["read_user_profile", "read_system_logs", "write_user_notes", "exfiltrate_data"],
        )

        result = delegation_service._create_mock_delegation_token(
            agent_id=AGENT_ID,
            allowed_tools=allowed,
            user_id=USER_ID,
            enabled_scopes=enabled,
        )

        token = result["access_token"]
        payload = _decode_mock_jwt_payload(token)
        scope_str = payload["scope"]

        assert "tools:read" in scope_str
        assert "tools:write" not in scope_str
        assert "tools:system" not in scope_str
        assert "tool:read_user_profile" in scope_str
        assert "tool:exfiltrate_data" not in scope_str

    def test_token_act_claim_structure(self, delegation_service):
        """PD-003: Token act claim follows RFC 8693 §4.1 format."""
        result = delegation_service._create_mock_delegation_token(
            agent_id="my-agent-42",
            allowed_tools=["some_tool"],
            user_id="user-abc",
            enabled_scopes=["tools:read"],
        )

        payload = _decode_mock_jwt_payload(result["access_token"])
        assert "act" in payload, "Missing 'act' claim per RFC 8693 §4.1"
        assert "sub" in payload["act"]
        assert payload["act"]["sub"] == "agent:my-agent-42"

    def test_permission_change_immediate_effect(self, configured_perm_manager):
        """PD-004: Toggling a scope takes effect immediately (same session)."""
        pm = configured_perm_manager

        # Start with tools:write disabled
        pm.set_agent_scopes(USER_ID, AGENT_ID, {"tools:write": False})
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "write_user_notes") is False

        # Enable tools:write
        pm.set_agent_scopes(USER_ID, AGENT_ID, {"tools:write": True})
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "write_user_notes") is True

        # Disable again
        pm.set_agent_scopes(USER_ID, AGENT_ID, {"tools:write": False})
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "write_user_notes") is False

    def test_per_tool_override(self, configured_perm_manager):
        """PD-005: Scope enabled but specific tool disabled via override."""
        pm = configured_perm_manager

        # Enable entire tools:write scope
        pm.set_agent_scopes(USER_ID, AGENT_ID, {"tools:write": True})
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "write_user_notes") is True
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "update_user_settings") is True

        # Override: disable write_user_notes specifically
        pm.set_tool_overrides(USER_ID, AGENT_ID, {"write_user_notes": False})

        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "write_user_notes") is False
        assert pm.is_tool_allowed(USER_ID, AGENT_ID, "update_user_settings") is True

    def test_cross_user_isolation(self, configured_perm_manager):
        """PD-006: Different users have independent permission grants."""
        pm = configured_perm_manager
        user_a = "user-alpha"
        user_b = "user-beta"

        pm.set_agent_scopes(user_a, AGENT_ID, {"tools:read": True, "tools:write": True})
        pm.set_agent_scopes(user_b, AGENT_ID, {"tools:read": True, "tools:write": False})

        assert pm.is_tool_allowed(user_a, AGENT_ID, "write_user_notes") is True
        assert pm.is_tool_allowed(user_b, AGENT_ID, "write_user_notes") is False
        # Both can read
        assert pm.is_tool_allowed(user_a, AGENT_ID, "read_user_profile") is True
        assert pm.is_tool_allowed(user_b, AGENT_ID, "read_user_profile") is True
