"""Tests for the client-hosted Windows tools agent: the tools produce valid
SDUI components, and the A2A dispatch mirrors the backend MCPServer contract."""
from __future__ import annotations

from win_agent import agent, tools


def _types(result):
    return [c["type"] for c in result["_ui_components"]]


def test_system_info_components():
    r = tools.get_system_info()
    assert "hero" in _types(r) and "card" in _types(r)
    assert "OS" in r["_data"]


def test_list_directory(tmp_path, monkeypatch):
    # list_directory is workspace-confined (feature 067); set the workspace to
    # a tmp dir with a file in it.
    monkeypatch.setenv("ASTRAL_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    r = tools.list_directory()
    assert _types(r) == ["card"]
    assert r["_data"]["count"] >= 1


def test_list_directory_bad_path():
    r = tools.list_directory(path="Z:/no/such/folder/xyz")
    assert r["_ui_components"][0]["variant"] == "error"


def test_write_then_read_clipboard():
    # round-trips through the real Windows clipboard (harmless).
    w = tools.write_clipboard(text="astral-test-123")
    assert w["_ui_components"][0]["variant"] == "success"
    r = tools.read_clipboard()
    # read returns a card with the text (or info if clipboard tooling absent)
    assert r["_ui_components"][0]["type"] in ("card", "alert")


def test_open_path_requires_arg():
    r = tools.open_path(path="")
    assert r["_ui_components"][0]["variant"] == "warning"


# --- A2A dispatch contract ------------------------------------------------- #

def test_card_lists_all_tools(monkeypatch):
    # The dangerous run_shell tool is only advertised when the bypass flag is on;
    # with it off (default) the card lists every tool EXCEPT run_shell.
    monkeypatch.delenv("ASTRAL_DANGEROUS_BYPASS", raising=False)
    card = agent.build_card()
    assert card["agent_id"] == "windows-tools-1"
    expected = set(tools.TOOL_REGISTRY) - {"run_shell"}
    assert {s["name"] for s in card["skills"]} == expected


def test_card_lists_run_shell_when_bypass_on(monkeypatch):
    monkeypatch.setenv("ASTRAL_DANGEROUS_BYPASS", "1")
    card = agent.build_card()
    assert "run_shell" in {s["name"] for s in card["skills"]}


def test_dispatch_tools_list():
    resp = agent.dispatch({"type": "mcp_request", "request_id": "1", "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "get_system_info" in names and "notify" in names


def test_dispatch_tools_call():
    resp = agent.dispatch({"type": "mcp_request", "request_id": "2", "method": "tools/call",
                           "params": {"name": "get_system_info", "arguments": {}}})
    assert resp["request_id"] == "2"
    assert resp["ui_components"] and resp["error"] is None if "error" in resp else resp["ui_components"]


def test_dispatch_unknown_tool():
    resp = agent.dispatch({"type": "mcp_request", "request_id": "3", "method": "tools/call",
                           "params": {"name": "no_such_tool", "arguments": {}}})
    assert resp["error"]["code"] == -32601


def test_dispatch_unknown_method():
    resp = agent.dispatch({"type": "mcp_request", "request_id": "4", "method": "frobnicate"})
    assert resp["error"]["code"] == -32601


def test_register_message_shape():
    import json
    msg = json.loads(agent._register_message())
    assert msg["type"] == "register_agent"
    assert msg["agent_card"]["agent_id"] == "windows-tools-1"
