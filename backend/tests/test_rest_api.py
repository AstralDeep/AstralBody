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
os.environ["VITE_USE_MOCK_AUTH"] = "true"

from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.api import chat_router, component_router, agent_router, dashboard_router
from orchestrator.auth import auth_router


# Mock JWT token (same as test_mock_auth.py)
MOCK_JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiYWRtaW4iLCJ1c2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYXN0cmFsLWZyb250ZW5kIjp7InJvbGVzIjpbImFkbWluIiwidXNlciJdfX0sInN1YiI6ImRldi11c2VyLWlkIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiRGV2VXNlciJ9."
    "fake-signature-ignore"
)

AUTH_HEADER = {"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}


def _create_test_app():
    """Create a minimal FastAPI app for testing with a mock orchestrator."""
    from unittest.mock import MagicMock
    from orchestrator.history import HistoryManager
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
    mock_orch.ui_clients = []
    mock_orch.ui_sessions = {}

    app.state.orchestrator = mock_orch

    app.include_router(chat_router)
    app.include_router(component_router)
    app.include_router(agent_router)
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

    def test_create_and_list_chats(self, client):
        """Create a chat and verify it appears in the list."""
        # Create
        resp = client.post("/api/chats", headers=AUTH_HEADER)
        assert resp.status_code == 201
        data = resp.json()
        assert "chat_id" in data
        chat_id = data["chat_id"]

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
        """List agents when none are connected."""
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert resp.json()["agents"] == []

    def test_dashboard(self, client):
        """Get dashboard data."""
        resp = client.get("/api/dashboard", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total_tools" in data


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
