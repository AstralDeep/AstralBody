"""DB round-trip budgets for the agents chrome surface (feature 052, T016/T017).

Renders the agents list and detail views through the surface's real
``render()`` against the live test Postgres (same posture as
test_query_budgets.py) with a minimal orchestrator stub, and proves with the
count_queries helper that the list view stays within 2 round trips and the
detail view within 3 — while still containing the expected agent content.
"""
import asyncio
import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.history import HistoryManager
from orchestrator.tool_permissions import ToolPermissionManager
from tests.helpers.query_count import count_queries
from webrender.chrome.surfaces import agents as surface

OWNER_EMAIL = "owner@example.com"


class StubSkill:
    """Card skill shape the surface reads (id/name/description/scope)."""

    def __init__(self, sid, description, scope):
        self.id = sid
        self.name = sid
        self.description = description
        self.scope = scope


class StubCard:
    """Agent-card shape the surface reads (name/description/skills/metadata)."""

    def __init__(self, agent_id, name, description, skills=None, metadata=None):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.skills = skills or []
        self.metadata = metadata or {}


class StubHistory:
    """History facade exposing only the shared Database instance."""

    def __init__(self, db):
        self.db = db


class StubOrch:
    """Minimal orchestrator surface for agents render (no credential_manager:
    proves the consolidated context query path is the one exercised)."""

    def __init__(self, db, perms, cards):
        self.history = StubHistory(db)
        self.tool_permissions = perms
        self.agent_cards = cards

    def _is_draft_agent(self, agent_id):
        return False


@pytest.fixture(scope="module")
def hm(tmp_path_factory):
    """A HistoryManager backed by the live test Postgres."""
    return HistoryManager(data_dir=str(tmp_path_factory.mktemp("surface-budget-data")))


@pytest.fixture
def env(hm):
    """A seeded user + two agents (owned/private and foreign/public)."""
    db = hm.db
    uid = f"sbudget-{uuid.uuid4().hex[:12]}"
    agent_a = f"sbudget-alpha-{uuid.uuid4().hex[:8]}"
    agent_b = f"sbudget-beta-{uuid.uuid4().hex[:8]}"

    db.upsert_user(uid, email=OWNER_EMAIL)
    db.set_agent_ownership(agent_a, OWNER_EMAIL, is_public=False)
    db.set_agent_ownership(agent_b, "someone-else@example.com", is_public=True)
    db.set_user_agent_disabled(uid, agent_b, True)
    db.upsert_agent_safe(agent_a, True, "test-seed")
    now = int(time.time() * 1000)
    db.execute(
        "INSERT INTO user_credentials "
        "(user_id, agent_id, credential_key, encrypted_value, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (uid, agent_a, "API_KEY", "enc", now, now),
    )

    perms = ToolPermissionManager(db=db)
    perms.register_tool_scopes(agent_a, {
        "get_data": "tools:read",
        "write_data": "tools:write",
    })
    perms.set_agent_scopes(uid, agent_a, {"tools:read": True, "tools:write": False})
    perms.set_tool_permission(uid, agent_a, "get_data", "tools:read", True)

    cards = {
        agent_a: StubCard(
            agent_a, "Alpha Analysis", "Reads and writes analysis data.",
            skills=[StubSkill("get_data", "Fetch records", "tools:read"),
                    StubSkill("write_data", "Modify records", "tools:write")],
            metadata={"required_credentials": ["API_KEY"]},
        ),
        agent_b: StubCard(agent_b, "Beta Helper", "A public helper agent."),
    }
    orch = StubOrch(db, perms, cards)
    yield orch, uid, agent_a, agent_b

    db.execute("DELETE FROM tool_overrides WHERE agent_id IN (?, ?)", (agent_a, agent_b))
    db.execute("DELETE FROM agent_scopes WHERE agent_id IN (?, ?)", (agent_a, agent_b))
    db.execute("DELETE FROM user_credentials WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM agent_trust WHERE agent_id IN (?, ?)", (agent_a, agent_b))
    db.execute("DELETE FROM agent_ownership WHERE agent_id IN (?, ?)", (agent_a, agent_b))
    db.execute("DELETE FROM user_preferences WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM users WHERE id = ?", (uid,))


def test_agents_list_max_2(env):
    """The list view renders each tab in at most 2 DB round trips."""
    orch, uid, agent_a, agent_b = env

    with count_queries(orch.history.db) as counter:
        html = asyncio.run(surface.render(orch, uid, ["user"], {"tab": "mine"}))
    assert counter.count <= 2, counter.queries
    assert "Alpha Analysis" in html
    assert "Beta Helper" not in html
    assert "Yours" in html

    with count_queries(orch.history.db) as counter:
        html = asyncio.run(surface.render(orch, uid, ["user"], {"tab": "public"}))
    assert counter.count <= 2, counter.queries
    assert "Beta Helper" in html
    assert "Disabled by you" in html


def test_agent_detail_max_3(env):
    """The detail view renders in at most 3 DB round trips with full content."""
    orch, uid, agent_a, agent_b = env

    with count_queries(orch.history.db) as counter:
        html = asyncio.run(surface.render(orch, uid, ["user"], {"agent_id": agent_a}))

    assert counter.count <= 3, counter.queries
    assert "Alpha Analysis" in html
    assert 'name="get_data::tools:read" checked' in html
    assert 'name="__scope::tools:read" checked' in html
    assert 'name="__scope::tools:write" checked' not in html
    assert 'data-ui-action="chrome_visibility_set"' in html
    assert 'data-ui-action="chrome_safe_set"' in html
    assert ">Unmark safe<" in html
    assert "API_KEY" in html and ">Stored<" in html


def test_agent_detail_non_owner_hides_owner_sections(env):
    """A foreign public agent renders without owner controls, same budget."""
    orch, uid, agent_a, agent_b = env

    with count_queries(orch.history.db) as counter:
        html = asyncio.run(surface.render(orch, uid, ["user"], {"agent_id": agent_b}))

    assert counter.count <= 3, counter.queries
    assert "Beta Helper" in html
    assert 'data-ui-action="chrome_visibility_set"' not in html
    assert 'data-ui-action="chrome_safe_set"' not in html
    assert ">Enable<" in html
