"""
Tests for DelegationService — RFC 8693 Token Exchange.

Verifies:
1. Mock delegation token creation with act claim
2. Token scope filtering (only allowed tools)
3. Delegation info extraction from decoded payload
4. is_tool_in_scope checks
"""
import os
import sys
import json
import base64
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force mock auth for testing
os.environ["VITE_USE_MOCK_AUTH"] = "true"

from orchestrator.delegation import DelegationService


@pytest.fixture
def service():
    return DelegationService()


TOOLS = ["get_system_status", "modify_data", "search_wikipedia"]


class TestMockDelegationToken:
    def test_creates_token(self, service):
        """Mock mode creates a valid JWT-like token."""
        result = service._create_mock_delegation_token(
            agent_id="general-1",
            allowed_tools=TOOLS,
            user_id="test-user"
        )
        assert "access_token" in result
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == 300
        assert result["agent_id"] == "general-1"

    def test_token_has_act_claim(self, service):
        """Delegation token includes RFC 8693 act claim."""
        result = service._create_mock_delegation_token(
            agent_id="general-1",
            allowed_tools=TOOLS,
            user_id="test-user"
        )
        token = result["access_token"]
        # Decode the JWT payload
        parts = token.split(".")
        assert len(parts) == 3
        payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        assert payload["sub"] == "test-user"
        assert "act" in payload
        assert payload["act"]["sub"] == "agent:general-1"

    def test_token_scope_contains_tools(self, service):
        """Token scope lists allowed tools."""
        result = service._create_mock_delegation_token(
            agent_id="general-1",
            allowed_tools=TOOLS,
            user_id="test-user"
        )
        scope = result["scope"]
        for tool in TOOLS:
            assert f"tool:{tool}" in scope

    def test_token_scope_limited(self, service):
        """Token scope only contains specified tools."""
        result = service._create_mock_delegation_token(
            agent_id="general-1",
            allowed_tools=["get_system_status"],
            user_id="test-user"
        )
        assert "tool:get_system_status" in result["scope"]
        assert "tool:modify_data" not in result["scope"]

    def test_delegation_flag(self, service):
        """Mock token includes custom delegation flag."""
        result = service._create_mock_delegation_token(
            agent_id="general-1",
            allowed_tools=TOOLS,
            user_id="test-user"
        )
        token = result["access_token"]
        parts = token.split(".")
        payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload.get("delegation") is True


class TestDelegationInfoExtraction:
    def test_extract_from_delegation_token(self):
        """Extract actor and scopes from delegation payload."""
        payload = {
            "sub": "user-123",
            "act": {"sub": "agent:general-1"},
            "scope": "tool:get_system_status tool:modify_data"
        }
        info = DelegationService.extract_delegation_info(payload)
        assert info is not None
        assert info["user_id"] == "user-123"
        assert info["actor"] == "agent:general-1"
        assert "tool:get_system_status" in info["scopes"]
        assert "tool:modify_data" in info["scopes"]
        assert info["is_delegation"] is True

    def test_extract_from_regular_token(self):
        """Regular token (no act claim) returns None."""
        payload = {
            "sub": "user-123",
            "scope": "openid profile"
        }
        info = DelegationService.extract_delegation_info(payload)
        assert info is None


class TestToolScopeCheck:
    def test_tool_in_scope(self):
        scopes = ["tool:get_system_status", "tool:modify_data"]
        assert DelegationService.is_tool_in_scope("get_system_status", scopes) is True
        assert DelegationService.is_tool_in_scope("modify_data", scopes) is True

    def test_tool_not_in_scope(self):
        scopes = ["tool:get_system_status"]
        assert DelegationService.is_tool_in_scope("modify_data", scopes) is False

    def test_no_tool_scopes_allows_all(self):
        """When no tool-specific scopes exist, all tools are allowed."""
        scopes = ["openid", "profile"]
        assert DelegationService.is_tool_in_scope("modify_data", scopes) is True
        assert DelegationService.is_tool_in_scope("anything", scopes) is True

    def test_empty_scopes_allows_all(self):
        assert DelegationService.is_tool_in_scope("modify_data", []) is True
