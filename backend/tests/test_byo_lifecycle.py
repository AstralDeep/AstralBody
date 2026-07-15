"""Feature 058 (T031) — user-agent lifecycle through the REAL orchestrator.

Unlike ``test_byo_authoring_flow`` (which pins the phase machine), these drive the
chrome surface's handlers against a live ``Orchestrator``: owner-only listing,
derived running/offline status, revise-requires-a-fresh-Analyze, delete-stops-the-
host, and cross-user invisibility. Only the two LLM-dependent lifecycle calls
(``create_draft``/``generate_code``) are stubbed — the tunnel, registration,
owner-binding, routing and soft-delete paths are the real ones.

Sync (DB-touching) helpers ride ``_t`` (asyncio.to_thread) — feature 052's
event-loop-blocking detector is CI-enforced with an empty allowlist.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.orchestrator import Orchestrator  # noqa: E402
from orchestrator import agent_authoring as aa  # noqa: E402
from orchestrator import user_agents as ua  # noqa: E402
from shared.feature_flags import flags  # noqa: E402
from shared.protocol import AgentCard, AgentSkill, RegisterAgent  # noqa: E402
from webrender.chrome.surfaces import authoring  # noqa: E402

OWNER = "byolife-owner"
FOREIGN = "byolife-foreign"
AID = "ua-mailer-byolifeo"        # == slug_agent_id("Mailer", OWNER)

BUNDLE = {"agent_main.py": "print('x')", "mcp_tools.py": "TOOL_REGISTRY = {}",
          "manifest.json": "{}"}


async def _t(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


class FakeUI:
    def __init__(self):
        self.sent = []

    async def send_text(self, t):
        self.sent.append(t)

    async def send(self, t):
        self.sent.append(t)

    async def close(self, *a, **k):
        return None


def _cleanup(db):
    db.execute("DELETE FROM draft_agents WHERE user_id LIKE 'byolife-%'")
    db.execute("DELETE FROM user_agent WHERE owner_user_id LIKE 'byolife-%'")
    for t in ("user_agent", "agent_ownership"):
        db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (AID,))


@pytest.fixture()
def orch(monkeypatch):
    monkeypatch.setitem(flags._flags, "byo_agents", True)
    o = Orchestrator()
    db = o.history.db
    _cleanup(db)

    async def _create_draft(user_id, agent_name, description, tools_spec=None, **kw):
        did = str(uuid.uuid4())

        def _insert():
            db.create_draft_agent(draft_id=did, user_id=user_id, agent_name=agent_name,
                                  agent_slug="byolife-" + did[:8], description=description,
                                  tools_spec=None)
            return db.get_draft_agent(did)

        return await asyncio.to_thread(_insert)

    # The two LLM/codegen-dependent lifecycle calls are the only stubs.
    o.lifecycle_manager.create_draft = AsyncMock(side_effect=_create_draft)
    o.lifecycle_manager.generate_code = AsyncMock(
        return_value={"status": "generated", "files": dict(BUNDLE)})
    o._call_llm_json = AsyncMock(return_value=None)
    yield o
    _cleanup(db)


def _reg_frame(agent_id=AID, name="Mailer"):
    card = AgentCard(name=name, description="mails", agent_id=agent_id,
                     skills=[AgentSkill(name="send_mail", description="s", id="send_mail",
                                        scope="tools:read", input_schema={})])
    return RegisterAgent(agent_card=card).to_json()


async def _connect_host(orch, owner=OWNER, agent_id=AID):
    """Bring a user agent live exactly as the desktop host does: tunnel a
    register_agent frame over the owner's authenticated UI socket."""
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": owner}
    orch.ui_clients.append(ws)
    await orch._handle_agent_tunnel(ws, SimpleNamespace(
        action="agent_tunnel",
        payload={"agent_id": agent_id, "frame": _reg_frame(agent_id),
                 "host_session_id": "hs-1"}))
    return ws


def _seed_agent(orch, owner=OWNER, agent_id=AID, name="Mailer"):
    db = orch.history.db
    ua.create_user_agent(db, agent_id=agent_id, owner_user_id=owner, display_name=name,
                         declared_tools=["send_mail"], declared_scopes=["tools:read"])
    ua.mark_validated(db, agent_id, "0.1.0")


# ── owner-only list + derived running/offline (T026) ─────────────────────────

async def test_list_derives_running_from_a_live_tunnel(orch):
    await _t(_seed_agent, orch)
    html = await authoring.render(orch, OWNER, ["user"], {})
    assert "Mailer" in html and "offline" in html and "running" not in html

    await _connect_host(orch)
    assert aa.agent_status(orch, OWNER, AID) == "running"
    html = await authoring.render(orch, OWNER, ["user"], {})
    assert "running" in html
    # FR-024: the surface always says where these things actually run.
    assert "desktop host" in html


async def test_list_is_owner_only(orch):
    await _t(_seed_agent, orch)
    await _connect_host(orch)
    foreign_html = await authoring.render(orch, FOREIGN, ["user"], {})
    assert "Mailer" not in foreign_html and AID not in foreign_html
    assert await _t(ua.list_user_agents, orch.history.db, FOREIGN) == []
    # …and the OWNER's own view is unaffected by the other user existing.
    assert "Mailer" in await authoring.render(orch, OWNER, ["user"], {})


async def test_running_status_is_not_leaked_across_owners(orch):
    """Liveness is keyed by (owner, agent_id): another user asking about the same
    id must not see it as running."""
    await _t(_seed_agent, orch)
    await _connect_host(orch)
    assert aa.agent_status(orch, FOREIGN, AID) == "offline"
    assert aa.host_online(orch, FOREIGN) is False
    assert aa.host_online(orch, OWNER) is True


# ── cross-user invisibility of authoring sessions (FR-016) ───────────────────

async def test_foreign_user_cannot_see_or_drive_a_session(orch):
    session = await aa.start_session(orch, user_id=OWNER, agent_name="Mailer",
                                     description="sends my own mail every morning")
    assert await _t(aa.get_session, orch, OWNER, session["id"]) is not None
    assert await _t(aa.get_session, orch, FOREIGN, session["id"]) is None    # invisible
    assert await _t(aa.list_sessions, orch, FOREIGN) == []

    # …and every write path refuses for the non-owner.
    ok, _phase, _msg = await _t(aa.advance, orch, FOREIGN, session["id"], {})
    assert not ok
    result = await aa.generate_from_session(orch, FOREIGN, session["id"])
    assert result["status"] == "unavailable"
    orch.lifecycle_manager.generate_code.assert_not_awaited()

    _s, _p, notice = await authoring._h_generate(
        orch, None, FOREIGN, ["user"], {"draft_id": session["id"]})
    assert "not available" in notice
    orch.lifecycle_manager.generate_code.assert_not_awaited()


# ── delete (T028) ────────────────────────────────────────────────────────────

async def test_delete_stops_the_host_and_soft_deletes(orch):
    await _t(_seed_agent, orch)
    ws = await _connect_host(orch)
    assert AID in orch.agents
    ws.sent.clear()

    _s, _p, notice = await authoring._h_delete(orch, None, OWNER, ["user"],
                                               {"agent_id": AID})
    assert "Deleted" in notice
    assert AID not in orch.agents                       # routing removed
    assert (OWNER, AID) not in orch._tunnel_sockets     # tunnel dropped
    assert any(json.loads(f).get("type") == "agent_stop" for f in ws.sent)  # host told

    row = await _t(ua.get_user_agent, orch.history.db, AID)
    assert row["status"] == "disabled" and row["deleted_at"] is not None   # retained
    assert AID not in await authoring.render(orch, OWNER, ["user"], {})    # gone from list


async def test_delete_refused_for_a_non_owner(orch):
    await _t(_seed_agent, orch)
    await _connect_host(orch)
    _s, _p, notice = await authoring._h_delete(orch, None, FOREIGN, ["user"],
                                               {"agent_id": AID})
    assert "not available" in notice
    row = await _t(ua.get_user_agent, orch.history.db, AID)
    assert row["deleted_at"] is None and AID in orch.agents   # untouched, still running


# ── revise (T027 authoring half / FR-026) ────────────────────────────────────

async def test_revise_reenters_authoring_and_cannot_ship_without_a_new_analyze(orch):
    await _t(_seed_agent, orch)
    await _connect_host(orch)

    _s, params, notice = await authoring._h_revise(orch, None, OWNER, ["user"],
                                                   {"agent_id": AID})
    assert "Analyze again" in notice
    draft_id = params["draft_id"]
    session = await _t(aa.get_session, orch, OWNER, draft_id)
    assert aa.phase_of(session) == "specify"            # back to the start of the flow
    assert session["revises_agent_id"] == AID           # same identity
    # FR-026: the live version keeps running while the revision is authored.
    assert AID in orch.agents

    # The revision cannot generate until IT passes Analyze.
    result = await aa.generate_from_session(orch, OWNER, draft_id)
    assert result["status"] == "gate_blocked"
    orch.lifecycle_manager.generate_code.assert_not_awaited()

    # Walk it through the gates for real.
    ok, phase, msg = await _t(
        aa.advance, orch, OWNER, draft_id,
        {"specification": "sends my own mail, now with attachments"})
    assert ok and phase == "clarify", msg
    await _t(orch.history.db.update_draft_agent, draft_id, clarify_answers=json.dumps(
        [{"question": "Which account?", "answer": "my work account"}]))
    assert (await _t(aa.advance, orch, OWNER, draft_id, {}))[0]
    assert (await _t(aa.advance, orch, OWNER, draft_id,
                     {"tools": "send_mail | tools:read | sends my own mail",
                      "scopes": "", "egress": ""}))[0]
    assert (await _t(aa.advance, orch, OWNER, draft_id, {"tasks": "read\nsend"}))[0]
    assert (await _t(aa.run_analyze, orch, OWNER, draft_id))["status"] == "passed"

    result = await aa.generate_from_session(orch, OWNER, draft_id)
    assert result["status"] == "delivered"
    assert result["agent_id"] == AID                    # the revision REPLACES the agent
    row = await _t(ua.get_user_agent, orch.history.db, AID)
    assert row["status"] == "validated" and row["revalidation_required"] is False


async def test_revalidation_required_blocks_registration_and_is_surfaced(orch):
    """T029: a constitution bump flags the agent; the boundary refuses it until a
    fresh Analyze passes, and the surface says so."""
    await _t(_seed_agent, orch)
    await _t(ua.mark_revalidation_required, orch.history.db, AID, True)

    ok, reason = await _t(ua.authorize_registration, orch.history.db, OWNER, AID)
    assert not ok and "Analyze" in reason               # fail-closed at the boundary
    await _connect_host(orch)
    assert AID not in orch.agents                       # refused, not routed

    html = await authoring.render(orch, OWNER, ["user"], {})
    assert "rules changed" in html and "Analyze" in html


async def test_revise_refused_for_a_non_owner(orch):
    await _t(_seed_agent, orch)
    _s, _p, notice = await authoring._h_revise(orch, None, FOREIGN, ["user"],
                                               {"agent_id": AID})
    assert "not available" in notice
    assert await _t(aa.list_sessions, orch, FOREIGN) == []
