"""Feature 058 — user-agent Mode-1 tunnel: owner-bound registration, outbound
frame wrap, honest-offline on disconnect. Exercises the whole server-side tunnel
path with a fake UI socket (only the real Windows host needs a live client)."""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.orchestrator import Orchestrator  # noqa: E402
from orchestrator import user_agents as ua  # noqa: E402
from shared.feature_flags import flags  # noqa: E402
from shared.local_transport import TunnelSocket  # noqa: E402
from shared.protocol import AgentCard, AgentSkill, RegisterAgent  # noqa: E402

OWNER = "byo058own"
FOREIGN = "byo058foreign"
AID = "byo058-greeter"


class FakeUI:
    """A UI websocket that captures frames the orchestrator sends to the client."""

    def __init__(self):
        self.sent = []

    async def send_text(self, t):
        self.sent.append(t)

    async def send(self, t):
        self.sent.append(t)

    async def close(self, *a, **k):
        return None


@pytest.fixture()
def orch(monkeypatch):
    monkeypatch.setitem(flags._flags, "byo_agents", True)
    o = Orchestrator()
    db = o.history.db
    for t in ("user_agent", "agent_ownership"):
        db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (AID,))
    ua.create_user_agent(db, agent_id=AID, owner_user_id=OWNER, display_name="Greeter")
    ua.mark_validated(db, AID, "0.1.0")   # runnable
    yield o
    for t in ("user_agent", "agent_ownership"):
        db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (AID,))


def _reg_frame(agent_id=AID):
    card = AgentCard(name="Greeter", description="greets", agent_id=agent_id,
                     skills=[AgentSkill(name="greet", description="g", id="greet",
                                        scope="tools:read", input_schema={})])
    return RegisterAgent(agent_card=card).to_json()


async def _tunnel(o, ws, frame, agent_id=AID):
    msg = SimpleNamespace(action="agent_tunnel",
                          payload={"agent_id": agent_id, "frame": frame,
                                   "host_session_id": "hs-1"})
    await o._handle_agent_tunnel(ws, msg)


async def test_owner_tunnel_registers_and_goes_live(orch):
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": OWNER}
    await _tunnel(orch, ws, _reg_frame())
    assert AID in orch.agents and isinstance(orch.agents[AID], TunnelSocket)
    assert orch.agents[AID].owner_sub == OWNER
    row = ua.get_user_agent(orch.history.db, AID)
    assert row["status"] == "live"           # go_live ran
    own = orch.history.db.get_agent_ownership(AID)
    assert own is not None and bool(own["is_public"]) is False   # private companion row


async def test_foreign_owner_registration_refused(orch):
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": FOREIGN}   # not the owner
    await _tunnel(orch, ws, _reg_frame())
    assert AID not in orch.agents            # owner-binding refused, fail-closed


async def test_outbound_frame_is_tunnel_wrapped(orch):
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": OWNER}
    await _tunnel(orch, ws, _reg_frame())
    ws.sent.clear()
    await orch.agents[AID].send('{"method":"tools/call","x":1}')
    env = json.loads(ws.sent[-1])
    assert env["type"] == "agent_tunnel" and env["agent_id"] == AID
    assert env["frame"] == '{"method":"tools/call","x":1}'


async def test_offline_on_disconnect_yields_honest_offline(orch):
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": OWNER}
    await _tunnel(orch, ws, _reg_frame())
    assert AID in orch.agents
    await orch._teardown_owner_tunnels(ws)   # client disconnects
    assert AID not in orch.agents
    resp = await orch._dispatch_tool_call(AID, "greet", {}, 5.0, None)
    assert resp is not None and resp.error and resp.error.get("offline") is True


async def test_flag_off_tunnel_is_inert(orch, monkeypatch):
    monkeypatch.setitem(flags._flags, "byo_agents", False)
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": OWNER}
    await _tunnel(orch, ws, _reg_frame())
    assert AID not in orch.agents            # flag off → no registration path
