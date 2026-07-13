"""AstralDeep native Windows client — main window.

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
import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from PySide6.QtGui import QAction, QBrush, QColor

from . import theme as T
from .auth import LoginCancelled
from . import confirm as _confirm
from . import integrity as _integrity
from . import __version__ as _APP_VERSION
from .protocol import OrchestratorClient, device_caps
from .protocol_manifest import CLIENT_LOCAL_ACTIONS, is_classified, is_handled
from .renderer import (
    RenderContext,
    render,
    supported_types as native_types,
    _btn_label,
    _scoped,
)
from .streaming import stream_error_ops, stream_frame_to_ops, subscribe_ack_ops
from .chrome import chrome_render_notice
from . import rest

logger = logging.getLogger("astral.client")


def normalize_error(msg: dict) -> str:
    """Feature 044 (FR-002): collapse the three historical server error shapes —
    ``{code,message}`` | ``{payload:{message}}`` | ``{message}`` — into one
    human string for the error banner."""
    text = (
        msg.get("message")
        or (msg.get("payload") or {}).get("message")
        or "Something went wrong."
    )
    code = msg.get("code")
    return f"{text} ({code})" if code and code != "internal" else str(text)


def parser_status_glyph(status: str) -> tuple:
    """Feature 044 (US4): map an attachment ``parser_status`` to a
    ``(glyph, label)`` for its chip — covered→ready, preparing/pending→working,
    unavailable→can't-read. Mirrors the web chip states."""
    return {
        "covered": ("✓", "ready"),
        "preparing": ("⏳", "preparing a reader"),
        "pending_admin_approval": ("⏳", "needs admin approval"),
        "unavailable": ("✗", "can't read this type yet"),
    }.get(status or "", ("•", "staged"))


#: ui_event actions handled entirely in-app (never sent to the server, so they
#: never produce a server ``chrome_surface`` re-render) — a surface's
#: load-timeout bound is NOT armed for them (which would wrongly fire and wipe
#: the surface, feature 044 fix). A committed constant mirroring the manifest's
#: ``client_local_actions`` (a packaged build has no repo tree to probe);
#: tests/test_protocol_manifest.py asserts the sync.
_CLIENT_LOCAL_ACTIONS = CLIENT_LOCAL_ACTIONS


# Feature 040 (US5): slash-command discovery. Mirrors the web client's typeahead
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

    def add_note(self, text: str) -> None:
        """A small muted line in the rail (feature 044 — used to show a turn's
        attachment chips, mirroring the web '📎 name')."""
        self._drop_hint()
        lbl = QLabel(str(text))
        lbl.setWordWrap(True)
        lbl.setFrameShape(QFrame.Shape.NoFrame)
        lbl.setStyleSheet(
            f"color:{T.MUTED}; font-size:11px; background:transparent; padding:0 6px;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def show_empty_hint(self) -> None:
        """A gentle empty-state so a fresh chat rail isn't a blank void."""
        self.clear()
        hint = QLabel(
            "Ask something below and AstralDeep will build a live interface for it."
        )
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
        # Source component payload per id, so a full render that re-delivers an
        # existing id with CHANGED content (timeline snapshots, combine/condense)
        # renders fresh instead of reusing the stale widget (parity with the
        # Android twin's in-place update).
        self._rendered: Dict[str, Any] = {}
        # Retained last-rendered component list so a live theme change can rebuild
        # inline-styled content with the new palette (feature 044 US5, restyle()).
        self._last_components: list = []
        # True whenever the canvas diverged from _last_components (apply_ops
        # patches, restyle's forced rebuild) — gates the set_components
        # unchanged-payload early exit.
        self._mutated_since_render = False
        # Shared cross-client empty-canvas hint (parity with web/Android/Apple).
        self._empty: Optional[QWidget] = None
        # Query-start loading placeholder (the Android twin's SkeletonCanvas):
        # shown when a chat turn is sent, removed by the FIRST canvas content
        # of the turn (set_components / apply_ops, which streaming also routes
        # through) or explicitly when the turn ends without any.
        self._skeleton: Optional[QWidget] = None
        # Mirrors the window's per-turn flag (feature 055 US1): an EMPTY full
        # render mid-turn keeps the loading state instead of swapping the
        # skeleton for the idle hint; out-of-turn empty renders remain
        # authoritative clears.
        self.turn_active = False
        self.show_empty_state()

    def _drop_empty(self) -> None:
        if self._empty is not None:
            self._empty.setParent(None)
            self._empty.deleteLater()
            self._empty = None

    def show_empty_state(self) -> None:
        """The shared empty-canvas copy (sparkle + headline + subtitle), muted,
        shown while no components are rendered."""
        if self._empty is not None:
            return
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(24, 60, 24, 60)
        lay.setSpacing(6)
        glyph = QLabel("✦")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setStyleSheet(f"color:{T.PRIMARY}; font-size:28px; background:transparent;")
        title = QLabel("Your generated interface appears here")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{T.TEXT}; font-size:15px; font-weight:600; background:transparent;"
        )
        sub = QLabel("Ask something below and AstralDeep will build a live interface for it.")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{T.MUTED}; font-size:12px; background:transparent;")
        lay.addWidget(glyph)
        lay.addWidget(title)
        lay.addWidget(sub)
        self._lay.insertWidget(0, box)
        self._empty = box

    def _insert(self, widget: QWidget) -> None:
        self._lay.insertWidget(self._lay.count() - 1, widget)

    def show_skeleton(self) -> None:
        """Append the loading placeholder below any existing components."""
        if self._skeleton is not None:
            return
        # The idle hint never co-shows with a turn's loading state (055
        # FR-005); resolve_loading restores it if the turn ends canvas-empty.
        self._drop_empty()
        w = render({"type": "skeleton", "variant": "card", "count": 3}, self.ctx)
        self._skeleton = w
        self._insert(w)

    def hide_skeleton(self) -> None:
        w = self._skeleton
        self._skeleton = None
        if w is not None:
            w.setParent(None)
            w.deleteLater()

    def resolve_loading(self) -> None:
        """Turn-end resolution (chat_status done / error): drop the skeleton
        and, when the turn ended with no canvas output (a text-only answer
        after the welcome purge), restore the idle empty-state hint — the
        server no longer sends the turn-start empty render that used to leave
        the hint behind (feature 055 US1)."""
        self.hide_skeleton()
        if not self._last_components and not self._by_id:
            self.show_empty_state()

    def purge_welcome(self) -> None:
        """Feature 055 (US1, uniform rule): at turn start drop every ephemeral
        welcome component — identity (``component_id`` or ``id``) prefixed
        ``wel_`` — re-rendering the remainder through the identity-reconciled
        path. When the server flag is off the welcome arrives id-less, nothing
        matches and this is a byte-equivalent no-op. Callers flip
        ``turn_active`` first, so a welcome-only canvas empties WITHOUT the
        idle hint (the skeleton is armed right after)."""
        kept = [
            comp for comp in self._last_components
            if not (isinstance(comp, dict) and str(
                comp.get("component_id") or comp.get("id") or ""
            ).startswith("wel_"))
        ]
        if len(kept) != len(self._last_components):
            self.set_components(kept)

    def set_components(self, components: list) -> None:
        """Full canvas render (a `ui_render` to the canvas region), reconciled BY
        component identity instead of a blind drop-and-rebuild (feature 044 T024).

        A component_id already on the canvas keeps its existing widget — its
        identity persists across the render (streaming nodes, interactive state,
        scroll position). Ids absent from the new set are removed; brand-new ids
        (and unkeyed components) are rendered fresh. This is the fix for the
        clobber bug where a full render threw away components the new set still
        contains (e.g. one just added via a `ui_upsert`).

        Cheap early-exit: when nothing has mutated the canvas since the last
        full render and the incoming list is the same object as (or compares
        equal to) the previous one, the canvas already IS this state — skip
        reconciliation entirely. apply_ops/restyle flip ``_mutated_since_render``
        so patched or palette-stale canvases always reconcile.

        Feature 055 (US1): an EMPTY set while a turn is in flight
        (``turn_active``) keeps the loading state — the armed skeleton
        survives the rebuild and the idle empty-state hint is NOT shown. Only
        out-of-turn empty renders resolve to the hint (authoritative clears)."""
        incoming = components or []
        # Mid-turn empty render: never swap the skeleton for the idle hint.
        keep_loading = not incoming and self.turn_active
        if not self._mutated_since_render and (
            incoming is self._last_components
            or incoming == self._last_components
        ):
            if not keep_loading:
                self.hide_skeleton()
            return
        components = list(incoming)
        skeleton = self._skeleton if keep_loading else None
        if skeleton is None:
            self.hide_skeleton()  # canvas content arrived (or is being rebuilt)
        self._last_components = components  # retained for restyle() (US5)
        # The empty-state hint is dropped before the rebuild (the detach loop
        # below would otherwise delete it out from under self._empty) and
        # re-shown afterwards when the new set is empty.
        self._drop_empty()
        # A widget is reusable only when its id survives into the new set AND
        # the incoming component payload equals what it was rendered from — a
        # re-delivered id with CHANGED content (timeline snapshots, combine/
        # condense) must render fresh, not keep showing stale live data.
        reusable: Dict[str, QWidget] = {}
        for comp in components:
            if isinstance(comp, dict):
                raw = comp.get("component_id") or comp.get("id")
                cid = str(raw) if raw else None
                if (cid and cid not in reusable and cid in self._by_id
                        and self._rendered.get(cid) == comp):
                    reusable[cid] = self._by_id[cid]
        # Detach every current child (keep the trailing stretch); widgets not
        # reused (unkeyed, dropped ids, changed content) are deleted.
        detached: List[QWidget] = []
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                detached.append(w)
        reused = set(reusable.values())
        for w in detached:
            if w not in reused and w is not skeleton:
                w.setParent(None)
                w.deleteLater()
        # Re-insert in the new order, reusing a kept widget by id or rendering
        # fresh. `_insert` appends before the stretch, so order follows the list.
        self._by_id = {}
        rendered: Dict[str, Any] = {}
        placed: set = set()
        for comp in components:
            cid = None
            if isinstance(comp, dict):
                raw = comp.get("component_id") or comp.get("id")
                cid = str(raw) if raw else None
            # A component_id repeated within one payload must NOT reuse (or
            # re-insert) the same widget twice — render the duplicate fresh so a
            # single widget object is never added to the layout more than once.
            w = reusable.get(cid) if (cid and cid not in placed) else None
            if w is None:
                w = render(comp, self.ctx)
                if cid:
                    w.setProperty("component_id", cid)
            self._insert(w)
            if cid:
                self._by_id[cid] = w
                if cid not in placed:
                    rendered[cid] = comp
                placed.add(cid)
        if skeleton is not None:
            self._insert(skeleton)  # the loading placeholder stays at the bottom
        self._rendered = rendered
        self._mutated_since_render = False
        if not components and not keep_loading:
            self.show_empty_state()

    def restyle(self) -> None:
        """Re-render the retained components so inline-styled SDUI content (cards,
        hero, alerts, badges — styled from the theme palette AT render time, not
        via global QSS) picks up a live theme change (feature 044 US5). Identity
        reconciliation would reuse the existing widgets, which keep their stale
        inline CSS, so the id map is cleared to force a fresh rebuild.

        The full rebuild here is INTENTIONAL: every renderer reads the palette
        globals at render time, so after a theme change effectively all retained
        widgets are palette-stale — there is no "unaffected component" subset to
        preserve. The per-frame path (set_components) keeps identity reuse plus
        the unchanged-payload early exit; only theme changes pay for a rebuild."""
        comps = self._last_components
        # Force a fresh render (reused widgets keep stale inline CSS); the
        # payload map is cleared with the id map so reuse can't kick in.
        self._by_id = {}
        self._rendered = {}
        self._mutated_since_render = True
        self.set_components(comps)

    def apply_ops(self, ops: list) -> None:
        """In-place workspace patch (a `ui_upsert`)."""
        if ops:
            self.hide_skeleton()  # first canvas content of the turn
            # The canvas now diverges from _last_components, so the next full
            # render must reconcile even if its payload looks unchanged.
            self._mutated_since_render = True
        if any((op or {}).get("op", "upsert") != "remove" for op in ops or []):
            self._drop_empty()  # content is arriving — hide the empty-state hint
        for op in ops or []:
            kind = op.get("op", "upsert")
            cid = op.get("component_id")
            if kind == "remove":
                w = self._by_id.pop(cid, None)
                self._rendered.pop(cid, None)
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
            self._rendered[cid] = comp  # keep the payload map in sync


class SurfaceDialog(QDialog):
    """Feature 043 — a settings surface delivered as SDUI (``chrome_surface``),
    rendered natively with the SAME component renderer used for the chat canvas.
    Replaces the "coming soon" placeholder for the ported surfaces (theme, user
    guide, LLM settings, personalization)."""

    #: How long to wait for a `chrome_surface` before showing the retry error.
    LOAD_TIMEOUT_MS = 10000

    def __init__(self, parent, emit, download=None, on_retry=None, apply_theme=None,
                 on_sign_out=None):
        super().__init__(parent)
        self.setModal(False)
        self.resize(600, 560)
        self._raw_emit = emit
        self._on_retry = on_retry
        self._on_sign_out = on_sign_out
        self._surface = ""
        self._params: dict = {}
        # Feature 054 (T019): first-run gate pin. While the server pushes
        # mode:"mandatory" the dialog is application-modal with every dismissal
        # affordance suppressed; only the server's blank close frame (or Sign
        # out) releases it. _flags_before restores the stock flags on unpin.
        self._mandatory = False
        self._flags_before = self.windowFlags()
        # Feature 044 (T040): actions submitted from inside the surface show an
        # in-flight state and re-arm the load bound (the server replies with a
        # chrome_surface re-render that cancels it). `apply_theme` routes the
        # Theme surface's theme_apply/color-pick to the app's single theme path.
        self._ctx = RenderContext(emit=self._emit_from_surface, download=download,
                                  apply_theme=apply_theme)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        self._title = QLabel("Settings")
        self._title.setStyleSheet(f"color:{T.TEXT}; font-size:15px; font-weight:600;")
        outer.addWidget(self._title)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{T.MUTED}; font-size:12px;")
        self._status.setVisible(False)
        outer.addWidget(self._status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(12)
        self._lay.addStretch(1)
        scroll.setWidget(self._inner)
        outer.addWidget(scroll, 1)
        # Feature 054 (T019): the mandatory gate blocks the main window (and
        # its gear menu) behind an application-modal dialog, so the FR-013
        # sign-out escape hatch must live IN the dialog — same routine as the
        # gear menu's Sign out. Hidden unless mandatory.
        self._signout_btn = QPushButton("Sign out")
        self._signout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signout_btn.clicked.connect(self._request_sign_out)
        self._signout_btn.setVisible(False)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self._signout_btn)
        outer.addLayout(btn_row)
        # Load-timeout bound (T040): armed on open/submit, cancelled on arrival.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.LOAD_TIMEOUT_MS)
        self._timer.timeout.connect(self._on_timeout)

    def set_mandatory(self, on: bool) -> None:
        """Feature 054 (T019): pin/unpin the first-run gate. Pinned = the
        dialog is application-modal and undismissable: the titlebar ✕ is
        removed (CustomizeWindowHint — clearing the close hint alone leaves
        the platform defaults in force) and Esc/close are refused by the
        reject/closeEvent overrides until the server's blank close frame."""
        on = bool(on)
        if on == self._mandatory:
            return
        self._mandatory = on
        # Modality and window flags only apply on the next show(); a flag
        # change also re-creates the native window — hide first, re-show after.
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
        if on:
            self.setWindowFlags(Qt.WindowType.Dialog
                                | Qt.WindowType.CustomizeWindowHint
                                | Qt.WindowType.WindowTitleHint)
        else:
            self.setWindowFlags(self._flags_before)
        self.setModal(on)
        self._signout_btn.setVisible(on)
        if was_visible:
            self.show()

    def _request_sign_out(self) -> None:
        if callable(self._on_sign_out):
            self._on_sign_out()

    def reject(self) -> None:
        # Esc / programmatic dismissal: refused while the gate is pinned (054).
        if self._mandatory:
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._mandatory:
            event.ignore()
            return
        super().closeEvent(event)

    def _clear_body(self) -> None:
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # Reparent BEFORE deleteLater: a deferred delete only runs once
                # control returns to the exec() loop, so during nested event
                # processing (or a synthetic processEvents pump, e.g. the
                # screenshot harness) the removed widget would otherwise keep
                # painting over the next surface's components — visible as one
                # settings page stacking on another when switching surfaces.
                w.setParent(None)
                w.deleteLater()

    def _emit_from_surface(self, action: str, payload: dict) -> None:
        self._raw_emit(action, payload)
        # A form submit re-renders the surface; show in-flight + re-arm the bound.
        # But a client-local action (e.g. attach_existing) is handled in-app and
        # never produces a server chrome_surface re-render, so arming the
        # load-timeout would wrongly fire and wipe the surface — skip it.
        if action != "chat_message" and action not in _CLIENT_LOCAL_ACTIONS:
            self._status.setText("Applying…")
            self._status.setVisible(True)
            self._timer.start()

    def begin_load(self, surface: str, params: dict, title: str = "") -> None:
        """Show the in-flight state for a requested surface and arm the
        load-timeout bound (T040). Called right after sending `chrome_open`."""
        self._surface = surface or self._surface
        self._params = params or {}
        self.setWindowTitle(title or self._surface or "Settings")
        self._title.setText(title or self._surface or "Settings")
        self._status.setText("Loading…")
        self._status.setVisible(True)
        self._clear_body()
        loading = QLabel("Loading…")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet(f"color:{T.MUTED}; font-size:13px; padding:32px;")
        self._lay.insertWidget(self._lay.count() - 1, loading)
        self._timer.start()

    def _on_timeout(self) -> None:
        """The surface didn't arrive in time — show an inline error + Retry."""
        self._timer.stop()
        self._status.setVisible(False)
        self._clear_body()
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 24, 0, 0)
        bl.setSpacing(10)
        msg = QLabel("This settings screen didn't load. Check your connection and try again.")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"color:{T.VARIANT_COLORS['warning'][0]}; font-size:13px;")
        self._retry_btn = QPushButton("Retry")
        self._retry_btn.setObjectName("primary")
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.clicked.connect(self._retry)
        bl.addWidget(msg)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._retry_btn)
        row.addStretch(1)
        bl.addLayout(row)
        self._lay.insertWidget(self._lay.count() - 1, box)

    def _retry(self) -> None:
        """Re-send `chrome_open` for the pending surface (re-arms the bound)."""
        self.begin_load(self._surface, self._params, title=self._title.text())
        if callable(self._on_retry):
            self._on_retry(self._surface, self._params)

    def set_surface(self, title: str, components: list) -> None:
        """Replace the modal body with a freshly-rendered component list. Cancels
        the load-timeout bound — this is the arrival path (T040)."""
        self._timer.stop()
        self._status.setVisible(False)
        self.setWindowTitle(title or "Settings")
        self._title.setText(title or "Settings")
        self._clear_body()
        for comp in components or []:
            self._lay.insertWidget(self._lay.count() - 1, render(comp, self._ctx))


class TopBar(QFrame):
    """Native app chrome header, identical across clients (feature 042 —
    Constitution XII): a small brand mark · a New-chat button · a Recent-chats
    button · a Settings gear whose dropdown holds ALL settings (ACCOUNT / HELP /
    ADMIN TOOLS + a red Sign out), built from the single server-owned menu model.
    Nothing else — Agents/Audit/LLM/etc. live inside the gear menu, exactly as on
    the web. Connection/integrity status is carried in the mark's tooltip so the
    bar stays clean."""

    def __init__(self, user: str, on_new_chat, on_recent, on_open_surface, on_sign_out):
        super().__init__()
        self.setObjectName("topbar")
        self.setStyleSheet(
            f"#topbar {{ background:{T.SURFACE}; border-bottom:1px solid {T.BORDER}; }}"
        )
        self._on_open_surface = on_open_surface
        self._on_sign_out = on_sign_out

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 12, 8)
        lay.setSpacing(8)

        # Small brand mark only — no wordmark, no visible status/identity text.
        self._mark = QLabel("◆")
        self._mark.setStyleSheet(
            f"color:{T.PRIMARY}; font-size:16px; font-weight:800; background:transparent;"
        )
        self._mark.setToolTip("connecting…")

        self.new_btn = QPushButton("＋ New")
        self.new_btn.setObjectName("primary")
        self.new_btn.clicked.connect(on_new_chat)
        # Recent chats (the web's history icon) — reopen a past conversation.
        self.recent_btn = QPushButton("🕓 Recent chats")
        self.recent_btn.clicked.connect(on_recent)
        # Settings gear → dropdown built from the server-owned menu model.
        self.settings_btn = QPushButton("⚙ Settings")
        self._menu = QMenu(self)
        self._menu.setStyleSheet(
            f"QMenu {{ background:{T.SURFACE}; color:{T.TEXT}; border:1px solid {T.BORDER}; padding:4px; }}"
            f"QMenu::item {{ padding:6px 24px; }}"
            f"QMenu::item:selected {{ background:{T.PRIMARY}; color:#ffffff; }}"
            f"QMenu::separator {{ height:1px; background:{T.BORDER}; margin:4px 8px; }}"
        )
        self.settings_btn.setMenu(self._menu)
        for b in (self.new_btn, self.recent_btn, self.settings_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        # Feature 044 (T038): server-model top-bar action controls (pulse,
        # timeline, …) render as buttons in this holder, left of the gear. Each
        # emits its chrome_open{surface} via on_open_surface. Rebuilt from the
        # chrome menu model; empty until it arrives.
        self._actions_holder = QWidget()
        self._actions_lay = QHBoxLayout(self._actions_holder)
        self._actions_lay.setContentsMargins(0, 0, 0, 0)
        self._actions_lay.setSpacing(6)
        self._action_buttons: List[QPushButton] = []

        lay.addWidget(self._mark)
        lay.addStretch(1)
        lay.addWidget(self._actions_holder)
        lay.addWidget(self.new_btn)
        lay.addWidget(self.recent_btn)
        lay.addWidget(self.settings_btn)

        # Until the server model arrives, offer just Sign out (always safe).
        self._rebuild_menu({"sections": [], "signout": {"label": "Sign out", "action": "logout"}})

    #: Known top-bar action icon names → a leading glyph (falls back to label).
    _ACTION_ICONS = {"history": "🕓", "pulse": "⚡", "activity": "⚡", "clock": "🕓"}

    def set_menu_model(self, model: dict) -> None:
        """(Re)build the Settings dropdown AND the top-bar action buttons from the
        server-owned chrome model (the `chrome_menu` WS frame / GET
        /api/chrome/menu)."""
        from .rest import parse_chrome_menu

        parsed = parse_chrome_menu(model)
        self._rebuild_menu(parsed)
        self._rebuild_topbar_actions(parsed.get("topbar_actions", []))

    def _rebuild_topbar_actions(self, actions: list) -> None:
        """Render the server model's `kind:"action"` top-bar controls as buttons
        (feature 044 T038). Each triggers its `chrome_open{surface}` through the
        shared on_open_surface callback — the same path the gear-menu items use."""
        while self._actions_lay.count():
            item = self._actions_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._action_buttons = []
        for a in actions or []:
            if not isinstance(a, dict):
                continue
            surface = a.get("surface", "")
            if not surface:
                continue
            label = a.get("label") or surface
            glyph = self._ACTION_ICONS.get(a.get("icon", ""), "")
            btn = QPushButton(f"{glyph} {label}".strip() if glyph else str(label))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(str(label))
            btn.clicked.connect(
                lambda _checked=False, s=surface, ln=label: self._emit_open(s, ln)
            )
            self._actions_lay.addWidget(btn)
            self._action_buttons.append(btn)

    def _rebuild_menu(self, parsed: dict) -> None:
        self._menu.clear()
        for section in parsed.get("sections", []):
            heading = str(section.get("label", "")).strip()
            if heading:
                # A styled QWidgetAction, NOT addSection(): several QStyles
                # (Fusion included) drop a section's text entirely, which hid
                # the ACCOUNT / HELP group headers the web + Android menus show.
                head = QLabel(heading.upper())
                head.setStyleSheet(
                    f"color:{T.MUTED}; font-size:10px; font-weight:700; "
                    "letter-spacing:1px; padding:6px 24px 2px 24px; background:transparent;"
                )
                ha = QWidgetAction(self._menu)
                ha.setDefaultWidget(head)
                ha.setEnabled(False)
                self._menu.addAction(ha)
            for item in section.get("items", []):
                label = item.get("label", "")
                # Qt mnemonic escape: "Agents & permissions" must render its
                # ampersand literally, exactly like the web/Android menus.
                act = QAction(_btn_label(label), self._menu)
                surface = item.get("surface", "")
                act.triggered.connect(
                    lambda _checked=False, s=surface, ln=label: self._emit_open(s, ln)
                )
                self._menu.addAction(act)
        self._menu.addSeparator()
        # Red Sign out at the very bottom (a QWidgetAction so we can color it).
        so = parsed.get("signout", {}) or {}
        so_label = QLabel(so.get("label", "Sign out"))
        so_label.setStyleSheet("color:#EF4444; padding:6px 24px; background:transparent;")
        so_label.setCursor(Qt.CursorShape.PointingHandCursor)
        so_label.mousePressEvent = lambda _ev: (self._menu.close(), self._emit_sign_out())
        wa = QWidgetAction(self._menu)
        wa.setDefaultWidget(so_label)
        self._menu.addAction(wa)

    def _emit_open(self, surface: str, label: str) -> None:
        if callable(self._on_open_surface):
            self._on_open_surface(surface, label)

    def _emit_sign_out(self) -> None:
        if callable(self._on_sign_out):
            self._on_sign_out()

    def set_status(self, text: str, color: str) -> None:
        """Status/integrity is surfaced on the brand mark (tooltip + tint) so the
        top bar stays minimal (logo · New · Recent · Settings)."""
        self._mark.setToolTip(text)
        self._mark.setStyleSheet(
            f"color:{color}; font-size:16px; font-weight:800; background:transparent;"
        )

    def set_user(self, user: str) -> None:
        """No-op retained for callers: the identity label was removed from the
        minimal top bar (feature 042)."""
        return

    def highlight_agents(self, on: bool) -> None:
        """No-op retained for callers: Agents now lives inside the Settings menu
        (matching the web), so there is no standalone Agents button to accent."""
        return


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


class AuditDialog(QDialog):
    """Native, read-only audit-log viewer (parity with the web ``audit`` chrome
    surface), backed by ``GET /api/audit``.

    A filter bar (event class / outcome / keyword) over a reverse-chronological
    table — time, class, action, outcome, description — with cursor-based
    "Load more" pagination. The MainWindow fetches pages on a background thread
    and feeds them in via ``begin_load`` / ``add_page`` / ``set_error``; this
    dialog owns no I/O and no token.
    """

    _COLUMNS = ("Time", "Class", "Action", "Outcome", "Description")
    _ROW_KEYS = ("recorded_at", "event_class", "action_type", "outcome", "description")
    # Map an outcome to a theme variant for the cell colour (parity with the web badges).
    _OUTCOME_VARIANT = {
        "success": "success", "failure": "error",
        "in_progress": "accent", "interrupted": "warning",
    }

    def __init__(self, parent, on_query):
        super().__init__(parent)
        self._on_query = on_query  # callable(filters: dict, reset: bool) -> None
        self._next_cursor: Optional[str] = None
        self.setWindowTitle("Audit log")
        self.resize(940, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QLabel("Audit log")
        head.setStyleSheet(f"color:{T.TEXT}; font-size:16px; font-weight:700;")
        root.addWidget(head)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._class = QComboBox()
        self._class.addItem("All classes", "")
        for c in rest.EVENT_CLASSES:
            self._class.addItem(c, c)
        self._outcome = QComboBox()
        self._outcome.addItem("All outcomes", "")
        for o in rest.OUTCOMES:
            self._outcome.addItem(o, o)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search description or action…")
        self._search.returnPressed.connect(self._apply)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply)
        for w in (self._class, self._outcome, apply_btn):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(self._class)
        bar.addWidget(self._outcome)
        bar.addWidget(self._search, 1)
        bar.addWidget(apply_btn)
        root.addLayout(bar)

        self._table = QTableWidget(0, len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(list(self._COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setWordWrap(False)
        header = self._table.horizontalHeader()
        for i in range(len(self._COLUMNS) - 1):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(self._COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            f"QTableWidget {{ background:{T.SURFACE}; color:{T.TEXT}; "
            f"border:1px solid {T.BORDER}; border-radius:8px; gridline-color:{T.BORDER}; }}"
            f"QHeaderView::section {{ background:{T.SURFACE_2}; color:{T.MUTED}; "
            f"border:none; padding:6px 8px; font-weight:600; }}"
        )
        root.addWidget(self._table, 1)

        foot = QHBoxLayout()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{T.MUTED}; font-size:12px;")
        self._more_btn = QPushButton("Load more")
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.clicked.connect(self._load_more)
        self._more_btn.setVisible(False)
        foot.addWidget(self._status_lbl, 1)
        foot.addWidget(self._more_btn)
        root.addLayout(foot)

    # --- filter state --- #
    def filters(self) -> dict:
        return {
            "event_class": self._class.currentData() or "",
            "outcome": self._outcome.currentData() or "",
            "q": self._search.text().strip(),
        }

    def _apply(self) -> None:
        self._on_query(self.filters(), True)

    def _load_more(self) -> None:
        if self._next_cursor:
            f = self.filters()
            f["cursor"] = self._next_cursor
            self._on_query(f, False)

    # --- population (called on the GUI thread) --- #
    def begin_load(self, reset: bool) -> None:
        if reset:
            self._table.setRowCount(0)
            self._next_cursor = None
        self._status_lbl.setText("Loading…")
        self._more_btn.setEnabled(False)

    def add_page(self, rows: list, next_cursor: Optional[str]) -> None:
        for r in rows or []:
            self._append_row(r)
        self._next_cursor = next_cursor
        self._more_btn.setVisible(bool(next_cursor))
        self._more_btn.setEnabled(bool(next_cursor))
        n = self._table.rowCount()
        if n == 0:
            self._status_lbl.setText("No audit entries match the current filters.")
        else:
            suffix = " (more available)" if next_cursor else ""
            self._status_lbl.setText(f"{n} event{'s' if n != 1 else ''}{suffix}")

    def set_error(self, message: str) -> None:
        self._status_lbl.setText(f"Could not load audit log: {message}")
        self._more_btn.setEnabled(bool(self._next_cursor))

    def _append_row(self, r: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col, key in enumerate(self._ROW_KEYS):
            text = str(r.get(key, ""))
            item = QTableWidgetItem(text)
            if key == "outcome":
                variant = self._OUTCOME_VARIANT.get(r.get("outcome"))
                if variant:
                    item.setForeground(QBrush(QColor(T.VARIANT_COLORS[variant][0])))
            elif key == "description":
                item.setToolTip(text)
            self._table.setItem(row, col, item)


class MainWindow(QMainWindow):
    # Launch-time integrity verdict, marshalled from the worker thread to the
    # GUI thread (level, message). Qt queues the emit across threads safely.
    _integrity_notice = Signal(str, str)
    # Audit-log page fetched off-thread -> GUI thread (dict payload).
    _audit_loaded = Signal(object)
    _download_done = Signal(object)
    # Attachment upload resolved off-thread -> GUI thread (dict payload).
    _attachment_uploaded = Signal(object)
    # Sign-out revocation resolved off-thread -> GUI thread (outcome string).
    _signed_out = Signal(str)
    # Interactive re-auth completed off-thread -> GUI thread (Session or None).
    _reauth_done = Signal(object)
    # Silent token refresh resolved off-thread -> GUI thread (new token or None).
    _silent_refresh_done = Signal(object)
    # Window-first startup login resolved off-thread -> GUI thread (dict outcome).
    _login_resolved = Signal(object)

    def __init__(self, url: str, token: str, session=None, login_params=None,
                 connect: bool = True):
        super().__init__()
        self.setWindowTitle("AstralDeep — Windows")
        self.resize(1280, 860)
        self.active_chat: Optional[str] = None
        self._url = url
        self._auth_session = session
        # Login params (authority/client_id/bff) so an expired-and-unrefreshable
        # session can run a fresh interactive login (FR-004) instead of dead-ending.
        self._login_params = login_params or {}
        self._reauth_tries = 0
        # Guard so two auth_required frames don't fire two concurrent refreshes.
        self._silent_refresh_active = False
        # Window-first startup login state (begin_login/cancel_login).
        self._login_active = False
        self._login_cancel: Optional[threading.Event] = None
        self._login_resolver = None
        # False until a workspace is applied — the first-run folder picker is
        # deferred to the first file-tool use so no dialog blocks first paint.
        self._workspace_ready = False
        self._agents: List[dict] = []
        self._agents_dialog: Optional[AgentsDialog] = None
        self._history_dialog: Optional[HistoryDialog] = None
        # Live-stream seq tracker (stream-key -> last seq) for the push
        # streaming consumer; reset when the active conversation changes.
        self._stream_seq: Dict[str, int] = {}
        # Bearer token for REST surfaces (audit log); kept current on reconnect.
        self._token = token
        self._audit_dialog: Optional[AuditDialog] = None
        self._surface_dialog: Optional[SurfaceDialog] = None  # feature 043 (SDUI settings)
        # Feature 044 turn/UI state.
        self._turn_active = False
        self._timeline_mode = False
        self._user_prefs: dict = {}
        # Feature 044 (US4): staged chat attachments (chip records) for the turn.
        self._attachments: List[dict] = []

        ctx = RenderContext(emit=self._emit, download=self._download,
                            apply_theme=self._apply_theme_pref)
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
            self._open_history,  # Recent chats
            self._open_surface,
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
        self._input.setPlaceholderText("Message AstralDeep…  (type / for commands)")
        self._input.returnPressed.connect(self._send)
        # Feature 040 (US5): pop up the slash-command options as the user types "/".
        self._input.setCompleter(build_slash_completer(self._input))
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("primary")
        self._send_btn.clicked.connect(self._send)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Feature 044 (US4): a paperclip → Upload files… / Choose from your files,
        # and a chips strip (above the input) for staged attachments.
        self._attach_btn = QPushButton("📎")
        self._attach_btn.setToolTip("Attach files")
        self._attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        attach_menu = QMenu(self._attach_btn)
        attach_menu.setStyleSheet(
            f"QMenu {{ background:{T.SURFACE}; color:{T.TEXT}; border:1px solid {T.BORDER}; padding:4px; }}"
            f"QMenu::item {{ padding:6px 24px; }}"
            f"QMenu::item:selected {{ background:{T.PRIMARY}; color:#ffffff; }}"
        )
        act_up = attach_menu.addAction("Upload files…")
        act_up.triggered.connect(self._pick_files)
        act_ex = attach_menu.addAction("Choose from your files")
        act_ex.triggered.connect(lambda: self._open_surface("attachments", "Your files"))
        self._attach_btn.setMenu(attach_menu)

        self._chips_bar = QWidget()
        self._chips_lay = QHBoxLayout(self._chips_bar)
        self._chips_lay.setContentsMargins(12, 6, 12, 0)
        self._chips_lay.setSpacing(6)
        self._chips_bar.setVisible(False)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 8, 12, 12)
        bottom.setSpacing(8)
        bottom.addWidget(self._attach_btn)
        bottom.addWidget(self._input, 1)
        bottom.addWidget(self._send_btn)

        # Feature 044 (FR-002/FR-003): a dismissible banner strip under the top
        # bar for connection state + server errors + queue-drop notices. Hidden
        # until there is something to say.
        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setVisible(False)
        self._banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self._banner.setStyleSheet(
            f"background:{T.SURFACE_2}; color:{T.TEXT}; border-bottom:1px solid {T.BORDER};"
            "padding:6px 14px; font-size:12px;"
        )
        # Click to dismiss (errors/notices); the reconnect banner re-asserts
        # itself; during a startup sign-in the click cancels the login instead.
        self._banner.mousePressEvent = lambda _ev: self._on_banner_clicked()

        root = QWidget()
        root.setObjectName("root")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.topbar)
        rl.addWidget(self._banner)
        rl.addWidget(split, 1)
        rl.addWidget(self._chips_bar)
        rl.addLayout(bottom)
        self.setCentralWidget(root)
        self._input.setFocus()  # cursor ready in the message box on launch

        # Attach the cross-thread confirmation bridge so the win_agent thread
        # can ask the GUI thread to show a native Allow/Deny (or directory
        # picker) modal. Must happen on the GUI thread, before any tool call.
        _confirm.BRIDGE.attach(self._show_confirm_dialog)

        # Apply a persisted/env workspace silently; the first-run folder picker
        # is deferred to the first file-tool use so it never blocks first paint.
        self._init_workspace()

        if connect:
            self.client.start()

        # Launch-time integrity / update check (feature 039 B.5). Verifies the
        # running build's SHA-256 + sigstore signature against the GitHub release
        # before the binary is trusted — runs on a background thread so it never
        # delays the GUI, and fails open (offline ⇒ keep running) so it can never
        # block launch. The verdict is surfaced in the top-bar status line.
        self._integrity_notice.connect(self._on_integrity_notice)
        self._audit_loaded.connect(self._on_audit_loaded)
        self._download_done.connect(self._on_download_done)
        self._attachment_uploaded.connect(self._on_attachment_uploaded)
        self._signed_out.connect(self._finish_sign_out)
        self._reauth_done.connect(self._on_reauth_done)
        self._silent_refresh_done.connect(self._on_silent_refresh_done)
        self._login_resolved.connect(self._on_login_resolved)
        self._signing_out_done = False
        self._connected_once = False
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

    def _apply_theme_pref(self, theme) -> None:
        """Apply a stored/pushed/surface-emitted theme spec (feature 044 US5) —
        the app's SINGLE theme-apply implementation. Boot (`user_preferences`),
        the Theme surface's `theme_apply` component and the color picker (both
        via ``RenderContext.apply_theme``) all route here. The palette mutation
        is synchronous; the global restyle is DEFERRED to the next event-loop
        turn because this can be reached from *inside* a render pass, where a
        global re-polish is re-entrant and segfaults headless Qt (commit
        7a3ea3e). In a unit test with no running event loop the deferred
        restyle simply never fires — palette assertions still hold."""
        if not theme:
            return
        applier = getattr(T, "apply_theme", None)
        if callable(applier):
            try:
                if applier(theme):
                    QTimer.singleShot(0, self._restyle_all)
            except Exception:
                logger.debug("theme apply failed", exc_info=True)

    def _restyle_all(self) -> None:
        """Re-apply the app stylesheet + re-render open surfaces after a theme
        change (feature 044 US5). Extended alongside the dynamic palette."""
        app = QApplication.instance()
        if app is not None and hasattr(T, "build_stylesheet"):
            app.setStyleSheet(T.build_stylesheet() + getattr(T, "ROOT_BG_STYLE", ""))
        # setStyleSheet above restyles the QSS-driven widgets (buttons, inputs,
        # tables), but the SDUI canvas content is styled INLINE from the palette
        # at render time, so re-render it to pick up the new palette (US5).
        self.canvas.restyle()
        # The chat-rail bubbles + top-bar chrome are also inline-styled and are
        # not cheaply re-renderable, so they adopt the new palette on the NEXT
        # message rather than retroactively — a deliberate, disclosed limitation
        # (FR-019), not a silent no-op.

    # --- banner (connection state / errors / notices) ------------------- #
    def _show_banner(self, text: str, kind: str = "info") -> None:
        color = {
            "error": T.VARIANT_COLORS["error"][0],
            "warning": T.VARIANT_COLORS["warning"][0],
        }.get(kind, T.TEXT)
        self._banner.setText(text)
        self._banner.setStyleSheet(
            f"background:{T.SURFACE_2}; color:{color}; border-bottom:1px solid {T.BORDER};"
            "padding:6px 14px; font-size:12px;"
        )
        self._banner.setVisible(True)

    def _hide_banner(self) -> None:
        self._banner.setVisible(False)
        self._banner.setText("")

    def _on_banner_clicked(self) -> None:
        """Banner click: cancel an in-flight startup sign-in, else dismiss."""
        if self._login_active:
            self.cancel_login()
        self._hide_banner()

    def _set_composer_enabled(self, enabled: bool) -> None:
        """Enable/disable the message input + Send button (feature 044 FR-007 —
        read-only enforcement while viewing workspace history)."""
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        self._input.setPlaceholderText(
            "Message AstralDeep…  (type / for commands)" if enabled
            else "Viewing workspace history — return to live to send messages"
        )

    # --- chrome actions -------------------------------------------------- #
    def _new_chat(self) -> None:
        self.active_chat = None
        self.canvas.ctx.chat_id = None
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

    def _open_surface(self, surface: str, label: str) -> None:
        """Route a settings-menu item (from the server-owned model) to its native
        surface. Agents/Audit have native dialogs today; every other surface
        (workspace_timeline included — its SDUI snapshot list/view/back-to-live
        is server-driven) goes through the generic SDUI chrome_open round-trip."""
        s = (surface or "").strip()
        if s == "agents":
            self._open_agents()
        elif s == "audit":
            self._open_audit()
        else:
            # Feature 043: request the SDUI surface and render it natively when
            # the chrome_surface frame arrives (replaces the placeholder).
            # Feature 044 (T040): show an in-flight state + bound the wait.
            if self._surface_dialog is None:
                self._surface_dialog = SurfaceDialog(
                    self, self._emit, self._download, on_retry=self._retry_surface,
                    apply_theme=self._apply_theme_pref, on_sign_out=self._sign_out)
            self._surface_dialog.begin_load(s, {}, title=label or s)
            self._surface_dialog.show()
            self._surface_dialog.raise_()
            self.client.send_event("chrome_open", {"surface": s, "params": {}})

    def _retry_surface(self, surface: str, params: dict) -> None:
        """Feature 044 (T040): re-request a settings surface that failed to load
        in time (the SurfaceDialog re-arms its in-flight state; we re-send)."""
        self.client.send_event("chrome_open", {"surface": surface, "params": params or {}})

    def _open_history(self) -> None:
        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(self, self._load_chat)
        self.client.send_event("get_history", {})
        self._history_dialog.show()
        self._history_dialog.raise_()

    def _open_audit(self) -> None:
        if self._audit_dialog is None:
            self._audit_dialog = AuditDialog(self, self._query_audit)
        self._audit_dialog.show()
        self._audit_dialog.raise_()
        self._query_audit({}, True)  # initial page (no filters)

    def _on_chrome_surface(self, msg: dict) -> None:
        """Feature 043 — render a pushed SDUI settings surface natively (open the
        dialog if a re-render arrives for a surface the user opened). Feature 044
        (T040): arrival cancels the load-timeout bound (via set_surface).

        An empty ``surface_key`` + empty ``components`` is the server's CLOSE
        instruction (shared/protocol.py: "Empty components clears/closes the
        modal", sent after workspace-timeline view/live and chrome_close) —
        close the dialog if one is open; never lazily create one just to show
        a blank "Settings" page.

        Feature 054 (T019): ``mode:"mandatory"`` (reserved field, previously
        always "replace") pins the dialog as the undismissable first-run gate;
        the blank close frame clears the pin before closing."""
        components = msg.get("components") or []
        mode = str(msg.get("mode") or "replace")
        if not msg.get("surface_key") and not components:
            if self._surface_dialog is not None:
                self._surface_dialog.set_mandatory(False)
                self._surface_dialog.close()
            return
        if self._surface_dialog is None:
            self._surface_dialog = SurfaceDialog(
                self, self._emit, self._download, on_retry=self._retry_surface,
                apply_theme=self._apply_theme_pref, on_sign_out=self._sign_out)
        self._surface_dialog.set_mandatory(mode == "mandatory")
        self._surface_dialog.set_surface(
            msg.get("title") or "Settings", components)
        self._surface_dialog.show()
        self._surface_dialog.raise_()

    def _current_token(self) -> str:
        """The freshest bearer token: the OIDC session's (refreshed) access
        token when present, else the launch/dev token."""
        if self._auth_session is not None and getattr(self._auth_session, "access_token", ""):
            return self._auth_session.access_token
        return self._token

    def _query_audit(self, filters: dict, reset: bool) -> None:
        """Fetch a page of /api/audit on a background thread and marshal the
        result back to the GUI thread via the _audit_loaded signal."""
        if self._audit_dialog is not None:
            self._audit_dialog.begin_load(reset)
        url = rest.audit_url(
            _http_base(self._url),
            event_class=filters.get("event_class", ""),
            outcome=filters.get("outcome", ""),
            q=filters.get("q", ""),
            cursor=filters.get("cursor", ""),
        )
        token = self._current_token()

        def _work() -> None:
            try:
                data = rest.fetch_json(url, token)
                rows, nxt = rest.parse_audit_response(data)
                self._audit_loaded.emit({"rows": rows, "next_cursor": nxt, "error": None})
            except Exception as exc:  # noqa: BLE001 — surfaced in the dialog
                self._audit_loaded.emit({"rows": [], "next_cursor": None, "error": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

    def _download(self, url: str, filename: str) -> None:
        """Download an authed backend file (``/api/download/...``) to disk: open a
        native Save dialog, then fetch with the session token on a background
        thread and marshal the outcome back via ``_download_done``."""
        fn = filename or "download"
        save_path, _ = QFileDialog.getSaveFileName(self, "Save file", fn)
        if not save_path:
            return
        full = str(url) if str(url).startswith("http") else _http_base(self._url) + str(url)
        token = self._current_token()
        self.topbar.set_status(f"Downloading {os.path.basename(save_path)}…", T.MUTED)

        def _work() -> None:
            try:
                data = rest.fetch_bytes(full, token)
                with open(save_path, "wb") as fh:
                    fh.write(data)
                self._download_done.emit({"path": save_path, "error": None})
            except Exception as exc:  # noqa: BLE001 — surfaced in the status bar
                self._download_done.emit({"path": None, "error": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

    def _on_download_done(self, result: object) -> None:
        """GUI-thread handler for a finished download."""
        if not isinstance(result, dict):
            return
        if result.get("error"):
            self.topbar.set_status(f"Download failed: {result['error']}", T.VARIANT_COLORS["error"][0])
        else:
            self.topbar.set_status(
                f"Saved {os.path.basename(str(result.get('path')))}", T.VARIANT_COLORS["success"][0])

    # --- chat attachments (feature 044 US4) -------------------------------- #
    def _pick_files(self) -> None:
        """Paperclip → Upload files…: multi-select up to 10 staged files total,
        each uploaded on a worker thread (result marshalled back via signal)."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Upload files", "", "All files (*)")
        if not paths:
            return
        room = 10 - len(self._attachments)
        if room <= 0:
            self._show_banner("You can attach up to 10 files per message.", "warning")
            return
        if len(paths) > room:
            self._show_banner("You can attach up to 10 files per message.", "warning")
        for path in paths[:room]:
            self._stage_upload(path)

    def _stage_upload(self, path: str) -> None:
        """Stage a chip in the 'uploading' state and upload the file off-thread."""
        import uuid

        chip_id = uuid.uuid4().hex
        self._attachments.append({
            "chip_id": chip_id, "attachment_id": None,
            "filename": os.path.basename(path), "category": "file",
            "parser_status": None, "status": "uploading",
        })
        self._render_chips()
        token = self._current_token()
        http_base = _http_base(self._url)

        def _work() -> None:
            import mimetypes

            try:
                with open(path, "rb") as fh:
                    data = fh.read()
                mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
                result = rest.upload_attachment(
                    http_base, token, os.path.basename(path), mime, data)
                self._attachment_uploaded.emit({"chip_id": chip_id, "result": result, "error": None})
            except Exception as exc:  # noqa: BLE001 — surfaced on the chip / banner
                self._attachment_uploaded.emit({"chip_id": chip_id, "result": None, "error": str(exc)})

        threading.Thread(target=_work, daemon=True).start()

    def _on_attachment_uploaded(self, payload: object) -> None:
        """GUI-thread handler for a finished upload: flip the chip to staged/failed."""
        if not isinstance(payload, dict):
            return
        rec = next((c for c in self._attachments
                    if c.get("chip_id") == payload.get("chip_id")), None)
        if rec is None:
            return  # the chip was removed before the upload finished
        result = payload.get("result")
        if payload.get("error") or not isinstance(result, dict):
            rec["status"] = "failed"
            self._show_banner(
                f"Couldn't upload {rec['filename']}: {payload.get('error') or 'upload failed'}",
                "warning")
        else:
            rec["attachment_id"] = result.get("attachment_id")
            rec["filename"] = result.get("filename") or rec["filename"]
            rec["category"] = result.get("category") or "file"
            rec["parser_status"] = result.get("parser_status") or "covered"
            rec["status"] = "staged" if rec["attachment_id"] else "failed"
        self._render_chips()

    def _stage_existing(self, payload: dict) -> None:
        """Stage a chip for an already-uploaded file (the attachments surface
        'Attach' button → `attach_existing`, intercepted client-side)."""
        aid = (payload or {}).get("attachment_id")
        if not aid:
            return
        if any(c.get("attachment_id") == aid for c in self._attachments):
            return  # already staged
        if len(self._attachments) >= 10:
            self._show_banner("You can attach up to 10 files per message.", "warning")
            return
        import uuid

        self._attachments.append({
            "chip_id": uuid.uuid4().hex, "attachment_id": aid,
            "filename": payload.get("filename") or "file",
            "category": payload.get("category") or "file",
            "parser_status": payload.get("parser_status") or "covered",
            "status": "staged",
        })
        self._render_chips()

    def _remove_chip(self, chip_id: str) -> None:
        self._attachments = [c for c in self._attachments if c.get("chip_id") != chip_id]
        self._render_chips()

    def _clear_attachments(self) -> None:
        self._attachments = []
        self._render_chips()

    def _clear_sent_attachments(self) -> None:
        """After a send, drop the chips that went out (staged) and any failed
        ones, but KEEP still-uploading chips so a late ``_on_attachment_uploaded``
        for one isn't silently dropped — they stay staged for the next turn."""
        self._attachments = [
            c for c in self._attachments if c.get("status") == "uploading"
        ]
        self._render_chips()

    def _sendable_attachments(self) -> List[dict]:
        """The staged (successfully uploaded) attachments to attach to a turn."""
        return [{"attachment_id": c["attachment_id"], "filename": c["filename"],
                 "category": c.get("category") or "file"}
                for c in self._attachments
                if c.get("attachment_id") and c.get("status") == "staged"]

    def _chip_widget(self, rec: dict) -> QWidget:
        chip = QFrame()
        _scoped(chip, f"background:{T.SURFACE_2}; border:1px solid {T.BORDER}; border-radius:12px;")
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(10, 3, 6, 3)
        lay.setSpacing(6)
        status = rec.get("status")
        if status == "uploading":
            glyph, tip = "⏳", "uploading…"
        elif status == "failed":
            glyph, tip = "✗", "upload failed"
        else:
            glyph, tip = parser_status_glyph(rec.get("parser_status"))
        lbl = QLabel(f"{glyph} {rec.get('filename', 'file')}".strip())
        lbl.setToolTip(tip)
        lbl.setStyleSheet(f"color:{T.TEXT}; font-size:12px; background:transparent;")
        rm = QPushButton("✕")
        rm.setFixedSize(18, 18)
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setStyleSheet("padding:0; border:none; background:transparent;")
        rm.clicked.connect(lambda _=False, cid=rec.get("chip_id"): self._remove_chip(cid))
        lay.addWidget(lbl)
        lay.addWidget(rm)
        return chip

    def _render_chips(self) -> None:
        while self._chips_lay.count():
            item = self._chips_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for rec in self._attachments:
            self._chips_lay.addWidget(self._chip_widget(rec))
        self._chips_lay.addStretch(1)
        self._chips_bar.setVisible(bool(self._attachments))

    def _on_audit_loaded(self, result: object) -> None:
        """GUI-thread handler for a loaded audit page."""
        if self._audit_dialog is None or not isinstance(result, dict):
            return
        if result.get("error"):
            self._audit_dialog.set_error(str(result["error"]))
        else:
            self._audit_dialog.add_page(result.get("rows") or [], result.get("next_cursor"))

    def _load_chat(self, chat_id: str) -> None:
        self.rail.clear()
        self._stream_seq.clear()
        self.client.send_event("load_chat", {"chat_id": chat_id})

    def _sign_out(self) -> None:
        if (
            QMessageBox.question(self, "Sign out", "Sign out of AstralDeep?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        # Feature 044 (FR-005): server-revoking sign-out. Capture the refresh
        # credential BEFORE tearing down, then revoke best-effort on a worker
        # thread (backend → direct-Keycloak fallback → local-only) so the UI
        # never blocks; the app quits when revocation resolves or times out.
        sess = self._auth_session
        refresh_token = getattr(sess, "refresh_token", None) if sess else None
        client_id = getattr(sess, "client_id", "astral-desktop") if sess else "astral-desktop"
        token_url = getattr(sess, "token_url", "") if sess else ""
        access = self._current_token()
        http_base = _http_base(self._url)
        self._show_banner("Signing out…")

        def _revoke() -> None:
            outcome = "local-only"
            if refresh_token:
                if rest.native_logout(http_base, access, refresh_token, client_id):
                    outcome = "revoked (server)"
                else:
                    authority = ""
                    if token_url.endswith("/protocol/openid-connect/token"):
                        authority = token_url[: -len("/protocol/openid-connect/token")]
                    if authority and rest.keycloak_logout(authority, client_id, refresh_token):
                        outcome = "revoked (keycloak)"
                    else:
                        outcome = "revocation failed — local sign-out only"
            logger.info("sign-out: %s", outcome)
            self._signed_out.emit(outcome)

        threading.Thread(target=_revoke, daemon=True).start()
        # Safety net: quit even if the network hangs past the request timeouts.
        QTimer.singleShot(12000, self._finish_sign_out)

    def _finish_sign_out(self, _outcome: str = "") -> None:
        if getattr(self, "_signing_out_done", False):
            return
        self._signing_out_done = True
        try:
            self.client.stop()
        except Exception:
            pass
        QApplication.instance().quit()

    # --- outbound -------------------------------------------------------- #
    def _send(self) -> None:
        text = self._input.text().strip()
        atts = self._sendable_attachments()
        if not text and not atts:
            return
        self._input.clear()
        # Show the turn in the rail (auto-drops the empty-state hint), plus a
        # small attachment line mirroring the web '📎 name'.
        if text:
            self.rail.add("user", text)
        if atts:
            names = ", ".join(a["filename"] for a in atts)
            if not text:
                self.rail.add("user", "📎 " + names)
            else:
                self.rail.add_note("📎 " + names)
        self.client.send_chat(text, self.active_chat, attachments=atts or None)
        # Optimistic loading state until the turn's first canvas content — the
        # typed path matches _emit's chat_message twin (feature 055 US1):
        # retire the ephemeral welcome, then arm the skeleton.
        if not self._timeline_mode:
            self._set_turn_active(True)
            self.canvas.purge_welcome()
            self.canvas.show_skeleton()
        # Clear only the chips that went out; keep still-uploading ones so a late
        # upload result isn't lost (they remain staged for the next turn).
        self._clear_sent_attachments()

    def _emit(self, action: str, payload: dict) -> None:
        if action == "attach_existing":
            # Feature 044 (US4): the attachments-surface 'Attach' button stages a
            # chip locally — it is NOT forwarded to the server.
            self._stage_existing(payload or {})
            return
        if action == "chat_message":
            msg = payload.get("message", "")
            if msg:
                self.rail.add("user", msg)
            self.client.send_chat(msg, self.active_chat)
            # Optimistic loading state until the turn's first canvas content
            # (parity with the Android twin's send-time skeleton); the welcome
            # is retired BEFORE the skeleton arms (feature 055 US1).
            if not self._timeline_mode:
                self._set_turn_active(True)
                self.canvas.purge_welcome()
                self.canvas.show_skeleton()
        else:
            self.client.send_event(action, payload, session_id=self.active_chat)

    def _emit_chrome(self, action: str, payload: dict) -> None:
        """Actions from native chrome dialogs (agents)."""
        self.client.send_event(action, payload, session_id=self.active_chat)

    # --- inbound --------------------------------------------------------- #
    def _on_status(self, s: str) -> None:
        # Feature 044: the transport now owns reconnect + a bounded outbound
        # queue, so its status vocabulary widened to connecting / connected /
        # reconnecting:<n> / closed:<why> / auth_required:<reason> /
        # send_dropped:<action>. The connection banner mirrors it; errors and
        # drop notices reuse the same banner.
        if s.startswith("send_dropped:"):
            action = s.split(":", 1)[1] or "message"
            self._show_banner(
                f"Couldn't send while offline: {action}. It was not queued — "
                "reconnect and try again.", "warning")
            return

        nice = {"connecting": "Connecting…", "connected": "Connected"}.get(s, s)
        color = (
            T.VARIANT_COLORS["success"][0]
            if s == "connected"
            else (
                T.VARIANT_COLORS["error"][0]
                if s.startswith(("closed", "auth_required"))
                else T.VARIANT_COLORS["accent"][0]
            )
        )
        if s.startswith("closed"):
            nice = "Disconnected"
            # C-3: a dropped connection (e.g. orchestrator restart) must re-send
            # register_external_agent on the next 'connected', or the win_agent
            # stays unreachable to the orchestrator until the app is relaunched.
            self._win_agent_registered = False
            self._show_banner("Disconnected — reconnecting…", "warning")
        elif s.startswith("reconnecting"):
            attempt = s.split(":", 1)[1] if ":" in s else "?"
            nice = "Reconnecting…"
            self._show_banner(f"Reconnecting… (attempt {attempt})", "warning")
        elif s == "connecting":
            if self._connected_once:
                self._show_banner("Reconnecting…", "warning")
        elif s.startswith("auth_required"):
            nice = "Re-authenticating…"
        self.topbar.set_status(nice, color)
        if s == "connected":
            self._reauth_tries = 0
            self._connected_once = True
            self._hide_banner()
            if not self._win_agent_registered:
                self._win_agent_registered = True
                url = f"http://{self._win_agent_host}:{self._win_agent_port}"
                self.client.send_event("register_external_agent", {"url": url})
            # Pull chrome state so the native dialogs + CTA are accurate.
            self.client.send_event("discover_agents", {})
            self.client.send_event("get_history", {})
        elif s.startswith("auth_required"):
            self._begin_silent_refresh()

    def _reset_status_line(self) -> None:
        """Set the top-bar mark back to 'Connected' (green) WITHOUT the full
        reconnect re-sync. Used to clear a per-turn status line (chat_status:done,
        stream_unsubscribed): unlike the real ``connected`` transition it does not
        hide banners or re-send discover_agents/get_history/win-agent
        registration, which on every turn completion would wipe task/error/
        notification banners and cause redundant round-trips (feature 044 fix)."""
        self.topbar.set_status("Connected", T.VARIANT_COLORS["success"][0])

    def _set_turn_active(self, active: bool) -> None:
        """Single write point for the per-turn flag; the canvas mirrors it so
        an empty render mid-turn keeps the loading state instead of the idle
        empty-state hint (feature 055 US1)."""
        self._turn_active = active
        self.canvas.turn_active = active

    def _begin_silent_refresh(self) -> None:
        """FR-004: silently refresh the session token OFF the GUI thread — the
        refresh does a blocking urlopen (up to 15 s) that would freeze the GUI if
        run here (this is a slot on the transport `status` signal). The new token
        is marshaled back via ``_silent_refresh_done``; on success we reconnect,
        on failure we offer an explicit sign-in. Bounded to ``_reauth_tries < 2``
        and guarded so two ``auth_required`` frames don't fire two concurrent
        refreshes. With no refreshable session (dev-token) we prompt immediately."""
        if self._silent_refresh_active:
            return
        if not (self._auth_session and self._reauth_tries < 2):
            # No session to refresh, or the retry bound is exhausted — never a
            # dead session: offer an explicit sign-in (FR-004).
            self._prompt_reauth()
            return
        self._reauth_tries += 1
        self._silent_refresh_active = True
        sess = self._auth_session

        def _work() -> None:
            try:
                token = sess.refresh()
            except Exception:  # noqa: BLE001 — treated as a failed refresh
                token = None
            self._silent_refresh_done.emit(token)

        threading.Thread(target=_work, name="astral-silent-refresh", daemon=True).start()

    def _on_silent_refresh_done(self, token: object) -> None:
        """GUI-thread handler for a finished silent refresh (M1). Reconnect with
        the new token, or fall through to the explicit sign-in prompt."""
        self._silent_refresh_active = False
        if isinstance(token, str) and token:
            self._reconnect(token)
        else:
            # FR-004: never a dead session — offer an explicit sign-in instead of
            # a frozen "Re-authenticating…" caption.
            self._prompt_reauth()

    def _reconnect(self, token: str) -> None:
        try:
            self.client.stop()
        except Exception:
            pass
        # Detach the dead client's signals before swapping it out, so a late
        # queued frame from the old transport thread can't drive the new UI.
        try:
            self.client.message.disconnect(self._on_message)
            self.client.status.disconnect(self._on_status)
        except (RuntimeError, TypeError, AttributeError):
            pass
        self._token = token
        self._win_agent_registered = False
        self.client = OrchestratorClient(
            self._url, token, device_caps(supported_types=native_types())
        )
        self.client.message.connect(self._on_message)
        self.client.status.connect(self._on_status)
        self.client.start()

    def _prompt_reauth(self) -> None:
        """FR-004: session expired and cannot silently refresh — offer an
        explicit sign-in rather than a dead 'Re-authenticating…' caption."""
        self.topbar.set_status("Signed out", T.VARIANT_COLORS["error"][0])
        self._show_banner("Your session expired.", "error")
        authority = self._login_params.get("authority")
        if not authority:
            # dev-token / no configured IdP — nothing to sign in against.
            self._show_banner(
                "Your session expired. Restart the app to sign in again.", "error")
            return
        if (
            QMessageBox.question(self, "Session expired",
                                 "Your session expired. Sign in again?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._show_banner("Opening your browser to sign in…")

        def _login() -> None:
            try:
                from .auth import oidc_login
                bff_base = (_http_base(self._url)
                            if self._login_params.get("bff") else None)
                session = oidc_login(
                    authority,
                    client_id=self._login_params.get("client_id", "astral-desktop"),
                    bff_base=bff_base,
                )
                self._reauth_done.emit(session)
            except Exception:  # noqa: BLE001 — surfaced in the banner
                logger.warning("interactive re-auth failed", exc_info=True)
                self._reauth_done.emit(None)

        threading.Thread(target=_login, daemon=True).start()

    def _on_reauth_done(self, session: object) -> None:
        if session is None:
            self._show_banner("Sign-in failed. Try again from the menu.", "error")
            return
        self._auth_session = session
        self._reauth_tries = 0
        self._reconnect(session.access_token)
        self._hide_banner()

    # --- window-first startup sign-in ------------------------------------ #
    def begin_login(self, resolver) -> None:
        """Resolve auth on a worker thread while the window stays interactive.

        ``resolver(cancel_event)`` returns ``(token, session)`` (or raises
        ``LoginCancelled``); the outcome is marshalled back to the GUI thread
        via ``_login_resolved``. The top-bar shows sign-in progress and the
        banner offers a click-to-cancel path for the loopback wait.
        """
        if self._login_active:
            return
        self._login_active = True
        self._login_resolver = resolver
        self._login_cancel = threading.Event()
        cancel = self._login_cancel
        self.topbar.set_status("Signing in…", T.MUTED)
        self._show_banner(
            "Signing in — complete the sign-in in your browser. "
            "Click here to cancel."
        )

        def _work() -> None:
            try:
                token, session = resolver(cancel)
                self._login_resolved.emit({"token": token, "session": session})
            except LoginCancelled:
                self._login_resolved.emit({"cancelled": True})
            except Exception as exc:  # noqa: BLE001 — surfaced via the retry prompt
                logger.warning("startup sign-in failed", exc_info=True)
                self._login_resolved.emit({"error": str(exc)})

        threading.Thread(target=_work, name="astral-login", daemon=True).start()

    def cancel_login(self) -> None:
        """Abort an in-flight startup sign-in (unblocks the loopback wait)."""
        if self._login_cancel is not None:
            self._login_cancel.set()
            self.topbar.set_status("Cancelling sign-in…", T.MUTED)

    def _on_login_resolved(self, result: object) -> None:
        """GUI-thread handler for the startup sign-in outcome: adopt the token,
        or offer a retry/quit choice on cancel/failure."""
        self._login_active = False
        result = result if isinstance(result, dict) else {}
        token = result.get("token")
        if isinstance(token, str) and token:
            self._hide_banner()
            self._apply_login(token, result.get("session"))
            return
        self.topbar.set_status("Not signed in", T.VARIANT_COLORS["error"][0])
        self._login_retry_prompt("cancelled" if result.get("cancelled") else "failed")

    def _login_retry_prompt(self, verb: str) -> None:
        """Modal retry/quit choice after a cancelled/failed startup sign-in."""
        box = QMessageBox(self)
        box.setWindowTitle("Sign in")
        box.setText(f"Sign-in {verb}. Retry, or quit?")
        retry = box.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Quit", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is retry and self._login_resolver is not None:
            self.begin_login(self._login_resolver)
        else:
            self.close()

    def _apply_login(self, token: str, session=None) -> None:
        """Adopt a startup-resolved login: keep the refresh session, update the
        top-bar identity, and connect via the existing rebuild-with-new-token
        flow (no separate token-injection mechanism)."""
        self._auth_session = session
        self._reauth_tries = 0
        self.topbar.set_user(_user_from_token(token))
        self._reconnect(token)

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
                self._on_history_render(comps)
            else:
                self.canvas.set_components(comps)
        elif t == "ui_upsert":
            if not msg.get("chat_id") or msg.get("chat_id") == self.active_chat:
                self.canvas.apply_ops(msg.get("ops") or [])
        elif t == "chat_created":
            self.active_chat = (msg.get("payload") or {}).get(
                "chat_id"
            ) or self.active_chat
            self.canvas.ctx.chat_id = self.active_chat
        elif t == "chat_loaded":
            chat = msg.get("chat") or {}
            self.active_chat = chat.get("id") or self.active_chat
            self.canvas.ctx.chat_id = self.active_chat
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
        elif t == "chrome_menu":
            # Feature 042: (re)build the Settings dropdown from the server-owned
            # menu model (pushed after register / on role/flag change).
            self.topbar.set_menu_model(msg.get("model") or {})
        elif t == "chrome_surface":
            # Feature 043: a settings surface delivered as SDUI components.
            self._on_chrome_surface(msg)
        elif t == "chat_status":
            st = msg.get("status")
            if st in ("thinking", "executing", "fixing", "processing_async",
                      "combining", "condensing"):
                self._set_turn_active(True)
                self.topbar.set_status(
                    msg.get("message") or st, T.VARIANT_COLORS["accent"][0]
                )
            elif st == "done":
                self._set_turn_active(False)
                # The turn ended without canvas output (text-only answer,
                # cancellation) — clear the query-start skeleton (and restore
                # the idle hint when the canvas ended the turn empty).
                self.canvas.resolve_loading()
                # A per-turn status reset ONLY — not the full reconnect re-sync
                # (which would hide banners + re-fire discover/history every turn).
                self._reset_status_line()
        elif t == "error":
            # FR-002/SC-006 — never silent; resolve any stuck turn.
            self._show_banner(normalize_error(msg), "error")
            self._set_turn_active(False)
            self.canvas.resolve_loading()
            self.topbar.set_status("Connected", T.VARIANT_COLORS["success"][0])
        elif t == "notification":
            title = msg.get("title") or ""
            body = msg.get("body") or ""
            self._show_banner(f"{title}: {body}" if title else body,
                              "error" if msg.get("level") == "error" else "info")
        elif t == "user_message_acked":
            self._set_turn_active(True)
            self.topbar.set_status("Working…", T.VARIANT_COLORS["accent"][0])
        elif t == "chat_step":
            step = msg.get("step") or {}
            name = step.get("name") or step.get("kind") or "step"
            icon = {"completed": "✓", "errored": "✗"}.get(step.get("status"), "•")
            self.topbar.set_status(f"{icon} {name}", T.VARIANT_COLORS["accent"][0])
        elif t == "tool_progress":
            label = (msg.get("label") or msg.get("tool_name")
                     or msg.get("message") or "working")
            self.topbar.set_status(str(label), T.VARIANT_COLORS["accent"][0])
        elif t == "task_started":
            self._show_banner("Working on this in the background…")
        elif t == "task_completed":
            self._set_turn_active(False)
            self._show_banner("Background task finished.")
        elif t == "workspace_timeline_mode":
            self._timeline_mode = bool(msg.get("active") or msg.get("on"))
            if self._timeline_mode:
                self.canvas.hide_skeleton()
            # FR-007: a historical workspace view is strictly read-only — disable
            # the mutating affordances (message input + Send) while active and
            # restore them when the user returns to live. Component-action
            # mutations are also refused server-side (`_ws_timeline_mode` guard).
            self._set_composer_enabled(not self._timeline_mode)
            if self._timeline_mode:
                self._show_banner("Viewing workspace history (read-only).")
            else:
                self._hide_banner()
        elif t == "user_preferences":
            # Boot-time preferences; the theme lives under preferences.theme and
            # is applied live by the theme surface (feature 044 US5). Retained
            # so a restart honors the stored preset.
            self._user_prefs = msg.get("preferences") or {}
            self._apply_theme_pref(self._user_prefs.get("theme"))
        else:
            # Feature 044 (FR-002): classified-ignore is logged, not silent; a
            # type that is neither handled nor classified is a drift signal.
            if is_classified(t) and not is_handled(t):
                logger.info("ignored frame type=%s", t)
            elif not is_handled(t):
                logger.warning("unhandled frame type=%s", t)

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
            # Legacy teardown ack — clear the streaming status line only (a
            # per-turn reset, not the full reconnect re-sync).
            self._reset_status_line()
        # stream_list: no native surface yet.

    def _on_chrome_render(self, msg: dict) -> None:
        """Server-pushed app-chrome is web-shell HTML; this native client renders
        chrome as Qt (driven by data actions), so we acknowledge the frame rather
        than silently dropping it — never injecting a web view."""
        notice = chrome_render_notice(msg)
        if notice:
            self.topbar.set_status(notice, T.MUTED)

    def _on_history_render(self, components: list) -> None:
        """Feature 044 (T032) — a server-pushed SDUI history surface
        (``ui_render target=history``, feature 037). The desktop shows recent
        chats in a native Recent-chats dialog fed by ``history_list``; when that
        dialog is open we refresh it from this surface's ``chat_history`` items so
        the SDUI surface still drives the native surface. Never silently dropped
        (was ``pass``): the render is logged with intent even when no dialog is
        open, consistent with ``load_chat``/``history_list`` handling."""
        items: List[dict] = []
        for comp in components or []:
            if not isinstance(comp, dict):
                continue
            if comp.get("type") == "chat_history":
                for it in comp.get("items", comp.get("chats", [])) or []:
                    if isinstance(it, dict):
                        items.append(it)
        if self._history_dialog is not None and items:
            self._history_dialog.set_chats(items)
        logger.info("history surface rendered (%d chats)", len(items))

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
            # Feature 044 (US4): re-hydrate a turn's attachment chips as a small
            # rail line (the server re-adds `attachments` on user messages).
            atts = m.get("attachments")
            if isinstance(atts, list) and atts:
                names = ", ".join(
                    str(a.get("filename") or "file") for a in atts if isinstance(a, dict))
                if names:
                    self.rail.add_note("📎 " + names)
                    shown = True
        if not shown:
            self.rail.show_empty_hint()

    # --- cross-thread confirmation + workspace (feature 039 UX) ------------- #

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
        # Lazy first-use workspace pick: a redirected pick denies the in-flight
        # call (it was confined to the old default root) — retry runs under it.
        if not self._ensure_workspace_selected():
            return {"accepted": False, "choice": None}
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
        return QSettings("AstralDeep", "WindowsClient")

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
        """Apply a persisted/env workspace at startup — never prompts.

        Precedence: persisted QSettings choice > ASTRAL_WORKSPACE_DIR env.
        With neither, nothing is applied here: the folder picker is deferred to
        the first file-tool use (``_ensure_workspace_selected`` via the confirm
        bridge) so no modal dialog can block first paint.
        """
        env_dir = os.getenv("ASTRAL_WORKSPACE_DIR", "").strip()
        persisted = self._settings().value("workspace_dir", "", type=str) or ""
        chosen = persisted or env_dir
        if chosen:
            self._activate_workspace(chosen)

    def _activate_workspace(self, chosen: str) -> None:
        """Create + persist + apply a workspace folder (falls back to the
        default ~/AstralWorkspace when the folder can't be created)."""
        chosen = os.path.realpath(chosen)
        try:
            os.makedirs(chosen, exist_ok=True)
        except OSError:
            chosen = os.path.join(os.path.expanduser("~"), "AstralWorkspace")
            os.makedirs(chosen, exist_ok=True)
        self._settings().setValue("workspace_dir", chosen)
        self._apply_workspace(chosen)

    def _default_workspace(self) -> str:
        """The launch-default confinement root the tools fall back to before
        any workspace is applied (mirrors win_agent.tools.workspace_root)."""
        return os.path.realpath(
            os.path.expanduser(os.path.join("~", "AstralWorkspace"))
        )

    def _ensure_workspace_selected(self) -> bool:
        """Lazily resolve the workspace on the first file-tool use.

        Returns True when the in-flight tool call may proceed. When the
        first-time pick lands somewhere OTHER than the default root the call
        was already confined to, the call is denied (False) so it can be
        retried under the newly chosen root — the pick still applies.
        """
        if self._workspace_ready:
            return True
        default_root = self._default_workspace()
        chosen = (
            self._gui_pick_directory(
                "Choose the folder where Astral may read & write files",
                os.path.expanduser("~"),
            )
            or default_root
        )
        self._activate_workspace(chosen)
        return os.path.realpath(chosen) == default_root

    def _apply_workspace(self, path: str) -> None:
        """Push the chosen workspace into the tools + audit modules + env."""
        path = os.path.realpath(path)
        os.environ["ASTRAL_WORKSPACE_DIR"] = path
        try:
            import win_agent.tools as _tools

            _tools.set_workspace_override(path)
        except Exception:  # noqa: BLE001
            pass
        self._workspace_ready = True
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

    # --- launch-time integrity / update check (feature 039 B.5) ------------- #

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
    from PySide6.QtGui import QFont, QFontDatabase, QIcon

    families = set(QFontDatabase.families())
    family = next(
        (f for f in ("Inter", "Segoe UI", "Arial") if f in families),
        app.font().family(),
    )
    app.setFont(QFont(family, 10))
    app.setStyleSheet(T.APP_STYLESHEET + T.ROOT_BG_STYLE)

    # Window/taskbar icon: assets/ sits next to the source tree in dev and is
    # extracted to sys._MEIPASS in a frozen build. Best-effort — a missing
    # asset must never block startup.
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(__file__), ".."))
    ico = os.path.join(base, "assets", "astraldeep.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))


def _http_base(ws_url: str) -> str:
    """ws://host:port/ws -> http://host:port (the orchestrator's HTTP origin)."""
    from urllib.parse import urlparse

    u = urlparse(ws_url)
    scheme = "https" if u.scheme == "wss" else "http"
    return f"{scheme}://{u.netloc}"


def resolve_auth(args, cancel_event=None):
    """Return (token, session). An explicit --token/ASTRAL_TOKEN wins (use
    'dev-token' for a mock-auth orchestrator). Otherwise, if a Keycloak authority
    is configured, run the interactive OIDC desktop login — by default with the
    dedicated public client (astral-desktop), exchanging the code DIRECTLY
    against Keycloak; with --bff it reuses the web's astral-frontend via the
    orchestrator's BFF proxy. Falls back to 'dev-token' on failure; a
    user-cancelled login (``cancel_event``) re-raises ``LoginCancelled`` —
    cancel is a choice, not a failure to paper over with a dev token."""
    if args.token:
        return args.token, None
    if args.authority:
        try:
            from .auth import oidc_login

            bff_base = _http_base(args.url) if getattr(args, "bff", False) else None
            session = oidc_login(
                args.authority, client_id=args.client_id, bff_base=bff_base,
                cancel_event=cancel_event,
            )
            return session.access_token, session
        except LoginCancelled:
            raise
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
    dlg.setWindowTitle("Configure AstralDeep")
    dlg.setMinimumWidth(540)
    dlg.setStyleSheet(f"QDialog {{ background:{T.BG}; }}")
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(8)
    intro = QLabel(
        "Point this app at your AstralDeep deployment. These are saved on this "
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
    explicit token; ``prompt=None`` resolves non-interactively (the window-first
    launch defers the first-run dialog until after first paint).
    ``settings``/``prompt`` are injected for testability.
    """
    authority = (os.getenv("KEYCLOAK_AUTHORITY")
                 or settings.value("config/authority", "", type=str) or "")
    ws_url = (os.getenv("ASTRAL_WS_URL")
              or settings.value("config/ws_url", "", type=str)
              or "ws://127.0.0.1:8001/ws")
    agent_key = (os.getenv("AGENT_API_KEY")
                 or settings.value("config/agent_key", "", type=str) or "")

    if not authority and not args.token and prompt is not None:
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
    ap = argparse.ArgumentParser(description="AstralDeep native Windows client")
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
    _win = _launch(args)  # keep the window referenced for the app's lifetime
    return app.exec()


def _launch(args, settings=None) -> "MainWindow":
    """Window-first startup: show the shell immediately, then resolve the
    first-run config prompt and the (potentially slow) OIDC sign-in AFTER first
    paint — auth runs on a worker thread and the token is adopted through the
    existing rebuild-with-new-token flow. An explicit --token/ASTRAL_TOKEN
    keeps the original synchronous path (it resolves instantly)."""
    settings = settings or QSettings("AstralDeep", "WindowsClient")
    _resolve_config(args, settings=settings, prompt=None)
    login_params = {
        "authority": args.authority,
        "client_id": args.client_id,
        "bff": bool(getattr(args, "bff", False)),
    }
    if args.token:
        token, session = resolve_auth(args)
        win = MainWindow(args.url, token, session=session, login_params=login_params)
        win.show()
        win.raise_()
        win.activateWindow()
        return win

    win = MainWindow(
        args.url, "", session=None, login_params=login_params, connect=False
    )
    win.show()
    win.raise_()
    win.activateWindow()
    win.topbar.set_status("Signing in…", T.MUTED)

    def _after_first_paint() -> None:
        """Deferred startup tail: first-run config dialog (if still needed),
        then the background sign-in."""
        if not args.authority:
            _resolve_config(args, settings=settings, prompt=_prompt_config)
            win._login_params.update(
                authority=args.authority,
                client_id=getattr(args, "client_id", "astral-desktop"),
                bff=bool(getattr(args, "bff", False)),
            )
        win.begin_login(lambda cancel: resolve_auth(args, cancel_event=cancel))

    QTimer.singleShot(0, _after_first_paint)
    return win


if __name__ == "__main__":
    raise SystemExit(main())
