"""Feature 060 credential-save completion: the surface must not be stranded.

A native client's provider Save is admitted as a durable work_admission
operation, so it completes through ``_complete_connection_operation`` and NEVER
through the chrome surface handler (``llm.py::_handle_save``). That split is why
an already-configured owner could save on macOS and be left staring at the form:
``unlock_after_save`` finds no first-run gate to close, and an Apple surface is a
full screen with no ✕ (web) and no system Back (Android).

These pin the real path — a handler-level test passes while this one fails.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.work_admission import OperationState


def _completed():
    return SimpleNamespace(state=OperationState.COMPLETED)


def _work(action="chrome_llm_save"):
    return SimpleNamespace(
        frame=SimpleNamespace(
            operation_kind="llm_credential_save",
            action=action,
            # Far enough out that the deadline never trips mid-test.
            deadline_at_monotonic=float("inf"),
        ),
        owner=SimpleNamespace(owner_user_id="owner-1"),
        operation_id="op-1",
        committed_operation=_completed(),
        auth_principal="owner-1@example",
    )


@pytest.fixture
def orch(monkeypatch):
    from orchestrator.orchestrator import Orchestrator
    from rote.rote import ROTE

    o = Orchestrator.__new__(Orchestrator)
    o.rote = ROTE()
    o.work_admission = MagicMock()
    o._send_operation_terminal = AsyncMock()
    o._send_operation_projection = AsyncMock()
    o._notify_interactive_capacity = AsyncMock()
    o._call_work_admission = AsyncMock(return_value=_completed())
    sent = []

    async def _safe_send(ws, data):
        sent.append((ws, data))
        return True

    o._safe_send = _safe_send
    o.sent = sent
    return o


def _ctx(orch, device):
    ws = MagicMock()
    orch.rote.register_device(ws, {"device_type": device})
    return SimpleNamespace(websocket=ws), ws


def _close_frames(orch):
    import json

    out = []
    for _ws, data in orch.sent:
        try:
            f = json.loads(data)
        except (TypeError, ValueError):
            continue
        if (f.get("type") == "chrome_surface"
                and f.get("surface_key") == ""
                and not (f.get("components") or [])):
            out.append(f)
    return out


@pytest.mark.parametrize("device", ["macos", "ios", "windows", "android"])
async def test_completed_save_closes_the_surface_when_no_gate_unlocked(
    orch, monkeypatch, device
):
    """The already-configured (settings-path) save: nothing to unlock."""
    from orchestrator import llm_gate

    monkeypatch.setattr(llm_gate, "unlock_after_save", AsyncMock(return_value=False))
    context, _ws = _ctx(orch, device)

    await orch._complete_connection_operation(context, _work())

    assert len(_close_frames(orch)) == 1


async def test_completed_save_does_not_double_close_when_the_gate_unlocked(
    orch, monkeypatch
):
    """First-run path: the unlock already closed + rendered the welcome."""
    from orchestrator import llm_gate

    monkeypatch.setattr(llm_gate, "unlock_after_save", AsyncMock(return_value=True))
    context, _ws = _ctx(orch, "macos")

    await orch._complete_connection_operation(context, _work())

    assert _close_frames(orch) == []


async def test_completed_save_leaves_the_web_modal_alone(orch, monkeypatch):
    """Web's modal carries a ✕ and its own success notice — untouched."""
    from orchestrator import llm_gate

    monkeypatch.setattr(llm_gate, "unlock_after_save", AsyncMock(return_value=False))
    context, _ws = _ctx(orch, "browser")

    await orch._complete_connection_operation(context, _work())

    assert _close_frames(orch) == []


async def test_legacy_llm_config_set_does_not_close_a_surface(orch, monkeypatch):
    """The typed frame isn't surface-originated; there may be nothing open."""
    from orchestrator import llm_gate

    monkeypatch.setattr(llm_gate, "unlock_after_save", AsyncMock(return_value=False))
    context, _ws = _ctx(orch, "macos")

    await orch._complete_connection_operation(context, _work(action="llm_config_set"))

    assert _close_frames(orch) == []
