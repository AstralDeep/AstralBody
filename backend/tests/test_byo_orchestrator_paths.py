"""Feature 058 — orchestrator tunnel / delivery / registration EDGE branches.

``test_byo_tunnel.py`` pins the happy owner-bound tunnel; this covers the
fail-safe corners: a malformed frame, the per-owner ingress cap dropping a frame
inside the tunnel handler, a reconnect superseding a stale socket, honest-offline
NOTIFYING the owner's other sockets, and the send/close/go_live exception handlers
that must never abort a delivery, delete, or refusal.

Sync DB helpers ride ``_t`` (asyncio.to_thread) — 052's loop-blocking detector is
CI-enforced with an empty allowlist.
"""
from __future__ import annotations

import asyncio
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

OWNER = "byoedge-own"
FOREIGN = "byoedge-foreign"
AID = "byoedge-greeter"


async def _t(fn, *a, **k):
    return await asyncio.to_thread(fn, *a, **k)


class FakeUI:
    def __init__(self):
        self.sent = []

    async def send_text(self, t):
        self.sent.append(t)

    async def send(self, t):
        self.sent.append(t)

    async def close(self, *a, **k):
        return None


class RaisingUI(FakeUI):
    """A socket that blows up on every outbound send — the orchestrator must
    swallow it and carry on with the other sockets."""

    async def send_text(self, t):
        raise RuntimeError("socket send exploded")

    async def send(self, t):
        raise RuntimeError("socket send exploded")


@pytest.fixture()
def orch(monkeypatch):
    monkeypatch.setitem(flags._flags, "byo_agents", True)
    o = Orchestrator()
    db = o.history.db
    for t in ("user_agent", "agent_ownership"):
        db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (AID,))
    ua.create_user_agent(db, agent_id=AID, owner_user_id=OWNER, display_name="Greeter")
    ua.mark_validated(db, AID, "0.1.0")
    yield o
    for t in ("user_agent", "agent_ownership"):
        db.execute(f"DELETE FROM {t} WHERE agent_id = ?", (AID,))


def _reg_frame(agent_id=AID):
    card = AgentCard(name="Greeter", description="greets", agent_id=agent_id,
                     skills=[AgentSkill(name="greet", description="g", id="greet",
                                        scope="tools:read", input_schema={})])
    return RegisterAgent(agent_card=card).to_json()


async def _tunnel(o, ws, frame=None, agent_id=AID, host_session_id="hs-1"):
    payload = {"agent_id": agent_id, "frame": frame if frame is not None else _reg_frame(agent_id),
               "host_session_id": host_session_id}
    await o._handle_agent_tunnel(ws, SimpleNamespace(action="agent_tunnel", payload=payload))


# ── malformed frame + ingress cap inside the tunnel handler ──────────────────

async def test_tunnel_ignores_a_frame_missing_the_agent_id(orch):
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": OWNER}
    await orch._handle_agent_tunnel(ws, SimpleNamespace(
        action="agent_tunnel", payload={"frame": _reg_frame()}))   # no agent_id
    assert AID not in orch.agents                # nothing registered from a malformed frame


async def test_tunnel_drops_a_frame_that_trips_the_ingress_cap(orch, monkeypatch):
    monkeypatch.setattr(type(orch), "_TUNNEL_MAX_FRAMES_PER_WINDOW", 1)
    ws = FakeUI()
    orch.ui_sessions[ws] = {"sub": OWNER}
    assert orch._tunnel_ingress_over_cap(OWNER) is False     # consume the 1-frame budget
    await _tunnel(orch, ws)                                   # this frame is over the cap
    assert AID not in orch.agents            # dropped before registration — owner isolated


# ── reconnect supersedes the stale socket ────────────────────────────────────

async def test_tunnel_reconnect_supersedes_the_stale_socket(orch):
    ws1 = FakeUI()
    orch.ui_sessions[ws1] = {"sub": OWNER}
    await _tunnel(orch, ws1)
    sock = orch._tunnel_sockets[(OWNER, AID)]
    assert isinstance(sock, TunnelSocket) and sock.ui_websocket is ws1

    ws2 = FakeUI()                              # the host reconnects on a new socket
    orch.ui_sessions[ws2] = {"sub": OWNER}
    await _tunnel(orch, ws2, host_session_id="hs-2")
    assert orch._tunnel_sockets[(OWNER, AID)] is sock        # same TunnelSocket, superseded
    assert sock.ui_websocket is ws2 and sock.host_session_id == "hs-2"
    # outbound now rides the new socket, not the stale one
    ws1.sent.clear()
    ws2.sent.clear()
    await sock.send('{"x":1}')
    assert any(json.loads(f).get("type") == "agent_tunnel" for f in ws2.sent)
    assert ws1.sent == []


# ── honest-offline notifies the owner's OTHER sockets ────────────────────────

async def test_teardown_notifies_the_owners_other_sockets_and_skips_foreigners(orch):
    host = FakeUI()
    orch.ui_sessions[host] = {"sub": OWNER}
    orch.ui_clients.append(host)
    await _tunnel(orch, host)
    assert AID in orch.agents

    other = FakeUI()                            # the owner's second socket (e.g. a tab)
    orch.ui_sessions[other] = {"sub": OWNER}
    orch.ui_clients.append(other)
    stranger = FakeUI()                         # a different user — must NOT be told
    orch.ui_sessions[stranger] = {"sub": FOREIGN}
    orch.ui_clients.append(stranger)

    await orch._teardown_owner_tunnels(host)
    assert AID not in orch.agents               # went offline
    offline = [json.loads(f) for f in other.sent if json.loads(f).get("type") == "agent_offline"]
    assert offline and offline[0]["agent_id"] == AID
    assert stranger.sent == []                  # the stranger heard nothing


# ── deliver / delete / register exception handlers are swallowed ─────────────

async def test_delivery_swallows_a_raising_low_level_send(orch, monkeypatch):
    host = FakeUI()
    orch._agent_host_sockets[id(host)] = "hs-x"
    orch.ui_sessions[host] = {"sub": OWNER}
    orch.ui_clients.append(host)

    async def _raise(ui, frame):
        raise RuntimeError("low-level send exploded")

    monkeypatch.setattr(orch, "_safe_send", _raise)
    # The push to the one host raises, but delivery must not crash — with no host
    # actually reached it reports 0, which the caller surfaces as honest 'no_host'.
    delivered = await orch.deliver_agent_bundle(OWNER, AID, {"mcp_tools.py": "c"}, "0.1.0")
    assert delivered == 0


async def test_delete_skips_foreign_sockets_and_swallows_a_send_error(orch):
    host = FakeUI()
    orch.ui_sessions[host] = {"sub": OWNER}
    await _tunnel(orch, host)
    orch.ui_clients.append(host)
    stranger = FakeUI()
    orch.ui_sessions[stranger] = {"sub": FOREIGN}
    orch.ui_clients.append(stranger)
    boom = RaisingUI()                          # an owner socket whose agent_stop send fails
    orch.ui_sessions[boom] = {"sub": OWNER}
    orch.ui_clients.append(boom)

    assert await orch.delete_user_agent(OWNER, AID) is True   # succeeds despite the send error
    assert AID not in orch.agents
    assert stranger.sent == []                                # foreign socket skipped
    row = await _t(ua.get_user_agent, orch.history.db, AID)
    assert row["status"] == "disabled" and row["deleted_at"] is not None


async def test_refused_tunnel_registration_closes_and_swallows_a_close_error(orch):
    """A foreign-owner tunnel registration is refused, audited, and the socket is
    closed — a close() that itself raises must not turn the refusal into a crash."""
    closed = {"tried": False}

    class ClosingWS(FakeUI):
        is_user_agent_tunnel = True
        owner_sub = FOREIGN                      # NOT the owner of AID → refused
        host_session_id = "hs-z"

        async def close(self, *a, **k):
            closed["tried"] = True
            raise RuntimeError("close exploded")

    ws = ClosingWS()
    await orch.register_agent(ws, RegisterAgent.from_json(_reg_frame()))
    assert closed["tried"] is True              # it attempted to close the socket
    assert AID not in orch.agents               # and did not register the agent


async def test_go_live_failure_during_registration_is_swallowed(orch, monkeypatch):
    """If go_live raises as the owner's host registers inward, the exception is
    logged, not propagated — the socket is already routed."""
    from orchestrator import user_agents as _ua_mod

    def _boom(*a, **k):
        raise RuntimeError("go_live exploded")

    monkeypatch.setattr(_ua_mod, "go_live", _boom)

    class TunnelWS(FakeUI):
        is_user_agent_tunnel = True
        owner_sub = OWNER
        host_session_id = "hs-1"

    ws = TunnelWS()
    await orch.register_agent(ws, RegisterAgent.from_json(_reg_frame()))
    # Registration proceeded (routing set) even though go_live failed.
    assert orch.agents.get(AID) is ws
