"""Feature 058 T011 (SC-002) — zero user-agent processes on the orchestrator host.

A BYO agent's code belongs to the user and runs on the user's desktop. Two paths
could put it on the central host, so both are pinned here:

1. the boot relaunch, which re-Popen'd every ``draft_agents`` row in status
   ``live`` with no origin filter, and
2. ``start_draft_agent`` itself, which is the only thing that Popens generated
   code — it now refuses a ``byo_client`` draft outright, so a future call site
   cannot reintroduce (1).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.database import Database  # noqa: E402
from orchestrator import agent_authoring as aa  # noqa: E402
from orchestrator.agent_lifecycle import AgentLifecycleManager, BYO_ORIGIN  # noqa: E402
from orchestrator.orchestrator import LIVE_DRAFT_RELAUNCH_QUERY  # noqa: E402


async def _t(fn, *a, **k):
    """Run a synchronous (DB-touching) helper off the event loop (052)."""
    return await asyncio.to_thread(fn, *a, **k)


@pytest.fixture()
def db():
    d = Database()
    d._init_db()
    return d


def _live_draft(db, origin):
    draft_id = str(uuid.uuid4())
    slug = "offsrv_" + draft_id[:8].replace("-", "")
    db.create_draft_agent(draft_id=draft_id, user_id="u-offsrv", agent_name=slug,
                          agent_slug=slug, description="d" * 20, origin=origin)
    db.update_draft_agent(draft_id, status="live")
    return draft_id


def test_boot_relaunch_query_excludes_byo_agents(db):
    byo_id = _live_draft(db, BYO_ORIGIN)
    server_id = _live_draft(db, "manual")
    try:
        relaunched = {r["id"] for r in db.fetch_all(LIVE_DRAFT_RELAUNCH_QUERY)}
        assert server_id in relaunched      # 027 agents still come back up
        assert byo_id not in relaunched     # a user agent is never Popen'd here
    finally:
        for d in (byo_id, server_id):
            db.delete_draft_agent(d)


async def test_start_draft_agent_refuses_a_byo_draft(db, monkeypatch):
    import subprocess

    def _no_popen(*a, **kw):
        raise AssertionError("Popen'd a user agent on the orchestrator host (SC-002)")

    monkeypatch.setattr(subprocess, "Popen", _no_popen)
    lm = AgentLifecycleManager(db, orchestrator=None)
    draft_id = await _t(_live_draft, db, BYO_ORIGIN)
    try:
        with pytest.raises(ValueError, match="BYO"):
            await lm.start_draft_agent(draft_id)
    finally:
        await _t(db.delete_draft_agent, draft_id)


async def test_approve_agent_refuses_a_byo_draft(db):
    # approve_agent both exec's the tools in-process AND Popens them. A BYO draft
    # id belongs to the user, so this entry point is reachable — refuse it.
    lm = AgentLifecycleManager(db, orchestrator=None)
    draft_id = await _t(_live_draft, db, BYO_ORIGIN)
    try:
        with pytest.raises(ValueError, match="BYO"):
            await lm.approve_agent(draft_id)
    finally:
        await _t(db.delete_draft_agent, draft_id)


async def test_refine_validates_a_byo_draft_out_of_process(db, monkeypatch, tmp_path):
    # The refine entry point validates too — and validation EXECUTES the tools.
    lm = AgentLifecycleManager(db, orchestrator=None)
    draft_id = await _t(_live_draft, db, BYO_ORIGIN)
    slug = (await _t(db.get_draft_agent, draft_id))["agent_slug"]
    agent_dir = os.path.join(lm._agents_dir, slug)
    os.makedirs(agent_dir, exist_ok=True)
    with open(os.path.join(agent_dir, "mcp_tools.py"), "w", encoding="utf-8") as fh:
        fh.write("TOOL_REGISTRY = {}\n")

    def _boom(*a, **kw):
        raise AssertionError("in-process exec of BYO code on refine (G1 violation)")

    monkeypatch.setattr(lm.validator, "validate", _boom)
    lm.generator.refine_tools_file = AsyncMock(return_value=(
        "from astralprims import Text\n\n"
        "def t(**kwargs):\n"
        "    return {'_ui_components': [Text(content='x').to_dict()], '_data': {}}\n\n"
        "TOOL_REGISTRY = {'t': {'function': t, 'description': 'd',\n"
        "  'input_schema': {'type': 'object', 'properties': {}}, 'scope': 'tools:read'}}\n"))
    try:
        state = await lm.refine_agent(draft_id, "add a tool")
        assert state["status"] == "generated"
        assert json.loads(state["validation_report"])["passed"]
    finally:
        shutil.rmtree(agent_dir, ignore_errors=True)
        await _t(db.delete_draft_agent, draft_id)


async def test_authoring_path_never_starts_a_process(monkeypatch, db):
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", MagicMock(
        side_effect=AssertionError("BYO authoring spawned a process")))

    o = MagicMock()
    o.history.db = db
    o.lifecycle_manager = MagicMock()
    o.lifecycle_manager.create_draft = AsyncMock(
        return_value={"id": "d-offsrv", "agent_slug": "offsrv"})
    o.deliver_agent_bundle = AsyncMock(return_value=1)

    updates = []
    real_update = db.update_draft_agent

    def _spy(draft_id, **kw):
        updates.append(kw)
        return real_update(draft_id, **kw)

    monkeypatch.setattr(db, "update_draft_agent", _spy)

    async def _generate(draft_id, **kw):
        # The origin filter only protects us if the row is stamped BEFORE the
        # draft can be picked up — i.e. before generation, not after delivery.
        assert any(u.get("origin") == BYO_ORIGIN for u in updates), \
            "draft was generated before it was stamped byo_client"
        assert kw.get("target") == "byo"
        assert kw.get("agent_id", "").startswith("ua-")   # owner-namespaced
        return {"status": "generated",
                "files": {"agent_main.py": "x", "mcp_tools.py": "y",
                          "manifest.json": "{}"}}

    o.lifecycle_manager.generate_code = AsyncMock(side_effect=_generate)

    res = await aa.author_and_deliver(
        o, user_id="u-offsrv", agent_name="Offserver",
        description="greets the owner by their name",
        declared_tools=["greet"], declared_scopes=["tools:read"],
        plan={"tools_used": ["greet"], "tool_scopes": {"greet": "tools:read"}})
    try:
        assert res["status"] == "delivered"          # bundle went to the host…
        o.deliver_agent_bundle.assert_awaited_once()
        o.lifecycle_manager.start_draft_agent.assert_not_called()   # …and nowhere else
        o.lifecycle_manager.approve_agent.assert_not_called()
    finally:
        for t in ("user_agent", "agent_ownership"):
            await _t(db.execute, f"DELETE FROM {t} WHERE agent_id = ?", (res["agent_id"],))
