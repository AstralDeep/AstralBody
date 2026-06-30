"""Tests for the runtime workspace-directory override (feature 039 UX).

The desktop GUI lets the user pick/change the coding-agent's workspace folder at
runtime via ``set_workspace_override``. These tests prove confinement tracks the
override: a write goes to the chosen folder, a path outside it is refused, and
changing the override mid-session changes where writes land.

Pure-Python — does NOT require PySide6 (the override + confinement are Qt-free).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astral_client import audit_log  # noqa: E402
from win_agent import tools  # noqa: E402


@pytest.fixture
def auto_allow(monkeypatch):
    """Auto-allow every per-action confirmation (no Qt display in tests)."""
    monkeypatch.setattr(tools, "_confirm_action", lambda **kw: True)


@pytest.fixture
def workspace_a(tmp_path, monkeypatch):
    a = tmp_path / "ws_a"
    a.mkdir()
    monkeypatch.setenv("ASTRAL_WORKSPACE_DIR", str(a))
    tools.set_workspace_override(None)  # clear any prior override
    monkeypatch.setattr(audit_log, "_appdata_dir", lambda: str(tmp_path))
    tools.set_context(
        actor="test-user",
        correlation_id="t1",
        audit=audit_log.AuditLogger(actor="test-user"),
    )
    return a


def test_override_is_used_over_env(workspace_a, tmp_path, auto_allow):
    """set_workspace_override wins over ASTRAL_WORKSPACE_DIR."""
    b = tmp_path / "ws_b"
    b.mkdir()
    tools.set_workspace_override(str(b))
    assert tools.workspace_root() == os.path.realpath(str(b))
    w = tools.write_file(path="hello.py", content="print('hi')")
    assert w["_ui_components"][0]["variant"] == "success"
    assert (b / "hello.py").exists()
    # The env-pointed workspace did NOT receive the file.
    assert not (workspace_a / "hello.py").exists()


def test_override_confines_to_chosen_folder(workspace_a, tmp_path, auto_allow):
    b = tmp_path / "ws_b"
    b.mkdir()
    tools.set_workspace_override(str(b))
    # A traversal attempt relative to the override root is refused.
    r = tools.write_file(path="../../evil.txt", content="x")
    assert r["_ui_components"][0]["variant"] == "error"
    assert not (tmp_path / "evil.txt").exists()


def test_changing_override_changes_confinement(workspace_a, tmp_path, auto_allow):
    b = tmp_path / "ws_b"
    b.mkdir()
    tools.set_workspace_override(str(b))
    tools.write_file(path="in_b.py", content="x")
    assert (b / "in_b.py").exists()

    c = tmp_path / "ws_c"
    c.mkdir()
    tools.set_workspace_override(str(c))
    # The file written now lands in c, not b.
    tools.write_file(path="in_c.py", content="y")
    assert (c / "in_c.py").exists()
    assert not (b / "in_c.py").exists()
    # b's earlier file is untouched.
    assert (b / "in_b.py").exists()


def test_clear_override_falls_back_to_env(workspace_a, tmp_path, auto_allow):
    b = tmp_path / "ws_b"
    b.mkdir()
    tools.set_workspace_override(str(b))
    assert tools.workspace_root() == os.path.realpath(str(b))
    tools.set_workspace_override(None)
    assert tools.workspace_root() == os.path.realpath(str(workspace_a))


def test_audit_path_redaction_uses_override(workspace_a, tmp_path, auto_allow):
    """audit_log redacts paths relative to the active override, not the env."""
    b = tmp_path / "ws_b"
    b.mkdir()
    tools.set_workspace_override(str(b))
    tools.write_file(path="tracked.py", content="x")
    rows = tools._CTX["audit"].tail(3)
    write_row = next(r for r in reversed(rows) if r["tool"] == "write_file")
    # The path is workspace-relative, not an absolute path under ws_a.
    assert write_row["args"]["path"] == "tracked.py"
