"""AstralBody native Windows client — main window.

A native, 100% Qt desktop app (no embedded web view): a top bar (identity,
connection, new chat, history, agents, sign-out), a chat rail on the left and a
native SDUI canvas on the right. Inbound `ui_render`/`ui_upsert` messages are
drawn as native Qt widgets via renderer.render; button / history-row / agent
interactions post `ui_event`s back. App chrome (agents & permissions, history)
is reimplemented as native Qt dialogs driven by the SAME WS events as the web
chrome — never an embedded HTML surface.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSettings, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import theme as T
from . import confirm as _confirm
from . import integrity as _integrity
from . import __version__ as _APP_VERSION
from .protocol import OrchestratorClient, device_caps
from .renderer import RenderContext, render, supported_types as native_types, _scoped
from .streaming import stream_error_ops, stream_frame_to_ops, subscribe_ack_ops
from .chrome import chrome_render_notice


# Feature 068 (US5): slash-command discovery. Mirrors the web client's typeahead
# and the server's orchestrator/slash_commands.COMMANDS registry — the server
# expands a typed "/command" into a normal prompt; this popup just lets users
# see the options as they type. Keep in sync with the web list.
_SLASH_COMMANDS = [
    ("/help", "show available commands"),
    ("/agents", "list your enabled agents"),
    ("/summarize", "summarize a link or text"),
    ("/research", "research + cited brief"),
    ("/weather", "weather + forecast"),
]


class _SlashCommandModel(QAbstractListModel):
    """Completion model for slash commands.

    Exposes the human-readable ``name  —  description`` under ``DisplayRole`` (so
    the popup is discoverable) while ``EditRole`` is the clean ``/command ``
    token QCompleter matches against and inserts. A ``QStandardItem`` cannot do
    this — it unifies Display/Edit roles — hence this small dedicated model.
    """

    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self._commands = list(commands)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._commands)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._commands)):
            return None
        name, desc = self._commands[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{name}  —  {desc}"
        if role == Qt.ItemDataRole.EditRole:
            return name + " "
        return None


def build_slash_completer(parent=None):
    """Build a QCompleter that pops up the available slash commands when the
    user starts typing ``/``.

    The popup DISPLAYS ``name  —  description`` (so options are discoverable) but
    inserts only the clean ``/command `` token (``Qt.EditRole``) so the field is
    ready for arguments. Filtering is case-insensitive prefix matching, so ``/``
    surfaces every command and ``/sum`` narrows to ``/summarize``.
    """
    completer = QCompleter(parent)
    # Parent the model to the completer so it survives past this function
    # (PySide6 GCs an unparented model whose last Python reference is dropped).
    model = _SlashCommandModel(_SLASH_COMMANDS, completer)
    completer.setModel(model)
    completer.setCompletionRole(Qt.ItemDataRole.EditRole)  # match/insert "/command "
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    return completer


def _user_from_token(token: str) -> str:
    """Best-effort display name from a JWT (preferred_username → name → sub)."""
    if not token or token == "dev-token":
        return "Developer"
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        c = json.loads(base64.urlsafe_b64decode(part))
        return (
            c.get("preferred_username")
            or c.get("name")
            or c.get("email")
            or c.get("sub")
            or "Signed in"
        )
    except Exception:
        return "Signed in"


class ChatRail(QWidget):
    """The text-only conversation rail (mirrors the web app's chat rail)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(12, 12, 12, 12)
        self._lay.setSpacing(10)
        self._lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, 1)
        self._hint: Optional[QWidget] = None

    def _drop_hint(self) -> None:
        if self._hint is not None:
            self._hint.setParent(None)  # remove from layout immediately
            self._hint.deleteLater()
            self._hint = None

    def add(self, role: str, text: str) -> None:
        self._drop_hint()
        bubble = QFrame()
        is_user = role == "user"
        bg = T.PRIMARY_SOFT if is_user else T.SURFACE
        _scoped(
            bubble, f"background:{bg}; border:1px solid {T.BORDER}; border-radius:10px;"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        who = QLabel("You" if is_user else "Assistant")
        who.setFrameShape(QFrame.Shape.NoFrame)
        who.setStyleSheet(
            f"color:{T.MUTED}; font-size:11px; font-weight:600; background:transparent;"
        )
        body = QLabel(text)
        body.setWordWrap(True)
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setTextFormat(Qt.TextFormat.MarkdownText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f"color:{T.TEXT}; font-size:13px; background:transparent;")
        bl.addWidget(who)
        bl.addWidget(body)
        self._lay.insertWidget(self._lay.count() - 1, bubble)
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear(self) -> None:
        self._hint = None
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_empty_hint(self) -> None:
        """A gentle empty-state so a fresh chat rail isn't a blank void."""
        self.clear()
        hint = QLabel("Ask anything below, or pick an example on the canvas →")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; background:transparent; padding:24px 10px;"
        )
        self._lay.insertWidget(0, hint)
        self._hint = hint


class Canvas(QScrollArea):
    """The SDUI canvas: native widgets per structured component, keyed by id."""

    def __init__(self, ctx: RenderContext):
        super().__init__()
        self.ctx = ctx
        self.setWidgetResizable(True)
        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(18, 18, 18, 18)
        self._lay.setSpacing(14)
        self._lay.addStretch(1)
        self.setWidget(self._inner)
        self._by_id: Dict[str, QWidget] = {}

    def _insert(self, widget: QWidget) -> None:
        self._lay.insertWidget(self._lay.count() - 1, widget)

    def set_components(self, components: list) -> None:
        """Full canvas replace (a `ui_render` to the canvas region)."""
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._by_id.clear()
        for comp in components or []:
            w = render(comp, self.ctx)
            self._insert(w)
            cid = w.property("component_id")
            if cid:
                self._by_id[cid] = w

    def apply_ops(self, ops: list) -> None:
        """In-place workspace patch (a `ui_upsert`)."""
        for op in ops or []:
            kind = op.get("op", "upsert")
            cid = op.get("component_id")
            if kind == "remove":
                w = self._by_id.pop(cid, None)
                if w:
                    w.deleteLater()
                continue
            comp = op.get("component") or {}
            new_w = render(comp, self.ctx)
            new_w.setProperty("component_id", cid)
            old = self._by_id.get(cid)
            if old is not None:
                idx = self._lay.indexOf(old)
                self._lay.insertWidget(idx, new_w)
                old.deleteLater()
            else:
                self._insert(new_w)
            self._by_id[cid] = new_w


class TopBar(QFrame):
    """Native app chrome header: brand, connection status, identity + actions."""

    def __init__(self, user: str, on_new_chat, on_history, on_agents, on_sign_out):
        super().__init__()
        self.setObjectName("topbar")
        self.setStyleSheet(
            f"#topbar {{ background:{T.SURFACE}; border-bottom:1px solid {T.BORDER}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 12, 8)
        lay.setSpacing(10)

        brand = QLabel("◆  AstralBody")
        brand.setStyleSheet(
            f"color:{T.TEXT}; font-size:14px; font-weight:700; background:transparent;"
        )
        self._status = QLabel("connecting…")
        self._status.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; background:transparent; padding:2px 8px;"
        )

        self._user = QLabel(user)
        self._user.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; background:transparent;"
        )

        self.new_btn = QPushButton("＋ New chat")
        self.new_btn.setObjectName("primary")
        self.new_btn.clicked.connect(on_new_chat)
        self.history_btn = QPushButton("History")
        self.history_btn.clicked.connect(on_history)
        self.agents_btn = QPushButton("Agents")
        self.agents_btn.clicked.connect(on_agents)
        self.signout_btn = QPushButton("Sign out")
        self.signout_btn.clicked.connect(on_sign_out)
        for b in (self.new_btn, self.history_btn, self.agents_btn, self.signout_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        lay.addWidget(brand)
        lay.addWidget(self._dot())
        lay.addWidget(self._status)
        lay.addStretch(1)
        lay.addWidget(self._user)
        lay.addSpacing(6)
        lay.addWidget(self.new_btn)
        lay.addWidget(self.history_btn)
        lay.addWidget(self.agents_btn)
        lay.addWidget(self.signout_btn)

    def _dot(self) -> QLabel:
        self._statusdot = QLabel("●")
        self._statusdot.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; background:transparent;"
        )
        return self._statusdot

    def set_status(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color:{color}; font-size:12px; background:transparent; padding:2px 8px;"
        )
        self._statusdot.setStyleSheet(
            f"color:{color}; font-size:12px; background:transparent;"
        )

    def set_user(self, user: str) -> None:
        self._user.setText(user)

    def highlight_agents(self, on: bool) -> None:
        """Accent the Agents button when no tools are enabled yet (call to action)."""
        if on:
            self.agents_btn.setText("⚡ Enable agents")
            self.agents_btn.setObjectName("primary")
        else:
            self.agents_btn.setText("Agents")
            self.agents_btn.setObjectName("")
        self.agents_btn.style().unpolish(self.agents_btn)
        self.agents_btn.style().polish(self.agents_btn)


class AgentsDialog(QDialog):
    """Native 'Agents & permissions' — one-click enable + per-agent state.

    Drives the same WS actions as the web chrome (`enable_recommended_agents`,
    scoped per-agent enable). For the Windows coding agent it additionally
    exposes per-scope Read/Write/Execute toggles (write/execute are never
    granted by the consent flow, so the user grants them explicitly here) and a
    workspace-folder chooser (the directory the coding agent is confined to)."""

    def __init__(self, parent, emit, on_change_workspace=None,
                 on_verify_integrity=None):
        super().__init__(parent)
        self._emit = emit
        self._on_change_workspace = on_change_workspace
        self._on_verify_integrity = on_verify_integrity
        self.setWindowTitle("Agents & permissions")
        self.setMinimumSize(600, 640)
        self.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        title = QLabel("Agents & permissions")
        title.setStyleSheet(f"color:{T.TEXT}; font-size:18px; font-weight:700;")
        sub = QLabel(
            "Enable agents to let chats use them. The Windows coding agent "
            "reads/writes files and runs commands only inside the workspace "
            "folder you choose — grant Read/Write/Execute per scope, and each "
            "action asks for your confirmation before it runs."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{T.MUTED}; font-size:12px;")
        root.addWidget(title)
        root.addWidget(sub)

        ws_row = QHBoxLayout()
        self._ws_label = QLabel(self._workspace_label())
        self._ws_label.setStyleSheet(f"color:{T.MUTED}; font-size:11px;")
        self._ws_label.setWordWrap(True)
        ws_btn = QPushButton("Change workspace…")
        ws_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ws_btn.clicked.connect(self._change_ws)
        ws_row.addWidget(self._ws_label, 1)
        ws_row.addWidget(ws_btn)
        if self._on_verify_integrity is not None:
            verify_btn = QPushButton("Verify integrity")
            verify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            verify_btn.clicked.connect(self._verify_integrity)
            ws_row.addWidget(verify_btn)
        root.addLayout(ws_row)

        enable_all = QPushButton("Enable recommended agents (read-only)")
        enable_all.setObjectName("primary")
        enable_all.setCursor(Qt.CursorShape.PointingHandCursor)
        enable_all.clicked.connect(self._enable_all)
        root.addWidget(enable_all)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:none;")
        self._list = QWidget()
        self._listlay = QVBoxLayout(self._list)
        self._listlay.setContentsMargins(0, 4, 0, 4)
        self._listlay.setSpacing(8)
        self._listlay.addStretch(1)
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        root.addLayout(row)

    def _enable_all(self) -> None:
        self._emit("enable_recommended_agents", {"source": "desktop"})

    def _workspace_label(self) -> str:
        import win_agent.tools as _tools

        root = _tools.workspace_root()
        return f"Workspace: {root}"

    def _change_ws(self) -> None:
        if self._on_change_workspace is not None:
            self._on_change_workspace()
        # Refresh the label after the picker closes.
        self._ws_label.setText(self._workspace_label())

    def _verify_integrity(self) -> None:
        if self._on_verify_integrity is not None:
            self._on_verify_integrity()

    def _enable_one(self, agent_id: str) -> None:
        self._emit(
            "enable_recommended_agents", {"source": "desktop", "agent_ids": [agent_id]}
        )

    def _set_scope(self, agent_id: str, scope: str, enabled: bool) -> None:
        """Grant/revoke a single scope on an agent (audited server-side).

        This is the path that grants ``tools:write`` — the recommended-agents
        consent flow deliberately never grants write, so the desktop client
        must call the granular ``set_agent_permissions`` ui_event for the
        coding agent's write/execute scopes.
        """
        self._emit(
            "set_agent_permissions",
            {"agent_id": agent_id, "scopes": {scope: bool(enabled)}},
        )

    def set_agents(self, agents: List[dict]) -> None:
        while self._listlay.count() > 1:
            item = self._listlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        visible = [a for a in agents if a.get("id") not in ("__orchestrator__",)]
        for a in sorted(visible, key=lambda x: str(x.get("name", "")).lower()):
            self._listlay.insertWidget(self._listlay.count() - 1, self._row(a))

    def _row(self, a: dict) -> QWidget:
        scopes = a.get("scopes") or {}
        on = any(bool(v) for v in scopes.values())
        public = bool(a.get("is_public"))
        aid = a.get("id", "")
        # The Windows coding agent exposes write/execute scopes the user must
        # grant explicitly (the consent flow never grants write). Give it
        # per-scope toggles instead of a single Enable button.
        is_win_agent = aid == "windows-tools-1"
        card = QFrame()
        _scoped(
            card,
            f"background:{T.SURFACE}; border:1px solid {T.BORDER}; border-radius:10px;",
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(str(a.get("name", a.get("id", "Agent"))))
        name.setStyleSheet(
            f"color:{T.TEXT}; font-size:13px; font-weight:600; background:transparent;"
        )
        desc = QLabel(str(a.get("description", "") or "")[:120])
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{T.MUTED}; font-size:11px; background:transparent;")
        col.addWidget(name)
        col.addWidget(desc)
        lay.addLayout(col, 1)
        if is_win_agent:
            lay.addLayout(self._scope_toggles(aid, scopes))
        elif on:
            badge = QLabel("✓ Enabled")
            c = T.VARIANT_COLORS["success"][0]
            badge.setStyleSheet(
                f"color:{c}; font-size:12px; font-weight:600; background:transparent;"
            )
            lay.addWidget(badge)
        elif public:
            btn = QPushButton("Enable")
            btn.setObjectName("primary")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, x=aid: self._enable_one(x))
            lay.addWidget(btn)
        else:
            tag = QLabel("Private")
            tag.setStyleSheet(
                f"color:{T.MUTED}; font-size:11px; background:transparent;"
            )
            lay.addWidget(tag)
        return card

    def _scope_toggles(self, aid: str, scopes: dict) -> QHBoxLayout:
        """Per-scope Read/Write/Execute checkboxes for the Windows coding agent.

        Execute is only enabled when the local ``ASTRAL_DANGEROUS_BYPASS`` flag
        is set (mirrors the agent's own advertisement of ``run_shell``).
        """
        row = QHBoxLayout()
        row.setSpacing(8)
        bypass = os.getenv("ASTRAL_DANGEROUS_BYPASS", "0") in ("1", "true", "yes", "on")
        for scope, label, needs_bypass in (
            ("tools:read", "Read", False),
            ("tools:write", "Write", False),
            ("tools:execute", "Execute", True),
        ):
            cb = QCheckBox(label)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setChecked(bool(scopes.get(scope, False)))
            if needs_bypass and not bypass:
                cb.setEnabled(False)
                cb.setToolTip("Enable the dangerous-bypass setting to grant Execute.")
            else:
                cb.stateChanged.connect(
                    lambda st, s=scope, a=aid: self._set_scope(
                        a, s, st == Qt.Checked.value
                    )
                )
            cb.setStyleSheet(f"color:{T.TEXT}; font-size:12px; background:transparent;")
            row.addWidget(cb)
        return row


class HistoryDialog(QDialog):
    """Native recent-chats picker (the web app's history surface, as Qt)."""

    def __init__(self, parent, on_open):
        super().__init__(parent)
        self._on_open = on_open
        self.setWindowTitle("Recent chats")
        self.setMinimumSize(460, 520)
        self.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(10)
        title = QLabel("Recent chats")
        title.setStyleSheet(f"color:{T.TEXT}; font-size:18px; font-weight:700;")
        root.addWidget(title)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:none;")
        self._list = QWidget()
        self._listlay = QVBoxLayout(self._list)
        self._listlay.setContentsMargins(0, 4, 0, 4)
        self._listlay.setSpacing(6)
        self._listlay.addStretch(1)
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll, 1)

    def set_chats(self, chats: List[dict]) -> None:
        while self._listlay.count() > 1:
            item = self._listlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not chats:
            empty = QLabel("No chats yet.")
            empty.setStyleSheet(f"color:{T.MUTED}; padding:16px;")
            self._listlay.insertWidget(0, empty)
            return
        for c in chats:
            cid = c.get("id") or c.get("chat_id")
            title = c.get("title") or c.get("name") or "Untitled chat"
            btn = QPushButton(str(title))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("text-align:left; padding:10px 12px;")
            if cid:
                btn.clicked.connect(lambda _=False, x=cid: self._open(x))
            self._listlay.insertWidget(self._listlay.count() - 1, btn)

    def _open(self, chat_id: str) -> None:
        self._on_open(chat_id)
        self.accept()


class MainWindow(QMainWindow):
    # Launch-time integrity verdict, marshalled from the worker thread to the
    # GUI thread (level, message). Qt queues the emit across threads safely.
    _integrity_notice = Signal(str, str)

    def __init__(self, url: str, token: str, session=None):
        super().__init__()
        self.setWindowTitle("AstralBody — Windows")
        self.resize(1280, 860)
        self.active_chat: Optional[str] = None
        self._url = url
        self._auth_session = session
        self._reauth_tries = 0
        self._agents: List[dict] = []
        self._agents_dialog: Optional[AgentsDialog] = None
        self._history_dialog: Optional[HistoryDialog] = None
        # Live-stream seq tracker (stream-key -> last seq) for the push
        # streaming consumer; reset when the active conversation changes.
        self._stream_seq: Dict[str, int] = {}

        ctx = RenderContext(emit=self._emit)
        self.client = OrchestratorClient(
            url, token, device_caps(supported_types=native_types())
        )
        self.client.message.connect(self._on_message)
        self.client.status.connect(self._on_status)

        self._win_agent_host = os.getenv("ASTRAL_AGENT_HOST", "host.docker.internal")
        self._win_agent_port = int(os.getenv("WIN_AGENT_PORT", "8771"))
        self._win_agent_registered = False
        if os.getenv("ASTRAL_WIN_AGENT", "1") not in ("0", "false", "no"):
            try:
                import win_agent.agent as _wa

                _wa.start_agent_thread(port=self._win_agent_port)
            except Exception:
                pass

        self.topbar = TopBar(
            _user_from_token(token),
            self._new_chat,
            self._open_history,
            self._open_agents,
            self._sign_out,
        )

        self.rail = ChatRail()
        self.rail.show_empty_hint()
        self.canvas = Canvas(ctx)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._wrap(self.rail, "Conversation"))
        split.addWidget(self._wrap(self.canvas, "Canvas"))
        split.setSizes([380, 900])

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message AstralBody…  (type / for commands)")
        self._input.returnPressed.connect(self._send)
        # Feature 068 (US5): pop up the slash-command options as the user types "/".
        self._input.setCompleter(build_slash_completer(self._input))
        send = QPushButton("Send")
        send.setObjectName("primary")
        send.clicked.connect(self._send)
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 8, 12, 12)
        bottom.setSpacing(8)
        bottom.addWidget(self._input, 1)
        bottom.addWidget(send)

        root = QWidget()
        root.setObjectName("root")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.topbar)
        rl.addWidget(split, 1)
        rl.addLayout(bottom)
        self.setCentralWidget(root)
        self._input.setFocus()  # cursor ready in the message box on launch

        # Attach the cross-thread confirmation bridge so the win_agent thread
        # can ask the GUI thread to show a native Allow/Deny (or directory
        # picker) modal. Must happen on the GUI thread, before any tool call.
        _confirm.BRIDGE.attach(self._show_confirm_dialog)

        # Resolve the coding-agent workspace: a persisted QSettings choice wins,
        # else an ASTRAL_WORKSPACE_DIR env, else prompt the user to pick one.
        self._init_workspace()

        self.client.start()

        # Launch-time integrity / update check (feature 067 B.5). Verifies the
        # running build's SHA-256 + sigstore signature against the GitHub release
        # before the binary is trusted — runs on a background thread so it never
        # delays the GUI, and fails open (offline ⇒ keep running) so it can never
        # block launch. The verdict is surfaced in the top-bar status line.
        self._integrity_notice.connect(self._on_integrity_notice)
        self._start_integrity_check()

    def _wrap(self, inner: QWidget, title: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QLabel(title)
        head.setStyleSheet(
            f"color:{T.MUTED}; font-size:11px; font-weight:700; letter-spacing:1px;"
            f"padding:8px 14px; background:{T.SURFACE};"
        )
        lay.addWidget(head)
        lay.addWidget(inner, 1)
        return w

    # --- chrome actions -------------------------------------------------- #
    def _new_chat(self) -> None:
        self.active_chat = None
        self.rail.clear()
        self.rail.show_empty_hint()
        self.canvas.set_components([])
        self._stream_seq.clear()
        self.client.send_event("new_chat", {})

    def _open_agents(self) -> None:
        if self._agents_dialog is None:
            self._agents_dialog = AgentsDialog(
                self, self._emit_chrome,
                on_change_workspace=self._change_workspace,
                on_verify_integrity=self._verify_integrity_now,
            )
        self._agents_dialog.set_agents(self._agents)
        self.client.send_event("discover_agents", {})  # refresh
        self._agents_dialog.show()
        self._agents_dialog.raise_()

    def _open_history(self) -> None:
        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(self, self._load_chat)
        self.client.send_event("get_history", {})
        self._history_dialog.show()
        self._history_dialog.raise_()

    def _load_chat(self, chat_id: str) -> None:
        self.rail.clear()
        self._stream_seq.clear()
        self.client.send_event("load_chat", {"chat_id": chat_id})

    def _sign_out(self) -> None:
        if (
            QMessageBox.question(self, "Sign out", "Sign out of AstralBody?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.client.stop()
        except Exception:
            pass
        QApplication.instance().quit()

    # --- outbound -------------------------------------------------------- #
    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.rail.add("user", text)  # auto-drops the empty-state hint
        self.client.send_chat(text, self.active_chat)

    def _emit(self, action: str, payload: dict) -> None:
        if action == "chat_message":
            msg = payload.get("message", "")
            if msg:
                self.rail.add("user", msg)
            self.client.send_chat(msg, self.active_chat)
        else:
            self.client.send_event(action, payload, session_id=self.active_chat)

    def _emit_chrome(self, action: str, payload: dict) -> None:
        """Actions from native chrome dialogs (agents)."""
        self.client.send_event(action, payload, session_id=self.active_chat)

    # --- inbound --------------------------------------------------------- #
    def _on_status(self, s: str) -> None:
        nice = {"connecting": "Connecting…", "connected": "Connected"}.get(s, s)
        color = (
            T.VARIANT_COLORS["success"][0]
            if s == "connected"
            else (
                T.VARIANT_COLORS["error"][0]
                if s.startswith(("closed", "auth_required"))
                else T.MUTED
            )
        )
        if s.startswith("closed"):
            nice = "Disconnected"
            # C-3: a dropped connection (e.g. orchestrator restart) must re-send
            # register_external_agent on the next 'connected', or the win_agent
            # stays unreachable to the orchestrator until the app is relaunched.
            self._win_agent_registered = False
        elif s.startswith("auth_required"):
            nice = "Re-authenticating…"
        self.topbar.set_status(nice, color)
        if s == "connected":
            self._reauth_tries = 0
            if not self._win_agent_registered:
                self._win_agent_registered = True
                url = f"http://{self._win_agent_host}:{self._win_agent_port}"
                self.client.send_event("register_external_agent", {"url": url})
            # Pull chrome state so the native dialogs + CTA are accurate.
            self.client.send_event("discover_agents", {})
            self.client.send_event("get_history", {})
        elif (
            s.startswith("auth_required")
            and self._auth_session
            and self._reauth_tries < 2
        ):
            self._reauth_tries += 1
            new_token = self._auth_session.refresh()
            if new_token:
                self._reconnect(new_token)

    def _reconnect(self, token: str) -> None:
        try:
            self.client.stop()
        except Exception:
            pass
        self._win_agent_registered = False
        self.client = OrchestratorClient(
            self._url, token, device_caps(supported_types=native_types())
        )
        self.client.message.connect(self._on_message)
        self.client.status.connect(self._on_status)
        self.client.start()

    def _on_message(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "ui_render":
            target = msg.get("target") or "canvas"
            comps = msg.get("components") or []
            if target == "chat":
                text = _flatten_text(comps)
                if text.strip():
                    self.rail.add("assistant", text)
            elif target == "history":
                pass
            else:
                self.canvas.set_components(comps)
        elif t == "ui_upsert":
            if not msg.get("chat_id") or msg.get("chat_id") == self.active_chat:
                self.canvas.apply_ops(msg.get("ops") or [])
        elif t == "chat_created":
            self.active_chat = (msg.get("payload") or {}).get(
                "chat_id"
            ) or self.active_chat
        elif t == "chat_loaded":
            chat = msg.get("chat") or {}
            self.active_chat = chat.get("id") or self.active_chat
            self._replay_transcript(chat)
        elif t == "agent_list":
            self._agents = msg.get("agents") or []
            any_on = any(
                any(bool(v) for v in (a.get("scopes") or {}).values())
                for a in self._agents
            )
            self.topbar.highlight_agents(not any_on)
            if self._agents_dialog is not None:
                self._agents_dialog.set_agents(self._agents)
        elif t == "history_list":
            chats = msg.get("chats") or []
            if self._history_dialog is not None:
                self._history_dialog.set_chats(chats)
        elif t in ("ui_stream_data", "stream_data"):
            self._on_stream_data(msg)
        elif t in ("stream_subscribed", "stream_error", "stream_unsubscribed", "stream_list"):
            self._on_stream_control(msg)
        elif t == "chrome_render":
            self._on_chrome_render(msg)
        elif t == "chat_status":
            st = msg.get("status")
            if st in ("thinking", "executing", "fixing"):
                self.topbar.set_status(
                    msg.get("message") or st, T.VARIANT_COLORS["accent"][0]
                )
            elif st == "done":
                self._on_status("connected")

    # --- live streaming (push) + native chrome ----------------------------- #
    def _on_stream_data(self, msg: dict) -> None:
        """Render a ``ui_stream_data`` / legacy ``stream_data`` frame in place on
        the canvas (structured ``components``, seq-deduped, chat-scoped)."""
        ops = stream_frame_to_ops(
            msg, active_chat=self.active_chat, seq_state=self._stream_seq
        )
        if ops:
            self.canvas.apply_ops(ops)

    def _on_stream_control(self, msg: dict) -> None:
        """Handle stream control frames (subscribe ack / error / teardown)."""
        t = msg.get("type")
        if t == "stream_subscribed":
            ops = subscribe_ack_ops(msg)
            if ops:
                self.canvas.apply_ops(ops)
            self.topbar.set_status(
                f"Streaming {msg.get('tool_name') or 'tool'}…",
                T.VARIANT_COLORS["accent"][0],
            )
        elif t == "stream_error":
            ops = stream_error_ops(msg)
            if ops:
                self.canvas.apply_ops(ops)
            else:
                payload = msg.get("payload") or {}
                text = payload.get("message") or msg.get("error") or "stream error"
                self.topbar.set_status(f"Stream error: {text}", T.VARIANT_COLORS["error"][0])
        elif t == "stream_unsubscribed":
            # Legacy teardown ack — clear the streaming status line.
            self._on_status("connected")
        # stream_list: no native surface yet.

    def _on_chrome_render(self, msg: dict) -> None:
        """Server-pushed app-chrome is web-shell HTML; this native client renders
        chrome as Qt (driven by data actions), so we acknowledge the frame rather
        than silently dropping it — never injecting a web view."""
        notice = chrome_render_notice(msg)
        if notice:
            self.topbar.set_status(notice, T.MUTED)

    def _replay_transcript(self, chat: dict) -> None:
        """Repopulate the rail from a loaded chat's messages (best-effort)."""
        self.rail.clear()
        msgs = chat.get("messages") or chat.get("history") or []
        shown = False
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role") or ("user" if m.get("is_user") else "assistant")
            content = m.get("content") or m.get("text") or ""
            if isinstance(content, str) and content.strip():
                self.rail.add("user" if role == "user" else "assistant", content)
                shown = True
        if not shown:
            self.rail.show_empty_hint()

    # --- cross-thread confirmation + workspace (feature 067 UX) ------------- #

    def _show_confirm_dialog(self, req: dict) -> dict:
        """GUI-thread callback for the confirm bridge. Shows the right native
        modal for an ``action`` (Allow/Deny) or ``directory`` (folder pick)
        request and returns ``{"accepted": bool, "choice": <str|None>}``.

        Runs on the GUI thread (called from the QTimer poller), so Qt is safe.
        """
        kind = req.get("kind")
        if kind == "directory":
            start = req.get("default") or ""
            chosen = QFileDialog.getExistingDirectory(
                self, req.get("title") or "Choose a folder", start
            )
            if not chosen:
                return {"accepted": False, "choice": None}
            return {"accepted": True, "choice": os.path.realpath(chosen)}
        # default: action confirm
        return self._action_dialog(req)

    def _action_dialog(self, req: dict) -> dict:
        """A native Allow/Deny modal for a mutating/exec tool call.

        Shows the tool, the workspace-relative target path / command, and a
        scrollable preview of the content to write or the command to run.
        """
        tool = req.get("tool", "tool")
        path = req.get("path") or ""
        command = req.get("command") or ""
        preview = req.get("preview") or ""
        summary = req.get("summary") or ""
        dangerous = tool in ("run_shell",) or bool(req.get("dangerous"))

        dlg = QDialog(self)
        dlg.setWindowTitle("Astral wants to act on your PC")
        dlg.setMinimumSize(560, 420)
        dlg.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        title_txt = (
            "⚠ DANGEROUS — full shell access" if dangerous else "Allow this action?"
        )
        title = QLabel(title_txt)
        title.setStyleSheet(
            f"color:{T.VARIANT_COLORS['error'][0] if dangerous else T.TEXT};"
            f"font-size:15px; font-weight:700;"
        )
        lay.addWidget(title)

        if summary:
            s = QLabel(summary)
            s.setWordWrap(True)
            s.setStyleSheet(f"color:{T.TEXT}; font-size:13px;")
            lay.addWidget(s)

        meta_lines = [f"Tool: {tool}"]
        if path:
            meta_lines.append(f"Path: {path}")
        if command:
            meta_lines.append(f"Command: {command}")
        meta = QLabel("\n".join(meta_lines))
        meta.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; font-family:{T.MONO};"
            f"background:{T.SURFACE}; padding:8px; border-radius:6px;"
        )
        meta.setWordWrap(True)
        lay.addWidget(meta)

        if preview:
            pt = QPlainTextEdit()
            pt.setReadOnly(True)
            pt.setPlainText(preview[:8000])
            pt.setStyleSheet(
                f"background:{T.SURFACE_2}; color:{T.TEXT};"
                f"font-family:{T.MONO}; font-size:12px; border:1px solid {T.BORDER};"
            )
            lay.addWidget(pt, 1)

        warn = QLabel(
            "A file on your computer will be changed."
            if not dangerous
            else "This runs an ARBITRARY command with full access. Approve only if you trust it."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{T.VARIANT_COLORS['warning'][0]}; font-size:11px;")
        lay.addWidget(warn)

        row = QHBoxLayout()
        row.addStretch(1)
        deny = QPushButton("Deny")
        deny.setCursor(Qt.CursorShape.PointingHandCursor)
        deny.clicked.connect(lambda: dlg.done(0))
        allow = QPushButton("Allow" if not dangerous else "Allow (dangerous)")
        allow.setObjectName("primary")
        allow.setCursor(Qt.CursorShape.PointingHandCursor)
        allow.clicked.connect(lambda: dlg.done(1))
        row.addWidget(deny)
        row.addWidget(allow)
        lay.addLayout(row)

        accepted = dlg.exec() == 1
        return {"accepted": accepted, "choice": None}

    # --- workspace directory (the coding agent's confinement root) --------- #

    def _settings(self) -> QSettings:
        return QSettings("AstralBody", "WindowsClient")

    def _gui_pick_directory(self, title: str, default: str = "") -> Optional[str]:
        """Pick a folder on the GUI thread directly (C-1 fix).

        ``QFileDialog.getExistingDirectory`` spins its own modal loop, so it works
        on the GUI thread even during ``__init__`` (before ``app.exec()``). The
        cross-thread confirm **bridge** must NOT be used here: it is driven by a
        ``QTimer`` poller that only ticks inside the running event loop, so calling
        ``BRIDGE.request_confirm`` from the GUI thread blocks that same thread and
        the poller can never service it — the first-launch workspace prompt would
        hang until the confirm timeout. The bridge is for the win_agent thread only.
        """
        chosen = QFileDialog.getExistingDirectory(self, title, default or "")
        return os.path.realpath(chosen) if chosen else None

    def _init_workspace(self) -> None:
        """Resolve the coding-agent workspace: persisted choice > env > prompt.

        Sets the in-process override on the tools + audit modules so every
        file/command tool is confined to the chosen folder for this session.
        """
        env_dir = os.getenv("ASTRAL_WORKSPACE_DIR", "").strip()
        persisted = self._settings().value("workspace_dir", "", type=str) or ""
        chosen = persisted or env_dir
        if not chosen:
            chosen = (
                self._gui_pick_directory(
                    "Choose the folder where Astral may read & write files",
                    os.path.expanduser("~"),
                )
                or ""
            )
        if not chosen:
            chosen = os.path.join(os.path.expanduser("~"), "AstralWorkspace")
        chosen = os.path.realpath(chosen)
        try:
            os.makedirs(chosen, exist_ok=True)
        except OSError:
            chosen = os.path.join(os.path.expanduser("~"), "AstralWorkspace")
            os.makedirs(chosen, exist_ok=True)
        self._settings().setValue("workspace_dir", chosen)
        self._apply_workspace(chosen)

    def _apply_workspace(self, path: str) -> None:
        """Push the chosen workspace into the tools + audit modules + env."""
        path = os.path.realpath(path)
        os.environ["ASTRAL_WORKSPACE_DIR"] = path
        try:
            import win_agent.tools as _tools

            _tools.set_workspace_override(path)
        except Exception:  # noqa: BLE001
            pass
        self.topbar.set_status(f"Workspace: {path}", T.MUTED)

    def _change_workspace(self) -> None:
        """Reopen the directory picker; persist + apply the new choice live."""
        chosen = self._gui_pick_directory(
            "Choose a new workspace folder",
            self._settings().value("workspace_dir", "", type=str)
            or os.path.expanduser("~"),
        )
        if not chosen:
            return
        chosen = os.path.realpath(chosen)
        try:
            os.makedirs(chosen, exist_ok=True)
        except OSError:
            QMessageBox.warning(
                self, "Workspace", f"Couldn't use that folder:\n{chosen}"
            )
            return
        self._settings().setValue("workspace_dir", chosen)
        self._apply_workspace(chosen)
        QMessageBox.information(self, "Workspace", f"Workspace set to:\n{chosen}")

    # --- launch-time integrity / update check (feature 067 B.5) ------------- #

    def _start_integrity_check(self) -> None:
        """Verify the running build off the GUI thread (non-blocking, fail-open).

        Packaged builds hash ``sys.executable`` and verify it against the signed
        release manifest + sigstore bundle; the verdict is posted to the GUI
        thread via ``_integrity_notice``. Any failure to *reach* GitHub leaves
        the current build running (offline tolerance) — only a real signature
        mismatch surfaces as an error. Never blocks or crashes launch.
        """

        def _work() -> None:
            import shutil
            import tempfile

            frozen = bool(getattr(sys, "frozen", False))
            exe_path = sys.executable if frozen else ""
            workdir = tempfile.mkdtemp(prefix="astral_integrity_")
            try:
                notice = _integrity.check_at_launch(
                    _APP_VERSION, exe_path, frozen=frozen, workdir=workdir
                )
            except Exception:  # noqa: BLE001 — worker must never crash the app
                notice = {"level": "muted", "message": ""}
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
            msg = notice.get("message") or ""
            if msg:
                self._integrity_notice.emit(notice.get("level", "muted"), msg)

        threading.Thread(target=_work, name="astral-integrity", daemon=True).start()

    def _on_integrity_notice(self, level: str, message: str) -> None:
        """GUI-thread slot: surface the integrity verdict in the top-bar status."""
        color = {
            "success": T.VARIANT_COLORS["success"][0],
            "warning": T.VARIANT_COLORS["warning"][0],
            "error": T.VARIANT_COLORS["error"][0],
        }.get(level, T.MUTED)
        self.topbar.set_status(message, color)

    def _verify_integrity_now(self) -> None:
        """Manual 'Verify integrity' action (Agents dialog) — re-runs the check."""
        self.topbar.set_status("Checking integrity…", T.MUTED)
        self._start_integrity_check()


def _flatten_text(components: list) -> str:
    out = []
    for c in components or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "text" or "content" in c:
            v = c.get("content") or c.get("message") or ""
            if isinstance(v, str):
                out.append(v)
        for kid_key in ("content", "children"):
            kids = c.get(kid_key)
            if isinstance(kids, list):
                out.append(_flatten_text(kids))
    return "\n\n".join(x for x in out if x)


def configure(app: QApplication) -> None:
    """Apply the theme + a guaranteed-present UI font (Inter if installed, else
    Segoe UI) so glyphs always render — the stylesheet family alone can fall back
    to a glyph-less font under some platforms."""
    from PySide6.QtGui import QFont, QFontDatabase

    families = set(QFontDatabase.families())
    family = next(
        (f for f in ("Inter", "Segoe UI", "Arial") if f in families),
        app.font().family(),
    )
    app.setFont(QFont(family, 10))
    app.setStyleSheet(T.APP_STYLESHEET + T.ROOT_BG_STYLE)


def _http_base(ws_url: str) -> str:
    """ws://host:port/ws -> http://host:port (the orchestrator's HTTP origin)."""
    from urllib.parse import urlparse

    u = urlparse(ws_url)
    scheme = "https" if u.scheme == "wss" else "http"
    return f"{scheme}://{u.netloc}"


def resolve_auth(args):
    """Return (token, session). An explicit --token/ASTRAL_TOKEN wins (use
    'dev-token' for a mock-auth orchestrator). Otherwise, if a Keycloak authority
    is configured, run the interactive OIDC desktop login — by default with the
    dedicated public client (astral-desktop), exchanging the code DIRECTLY
    against Keycloak; with --bff it reuses the web's astral-frontend via the
    orchestrator's BFF proxy. Falls back to 'dev-token' on failure."""
    if args.token:
        return args.token, None
    if args.authority:
        try:
            from .auth import oidc_login

            bff_base = _http_base(args.url) if getattr(args, "bff", False) else None
            session = oidc_login(
                args.authority, client_id=args.client_id, bff_base=bff_base
            )
            return session.access_token, session
        except Exception as exc:  # noqa: BLE001
            print(f"OIDC login failed ({exc}); falling back to dev-token.")
    return "dev-token", None


def _prompt_config(authority: str = "", ws_url: str = "", agent_key: str = ""):
    """First-run configuration dialog (C-6).

    A bare exe downloaded from GitHub has no `KEYCLOAK_AUTHORITY`/`AGENT_API_KEY`
    in its environment, so it used to silently fall back to a dev token the
    real-auth orchestrator rejects — the app "did nothing". This captures the
    deployment settings once (persisted to QSettings). Returns
    ``(authority, ws_url, agent_key)`` or ``None`` if skipped.
    """
    dlg = QDialog()
    dlg.setWindowTitle("Configure AstralBody")
    dlg.setMinimumWidth(540)
    dlg.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(8)
    intro = QLabel(
        "Point this app at your AstralBody deployment. These are saved on this "
        "PC, so you'll only be asked once."
    )
    intro.setWordWrap(True)
    intro.setStyleSheet(f"color:{T.MUTED}; font-size:12px;")
    lay.addWidget(intro)

    def _field(label: str, value: str, placeholder: str) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{T.TEXT}; font-size:12px; font-weight:600;")
        lay.addWidget(lbl)
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        lay.addWidget(edit)
        return edit

    auth_e = _field("Keycloak realm URL", authority,
                    "https://iam.example.edu/realms/Astral")
    url_e = _field("Orchestrator WebSocket URL", ws_url or "ws://127.0.0.1:8001/ws",
                   "ws://127.0.0.1:8001/ws")
    key_e = _field("Agent API key (optional)", agent_key,
                   "leave blank if your deployment doesn't require one")
    key_e.setEchoMode(QLineEdit.EchoMode.Password)

    row = QHBoxLayout()
    row.addStretch(1)
    skip = QPushButton("Skip")
    skip.setCursor(Qt.CursorShape.PointingHandCursor)
    skip.clicked.connect(lambda: dlg.done(0))
    save = QPushButton("Save")
    save.setObjectName("primary")
    save.setCursor(Qt.CursorShape.PointingHandCursor)
    save.clicked.connect(lambda: dlg.done(1))
    row.addWidget(skip)
    row.addWidget(save)
    lay.addLayout(row)

    if dlg.exec() != 1:
        return None
    return (
        auth_e.text().strip(),
        url_e.text().strip() or "ws://127.0.0.1:8001/ws",
        key_e.text().strip(),
    )


def _resolve_config(args, *, settings, prompt) -> None:
    """C-6: resolve deployment config with precedence env > QSettings > prompt.

    Mutates ``args`` (authority/url) and ``os.environ['AGENT_API_KEY']`` so the
    rest of startup (OIDC login + the win_agent registration) works for a bare
    download. Prompts (once, persisting) only when there's no authority and no
    explicit token. ``settings``/``prompt`` are injected for testability.
    """
    authority = (os.getenv("KEYCLOAK_AUTHORITY")
                 or settings.value("config/authority", "", type=str) or "")
    ws_url = (os.getenv("ASTRAL_WS_URL")
              or settings.value("config/ws_url", "", type=str)
              or "ws://127.0.0.1:8001/ws")
    agent_key = (os.getenv("AGENT_API_KEY")
                 or settings.value("config/agent_key", "", type=str) or "")

    if not authority and not args.token:
        vals = prompt(authority, ws_url, agent_key)
        if vals:
            authority, ws_url, agent_key = vals
            settings.setValue("config/authority", authority)
            settings.setValue("config/ws_url", ws_url)
            settings.setValue("config/agent_key", agent_key)

    args.authority = authority
    args.url = ws_url
    if agent_key:
        os.environ["AGENT_API_KEY"] = agent_key


def main() -> int:
    ap = argparse.ArgumentParser(description="AstralBody native Windows client")
    ap.add_argument(
        "--url", default=os.getenv("ASTRAL_WS_URL", "ws://127.0.0.1:8001/ws")
    )
    ap.add_argument("--token", default=os.getenv("ASTRAL_TOKEN", ""))
    ap.add_argument("--authority", default=os.getenv("KEYCLOAK_AUTHORITY", ""))
    # Dedicated public client (default): the desktop exchanges the auth code
    # directly against Keycloak. See docs/keycloak-windows-client-setup.md.
    ap.add_argument(
        "--client-id",
        default=(
            os.getenv("ASTRAL_CLIENT_ID")
            or os.getenv("KEYCLOAK_DESKTOP_CLIENT_ID")
            or "astral-desktop"
        ),
    )
    # Legacy: reuse the web's confidential astral-frontend client by proxying
    # the token exchange through the orchestrator's BFF (POST /auth/token).
    ap.add_argument(
        "--bff",
        action="store_true",
        default=os.getenv("ASTRAL_AUTH_BFF", "").lower() in ("1", "true", "yes"),
    )
    args = ap.parse_args()

    app = QApplication(sys.argv)
    configure(app)
    # C-6: resolve/capture deployment config (authority, ws url, agent key) so a
    # bare-downloaded exe is usable without env vars instead of silently failing.
    _resolve_config(
        args, settings=QSettings("AstralBody", "WindowsClient"), prompt=_prompt_config
    )
    token, session = resolve_auth(args)
    win = MainWindow(args.url, token, session=session)
    win.show()
    win.raise_()
    win.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
