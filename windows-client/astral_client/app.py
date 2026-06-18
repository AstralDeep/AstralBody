"""AstralBody native Windows client — main window.

A chat rail on the left, a native SDUI canvas on the right. Inbound `ui_render`
/`ui_upsert` messages from the orchestrator are drawn as native Qt widgets via
renderer.render; button / history-row interactions post `ui_event`s back.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget, QFrame,
)

from . import theme as T
from .protocol import OrchestratorClient, device_caps
from .renderer import RenderContext, render, supported_types as native_types, _scoped


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

    def add(self, role: str, text: str) -> None:
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
        body.setStyleSheet(f"color:{T.TEXT}; font-size:13px; background:transparent;")
        bl.addWidget(who); bl.addWidget(body)
        self._lay.insertWidget(self._lay.count() - 1, bubble)
        bar = self._scroll.verticalScrollBar(); bar.setValue(bar.maximum())


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


class MainWindow(QMainWindow):
    def __init__(self, url: str, token: str):
        super().__init__()
        self.setWindowTitle("AstralBody — Windows")
        self.resize(1280, 860)
        self.active_chat: Optional[str] = None

        ctx = RenderContext(emit=self._emit)
        self.client = OrchestratorClient(url, token, device_caps(supported_types=native_types()))
        self.client.message.connect(self._on_message)
        self.client.status.connect(self._on_status)

        # top status bar
        self._status = QLabel("connecting…")
        self._status.setStyleSheet(f"color:{T.MUTED}; padding:6px 14px; background:{T.SURFACE};")

        self.rail = ChatRail()
        self.canvas = Canvas(ctx)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._wrap(self.rail, "Conversation"))
        split.addWidget(self._wrap(self.canvas, "Canvas"))
        split.setSizes([380, 900])

        self._input = QLineEdit(); self._input.setPlaceholderText("Message AstralBody…")
        self._input.returnPressed.connect(self._send)
        send = QPushButton("Send"); send.setObjectName("primary"); send.clicked.connect(self._send)
        bottom = QHBoxLayout(); bottom.setContentsMargins(12, 8, 12, 12); bottom.setSpacing(8)
        bottom.addWidget(self._input, 1); bottom.addWidget(send)

        root = QWidget(); root.setObjectName("root")
        rl = QVBoxLayout(root); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        rl.addWidget(self._status)
        rl.addWidget(split, 1)
        rl.addLayout(bottom)
        self.setCentralWidget(root)
        self.client.start()

    def _wrap(self, inner: QWidget, title: str) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        head = QLabel(title)
        head.setStyleSheet(f"color:{T.MUTED}; font-size:11px; font-weight:700; letter-spacing:1px;"
                           f"padding:8px 14px; background:{T.SURFACE};")
        lay.addWidget(head); lay.addWidget(inner, 1)
        return w

    # --- outbound -------------------------------------------------------- #
    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.rail.add("user", text)
        self.client.send_chat(text, self.active_chat)

    def _emit(self, action: str, payload: dict) -> None:
        if action == "chat_message":
            self.client.send_chat(payload.get("message", ""), self.active_chat)
        else:
            self.client.send_event(action, payload, session_id=self.active_chat)

    # --- inbound --------------------------------------------------------- #
    def _on_status(self, s: str) -> None:
        nice = {"connecting": "connecting…", "connected": "● connected"}.get(s, s)
        color = T.VARIANT_COLORS["success"][0] if s == "connected" else (
            T.VARIANT_COLORS["error"][0] if s.startswith(("closed", "auth_required")) else T.MUTED)
        self._status.setText(nice)
        self._status.setStyleSheet(f"color:{color}; padding:6px 14px; background:{T.SURFACE};")

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
                pass  # history surface — not shown in MVP
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
        elif t == "chat_status":
            st = msg.get("status")
            if st in ("thinking", "executing", "fixing"):
                self._status.setText("● " + (msg.get("message") or st))
            elif st == "done":
                self._on_status("connected")


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


def main() -> int:
    ap = argparse.ArgumentParser(description="AstralBody native Windows client")
    ap.add_argument("--url", default=os.getenv("ASTRAL_WS_URL", "ws://127.0.0.1:8001/ws"))
    ap.add_argument("--token", default=os.getenv("ASTRAL_TOKEN", "dev-token"))
    args = ap.parse_args()

    app = QApplication(sys.argv)
    configure(app)
    win = MainWindow(args.url, args.token)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
