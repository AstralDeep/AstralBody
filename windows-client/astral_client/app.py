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
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from . import theme as T
from .protocol import OrchestratorClient, device_caps
from .renderer import RenderContext, render, supported_types as native_types, _scoped


def _user_from_token(token: str) -> str:
    """Best-effort display name from a JWT (preferred_username → name → sub)."""
    if not token or token == "dev-token":
        return "Developer"
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        c = json.loads(base64.urlsafe_b64decode(part))
        return (c.get("preferred_username") or c.get("name") or c.get("email")
                or c.get("sub") or "Signed in")
    except Exception:
        return "Signed in"


class ChatRail(QWidget):
    """The text-only conversation rail (mirrors the web app's chat rail)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._inner = QWidget(); self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(12, 12, 12, 12); self._lay.setSpacing(10)
        self._lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, 1)
        self._hint: Optional[QWidget] = None

    def _drop_hint(self) -> None:
        if self._hint is not None:
            self._hint.setParent(None)   # remove from layout immediately
            self._hint.deleteLater()
            self._hint = None

    def add(self, role: str, text: str) -> None:
        self._drop_hint()
        bubble = QFrame()
        is_user = role == "user"
        bg = T.PRIMARY_SOFT if is_user else T.SURFACE
        _scoped(bubble, f"background:{bg}; border:1px solid {T.BORDER}; border-radius:10px;")
        bl = QVBoxLayout(bubble); bl.setContentsMargins(12, 8, 12, 8)
        who = QLabel("You" if is_user else "Assistant")
        who.setFrameShape(QFrame.Shape.NoFrame)
        who.setStyleSheet(f"color:{T.MUTED}; font-size:11px; font-weight:600; background:transparent;")
        body = QLabel(text); body.setWordWrap(True)
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setTextFormat(Qt.TextFormat.MarkdownText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f"color:{T.TEXT}; font-size:13px; background:transparent;")
        bl.addWidget(who); bl.addWidget(body)
        self._lay.insertWidget(self._lay.count() - 1, bubble)
        bar = self._scroll.verticalScrollBar(); bar.setValue(bar.maximum())

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
        hint.setStyleSheet(f"color:{T.MUTED}; font-size:12px; background:transparent; padding:24px 10px;")
        self._lay.insertWidget(0, hint)
        self._hint = hint


class Canvas(QScrollArea):
    """The SDUI canvas: native widgets per structured component, keyed by id."""

    def __init__(self, ctx: RenderContext):
        super().__init__()
        self.ctx = ctx
        self.setWidgetResizable(True)
        self._inner = QWidget(); self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(18, 18, 18, 18); self._lay.setSpacing(14)
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
            f"#topbar {{ background:{T.SURFACE}; border-bottom:1px solid {T.BORDER}; }}")
        lay = QHBoxLayout(self); lay.setContentsMargins(14, 8, 12, 8); lay.setSpacing(10)

        brand = QLabel("◆  AstralBody")
        brand.setStyleSheet(
            f"color:{T.TEXT}; font-size:14px; font-weight:700; background:transparent;")
        self._status = QLabel("connecting…")
        self._status.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; background:transparent; padding:2px 8px;")

        self._user = QLabel(user)
        self._user.setStyleSheet(
            f"color:{T.MUTED}; font-size:12px; background:transparent;")

        self.new_btn = QPushButton("＋ New chat"); self.new_btn.setObjectName("primary")
        self.new_btn.clicked.connect(on_new_chat)
        self.history_btn = QPushButton("History"); self.history_btn.clicked.connect(on_history)
        self.agents_btn = QPushButton("Agents"); self.agents_btn.clicked.connect(on_agents)
        self.signout_btn = QPushButton("Sign out"); self.signout_btn.clicked.connect(on_sign_out)
        for b in (self.new_btn, self.history_btn, self.agents_btn, self.signout_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        lay.addWidget(brand)
        lay.addWidget(self._dot()); lay.addWidget(self._status)
        lay.addStretch(1)
        lay.addWidget(self._user)
        lay.addSpacing(6)
        lay.addWidget(self.new_btn); lay.addWidget(self.history_btn)
        lay.addWidget(self.agents_btn); lay.addWidget(self.signout_btn)

    def _dot(self) -> QLabel:
        self._statusdot = QLabel("●")
        self._statusdot.setStyleSheet(f"color:{T.MUTED}; font-size:12px; background:transparent;")
        return self._statusdot

    def set_status(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color:{color}; font-size:12px; background:transparent; padding:2px 8px;")
        self._statusdot.setStyleSheet(f"color:{color}; font-size:12px; background:transparent;")

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
    scoped per-agent enable). Advanced per-tool/credential config stays in the
    web app; this covers the everyday need: turn agents on so chats can act."""

    def __init__(self, parent, emit):
        super().__init__(parent)
        self._emit = emit
        self.setWindowTitle("Agents & permissions")
        self.setMinimumSize(560, 600)
        self.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
        root = QVBoxLayout(self); root.setContentsMargins(18, 18, 18, 16); root.setSpacing(12)

        title = QLabel("Agents & permissions")
        title.setStyleSheet(f"color:{T.TEXT}; font-size:18px; font-weight:700;")
        sub = QLabel("Enabling grants read-only permissions for the built-in agents — "
                     "search, data, file and system reads, never write access. "
                     "Each agent can be turned on individually below.")
        sub.setWordWrap(True); sub.setStyleSheet(f"color:{T.MUTED}; font-size:12px;")
        root.addWidget(title); root.addWidget(sub)

        enable_all = QPushButton("Enable recommended agents (read-only)")
        enable_all.setObjectName("primary"); enable_all.setCursor(Qt.CursorShape.PointingHandCursor)
        enable_all.clicked.connect(self._enable_all)
        root.addWidget(enable_all)

        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:none;")
        self._list = QWidget(); self._listlay = QVBoxLayout(self._list)
        self._listlay.setContentsMargins(0, 4, 0, 4); self._listlay.setSpacing(8)
        self._listlay.addStretch(1)
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll, 1)

        close = QPushButton("Close"); close.clicked.connect(self.accept)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(close)
        root.addLayout(row)

    def _enable_all(self) -> None:
        self._emit("enable_recommended_agents", {"source": "desktop"})

    def _enable_one(self, agent_id: str) -> None:
        self._emit("enable_recommended_agents", {"source": "desktop", "agent_ids": [agent_id]})

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
        card = QFrame()
        _scoped(card, f"background:{T.SURFACE}; border:1px solid {T.BORDER}; border-radius:10px;")
        lay = QHBoxLayout(card); lay.setContentsMargins(14, 10, 12, 10); lay.setSpacing(10)
        col = QVBoxLayout(); col.setSpacing(2)
        name = QLabel(str(a.get("name", a.get("id", "Agent"))))
        name.setStyleSheet(f"color:{T.TEXT}; font-size:13px; font-weight:600; background:transparent;")
        desc = QLabel(str(a.get("description", "") or "")[:120])
        desc.setWordWrap(True); desc.setStyleSheet(f"color:{T.MUTED}; font-size:11px; background:transparent;")
        col.addWidget(name); col.addWidget(desc)
        lay.addLayout(col, 1)
        if on:
            badge = QLabel("✓ Enabled")
            c = T.VARIANT_COLORS["success"][0]
            badge.setStyleSheet(f"color:{c}; font-size:12px; font-weight:600; background:transparent;")
            lay.addWidget(badge)
        elif public:
            btn = QPushButton("Enable"); btn.setObjectName("primary")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, x=a.get("id"): self._enable_one(x))
            lay.addWidget(btn)
        else:
            tag = QLabel("Private")
            tag.setStyleSheet(f"color:{T.MUTED}; font-size:11px; background:transparent;")
            lay.addWidget(tag)
        return card


class HistoryDialog(QDialog):
    """Native recent-chats picker (the web app's history surface, as Qt)."""

    def __init__(self, parent, on_open):
        super().__init__(parent)
        self._on_open = on_open
        self.setWindowTitle("Recent chats")
        self.setMinimumSize(460, 520)
        self.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
        root = QVBoxLayout(self); root.setContentsMargins(18, 18, 18, 16); root.setSpacing(10)
        title = QLabel("Recent chats")
        title.setStyleSheet(f"color:{T.TEXT}; font-size:18px; font-weight:700;")
        root.addWidget(title)
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:none;")
        self._list = QWidget(); self._listlay = QVBoxLayout(self._list)
        self._listlay.setContentsMargins(0, 4, 0, 4); self._listlay.setSpacing(6)
        self._listlay.addStretch(1)
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll, 1)

    def set_chats(self, chats: List[dict]) -> None:
        while self._listlay.count() > 1:
            item = self._listlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not chats:
            empty = QLabel("No chats yet."); empty.setStyleSheet(f"color:{T.MUTED}; padding:16px;")
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

        ctx = RenderContext(emit=self._emit)
        self.client = OrchestratorClient(url, token, device_caps(supported_types=native_types()))
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

        self.topbar = TopBar(_user_from_token(token), self._new_chat, self._open_history,
                             self._open_agents, self._sign_out)

        self.rail = ChatRail(); self.rail.show_empty_hint()
        self.canvas = Canvas(ctx)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._wrap(self.rail, "Conversation"))
        split.addWidget(self._wrap(self.canvas, "Canvas"))
        split.setSizes([380, 900])

        self._input = QLineEdit(); self._input.setPlaceholderText("Message AstralBody…")
        self._input.returnPressed.connect(self._send)
        send = QPushButton("Send"); send.setObjectName("primary"); send.clicked.connect(self._send)
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom = QHBoxLayout(); bottom.setContentsMargins(12, 8, 12, 12); bottom.setSpacing(8)
        bottom.addWidget(self._input, 1); bottom.addWidget(send)

        root = QWidget(); root.setObjectName("root")
        rl = QVBoxLayout(root); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        rl.addWidget(self.topbar)
        rl.addWidget(split, 1)
        rl.addLayout(bottom)
        self.setCentralWidget(root)
        self._input.setFocus()   # cursor ready in the message box on launch
        self.client.start()

    def _wrap(self, inner: QWidget, title: str) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        head = QLabel(title)
        head.setStyleSheet(f"color:{T.MUTED}; font-size:11px; font-weight:700; letter-spacing:1px;"
                           f"padding:8px 14px; background:{T.SURFACE};")
        lay.addWidget(head); lay.addWidget(inner, 1)
        return w

    # --- chrome actions -------------------------------------------------- #
    def _new_chat(self) -> None:
        self.active_chat = None
        self.rail.clear(); self.rail.show_empty_hint()
        self.canvas.set_components([])
        self.client.send_event("new_chat", {})

    def _open_agents(self) -> None:
        if self._agents_dialog is None:
            self._agents_dialog = AgentsDialog(self, self._emit_chrome)
        self._agents_dialog.set_agents(self._agents)
        self.client.send_event("discover_agents", {})  # refresh
        self._agents_dialog.show(); self._agents_dialog.raise_()

    def _open_history(self) -> None:
        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(self, self._load_chat)
        self.client.send_event("get_history", {})
        self._history_dialog.show(); self._history_dialog.raise_()

    def _load_chat(self, chat_id: str) -> None:
        self.rail.clear()
        self.client.send_event("load_chat", {"chat_id": chat_id})

    def _sign_out(self) -> None:
        if QMessageBox.question(self, "Sign out", "Sign out of AstralBody?") \
                != QMessageBox.StandardButton.Yes:
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
        self.rail.add("user", text)   # auto-drops the empty-state hint
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
        color = T.VARIANT_COLORS["success"][0] if s == "connected" else (
            T.VARIANT_COLORS["error"][0] if s.startswith(("closed", "auth_required")) else T.MUTED)
        if s.startswith("closed"):
            nice = "Disconnected"
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
        elif s.startswith("auth_required") and self._auth_session and self._reauth_tries < 2:
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
        self.client = OrchestratorClient(self._url, token, device_caps(supported_types=native_types()))
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
            self.active_chat = (msg.get("payload") or {}).get("chat_id") or self.active_chat
        elif t == "chat_loaded":
            chat = msg.get("chat") or {}
            self.active_chat = chat.get("id") or self.active_chat
            self._replay_transcript(chat)
        elif t == "agent_list":
            self._agents = msg.get("agents") or []
            any_on = any(any(bool(v) for v in (a.get("scopes") or {}).values())
                         for a in self._agents)
            self.topbar.highlight_agents(not any_on)
            if self._agents_dialog is not None:
                self._agents_dialog.set_agents(self._agents)
        elif t == "history_list":
            chats = msg.get("chats") or []
            if self._history_dialog is not None:
                self._history_dialog.set_chats(chats)
        elif t == "chat_status":
            st = msg.get("status")
            if st in ("thinking", "executing", "fixing"):
                self.topbar.set_status(msg.get("message") or st, T.VARIANT_COLORS["accent"][0])
            elif st == "done":
                self._on_status("connected")

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
    family = next((f for f in ("Inter", "Segoe UI", "Arial") if f in families),
                  app.font().family())
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
            session = oidc_login(args.authority, client_id=args.client_id, bff_base=bff_base)
            return session.access_token, session
        except Exception as exc:  # noqa: BLE001
            print(f"OIDC login failed ({exc}); falling back to dev-token.")
    return "dev-token", None


def main() -> int:
    ap = argparse.ArgumentParser(description="AstralBody native Windows client")
    ap.add_argument("--url", default=os.getenv("ASTRAL_WS_URL", "ws://127.0.0.1:8001/ws"))
    ap.add_argument("--token", default=os.getenv("ASTRAL_TOKEN", ""))
    ap.add_argument("--authority", default=os.getenv("KEYCLOAK_AUTHORITY", ""))
    # Dedicated public client (default): the desktop exchanges the auth code
    # directly against Keycloak. See docs/keycloak-windows-client-setup.md.
    ap.add_argument("--client-id", default=(os.getenv("ASTRAL_CLIENT_ID")
                                            or os.getenv("KEYCLOAK_DESKTOP_CLIENT_ID")
                                            or "astral-desktop"))
    # Legacy: reuse the web's confidential astral-frontend client by proxying
    # the token exchange through the orchestrator's BFF (POST /auth/token).
    ap.add_argument("--bff", action="store_true",
                    default=os.getenv("ASTRAL_AUTH_BFF", "").lower() in ("1", "true", "yes"))
    args = ap.parse_args()

    app = QApplication(sys.argv)
    configure(app)
    token, session = resolve_auth(args)
    win = MainWindow(args.url, token, session=session)
    win.show()
    win.raise_(); win.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
