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
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    """Carried through a render pass. `emit` posts a ui_event back to the server;
    `download` (optional) fetches an authed backend file URL and saves it natively."""

    emit: Callable[[str, dict], None]
    download: Optional[Callable[[str, str], None]] = None


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


def _to_number(text: str):
    """Mirror the web client's ``Number(value)`` coercion for number fields."""
    try:
        f = float(text)
    except (TypeError, ValueError):
        return text
    return int(f) if f.is_integer() else f


def _fill_template(template: str, state: dict) -> str:
    """Build a submit message from a template + collected field values.

    Mirrors client.js ``submitParamPicker``: ``{__values_json__}`` expands to the
    pretty-printed state, then ``{field}`` tokens are substituted (strings inline,
    other values as JSON); unknown tokens are left untouched.
    """
    msg = (template or "").replace("{__values_json__}", json.dumps(state, indent=2))

    def _repl(m):
        k = m.group(1)
        if k not in state:
            return m.group(0)
        v = state[k]
        return v if isinstance(v, str) else json.dumps(v)

    return re.sub(r"\{(\w+)\}", _repl, msg)


def _r_param_picker(c, ctx):
    """A field form + Submit; on submit emit a ``chat_message`` built from the
    field values and ``submit_message_template`` (parity with the web target)."""
    frame = _card_frame()
    lay = _vbox(10, (16, 14, 16, 14))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], size=16, bold=True))
    if c.get("description"):
        lay.addWidget(_label(c["description"], color=T.MUTED, size=13))
    getters: Dict[str, Callable[[], Any]] = {}
    for field in c.get("fields", []) or []:
        if not isinstance(field, dict):
            continue
        name = field.get("name", "")
        label = field.get("label") or name
        kind = field.get("kind", "text")
        default = field.get("default")
        if kind == "boolean":
            box = QCheckBox(str(label))
            box.setChecked(bool(default))
            getters[name] = lambda b=box: b.isChecked()
            lay.addWidget(box)
        elif kind == "select":
            lay.addWidget(_label(label, color=T.MUTED, size=12))
            combo = QComboBox()
            opts = [str(o) for o in (field.get("options") or [])]
            combo.addItems(opts)
            if default is not None and str(default) in opts:
                combo.setCurrentText(str(default))
            getters[name] = lambda cb=combo: cb.currentText()
            lay.addWidget(combo)
        elif kind == "checklist":
            lay.addWidget(_label(label, color=T.MUTED, size=12))
            sel = set(default) if isinstance(default, list) else set()
            chips: List = []
            row = QHBoxLayout()
            row.setSpacing(6)
            for opt in field.get("options") or []:
                btn = QPushButton(str(opt))
                btn.setCheckable(True)
                btn.setChecked(opt in sel)
                row.addWidget(btn)
                chips.append((opt, btn))
            row.addStretch(1)
            lay.addLayout(row)
            getters[name] = lambda ch=chips: [o for o, b in ch if b.isChecked()]
        elif kind == "number":
            lay.addWidget(_label(label, color=T.MUTED, size=12))
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            getters[name] = lambda e=edit: None if e.text() == "" else _to_number(e.text())
            lay.addWidget(edit)
        elif kind == "password":
            # Feature 043: write-only key field — never pre-filled (blank = keep).
            lay.addWidget(_label(label, color=T.MUTED, size=12))
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            getters[name] = lambda e=edit: e.text()
            lay.addWidget(edit)
        elif kind == "textarea":
            lay.addWidget(_label(label, color=T.MUTED, size=12))
            area = QPlainTextEdit()
            if default is not None:
                area.setPlainText(str(default))
            area.setMinimumHeight(72)
            getters[name] = lambda a=area: a.toPlainText()
            lay.addWidget(area)
        else:  # text (default)
            lay.addWidget(_label(label, color=T.MUTED, size=12))
            edit = QLineEdit()
            if default is not None:
                edit.setText(str(default))
            getters[name] = lambda e=edit: e.text()
            lay.addWidget(edit)
        if field.get("help"):
            lay.addWidget(_label(field["help"], color=T.MUTED, size=11))
    # Feature 043: settings forms (LLM, Personalization) submit their collected
    # fields to a chrome_* action (action-submit) rather than a chat message. A
    # form may carry several action buttons (Load / Test / Save) that all submit
    # the SAME fields. Falls back to the legacy chat_message submit otherwise.
    actions = c.get("actions") if isinstance(c.get("actions"), list) else []
    if not actions and c.get("submit_action"):
        actions = [{"label": c.get("submit_label", "Save"), "action": c["submit_action"],
                    "variant": "primary", "payload": c.get("submit_payload") or {}}]
    row = QHBoxLayout()
    row.addStretch(1)
    if actions:
        def _make(action, extra):
            def _s():
                state = {k: g() for k, g in getters.items()}
                ctx.emit(action, {"fields": state, **(extra or {})})
            return _s
        for a in actions:
            if not isinstance(a, dict) or not a.get("action"):
                continue
            btn = QPushButton(str(a.get("label") or "Submit"))
            if (a.get("variant") or "") == "primary":
                btn.setObjectName("primary")
            btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(_make(a["action"], a.get("payload") or {}))
            row.addWidget(btn)
    else:
        template = c.get("submit_message_template", "")
        submit = QPushButton(str(c.get("submit_label", "Submit")))
        submit.setObjectName("primary")
        submit.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        def _submit():
            state = {k: g() for k, g in getters.items()}
            ctx.emit("chat_message", {"message": _fill_template(template, state)})

        submit.clicked.connect(_submit)
        row.addWidget(submit)
    lay.addLayout(row)
    return frame


def _r_input(c, ctx):
    """A labeled single-line text field + Submit (emits a ``chat_message``)."""
    w = QWidget()
    lay = _vbox(6)
    w.setLayout(lay)
    name = c.get("name") or "value"
    label = c.get("label") or c.get("name")
    if label:
        lay.addWidget(_label(label, color=T.MUTED, size=12))
    edit = QLineEdit()
    edit.setText(str(c.get("value", "")))
    if c.get("placeholder"):
        edit.setPlaceholderText(str(c["placeholder"]))
    template = c.get("submit_message_template", "")
    submit = QPushButton(str(c.get("submit_label", "Submit")))
    submit.setObjectName("primary")
    submit.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def _submit():
        val = edit.text()
        msg = _fill_template(template, {name: val}) if template else val
        ctx.emit("chat_message", {"message": msg})

    submit.clicked.connect(_submit)
    edit.returnPressed.connect(_submit)
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(edit, 1)
    row.addWidget(submit)
    lay.addLayout(row)
    return w


def _accept_to_filter(accept: str) -> str:
    """Turn an HTML ``accept`` string into a Qt file dialog filter."""
    accept = (accept or "").strip()
    if not accept or accept == "*/*":
        return "All files (*)"
    pats = []
    for tok in accept.split(","):
        tok = tok.strip()
        if tok.startswith("."):
            pats.append("*" + tok)
        elif tok and "/" not in tok:
            pats.append("*." + tok)
    if not pats:
        return "All files (*)"
    return f"Accepted ({' '.join(pats)});;All files (*)"


def _r_file_upload(c, ctx):
    """A native file-picker button. When the component carries an ``action`` the
    chosen path is emitted with its payload (mirrors ``_r_button`` wiring)."""
    w = QWidget()
    lay = _vbox(6)
    w.setLayout(lay)
    label = c.get("label", "Upload File")
    accept = c.get("accept", "")
    action = c.get("action")
    payload = c.get("payload") or {}
    btn = QPushButton(str(label))
    btn.setObjectName("primary")
    btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    chosen = _label("", color=T.MUTED, size=12)

    def _pick():
        path, _sel = QFileDialog.getOpenFileName(
            btn, str(label), "", _accept_to_filter(accept)
        )
        if not path:
            return
        chosen.setText(path)
        if action:
            data = dict(payload)
            data["path"] = path
            ctx.emit(action, data)

    btn.clicked.connect(_pick)
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(btn)
    row.addWidget(chosen, 1)
    lay.addLayout(row)
    return w


def _r_file_download(c, ctx):
    """A download button/link showing the filename, opening the URL externally,
    plus a SHA-256 integrity block when present. Serves both ``file_download``
    and the richer ``download_card``."""
    frame = _card_frame()
    lay = _vbox(8, (16, 12, 16, 12))
    frame.setLayout(lay)
    if c.get("title"):
        lay.addWidget(_label(c["title"], size=14, bold=True))
    if c.get("description"):
        lay.addWidget(_label(c["description"], color=T.MUTED, size=12))
    version = c.get("version")
    platform = c.get("platform")
    meta = " · ".join(
        x for x in [f"v{version}" if version else "", platform or ""] if x
    )
    if meta:
        lay.addWidget(_label(meta, color=T.MUTED, size=11))
    # file_download uses `url`; download_card uses `download_url`.
    url = c.get("url") or c.get("download_url") or ""
    filename = c.get("filename") or c.get("title")
    label = c.get("label") or (f"Download {filename}" if filename else "Download File")
    valid = bool(url) and url != "#" and str(url).startswith(("http", "/"))
    btn = QPushButton(str(label))
    btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    if valid:
        btn.setObjectName("primary")
        u = str(url)
        # A root-relative /api/download/... URL is an authed backend file: fetch
        # it with the session token and save via a native dialog. An absolute
        # http(s) URL (e.g. a download_card GitHub asset) opens externally.
        if u.startswith("/") and getattr(ctx, "download", None) is not None:
            fn = str(filename or "download")
            btn.clicked.connect(lambda checked=False, uu=u, ff=fn: ctx.download(uu, ff))
        else:
            btn.clicked.connect(lambda checked=False, uu=u: QDesktopServices.openUrl(QUrl(uu)))
    else:
        btn.setEnabled(False)
        btn.setText(str(label) + " (unavailable)")
    lay.addWidget(btn)
    sha = str(c.get("sha256") or c.get("sha") or "").lower()
    if sha:
        lay.addWidget(_label("SHA-256", color=T.MUTED, size=11, bold=True))
        sha_lab = _label(sha, color=T.MUTED, size=11)
        sha_lab.setStyleSheet(
            f"color:{T.MUTED}; font-family:Consolas,monospace; font-size:11px;"
            "background:transparent;"
        )
        lay.addWidget(sha_lab)
    return frame


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
    "param_picker": _r_param_picker,
    "input": _r_input,
    "file_upload": _r_file_upload,
    "file_download": _r_file_download,
    "download_card": _r_file_download,
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


def _r_color_picker(c, ctx):
    """Feature 043 — a theme channel swatch + hex readout (Theme surface).

    Read-only display of one ``--astral-*`` colour; the preset buttons are the
    primary theme control, so per-channel live editing is a later refinement.
    """
    w = QWidget()
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 2, 0, 2)
    lay.setSpacing(8)
    w.setLayout(lay)
    val = str(c.get("value") or "#000000")
    swatch = QFrame()
    swatch.setFixedSize(22, 22)
    swatch.setStyleSheet(
        f"background:{val}; border:1px solid rgba(255,255,255,0.2); border-radius:4px;")
    lay.addWidget(swatch)
    lay.addWidget(_label(str(c.get("label") or c.get("color_key") or ""), color=T.TEXT, size=13))
    lay.addStretch(1)
    lay.addWidget(_label(val, color=T.MUTED, size=12))
    return w


def _r_theme_apply(c, ctx):
    """Feature 043 — the ``theme_apply`` side-effect carries the chosen preset's
    palette for the client to apply; it has no visible UI (zero-height spacer).
    The live restyle (US3) reads ``preset``/``colors`` off this frame."""
    w = QWidget()
    w.setFixedHeight(0)
    return w


REGISTRY.update({"color_picker": _r_color_picker, "theme_apply": _r_theme_apply})


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
