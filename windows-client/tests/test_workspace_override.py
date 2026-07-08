"""Tests for the runtime workspace-directory override (feature 039 UX).

The desktop GUI lets the user pick/change the coding-agent's workspace folder at
runtime via ``set_workspace_override``. These tests prove confinement tracks the
override: a write goes to the chosen folder, a path outside it is refused, and
changing the override mid-session changes where writes land.

The override/confinement tests are pure-Python (no PySide6). The lazy-workspace
section at the bottom drives MainWindow (window-first launch: startup applies
persisted/env silently; the folder picker is deferred to first file-tool use)
and skips gracefully when PySide6 is unavailable.
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


# --- lazy workspace resolution in the GUI (window-first launch) ------------- #


class _FakeSettings:
    """QSettings stand-in so tests never read/write the real registry."""

    def __init__(self, d=None):
        self.d = dict(d or {})

    def value(self, key, default="", type=str):
        return self.d.get(key, default)

    def setValue(self, key, val):
        self.d[key] = val


@pytest.fixture
def make_win(tmp_path, monkeypatch):
    """Factory building a MainWindow with transport/integrity stubbed, settings
    isolated, HOME redirected to tmp, and the folder picker instrumented."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from astral_client import app as appmod

    class _FakeSig:
        def connect(self, *_a):
            pass

        def disconnect(self, *_a):
            pass

    class _FakeClient:
        message = _FakeSig()
        status = _FakeSig()

        def __init__(self, *_a, **_k):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def send_event(self, *_a, **_k):
            pass

    monkeypatch.setenv("ASTRAL_WIN_AGENT", "0")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("ASTRAL_WORKSPACE_DIR", raising=False)
    monkeypatch.setattr(appmod, "OrchestratorClient", _FakeClient)
    monkeypatch.setattr(
        appmod.MainWindow, "_start_integrity_check", lambda self: None
    )
    tools.set_workspace_override(None)
    made = []

    def _make(persisted="", picker=None):
        settings = _FakeSettings(
            {"workspace_dir": persisted} if persisted else {}
        )
        monkeypatch.setattr(
            appmod.MainWindow, "_settings", lambda self: settings
        )
        if picker is None:
            def picker(self, *_a, **_k):
                raise AssertionError("folder picker must not open here")
        monkeypatch.setattr(appmod.MainWindow, "_gui_pick_directory", picker)
        win = appmod.MainWindow("ws://127.0.0.1:9/ws", "dev-token")
        made.append(win)
        return win, settings

    yield _make
    for w in made:
        w.close()
    tools.set_workspace_override(None)


def test_startup_applies_persisted_without_prompt(make_win, tmp_path):
    pers = tmp_path / "persisted_ws"
    pers.mkdir()
    win, _ = make_win(persisted=str(pers))
    assert win._workspace_ready is True
    assert tools.workspace_root() == os.path.realpath(str(pers))


def test_startup_without_config_defers_picker(make_win, tmp_path):
    win, _ = make_win()
    assert win._workspace_ready is False
    # Tools fall back to the launch default until first use resolves it.
    default_root = os.path.realpath(str(tmp_path / "AstralWorkspace"))
    assert tools.workspace_root() == default_root


def test_first_tool_use_prompts_and_denies_on_redirect(make_win, tmp_path, monkeypatch):
    """First confirm with no stored workspace opens the picker; a pick that
    lands OUTSIDE the default root denies the in-flight call (it was confined
    to the old default) while the pick still applies for the retry."""
    chosen = tmp_path / "elsewhere"
    chosen.mkdir()
    win, settings = make_win(picker=lambda self, *_a, **_k: str(chosen))
    actions = []
    monkeypatch.setattr(
        type(win), "_action_dialog",
        lambda self, req: actions.append(req) or {"accepted": True, "choice": None},
    )
    first = win._show_confirm_dialog({"kind": "action", "tool": "write_file"})
    assert first == {"accepted": False, "choice": None}
    assert actions == []  # the in-flight call never reached the Allow dialog
    assert win._workspace_ready is True
    assert tools.workspace_root() == os.path.realpath(str(chosen))
    assert settings.d["workspace_dir"] == os.path.realpath(str(chosen))
    # The retry proceeds under the newly chosen root.
    second = win._show_confirm_dialog({"kind": "action", "tool": "write_file"})
    assert second["accepted"] is True
    assert len(actions) == 1


def test_first_tool_use_default_pick_proceeds(make_win, tmp_path, monkeypatch):
    """Cancelling the first-use picker adopts the default root the call was
    already confined to, so the in-flight call proceeds to the Allow dialog."""
    win, _ = make_win(picker=lambda self, *_a, **_k: None)
    actions = []
    monkeypatch.setattr(
        type(win), "_action_dialog",
        lambda self, req: actions.append(req) or {"accepted": True, "choice": None},
    )
    result = win._show_confirm_dialog({"kind": "action", "tool": "write_file"})
    assert result["accepted"] is True
    assert len(actions) == 1
    assert win._workspace_ready is True
    assert tools.workspace_root() == os.path.realpath(str(tmp_path / "AstralWorkspace"))
