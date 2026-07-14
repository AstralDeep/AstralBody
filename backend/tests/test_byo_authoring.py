"""Feature 058 — BYO authoring orchestration: the Analyze gate is structurally
pre-generation (a violating draft produces NO code) and a passing draft generates
+ delivers to the host (never Popen'd). Generation is mocked; the real generator
needs a configured LLM and the real host round-trip needs the Windows client."""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.database import Database  # noqa: E402
from orchestrator import agent_authoring as aa  # noqa: E402
from orchestrator import user_agents as ua  # noqa: E402


def _fake_orch():
    o = MagicMock()
    o.history.db = Database()
    o.history.db._init_db()
    o.lifecycle_manager = MagicMock()
    o.lifecycle_manager.create_draft = AsyncMock(return_value={"id": "d1", "agent_slug": "greeter"})
    o.lifecycle_manager.generate_code = AsyncMock(
        return_value={"status": "ok", "files": {"greeter_agent.py": "print('hi')"}})
    o.deliver_agent_bundle = AsyncMock(return_value=1)
    return o


async def test_analyze_violation_blocks_generation(orch=None):
    o = _fake_orch()
    res = await aa.author_and_deliver(
        o, user_id="u-block", agent_name="Sharer",
        description="publishes and shares the agent with another user",
        declared_tools=["share_agent"], declared_scopes=["tools:read"])
    assert res["status"] == "analyze_failed"
    principles = {v["principle"] for v in res["violations"]}
    assert principles & {"K", "D"}                       # share/cross-user caught
    o.lifecycle_manager.create_draft.assert_not_awaited()  # NO draft
    o.lifecycle_manager.generate_code.assert_not_awaited() # NO code (FR-003)
    o.deliver_agent_bundle.assert_not_awaited()


async def test_analyze_pass_generates_validates_delivers():
    o = _fake_orch()
    res = await aa.author_and_deliver(
        o, user_id="u-ok", agent_name="Greeter",
        description="greets the owner by their name",
        declared_tools=["greet"], declared_scopes=["tools:read"],
        plan={"tools_used": ["greet"], "tool_scopes": {"greet": "tools:read"}})
    try:
        assert res["status"] == "delivered" and res["delivered_to"] == 1
        o.lifecycle_manager.generate_code.assert_awaited_once()
        o.deliver_agent_bundle.assert_awaited_once()
        row = ua.get_user_agent(o.history.db, res["agent_id"])
        assert row["status"] == "validated" and row["constitution_version"]
    finally:
        for t in ("user_agent", "agent_ownership"):
            o.history.db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (res["agent_id"],))


async def test_generation_failure_reported_no_delivery():
    o = _fake_orch()
    o.lifecycle_manager.generate_code = AsyncMock(
        return_value={"status": "error", "error_message": "codegen boom"})
    res = await aa.author_and_deliver(
        o, user_id="u-gen", agent_name="Greeter2",
        description="greets the owner by their name",
        declared_tools=["greet"], declared_scopes=["tools:read"],
        plan={"tools_used": ["greet"], "tool_scopes": {"greet": "tools:read"}})
    try:
        assert res["status"] == "generation_failed" and "boom" in (res["error"] or "")
        o.deliver_agent_bundle.assert_not_awaited()
    finally:
        for t in ("user_agent", "agent_ownership"):
            o.history.db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (res["agent_id"],))


def test_slug_is_owner_namespaced_and_non_reserved():
    a = aa.slug_agent_id("My Cool Agent!", "owner-abc-123")
    b = aa.slug_agent_id("My Cool Agent!", "different-owner")
    assert a != b and not a.startswith("__") and a.startswith("ua-")
