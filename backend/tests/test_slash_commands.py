"""Feature 040 (US5) — user-typed /slash-commands.

Covers: known commands expand into a prompt (not a tool call — no privileged
bypass), unknown commands produce a friendly relay (never an error), ordinary
text and slash-paths are left untouched, and discovery metadata is exposed.
Pure unit tests — no DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import slash_commands  # noqa: E402


def test_known_command_expands_to_prompt():
    out = slash_commands.expand_message("/summarize https://example.com/a")
    assert out != "/summarize https://example.com/a"
    assert "https://example.com/a" in out
    assert "summarize" in out.lower()


def test_research_command_includes_no_fabrication_guard():
    out = slash_commands.expand_message("/research fusion energy 2026")
    assert "fusion energy 2026" in out
    assert "fabricate" in out.lower()


def test_unknown_command_is_friendly_not_error():
    out = slash_commands.expand_message("/frobnicate stuff")
    # Friendly relay that lists real commands; never raises, never empty.
    assert "frobnicate" in out
    assert "/help" in out and "/summarize" in out


def test_ordinary_text_is_unchanged():
    assert slash_commands.expand_message("hello there") == "hello there"
    assert slash_commands.expand_message("the path is at /etc later") == "the path is at /etc later"


def test_slash_path_is_not_a_command():
    # A leading slash that is a path, not a clean command token, is left as text.
    assert slash_commands.expand_message("/usr/local/bin") == "/usr/local/bin"


def test_help_lists_all_commands():
    out = slash_commands.expand_message("/help")
    for name in ("/help", "/agents", "/summarize", "/research", "/weather"):
        assert name in out


def test_command_list_exposes_discovery_metadata():
    cmds = slash_commands.command_list()
    names = {c["name"] for c in cmds}
    assert {"help", "agents", "summarize", "research", "weather"} <= names
    assert all(c["usage"].startswith("/") for c in cmds)


def test_expansion_is_prompt_only_no_tool_directive():
    # The expansion is a natural-language prompt — it must not contain a literal
    # tool-call directive that would bypass the model + permission gate.
    out = slash_commands.expand_message("/weather Lexington KY")
    assert "Lexington KY" in out
    assert "tools/call" not in out and "tool_call" not in out
