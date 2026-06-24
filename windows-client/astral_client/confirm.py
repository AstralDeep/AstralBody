"""Cross-thread confirmation bridge for the Windows coding agent.

The coding tools run on the win_agent's daemon thread (its own asyncio loop),
but a native Qt dialog must be shown on the GUI main thread. This module is the
thread-safe bridge between them: a tool calls ``request_confirm`` (blocking,
from the agent thread); the GUI thread's ``QTimer`` poller picks up the request,
shows the right native dialog, and posts the reply on a thread-safe queue.

Two request kinds:

* ``"action"`` — a mutating/exec action needs an explicit Allow / Deny before
  it touches disk or runs a command. The dialog shows the tool name, the
  workspace-relative target, and a scrollable preview (file content / command).
* ``"directory"`` — ask the user to pick a workspace folder
  (``QFileDialog.getExistingDirectory``); returns the chosen path or ``None``.

Fail-closed: a timeout (``ASTRAL_CONFIRM_TIMEOUT``, default 300 s) or any bridge
error is treated as **declined** — no action is ever taken without an explicit
Allow. Mutating tools therefore never silently proceed when the GUI is absent
(headless test runs stub the bridge with an auto-reply, see the tests).

Pure-Python unit-testable: the poller is a plain function over a ``queue.Queue``,
so tests inject a fake "show dialog" callback and drive the poller without a
real Qt display. Qt is imported lazily inside the GUI-side callback so importing
this module never requires PySide6.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("astral.confirm")

_DEFAULT_TIMEOUT = 300  # seconds; overridable via ASTRAL_CONFIRM_TIMEOUT


def _timeout() -> float:
    try:
        return max(
            5.0, float(os.getenv("ASTRAL_CONFIRM_TIMEOUT", str(_DEFAULT_TIMEOUT)))
        )
    except ValueError:
        return float(_DEFAULT_TIMEOUT)


class _Bridge:
    """Singleton bridge. The GUI thread attaches once at startup; the agent
    thread calls ``request_confirm`` per action."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._reply: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._attached = False
        self._poller = None  # QTimer on the GUI thread, if Qt is attached

    def attach(self, show_fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Called once on the GUI thread. ``show_fn`` displays the dialog for a
        request dict and returns the reply dict
        ``{"accepted": bool, "choice": Optional[str]}``.

        Installs a ``QTimer`` that polls ``self._q`` on the GUI event loop.
        """
        with self._lock:
            self._show_fn = show_fn
            self._attached = True

        # Lazy Qt import — only the GUI thread has a QApplication.
        try:
            from PySide6.QtCore import QTimer
        except Exception:  # noqa: BLE001 — Qt optional in test/headless
            logger.info("confirm bridge attached without Qt (headless/test mode)")
            return

        timer = QTimer()
        timer.setInterval(100)  # ms
        timer.timeout.connect(self._drain_once)
        timer.start()
        self._poller = timer
        # Keep a reference so the timer isn't GC'd. The QApplication owns it
        # for the process lifetime; this is belt-and-braces.
        self._timer_ref = timer

    def _drain_once(self) -> None:
        """GUI-thread tick: drain one pending request (if any) and show it."""
        try:
            req = self._q.get_nowait()
        except queue.Empty:
            return
        try:
            reply = self._show_fn(req)
        except Exception as exc:  # noqa: BLE001 — never raise on the GUI thread
            logger.warning("confirm dialog failed: %s", exc)
            reply = {"accepted": False, "choice": None, "reason": "dialog_error"}
        self._reply.put(reply)

    def request_confirm(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Called from the agent thread. Blocks until the GUI replies or the
        timeout elapses. Returns ``{"accepted": bool, "choice": ...}``.

        If the bridge is not attached (no GUI — e.g. a standalone agent run or
        a test that didn't stub it), returns **declined** (fail-closed).
        """
        with self._lock:
            attached = self._attached
        if not attached:
            return {"accepted": False, "choice": None, "reason": "no_gui"}
        self._q.put(req)
        try:
            reply = self._reply.get(timeout=_timeout())
        except queue.Empty:
            logger.warning(
                "confirm request timed out after %ss: %s", _timeout(), req.get("kind")
            )
            return {"accepted": False, "choice": None, "reason": "timeout"}
        return reply


# Module-level singleton — one bridge per process.
BRIDGE = _Bridge()


# --------------------------------------------------------------------------- #
# Convenience wrappers for the two request kinds (called from tools.py)
# --------------------------------------------------------------------------- #


def confirm_action(
    *,
    tool: str,
    path: str = "",
    command: str = "",
    preview: str = "",
    summary: str = "",
) -> bool:
    """Ask the user to Allow/Deny a mutating action. Returns True iff allowed.

    ``preview`` is the scrollable text shown in the dialog (file content for
    write/edit, the command line for run_command/run_shell). Fail-closed on
    timeout / no-GUI / dialog error.
    """
    req: Dict[str, Any] = {
        "kind": "action",
        "tool": tool,
        "path": path,
        "command": command,
        "preview": preview,
        "summary": summary,
    }
    reply = BRIDGE.request_confirm(req)
    return bool(reply.get("accepted"))


def pick_directory(
    *, title: str = "Choose the folder Astral may read & write", default: str = ""
) -> Optional[str]:
    """Ask the user to pick a folder. Returns the absolute path or None."""
    req: Dict[str, Any] = {"kind": "directory", "title": title, "default": default}
    reply = BRIDGE.request_confirm(req)
    if not reply.get("accepted"):
        return None
    choice = reply.get("choice")
    return choice or None
