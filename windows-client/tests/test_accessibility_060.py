"""Spec 060 role/name/state/focus contracts for changed Windows controls."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ASTRAL_WIN_AGENT"] = "0"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAccessible  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton  # noqa: E402

from astral_client import app as appmod  # noqa: E402
from astral_client.app import AgentsDialog, MainWindow, TopBar  # noqa: E402


def _role(widget):
    interface = QAccessible.queryAccessibleInterface(widget)
    assert interface is not None
    return interface.role()


def test_application_status_has_stable_name_and_dynamic_state(qapp):
    topbar = TopBar("user", lambda: None, lambda: None, lambda *_: None, lambda: None)

    assert isinstance(topbar._mark, QLabel)
    assert _role(topbar._mark) == QAccessible.Role.StaticText
    assert topbar._mark.accessibleName() == "Application status"
    assert topbar._mark.accessibleDescription() == "Connecting"

    topbar.set_status("Saving credentials", "#ffffff")
    assert topbar._mark.accessibleName() == "Application status"
    assert topbar._mark.accessibleDescription() == "Saving credentials"
    topbar.close()


def test_agent_authoring_controls_expose_contextual_semantics_and_focus(
    qapp, monkeypatch
):
    monkeypatch.setenv("ASTRAL_DANGEROUS_BYPASS", "0")
    emitted = []
    dialog = AgentsDialog(None, lambda action, payload: emitted.append((action, payload)))
    dialog.set_agents(
        [
            {
                "id": "windows-tools-1",
                "name": "Windows coding",
                "description": "Local tools",
                "scopes": {"tools:read": True, "tools:write": False},
                "is_public": False,
                "_lifecycle_label": "Agent online",
            },
            {
                "id": "weather",
                "name": "Weather",
                "description": "Forecasts",
                "scopes": {},
                "is_public": True,
            },
        ]
    )
    dialog.show()
    qapp.processEvents()

    scopes = {
        checkbox.accessibleName(): checkbox
        for checkbox in dialog.findChildren(QCheckBox, "agentScopeToggle")
    }
    assert set(scopes) == {
        "Read permission for Windows coding",
        "Write permission for Windows coding",
        "Execute permission for Windows coding",
    }
    read = scopes["Read permission for Windows coding"]
    write = scopes["Write permission for Windows coding"]
    execute = scopes["Execute permission for Windows coding"]
    for checkbox in scopes.values():
        assert _role(checkbox) == QAccessible.Role.CheckBox
        assert checkbox.accessibleDescription()
        assert checkbox.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert read.isChecked()
    assert not write.isChecked()
    assert not execute.isEnabled()

    write.setFocus()
    qapp.processEvents()
    assert write.hasFocus()
    QTest.keyClick(write, Qt.Key.Key_Space)
    assert write.isChecked()
    assert emitted[-1] == (
        "set_agent_permissions",
        {"agent_id": "windows-tools-1", "scopes": {"tools:write": True}},
    )

    enable = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.property("astralAccessibilityControl") == "agent-enable"
    )
    assert _role(enable) == QAccessible.Role.Button
    assert enable.accessibleName() == "Enable Weather"
    assert enable.isEnabled()
    enable.setFocus()
    qapp.processEvents()
    assert enable.hasFocus()
    QTest.keyClick(enable, Qt.Key.Key_Space)
    assert emitted[-1] == (
        "enable_recommended_agents",
        {"source": "desktop", "agent_ids": ["weather"]},
    )

    lifecycle = dialog.findChild(QLabel, "agentLifecycleStatus")
    assert lifecycle is not None
    assert _role(lifecycle) == QAccessible.Role.StaticText
    assert lifecycle.accessibleName() == "Windows coding lifecycle status"
    assert lifecycle.accessibleDescription() == "Agent online"
    assert lifecycle.text() == "Agent online"
    dialog.close()


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(MainWindow, "_start_integrity_check", lambda self: None)
    monkeypatch.setattr(MainWindow, "_init_workspace", lambda self: None)
    monkeypatch.setattr(
        appmod,
        "load_or_create_host_id",
        lambda: "77777777-7777-4777-8777-777777777777",
    )
    win = MainWindow("ws://127.0.0.1:9/ws", "dev-token", connect=False)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_status_banner_is_a_named_keyboard_operable_button(qapp, window):
    window._show_banner("Agent offline")
    banner = window._banner

    assert isinstance(banner, QPushButton)
    assert _role(banner) == QAccessible.Role.Button
    assert banner.accessibleName() == "Status message"
    assert banner.accessibleDescription() == "Agent offline"
    assert banner.isEnabled()
    assert banner.focusPolicy() == Qt.FocusPolicy.StrongFocus

    banner.setFocus()
    qapp.processEvents()
    assert banner.hasFocus()
    QTest.keyClick(banner, Qt.Key.Key_Space)
    assert banner.isHidden()
    assert banner.accessibleDescription() == ""
