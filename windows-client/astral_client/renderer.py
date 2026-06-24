"""Native renderer: AstralBody SDUI component dicts -> PySide6 widgets.

This is a real ROTE/webrender *target* — it consumes the same structured
`components` that the orchestrator puts on every `ui_render`/`ui_upsert` (the
non-web wire layer, FR-018) and draws native Qt widgets instead of HTML. The web
renderer (backend/webrender/renderer.py) is the reference for field shapes.

Public API:
    render(component: dict, ctx: RenderContext) -> QWidget

`ctx.emit(action, payload)` is called for interactive components (buttons,
history rows, param-picker / table-pagination submits) so the app can post a
`ui_event` back to the orchestrator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QProgressBar,
    QHeaderView,
)

from . import theme as T


@dataclass
class RenderContext:
    """Carried through a render pass. `emit` posts a ui_event back to the server."""

    emit: Callable[[str, dict], None]


# --------------------------------------------------------------------------- #
# small widget helpers
# --------------------------------------------------------------------------- #


def _label(
    text: str,
    *,
    color: str = T.TEXT,
    size: int = 14,
    bold: bool = False,
    markdown: bool = False,
    wrap: bool = True,
) -> QLabel:
    lab = QLabel()
    lab.setFrameShape(QFrame.Shape.NoFrame)
    lab.setTextFormat(
        Qt.TextFormat.MarkdownText if markdown else Qt.TextFormat.PlainText
    )
    lab.setText(str(text))
    lab.setWordWrap(wrap)
    lab.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    lab.setOpenExternalLinks(True)
    weight = "600" if bold else "400"
    lab.setStyleSheet(
        f"color:{color}; font-size:{size}px; font-weight:{weight}; background:transparent;"
    )
    return lab


def _vbox(spacing: int = 8, margins: tuple = (0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    return lay


_box_counter = [0]


def _scoped(widget: QWidget, css: str) -> QWidget:
    """Apply ``css`` to ``widget`` ONLY, via an object-name selector.

    A bare-property stylesheet (e.g. ``border: 1px solid``) set directly on a
    container cascades that border onto every child widget in Qt — which is why
    a card's border was bleeding onto its labels. Scoping to ``#name`` confines
    it to the container itself.
    """
    _box_counter[0] += 1
    name = f"abox{_box_counter[0]}"
    widget.setObjectName(name)
    widget.setStyleSheet(f"#{name} {{ {css} }}")
    return widget


def _card_frame(
    radius: int = 12, bg: str = T.SURFACE, border: str = T.BORDER
) -> QFrame:
    f = QFrame()
    _scoped(f, f"background:{bg}; border:1px solid {border}; border-radius:{radius}px;")
    f.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return f


def _children(comp: dict) -> List[dict]:
    kids = comp.get("content")
    if kids is None:
        kids = comp.get("children")
    if isinstance(kids, dict):
        return [kids]
    if isinstance(kids, list):
        return [c for c in kids if isinstance(c, dict)]
    if isinstance(kids, str):
        return [{"type": "text", "content": kids}]
    return []


def _render_into(layout, items: List[dict], ctx: RenderContext) -> None:
    for child in items:
        layout.addWidget(render(child, ctx))


# --------------------------------------------------------------------------- #
# primitive renderers
# --------------------------------------------------------------------------- #

_TEXT_SIZES = {
    "h1": (26, True),
    "h2": (21, True),
    "h3": (17, True),
    "body": (14, False),
    "caption": (12, False),
}


def _r_text(c, ctx):
    variant = c.get("variant", "body")
    content = c.get("content", c.get("text", ""))
    if variant == "markdown":
        return _label(content, markdown=True)
    size, bold = _TEXT_SIZES.get(variant, (14, False))
    color = T.MUTED if variant == "caption" else T.TEXT
    return _label(content, color=color, size=size, bold=bold)


def _r_card(c, ctx):
    frame = _card_frame()
    lay = _vbox(10, (16, 14, 16, 14))
    frame.setLayout(lay)
    title = c.get("title")
    if title:
        row = QHBoxLayout()
        row.setSpacing(8)
        bar = QLabel()
        bar.setFixedSize(4, 18)
        bar.setStyleSheet(f"background:{T.PRIMARY}; border-radius:2px;")
        row.addWidget(bar)
        row.addWidget(_label(title, size=16, bold=True))
        row.addStretch(1)
        lay.addLayout(row)
    _render_into(lay, _children(c), ctx)
    return frame


def _r_container(c, ctx):
    w = QWidget()
    lay = _vbox(10)
    w.setLayout(lay)
    _render_into(lay, _children(c), ctx)
    return w


def _r_grid(c, ctx):
    w = QWidget()
    grid = QGridLayout()
    grid.setSpacing(10)
    grid.setContentsMargins(0, 0, 0, 0)
    w.setLayout(grid)
    cols = max(1, int(c.get("columns", 2) or 2))
    for i, child in enumerate(_children(c)):
        grid.addWidget(render(child, ctx), i // cols, i % cols)
    return w


def _r_hero(c, ctx):
    frame = QFrame()
    gradient = c.get("variant") == "gradient"
    bg = (
        T.GRAD
        if gradient
        else "qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        "stop:0 rgba(99,102,241,0.14), stop:1 rgba(139,92,246,0.06))"
    )
    _scoped(frame, f"background:{bg}; border:1px solid {T.BORDER}; border-radius:14px;")
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lay = _vbox(4, (20, 18, 20, 18))
    frame.setLayout(lay)
    if c.get("eyebrow"):
        lab = _label(str(c["eyebrow"]).upper(), color=T.PRIMARY, size=11, bold=True)
        lay.addWidget(lab)
    lay.addWidget(_label(c.get("title", ""), size=24, bold=True))
    if c.get("subtitle"):
        lay.addWidget(_label(c["subtitle"], color=T.MUTED, size=13))
    badges = c.get("badges") or []
    if badges:
        row = QHBoxLayout()
        row.setSpacing(6)
        for b in badges:
            row.addWidget(_r_badge({"label": b, "variant": "default"}, ctx))
        row.addStretch(1)
        lay.addLayout(row)
    return frame


def _r_badge(c, ctx):
    color, bg = T.VARIANT_COLORS.get(
        c.get("variant", "default"), T.VARIANT_COLORS["default"]
    )
    lab = QLabel(str(c.get("label", "")))
    lab.setStyleSheet(
        f"color:{color}; background:{bg}; border:1px solid {color};"
        f"border-radius:10px; padding:2px 10px; font-size:12px; font-weight:600;"
    )
    lab.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    return lab


def _r_metric(c, ctx):
    frame = QFrame()
    _scoped(
        frame,
        "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        "stop:0 rgba(99,102,241,0.18), stop:1 rgba(99,102,241,0.03));"
        f"border:1px solid {T.BORDER}; border-radius:12px;",
    )
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lay = _vbox(2, (16, 14, 16, 14))
    frame.setLayout(lay)
    lay.addWidget(
        _label(str(c.get("title", "")).upper(), color=T.MUTED, size=11, bold=True)
    )
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(_label(c.get("value", ""), size=24, bold=True))
    if c.get("delta"):
        row.addWidget(
            _label(
                str(c["delta"]),
                color=T.VARIANT_COLORS["success"][0],
                size=13,
                bold=True,
            )
        )
    row.addStretch(1)
    lay.addLayout(row)
    if c.get("subtitle"):
        lay.addWidget(_label(c["subtitle"], color=T.MUTED, size=12))
    return frame


def _r_keyvalue(c, ctx):
    frame = _card_frame()
    lay = _vbox(8, (16, 14, 16, 14))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], size=14, bold=True))
    grid = QGridLayout()
    grid.setSpacing(8)
    for i, item in enumerate(c.get("items", []) or []):
        if not isinstance(item, dict):
            continue
        k = _label(
            str(item.get("label", "")).upper(), color=T.MUTED, size=11, bold=True
        )
        v = _label(item.get("value", ""), size=14, bold=True)
        grid.addWidget(k, i, 0)
        grid.addWidget(v, i, 1)
    grid.setColumnStretch(1, 1)
    lay.addLayout(grid)
    return frame


def _r_timeline(c, ctx):
    frame = _card_frame()
    lay = _vbox(8, (16, 14, 16, 14))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], size=14, bold=True))
    for item in c.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        row = QHBoxLayout()
        row.setSpacing(10)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{T.PRIMARY}; font-size:10px;")
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        col = _vbox(0)
        if item.get("time"):
            col.addWidget(_label(item["time"], color=T.MUTED, size=11))
        col.addWidget(
            _label(item.get("title", item.get("label", "")), size=13, bold=True)
        )
        if item.get("description"):
            col.addWidget(_label(item["description"], color=T.MUTED, size=12))
        row.addLayout(col)
        row.addStretch(1)
        lay.addLayout(row)
    return frame


def _r_rating(c, ctx):
    try:
        val = float(c.get("value", 0))
        mx = int(c.get("max_value", c.get("max", 5)))
    except (TypeError, ValueError):
        val, mx = 0.0, 5
    mx = max(1, min(mx, 10))
    stars = "".join("★" if i < round(val) else "☆" for i in range(mx))
    frame = _card_frame()
    lay = _vbox(4, (16, 12, 16, 12))
    frame.setLayout(lay)
    if c.get("label") or c.get("title"):
        lay.addWidget(_label(c.get("label") or c.get("title"), size=13, bold=True))
    row = QHBoxLayout()
    row.setSpacing(8)
    sl = QLabel(stars)
    sl.setStyleSheet(f"color:{T.VARIANT_COLORS['warning'][0]}; font-size:18px;")
    row.addWidget(sl)
    row.addWidget(_label(f"{val:g}/{mx}", color=T.MUTED, size=13))
    row.addStretch(1)
    lay.addLayout(row)
    return frame


def _r_alert(c, ctx):
    color, _ = T.VARIANT_COLORS.get(c.get("variant", "info"), T.VARIANT_COLORS["info"])
    frame = QFrame()
    _scoped(
        frame,
        f"background:{T.SURFACE}; border:1px solid {T.BORDER};"
        f"border-left:3px solid {color}; border-radius:8px;",
    )
    lay = _vbox(4, (14, 12, 14, 12))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], color=color, size=14, bold=True))
    lay.addWidget(_label(c.get("message", ""), color=T.TEXT, size=13))
    return frame


def _r_button(c, ctx):
    btn = QPushButton(str(c.get("label", "Button")))
    if c.get("variant", "primary") == "primary":
        btn.setObjectName("primary")
    action = c.get("action")
    payload = c.get("payload") or {}
    if action:
        btn.clicked.connect(lambda: ctx.emit(action, dict(payload)))
    btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return btn


def _r_code(c, ctx):
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(c.get("code", ""))
    edit.setStyleSheet(
        f"background:{T.SURFACE_2}; border:1px solid {T.BORDER}; border-radius:8px;"
        f"font-family:Consolas,monospace; font-size:13px; color:{T.TEXT};"
    )
    lines = c.get("code", "").count("\n") + 1
    edit.setFixedHeight(min(360, 22 * lines + 20))
    return edit


def _r_divider(c, ctx):
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background:{T.BORDER}; max-height:1px;")
    return line


def _r_progress(c, ctx):
    w = QWidget()
    lay = _vbox(4)
    w.setLayout(lay)
    if c.get("label"):
        lay.addWidget(_label(c["label"], color=T.MUTED, size=12))
    bar = QProgressBar()
    bar.setRange(0, 100)
    try:
        bar.setValue(int(float(c.get("value", 0)) * 100))
    except (TypeError, ValueError):
        bar.setValue(0)
    bar.setTextVisible(bool(c.get("show_percentage", True)))
    bar.setStyleSheet(
        f"QProgressBar{{background:{T.SURFACE_2}; border:1px solid {T.BORDER};"
        f"border-radius:6px; height:14px; text-align:center; color:{T.TEXT};}}"
        f"QProgressBar::chunk{{background:{T.PRIMARY}; border-radius:6px;}}"
    )
    lay.addWidget(bar)
    return w


def _r_list(c, ctx):
    frame = _card_frame()
    lay = _vbox(6, (16, 12, 16, 12))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], size=14, bold=True))
    ordered = bool(c.get("ordered"))
    for i, item in enumerate(c.get("items", []) or []):
        if isinstance(item, dict):
            txt = item.get("title", item.get("content", json.dumps(item)))
        else:
            txt = str(item)
        bullet = f"{i + 1}." if ordered else "•"
        row = QHBoxLayout()
        row.setSpacing(8)
        b = _label(bullet, color=T.MUTED)
        b.setFixedWidth(20)
        row.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(_label(txt), 1)
        lay.addLayout(row)
    return frame


def _r_table(c, ctx):
    headers = c.get("headers", []) or []
    rows = c.get("rows", []) or []
    frame = _card_frame()
    lay = _vbox(8, (12, 12, 12, 12))
    frame.setLayout(lay)
    title = c.get("title") or c.get("label")
    if title:
        lay.addWidget(_label(title, size=14, bold=True))
    tbl = QTableWidget(len(rows), len(headers))
    tbl.setHorizontalHeaderLabels([str(h) for h in headers])
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    for r, row in enumerate(rows):
        for col, cell in enumerate(row if isinstance(row, list) else []):
            tbl.setItem(r, col, QTableWidgetItem(str(cell)))
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tbl.setFixedHeight(min(420, 32 * (len(rows) + 1) + 8))
    lay.addWidget(tbl)
    return frame


def _r_tabs(c, ctx):
    tabs = QTabWidget()
    for tab in c.get("tabs", []) or []:
        if not isinstance(tab, dict):
            continue
        page = QWidget()
        pl = _vbox(10, (12, 12, 12, 12))
        page.setLayout(pl)
        _render_into(pl, _children(tab), ctx)
        pl.addStretch(1)
        tabs.addTab(page, str(tab.get("label", "Tab")))
    return tabs


def _r_collapsible(c, ctx):
    frame = _card_frame()
    lay = _vbox(6, (12, 10, 12, 10))
    frame.setLayout(lay)
    body = QWidget()
    bl = _vbox(8)
    body.setLayout(bl)
    _render_into(bl, _children(c), ctx)
    body.setVisible(bool(c.get("default_open")))
    btn = QPushButton(
        ("▾ " if body.isVisible() else "▸ ") + str(c.get("title", "Details"))
    )
    btn.setStyleSheet(
        "text-align:left; border:none; background:transparent; font-weight:600;"
    )

    def toggle():
        body.setVisible(not body.isVisible())
        btn.setText(
            ("▾ " if body.isVisible() else "▸ ") + str(c.get("title", "Details"))
        )

    btn.clicked.connect(toggle)
    lay.addWidget(btn)
    lay.addWidget(body)
    return frame


def _r_chart(c, ctx):
    """bar/line/pie via QtCharts when available, else a labeled fallback."""
    try:
        from .charts import build_chart

        w = build_chart(c)
        if w is not None:
            return w
    except Exception:
        pass
    frame = _card_frame(bg=T.SURFACE_2)
    lay = _vbox(4, (16, 14, 16, 14))
    frame.setLayout(lay)
    lay.addWidget(_label(c.get("title", c.get("type", "chart")), size=14, bold=True))
    lay.addWidget(_label("(chart)", color=T.MUTED, size=12))
    return frame


def _r_chat_history(c, ctx):
    frame = _card_frame()
    lay = _vbox(4, (10, 10, 10, 10))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], size=14, bold=True))
    for item in c.get("items", c.get("chats", [])) or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("chat_id") or item.get("id")
        btn = QPushButton(str(item.get("title", "Chat")))
        btn.setStyleSheet("text-align:left; padding:8px;")
        if cid:
            btn.clicked.connect(
                lambda _=False, x=cid: ctx.emit("load_chat", {"chat_id": x})
            )
        lay.addWidget(btn)
    return frame


def _r_skeleton(c, ctx):
    w = QWidget()
    lay = _vbox(8)
    w.setLayout(lay)
    for _ in range(min(6, int(c.get("count", 3) or 3))):
        bar = QLabel()
        bar.setFixedHeight(14)
        bar.setStyleSheet(f"background:{T.SURFACE_2}; border-radius:7px;")
        lay.addWidget(bar)
    return w


def _r_fallback(c, ctx):
    frame = QFrame()
    frame.setStyleSheet(
        f"background:{T.SURFACE_2}; border:1px dashed {T.BORDER}; border-radius:8px;"
    )
    lay = _vbox(2, (12, 8, 12, 8))
    frame.setLayout(lay)
    lay.addWidget(_label(f"[{c.get('type', '?')}]", color=T.MUTED, size=12, bold=True))
    for k in ("title", "label", "message", "content", "value"):
        if isinstance(c.get(k), str):
            lay.addWidget(_label(c[k], color=T.TEXT, size=13))
            break
    return frame


REGISTRY: Dict[str, Callable[[dict, RenderContext], QWidget]] = {
    "text": _r_text,
    "card": _r_card,
    "container": _r_container,
    "grid": _r_grid,
    "hero": _r_hero,
    "badge": _r_badge,
    "metric": _r_metric,
    "keyvalue": _r_keyvalue,
    "timeline": _r_timeline,
    "rating": _r_rating,
    "alert": _r_alert,
    "button": _r_button,
    "code": _r_code,
    "divider": _r_divider,
    "progress": _r_progress,
    "list": _r_list,
    "table": _r_table,
    "tabs": _r_tabs,
    "collapsible": _r_collapsible,
    "bar_chart": _r_chart,
    "line_chart": _r_chart,
    "pie_chart": _r_chart,
    "chat_history": _r_chat_history,
    "skeleton": _r_skeleton,
}


def render(component: Any, ctx: RenderContext) -> QWidget:
    """Render one structured SDUI component dict into a native widget."""
    if not isinstance(component, dict):
        return _label(str(component))
    builder = REGISTRY.get(component.get("type", ""), _r_fallback)
    try:
        widget = builder(component, ctx)
    except Exception as exc:  # never let one bad component crash the canvas
        widget = _label(
            f"[render error: {component.get('type')}: {exc}]", color=T.MUTED, size=12
        )
    cid = component.get("component_id") or component.get("id")
    if cid:
        widget.setProperty("component_id", str(cid))
    return widget


def supported_types() -> List[str]:
    """The primitive types this native target renders directly (the rest fall
    back to a labeled placeholder) — used for ROTE capability negotiation."""
    return sorted(REGISTRY.keys())
