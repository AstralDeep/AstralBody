"""
Test REST API endpoints using FastAPI TestClient.

Verifies:
1. OpenAPI schema is generated at /openapi.json
2. Chat CRUD endpoints work
3. Component endpoints work
4. Agent/dashboard endpoints work
5. Auth is enforced (401 without token)
"""
import os
import sys
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Enable mock auth for testing
os.environ["USE_MOCK_AUTH"] = "true"

from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.api import (
    chat_router,
    component_router,
    agent_router,
    dashboard_router,
    draft_router,
    user_router,
)
from orchestrator.auth import auth_router


# Mock JWT token (same as test_mock_auth.py)
MOCK_JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiYWRtaW4iLCJ1c2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYXN0cmFsLWZyb250ZW5kIjp7InJvbGVzIjpbImFkbWluIiwidXNlciJdfX0sInN1YiI6ImRldi11c2VyLWlkIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiRGV2VXNlciJ9."
    "fake-signature-ignore"
)

AUTH_HEADER = {"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}


def _make_mock_token(payload: dict) -> str:
    """Build an unsigned JWT the mock-auth decoder accepts (payload only)."""
    import base64
    import json as _json
    body = base64.b64encode(_json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


class _FakeSkill:
    """Minimal stand-in for shared.protocol.AgentSkill in API tests."""

    def __init__(self, skill_id, description="", input_schema=None,
                 scope="tools:read"):
        self.id = skill_id
        self.description = description
        self.input_schema = input_schema or {}
        self.scope = scope


class _FakeCard:
    """Minimal stand-in for shared.protocol.AgentCard in API tests."""

    def __init__(self, agent_id, name="Fake Agent", skills=None):
        self.agent_id = agent_id
        self.name = name
        self.description = "a fake agent"
        self.skills = skills or [_FakeSkill("tool_a", "does A")]
        self.metadata = {}


def _create_test_app():
    """Create a minimal FastAPI app for testing with a mock orchestrator."""
    from unittest.mock import AsyncMock, MagicMock
    from orchestrator.history import HistoryManager
    from orchestrator.workspace import WorkspaceManager
    import tempfile

    app = FastAPI(title="Test App")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create real HistoryManager with a temp dir
    tmp_dir = tempfile.mkdtemp()
    history = HistoryManager(data_dir=tmp_dir)

    # Create a mock orchestrator with real history
    mock_orch = MagicMock()
    mock_orch.history = history
    mock_orch.agent_cards = {}
    mock_orch.agent_capabilities = {}
    from shared.protocol import CandidateCapabilityMap
    mock_orch.personal_agent_capabilities = CandidateCapabilityMap()
    mock_orch.get_personal_agent_capabilities = MagicMock(
        side_effect=lambda: mock_orch.personal_agent_capabilities.to_dict()[
            "capabilities"
        ]
    )
    mock_orch.ui_clients = []
    mock_orch.ui_sessions = {}
    # Component endpoints exercise the real semantic workspace. The narrow
    # mock omits the detached publication runner; api.py's unit-test seam runs
    # the mutation directly, while production Orchestrator instances always
    # use the revisioned atomic boundary.
    mock_orch.workspace = WorkspaceManager(history)
    mock_orch.send_ui_upsert = AsyncMock()
    mock_orch._reconcile_legacy_replacement = AsyncMock()
    # Draft listings hide draft agents via a to_thread call — a bare
    # MagicMock is truthy and would hide every card.
    mock_orch._is_draft_agent = MagicMock(return_value=False)
    mock_orch.security_flags = {}
    # Typed returns so the permission endpoints' response models validate.
    tp = MagicMock()
    tp.get_agent_scopes.return_value = {"tools:read": True}
    tp.get_tool_scope_map.return_value = {"tool_a": "tools:read"}
    tp.get_effective_permissions.return_value = {"tool_a": True}
    tp.get_effective_tool_permissions.return_value = {"tool_a": {"tools:read": True}}
    tp.get_tool_overrides.return_value = {}
    tp.is_scope_enabled.return_value = True
    tp.is_tool_allowed.return_value = True
    mock_orch.tool_permissions = tp
    mock_orch.credential_manager = MagicMock()
    mock_orch.credential_manager.list_credential_keys.return_value = ["API_KEY"]
    lifecycle = MagicMock()
    lifecycle.stop_draft_agent = AsyncMock()
    mock_orch.lifecycle_manager = lifecycle

    app.state.orchestrator = mock_orch

    app.include_router(chat_router)
    app.include_router(component_router)
    app.include_router(agent_router)
    app.include_router(user_router)
    app.include_router(draft_router)
    app.include_router(dashboard_router)
    app.include_router(auth_router)

    return app, mock_orch


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def app_and_orch():
    return _create_test_app()


@pytest.fixture
def client(app_and_orch):
    app, _ = app_and_orch
    return TestClient(app)


@pytest.fixture
def orch(app_and_orch):
    _, orch = app_and_orch
    return orch


# =========================================================================
# Tests
# =========================================================================

class TestOpenAPI:
    def test_openapi_schema_generated(self, client):
        """Verify /openapi.json returns valid OpenAPI schema."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Test App"
        assert "paths" in schema
        # Check key paths exist
        paths = schema["paths"]
        assert "/api/chats" in paths
        assert "/api/agents" in paths
        assert "/api/dashboard" in paths

    def test_docs_page_loads(self, client):
        """Verify /docs returns the Swagger UI page."""
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()


class TestChatEndpoints:
    def test_list_chats_requires_auth(self, client):
        """401 without auth token."""
        resp = client.get("/api/chats")
        assert resp.status_code == 401

    def test_create_and_list_chats(self, client, orch):
        """Create a chat, land its first message, verify it appears in the list.

        Feature 030: zero-message chats are excluded from the listing, so
        the chat needs a message before it shows up.
        """
        # Create
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        assert resp.status_code == 201
        data = resp.json()
        assert "chat_id" in data
        chat_id = data["chat_id"]

        # First message lands (mock JWT sub is dev-user-id)
        orch.history.add_message(chat_id, "user", "hello", user_id="dev-user-id")

        # List
        resp = client.get("/api/chats", headers=AUTH_HEADER)
        assert resp.status_code == 200
        chats = resp.json()["chats"]
        assert any(c["id"] == chat_id for c in chats)

    def test_get_chat_detail(self, client):
        """Load a specific chat."""
        # Create
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        chat_id = resp.json()["chat_id"]

        # Get detail
        resp = client.get(f"/api/chats/{chat_id}", headers=AUTH_HEADER)
        assert resp.status_code == 200
        chat = resp.json()["chat"]
        assert chat["id"] == chat_id

    def test_get_nonexistent_chat(self, client):
        """404 for missing chat."""
        resp = client.get("/api/chats/nonexistent-id", headers=AUTH_HEADER)
        assert resp.status_code == 404

    def test_delete_chat(self, client):
        """Delete a chat."""
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        chat_id = resp.json()["chat_id"]

        resp = client.delete(f"/api/chats/{chat_id}", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_send_message(self, client):
        """Send a message to a chat."""
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        chat_id = resp.json()["chat_id"]

        resp = client.post(
            f"/api/chats/{chat_id}/messages",
            headers=AUTH_HEADER,
            json={"message": "Hello, world!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_id"] == chat_id
        assert data["status"] == "accepted"


class TestComponentEndpoints:
    def test_save_and_list_components(self, client):
        """Save a component and retrieve it."""
        # Create chat first
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        chat_id = resp.json()["chat_id"]

        # Save component
        resp = client.post(
            f"/api/chats/{chat_id}/components",
            headers=AUTH_HEADER,
            json={
                "component_data": {"type": "card", "title": "Test"},
                "component_type": "card",
                "title": "Test Card",
            },
        )
        assert resp.status_code == 201
        comp = resp.json()["component"]
        assert comp["title"] == "Test Card"
        comp_id = comp["id"]

        # List
        resp = client.get(f"/api/chats/{chat_id}/components", headers=AUTH_HEADER)
        assert resp.status_code == 200
        components = resp.json()["components"]
        assert any(c["id"] == comp_id for c in components)

    def test_delete_component(self, client):
        """Delete a saved component."""
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        chat_id = resp.json()["chat_id"]

        resp = client.post(
            f"/api/chats/{chat_id}/components",
            headers=AUTH_HEADER,
            json={
                "component_data": {"type": "text", "content": "hi"},
                "component_type": "text",
            },
        )
        comp_id = resp.json()["component"]["id"]

        resp = client.delete(f"/api/components/{comp_id}", headers=AUTH_HEADER)
        assert resp.status_code == 200


class TestAgentEndpoints:
    def test_list_agents_empty(self, client):
        """List agents when none are connected (auth required since 013 —
        the response is scoped to the requesting user's disabled list)."""
        resp = client.get("/api/agents")
        assert resp.status_code == 401  # no token ⇒ refused

        resp = client.get("/api/agents", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["agents"] == []

    def test_dashboard(self, client):
        """Get dashboard data."""
        resp = client.get("/api/dashboard", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total_tools" in data
        assert data["capabilities"] == {
            "personal_agent_host": {
                "macos": {
                    "supported": False,
                    "runtime_contract_versions": [],
                    "source_feature": None,
                }
            }
        }


class TestSendMessageCreatesChat:
    def test_send_message_to_unknown_chat_creates_it(self, client, orch):
        """A message to a nonexistent chat transparently creates the chat."""
        import uuid
        chat_id = f"rest-auto-{uuid.uuid4()}"
        resp = client.post(
            f"/api/chats/{chat_id}/messages",
            headers=AUTH_HEADER,
            json={"message": "hello there"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        assert orch.history.get_chat(chat_id, user_id="dev-user-id") is not None
        orch.history.delete_chat(chat_id, user_id="dev-user-id")


class TestAgentPermissionEndpoints:
    def test_list_agents_includes_connected_card(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.get("/api/agents", headers=AUTH_HEADER)
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert [a["id"] for a in agents] == ["agent-x"]
        assert agents[0]["tools"][0]["name"] == "tool_a"

    def test_get_permissions_reads_all_views(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.get("/api/agents/agent-x/permissions", headers=AUTH_HEADER)
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == "agent-x"
        assert body["scopes"] == {"tools:read": True}
        assert body["per_tool_permissions"] == {"tool_a": {"tools:read": True}}
        assert orch.tool_permissions.backfill_per_tool_rows.called

    def test_get_permissions_unknown_agent_404(self, client, orch):
        orch.agent_cards = {}
        resp = client.get("/api/agents/ghost/permissions", headers=AUTH_HEADER)
        assert resp.status_code == 404

    def test_put_permissions_per_tool_shape(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/agents/agent-x/permissions",
            headers=AUTH_HEADER,
            json={"per_tool_permissions": {"tool_a": {"tools:read": True}}},
        )
        assert resp.status_code == 200
        orch.tool_permissions.set_tool_permission.assert_any_call(
            "dev-user-id", "agent-x", "tool_a", "tools:read", True)
        assert orch.tool_permissions.set_agent_scopes.called

    def test_put_permissions_rejects_unknown_tool(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/agents/agent-x/permissions",
            headers=AUTH_HEADER,
            json={"per_tool_permissions": {"ghost_tool": {"tools:read": True}}},
        )
        assert resp.status_code == 400

    def test_put_permissions_rejects_wrong_kind(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/agents/agent-x/permissions",
            headers=AUTH_HEADER,
            json={"per_tool_permissions": {"tool_a": {"tools:write": True}}},
        )
        assert resp.status_code == 400

    def test_put_permissions_legacy_shape(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/agents/agent-x/permissions",
            headers=AUTH_HEADER,
            json={"scopes": {"tools:read": True},
                  "tool_overrides": {"tool_a": True}},
        )
        assert resp.status_code == 200
        assert orch.tool_permissions.set_agent_scopes.called
        assert orch.tool_permissions.set_tool_overrides.called

    def test_put_permissions_empty_body_400(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/agents/agent-x/permissions", headers=AUTH_HEADER, json={})
        assert resp.status_code == 400

    def test_dashboard_counts_allowed_tools(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.get("/api/dashboard", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert [a["id"] for a in data["agents"]] == ["agent-x"]
        assert data["total_tools"] == 1


class TestToolSelectionEndpoints:
    def test_get_selection_defaults_to_none(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.get(
            "/api/users/me/tool-selection", headers=AUTH_HEADER,
            params={"agent_id": "agent-x"})
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent-x"

    def test_put_then_clear_selection(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/users/me/tool-selection", headers=AUTH_HEADER,
            json={"agent_id": "agent-x", "selected_tools": ["tool_a"]})
        assert resp.status_code == 200
        assert resp.json()["selected_tools"] == ["tool_a"]

        resp = client.get(
            "/api/users/me/tool-selection", headers=AUTH_HEADER,
            params={"agent_id": "agent-x"})
        assert resp.json()["selected_tools"] == ["tool_a"]

        resp = client.delete(
            "/api/users/me/tool-selection", headers=AUTH_HEADER,
            params={"agent_id": "agent-x"})
        assert resp.status_code == 204

    def test_put_selection_rejects_empty_and_foreign_and_blocked(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/users/me/tool-selection", headers=AUTH_HEADER,
            json={"agent_id": "agent-x", "selected_tools": []})
        assert resp.status_code == 400

        resp = client.put(
            "/api/users/me/tool-selection", headers=AUTH_HEADER,
            json={"agent_id": "agent-x", "selected_tools": ["ghost"]})
        assert resp.status_code == 400

        orch.tool_permissions.is_tool_allowed.return_value = False
        try:
            resp = client.put(
                "/api/users/me/tool-selection", headers=AUTH_HEADER,
                json={"agent_id": "agent-x", "selected_tools": ["tool_a"]})
            assert resp.status_code == 400
        finally:
            orch.tool_permissions.is_tool_allowed.return_value = True

    def test_agent_enabled_toggle(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.put(
            "/api/users/me/agent-enabled", headers=AUTH_HEADER,
            json={"agent_id": "agent-x", "enabled": False})
        assert resp.status_code == 200
        assert resp.json() == {"agent_id": "agent-x", "enabled": False}
        resp = client.put(
            "/api/users/me/agent-enabled", headers=AUTH_HEADER,
            json={"agent_id": "ghost", "enabled": True})
        assert resp.status_code == 404
        orch.history.db.set_user_agent_disabled("dev-user-id", "agent-x", False)


class TestAgentVisibilityAndCredentials:
    def test_visibility_owner_only(self, client, orch):
        import uuid
        agent_id = f"vis-test-{uuid.uuid4().hex[:8]}"
        orch.history.db.set_agent_ownership(agent_id, "owner@example.com")
        owner_token = _make_mock_token(
            {"sub": "dev-user-id", "email": "owner@example.com"})
        try:
            resp = client.put(
                f"/api/agents/{agent_id}/visibility",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"is_public": True})
            assert resp.status_code == 200
            assert resp.json()["is_public"] is True

            resp = client.put(
                f"/api/agents/{agent_id}/visibility",
                headers=AUTH_HEADER, json={"is_public": False})
            assert resp.status_code == 403

            resp = client.put(
                "/api/agents/never-owned/visibility",
                headers=AUTH_HEADER, json={"is_public": True})
            assert resp.status_code == 404
        finally:
            orch.history.db.execute(
                "DELETE FROM agent_ownership WHERE agent_id = ?", (agent_id,))

    def test_list_and_delete_agent_credentials(self, client, orch):
        orch.agent_cards = {"agent-x": _FakeCard("agent-x")}
        resp = client.get("/api/agents/agent-x/credentials", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["credential_keys"] == ["API_KEY"]

        resp = client.delete(
            "/api/agents/agent-x/credentials/API_KEY", headers=AUTH_HEADER)
        assert resp.status_code == 200
        orch.credential_manager.delete_credential.assert_called_with(
            "dev-user-id", "agent-x", "API_KEY")


class TestDraftEndpoints:
    def _make_draft(self, orch):
        import uuid
        draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        orch.history.db.create_draft_agent(
            draft_id, "dev-user-id", "Coverage Draft",
            f"cov_{uuid.uuid4().hex[:8]}", "coverage test draft")
        return draft_id

    def _delete_draft(self, orch, draft_id):
        orch.history.db.execute(
            "DELETE FROM draft_agents WHERE id = ?", (draft_id,))

    def test_list_drafts(self, client):
        resp = client.get("/api/agents/drafts", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert "drafts" in resp.json()

    def test_pending_review_requires_admin(self, client):
        resp = client.get(
            "/api/agents/drafts/pending-review", headers=AUTH_HEADER)
        assert resp.status_code == 403
        admin_token = _make_mock_token(
            {"sub": "dev-user-id", "roles": ["admin"]})
        resp = client.get(
            "/api/agents/drafts/pending-review",
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_unknown_draft_yields_404_everywhere(self, client):
        missing = "no-such-draft-052"
        assert client.get(
            f"/api/agents/drafts/{missing}", headers=AUTH_HEADER
        ).status_code == 404
        assert client.delete(
            f"/api/agents/drafts/{missing}", headers=AUTH_HEADER
        ).status_code == 404
        for verb in ("generate", "refine", "test", "stop", "approve"):
            body = {"message": "hi"} if verb == "refine" else None
            resp = client.post(
                f"/api/agents/drafts/{missing}/{verb}",
                headers=AUTH_HEADER, json=body)
            assert resp.status_code == 404, verb
        assert client.get(
            f"/api/agents/drafts/{missing}/credentials", headers=AUTH_HEADER
        ).status_code == 404
        assert client.put(
            f"/api/agents/drafts/{missing}/credentials",
            headers=AUTH_HEADER, json={"credentials": {"K": "v"}}
        ).status_code == 404

    def test_stop_draft_resets_status(self, client, orch):
        draft_id = self._make_draft(orch)
        try:
            resp = client.post(
                f"/api/agents/drafts/{draft_id}/stop", headers=AUTH_HEADER)
            assert resp.status_code == 200
            assert resp.json()["status"] == "generated"
            orch.lifecycle_manager.stop_draft_agent.assert_awaited_with(draft_id)
        finally:
            self._delete_draft(orch, draft_id)

    def test_draft_credentials_roundtrip(self, client, orch):
        draft_id = self._make_draft(orch)
        try:
            resp = client.get(
                f"/api/agents/drafts/{draft_id}/credentials",
                headers=AUTH_HEADER)
            assert resp.status_code == 200
            assert resp.json()["stored_credential_keys"] == ["API_KEY"]

            resp = client.put(
                f"/api/agents/drafts/{draft_id}/credentials",
                headers=AUTH_HEADER,
                json={"credentials": {"API_KEY": "secret"}})
            assert resp.status_code == 200
            assert orch.credential_manager.set_bulk_credentials.called
        finally:
            self._delete_draft(orch, draft_id)


class TestA2AAuth:
    def test_validate_agent_key_empty(self):
        """When no key configured, all connections allowed."""
        from orchestrator.auth import validate_agent_api_key
        os.environ["AGENT_API_KEY"] = ""
        assert validate_agent_api_key("anything") is True

    def test_validate_agent_key_correct(self):
        """Correct key passes."""
        from orchestrator.auth import validate_agent_api_key
        os.environ["AGENT_API_KEY"] = "test-secret-key"
        assert validate_agent_api_key("test-secret-key") is True

    def test_validate_agent_key_wrong(self):
        """Wrong key fails."""
        from orchestrator.auth import validate_agent_api_key
        os.environ["AGENT_API_KEY"] = "test-secret-key"
        assert validate_agent_api_key("wrong-key") is False
        os.environ["AGENT_API_KEY"] = ""  # cleanup
