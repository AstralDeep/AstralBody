"""Feature 052 — the orchestrator's off-loop inner seams execute for real.

Drives the ``get_history``/``load_chat`` WS actions, the legacy
combine/condense reconciliation, and the delegation scope-read through a live
Orchestrator so the ``asyncio.to_thread`` inner functions introduced by the
perf pass (``_hydrate_loaded_chat``, ``_stamp_and_snapshot``,
``_scope_reads``) run end-to-end instead of being replicated in test code.
Requires the docker-compose Postgres; skipped where unreachable.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://fake.api")
os.environ.setdefault("LLM_MODEL", "test-model")

pytestmark = pytest.mark.asyncio

USER_ID = "test_user"


def _fresh_socket():
    """A VirtualWebSocket capturing every frame the handlers send."""
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket
    task = BackgroundTask(task_id=uuid.uuid4().hex, chat_id="", user_id="")
    return VirtualWebSocket(task)


@pytest.fixture(scope="module")
def orch():
    """One real Orchestrator (mock auth) shared by the module's tests.

    Mock auth must be forced under BOTH env names AFTER imports: the
    ``shared`` package normalizes ``USE_MOCK_AUTH``/``VITE_USE_MOCK_AUTH``
    at import time and a container-exported ``USE_MOCK_AUTH=false`` would
    otherwise win over a module-level assignment.
    """
    saved = {name: os.environ.get(name)
             for name in ("USE_MOCK_AUTH", "VITE_USE_MOCK_AUTH")}
    os.environ["USE_MOCK_AUTH"] = "true"
    os.environ["VITE_USE_MOCK_AUTH"] = "true"
    from orchestrator.orchestrator import Orchestrator
    try:
        yield Orchestrator()
    except Exception as exc:
        pytest.skip(f"orchestrator/database unavailable: {exc}")
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture()
async def registered_ws(orch):
    """A VirtualWebSocket that completed the register_ui handshake."""
    ws = _fresh_socket()
    orch._registered_events[id(ws)] = asyncio.Event()
    await orch.handle_ui_message(ws, json.dumps(
        {"type": "register_ui", "token": "dev-token", "device": {}}))
    assert ws in orch.ui_sessions
    return ws


@pytest.fixture()
def chat_env(orch):
    """A real chat owned by the mock-auth user; deleted on teardown."""
    chat_id = orch.history.create_chat(user_id=USER_ID)
    yield chat_id
    orch.history.delete_chat(chat_id, user_id=USER_ID)


def _frames(ws, frame_type):
    return [f for f in ws.task.outputs if f.get("type") == frame_type]


async def test_get_history_pushes_skeleton_then_list(orch, registered_ws):
    ws = registered_ws
    await orch.handle_ui_message(ws, json.dumps(
        {"type": "ui_event", "action": "get_history", "payload": {}}))
    listings = _frames(ws, "history_list")
    assert listings, "get_history must answer with a history_list frame"
    assert isinstance(listings[-1].get("chats"), list)


async def test_load_chat_hydrates_transcript_html_off_loop(
        orch, registered_ws, chat_env):
    ws, chat_id = registered_ws, chat_env
    await asyncio.to_thread(
        orch.history.add_message, chat_id, "user", "show me my labs",
        user_id=USER_ID)
    await asyncio.to_thread(
        orch.history.add_message, chat_id, "assistant",
        [{"type": "alert", "message": "Lab results ready", "variant": "info"},
         {"type": "table", "title": "Labs", "headers": ["Test"], "rows": [["A1C"]]}],
        user_id=USER_ID)

    await orch.handle_ui_message(ws, json.dumps(
        {"type": "ui_event", "action": "load_chat",
         "payload": {"chat_id": chat_id}}))

    loaded = _frames(ws, "chat_loaded")
    assert loaded, "load_chat must answer with a chat_loaded frame"
    messages = loaded[-1]["chat"]["messages"]
    comp_msg = next(m for m in messages if isinstance(m["content"], list))
    assert "Lab results ready" in comp_msg.get("html", "")
    assert "<table" not in comp_msg.get("html", "")
    text_msg = next(m for m in messages if isinstance(m["content"], str))
    assert "html" not in text_msg


async def test_load_chat_rehydrates_attachment_chips(
        orch, registered_ws, chat_env, monkeypatch):
    ws, chat_id = registered_ws, chat_env
    await asyncio.to_thread(
        orch.history.add_message, chat_id, "user", "read this file",
        user_id=USER_ID)

    await asyncio.to_thread(
        orch.history.add_message, chat_id, "assistant", "no chips for me",
        user_id=USER_ID)

    from orchestrator.attachments.message_attachment_repo import (
        MessageAttachmentRepository,
    )
    from orchestrator.attachments.repository import AttachmentRepository
    att = SimpleNamespace(attachment_id="att-052", filename="notes.md",
                          category="text")
    monkeypatch.setattr(
        MessageAttachmentRepository, "list_for_message",
        lambda self, message_id, user_id: [{"attachment_id": "att-052"}])
    monkeypatch.setattr(
        AttachmentRepository, "get_by_id",
        lambda self, attachment_id, user_id: att)

    await orch.handle_ui_message(ws, json.dumps(
        {"type": "ui_event", "action": "load_chat",
         "payload": {"chat_id": chat_id}}))

    loaded = _frames(ws, "chat_loaded")
    assert loaded
    user_msg = next(m for m in loaded[-1]["chat"]["messages"]
                    if m["role"] == "user")
    assert user_msg.get("attachments") == [
        {"attachment_id": "att-052", "filename": "notes.md", "category": "text"}]
    assistant_msg = next(m for m in loaded[-1]["chat"]["messages"]
                         if m["role"] == "assistant")
    assert "attachments" not in assistant_msg


async def test_load_chat_survives_transcript_render_failure(
        orch, registered_ws, chat_env, monkeypatch):
    ws, chat_id = registered_ws, chat_env
    await asyncio.to_thread(
        orch.history.add_message, chat_id, "assistant",
        [{"type": "alert", "message": "boom bait", "variant": "info"}],
        user_id=USER_ID)

    from orchestrator.orchestrator import Orchestrator

    def _boom(content):
        raise RuntimeError("renderer down")

    monkeypatch.setattr(Orchestrator, "_transcript_html", staticmethod(_boom))

    await orch.handle_ui_message(ws, json.dumps(
        {"type": "ui_event", "action": "load_chat",
         "payload": {"chat_id": chat_id}}))

    loaded = _frames(ws, "chat_loaded")
    assert loaded, "transcript render failure must not break load_chat"
    assert all("html" not in m for m in loaded[-1]["chat"]["messages"])


async def test_load_chat_survives_attachment_rehydration_failure(
        orch, registered_ws, chat_env, monkeypatch):
    ws, chat_id = registered_ws, chat_env
    await asyncio.to_thread(
        orch.history.add_message, chat_id, "user", "hello", user_id=USER_ID)

    from orchestrator.attachments.message_attachment_repo import (
        MessageAttachmentRepository,
    )

    def _boom(self, message_id, user_id):
        raise RuntimeError("link repo down")

    monkeypatch.setattr(MessageAttachmentRepository, "list_for_message", _boom)

    await orch.handle_ui_message(ws, json.dumps(
        {"type": "ui_event", "action": "load_chat",
         "payload": {"chat_id": chat_id}}))

    loaded = _frames(ws, "chat_loaded")
    assert loaded, "chip re-hydration failure must not break load_chat"
    assert loaded[-1]["chat"]["id"] == chat_id


async def test_reconcile_legacy_replacement_stamps_identities(orch, chat_env):
    chat_id = chat_env
    now_ms = int(time.time() * 1000)

    def _seed_rows():
        db = orch.history.db
        db.execute(
            "INSERT INTO saved_components "
            "(id, chat_id, user_id, component_data, component_type, title, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), chat_id, USER_ID,
             json.dumps({"type": "metric", "title": "Fresh", "value": "1",
                         "_source_agent": "agent-a", "_source_tool": "tool-a",
                         "_source_params": {}}),
             "metric", "Fresh", now_ms))
        db.execute(
            "INSERT INTO saved_components "
            "(id, chat_id, user_id, component_data, component_type, title, "
            "created_at, component_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), chat_id, USER_ID,
             json.dumps({"type": "text", "content": "kept",
                         "component_id": "wc_prestamped"}),
             "text", "Kept", now_ms + 1, "wc_prestamped"))
        db.execute(
            "INSERT INTO saved_components "
            "(id, chat_id, user_id, component_data, component_type, title, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), chat_id, USER_ID, "not-json{",
             "text", "Broken", now_ms + 2))

    await asyncio.to_thread(_seed_rows)
    await orch._reconcile_legacy_replacement(
        None, chat_id, USER_ID, cause="combine_components")

    rows = await asyncio.to_thread(orch.workspace.live_rows, chat_id, USER_ID)
    by_title = {r["title"]: r for r in rows}
    assert by_title["Fresh"]["component_id"], "fresh legacy row must be stamped"
    assert by_title["Kept"]["component_id"] == "wc_prestamped"
    assert by_title["Broken"]["component_id"] is None
    count = await asyncio.to_thread(
        orch.workspace.count_snapshots, chat_id, USER_ID)
    assert count >= 1


async def test_reconcile_legacy_replacement_ignores_empty_chat(orch):
    await orch._reconcile_legacy_replacement(None, "", USER_ID, cause="noop")


async def test_get_delegation_token_scopes_off_loop(orch, monkeypatch):
    from shared.protocol import AgentCard, AgentSkill
    agent_id = f"deleg-test-{uuid.uuid4().hex[:8]}"
    card = AgentCard(
        name="Delegation Test", description="d", agent_id=agent_id,
        skills=[
            AgentSkill(name="a", description="", id="tool_a", scope="tools:read"),
            AgentSkill(name="b", description="", id="tool_b", scope="tools:read"),
            AgentSkill(name="c", description="", id="tool_c", scope="tools:read"),
        ])
    orch.agent_cards[agent_id] = card
    orch.security_flags[agent_id] = {"tool_b": {"blocked": True}}
    monkeypatch.setattr(
        orch.tool_permissions, "is_tool_allowed",
        lambda user_id, aid, tool: tool != "tool_c")
    monkeypatch.setattr(
        orch.tool_permissions, "get_enabled_scope_names",
        lambda user_id, aid: ["tools:read"])

    exchanged = {}

    class _StubDelegation:
        async def exchange_token_for_agent(self, raw_token, aid, allowed_tools,
                                           user_id, enabled_scopes):
            exchanged.update(raw_token=raw_token, allowed_tools=allowed_tools,
                             enabled_scopes=enabled_scopes)
            return {"access_token": "delegated-token"}

    monkeypatch.setattr(orch, "delegation", _StubDelegation())

    ws = _fresh_socket()
    orch.ui_sessions[ws] = {"sub": USER_ID, "_raw_token": "raw-user-token"}
    try:
        token = await orch._get_delegation_token(ws, agent_id, USER_ID)
        assert token == "delegated-token"
        assert exchanged["raw_token"] == "raw-user-token"
        assert exchanged["allowed_tools"] == ["tool_a"]
        assert exchanged["enabled_scopes"] == ["tools:read"]

        assert await orch._get_delegation_token(ws, "missing-agent", USER_ID) is None
        orch.ui_sessions[ws] = {"sub": USER_ID}
        assert await orch._get_delegation_token(ws, agent_id, USER_ID) is None
    finally:
        orch.ui_sessions.pop(ws, None)
        orch.agent_cards.pop(agent_id, None)
        orch.security_flags.pop(agent_id, None)
