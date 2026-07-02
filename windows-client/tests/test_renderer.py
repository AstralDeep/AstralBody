"""Headless tests: the native renderer turns SDUI component dicts into real Qt
widgets (offscreen). Mirrors the structured payloads the orchestrator sends."""
from __future__ import annotations

import pytest

# These tests exercise the PySide6 native renderer; skip the whole module when
# PySide6 isn't installed (the codegen/integrity tests are Qt-free and run
# without it). In CI with PySide6 present, the suite runs in full.
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QFrame, QLabel, QPushButton, QTableWidget, QTabWidget, QWidget,
)

from astral_client.renderer import RenderContext, render, supported_types  # noqa: E402


def _ctx(sink=None):
    return RenderContext(emit=(sink if sink is not None else (lambda a, p: None)))


# A representative canvas spanning the primitive vocabulary.
CANVAS = [
    {"type": "hero", "title": "Q2 Review", "subtitle": "Generated", "eyebrow": "DASHBOARD"},
    {"type": "card", "title": "Summary", "content": [
        {"type": "text", "content": "Up **4.2%** this quarter", "variant": "markdown"},
        {"type": "badge", "label": "On track", "variant": "success"}]},
    {"type": "metric", "title": "Total Return", "value": "+4.2%", "delta": "+1.1%"},
    {"type": "keyvalue", "title": "Allocations",
     "items": [{"label": "Equities", "value": "62%"}, {"label": "Bonds", "value": "28%"}]},
    {"type": "rating", "title": "Risk", "value": 3, "max_value": 5},
    {"type": "table", "headers": ["A", "B"], "rows": [["1", "2"], ["3", "4"]]},
    {"type": "timeline", "title": "Activity",
     "items": [{"title": "Bought AAPL", "time": "Mon"}]},
    {"type": "list", "items": ["one", "two", "three"]},
    {"type": "tabs", "tabs": [{"label": "T1", "content": [{"type": "text", "content": "hi"}]}]},
    {"type": "alert", "variant": "warning", "message": "heads up"},
    {"type": "code", "code": "print('hi')", "language": "python"},
    {"type": "divider"},
    {"type": "progress", "value": 0.5, "label": "Loading"},
    {"type": "bar_chart", "title": "Sales", "labels": ["x", "y"],
     "datasets": [{"label": "s", "data": [3, 5]}]},
]


def test_every_component_renders_to_a_widget(qapp):
    ctx = _ctx()
    for comp in CANVAS:
        w = render(comp, ctx)
        assert isinstance(w, QWidget), f"{comp['type']} did not render a QWidget"


def test_text_markdown(qapp):
    w = render({"type": "text", "content": "**bold**", "variant": "markdown"}, _ctx())
    assert isinstance(w, QLabel)
    assert "bold" in w.text()


def test_button_emits_action(qapp):
    seen = []
    w = render({"type": "button", "label": "Go", "action": "do_thing",
                "payload": {"x": 1}}, _ctx(lambda a, p: seen.append((a, p))))
    assert isinstance(w, QPushButton)
    w.click()
    assert seen == [("do_thing", {"x": 1})]


def test_table_shape(qapp):
    w = render({"type": "table", "headers": ["A", "B", "C"],
                "rows": [["1", "2", "3"], ["4", "5", "6"]]}, _ctx())
    tbl = w.findChild(QTableWidget)
    assert tbl is not None
    assert tbl.columnCount() == 3 and tbl.rowCount() == 2
    assert tbl.item(1, 2).text() == "6"


def test_tabs_pages(qapp):
    w = render({"type": "tabs", "tabs": [
        {"label": "One", "content": []}, {"label": "Two", "content": []}]}, _ctx())
    assert isinstance(w, QTabWidget)
    assert w.count() == 2 and w.tabText(1) == "Two"


def test_unknown_type_falls_back(qapp):
    w = render({"type": "totally_new_primitive", "title": "x"}, _ctx())
    assert isinstance(w, QFrame)
    labels = [c.text() for c in w.findChildren(QLabel)]
    assert any("totally_new_primitive" in t for t in labels)


def test_component_id_is_stashed(qapp):
    w = render({"type": "card", "component_id": "wc_123", "content": []}, _ctx())
    assert w.property("component_id") == "wc_123"


def test_card_renders_nested_children(qapp):
    w = render({"type": "card", "title": "P", "content": [
        {"type": "text", "content": "child-text"}]}, _ctx())
    labels = [c.text() for c in w.findChildren(QLabel)]
    assert any("child-text" in t for t in labels)


def test_bad_component_does_not_crash(qapp):
    # a malformed table (rows not lists) still yields a widget, never raises
    w = render({"type": "table", "headers": ["A"], "rows": "oops"}, _ctx())
    assert isinstance(w, QWidget)


def test_supported_types_published(qapp):
    types = supported_types()
    assert "card" in types and "hero" in types and "table" in types
    # Feature 044 (T028): vocabulary grew to include image + plotly_chart (33).
    assert "image" in types and "plotly_chart" in types


# --- feature 044 (T026): server-side table pagination pager -----------------

# A 1x1 transparent PNG as a data: URI (valid, decodes cleanly — no network).
_PNG_1x1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
)


def test_paginated_table_renders_pager(qapp):
    w = render({"type": "table", "headers": ["A", "B"], "rows": [["1", "2"]],
                "total_rows": 100, "page_size": 25, "page_offset": 0,
                "component_id": "tbl1"}, _ctx())
    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert any("Prev" in t for t in btns)
    assert any("Next" in t for t in btns)


def test_plain_table_has_no_pager(qapp):
    w = render({"type": "table", "headers": ["A"], "rows": [["1"], ["2"]]}, _ctx())
    assert w.findChildren(QPushButton) == []


def test_pager_prev_disabled_at_offset_zero(qapp):
    w = render({"type": "table", "headers": ["A"], "rows": [["1"]],
                "total_rows": 100, "page_size": 25, "page_offset": 0,
                "component_id": "t"}, _ctx())
    prev = next(b for b in w.findChildren(QPushButton) if "Prev" in b.text())
    nxt = next(b for b in w.findChildren(QPushButton) if "Next" in b.text())
    assert prev.isEnabled() is False
    assert nxt.isEnabled() is True


def test_pager_emits_table_paginate(qapp):
    seen = []
    ctx = RenderContext(emit=lambda a, p: seen.append((a, p)), chat_id="chatZ")
    w = render({"type": "table", "headers": ["A"], "rows": [["1"]],
                "total_rows": 100, "page_size": 25, "page_offset": 25,
                "component_id": "tblX"}, ctx)
    nxt = next(b for b in w.findChildren(QPushButton) if "Next" in b.text())
    nxt.click()
    assert seen[-1][0] == "table_paginate"
    payload = seen[-1][1]
    assert payload["component_id"] == "tblX"
    assert payload["params"] == {"page_offset": 50, "page_size": 25}
    assert payload["chat_id"] == "chatZ"  # scoped to the active chat


def test_pager_next_disabled_on_last_page(qapp):
    w = render({"type": "table", "headers": ["A"], "rows": [["1"]],
                "total_rows": 50, "page_size": 25, "page_offset": 25,
                "component_id": "t"}, _ctx())
    nxt = next(b for b in w.findChildren(QPushButton) if "Next" in b.text())
    prev = next(b for b in w.findChildren(QPushButton) if "Prev" in b.text())
    assert nxt.isEnabled() is False   # 25 + 25 >= 50
    assert prev.isEnabled() is True


# --- feature 044 (T028): image + plotly_chart native renderers --------------

def test_image_renders_data_uri(qapp):
    w = render({"type": "image", "url": _PNG_1x1, "alt": "dot"}, _ctx())
    assert isinstance(w, QWidget)


def test_image_malformed_does_not_raise(qapp):
    # no url, unknown scheme, and a garbage data uri all degrade to alt text
    for comp in ({"type": "image"},
                 {"type": "image", "url": "ftp://nope"},
                 {"type": "image", "url": "data:image/png;base64,not-base64!!"}):
        w = render(comp, _ctx())
        assert isinstance(w, QWidget)


# --- M2: remote images fetch OFF the GUI thread (never block render) ---------

def test_image_http_url_renders_placeholder_synchronously(qapp, monkeypatch):
    """A remote http(s) image renders an immediate alt-text placeholder and is
    returned synchronously — the bytes are fetched off the GUI thread (a
    synchronous urlopen here used to freeze the render up to 4s per image)."""
    from astral_client import renderer as rmod
    from astral_client.renderer import _AsyncImageLabel

    # never touch the network from the test's auto-spawned fetch thread
    monkeypatch.setattr(rmod, "_fetch_image_bytes", lambda url: None)
    w = render({"type": "image", "url": "https://example.com/x.png",
                "alt": "a picture"}, _ctx())
    assert isinstance(w, QWidget)
    lbl = w.findChild(_AsyncImageLabel)
    assert lbl is not None
    assert "a picture" in lbl.text()          # alt text shown immediately
    assert lbl.pixmap().isNull()              # no image bytes yet


def test_async_image_label_applies_fetched_pixmap(qapp, monkeypatch):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QPixmap

    from astral_client import renderer as rmod

    monkeypatch.setattr(rmod, "_fetch_image_bytes", lambda url: None)  # auto-thread no-op
    # a valid in-memory PNG (Qt-encoded so loadFromData round-trips cleanly)
    src = QPixmap(4, 4)
    src.fill()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    src.save(buf, "PNG")
    buf.close()
    png = bytes(ba)

    lbl = rmod._AsyncImageLabel("https://example.com/x.png", "alt", 480)
    assert lbl.pixmap().isNull()              # placeholder (text) — no pixmap yet
    lbl._apply_bytes(png)                     # simulate the fetched bytes arriving
    assert not lbl.pixmap().isNull()          # QPixmap applied on the GUI thread
    assert lbl.text() == ""                   # placeholder text cleared


def test_async_image_label_failed_fetch_keeps_placeholder(qapp, monkeypatch):
    from astral_client import renderer as rmod

    monkeypatch.setattr(rmod, "_fetch_image_bytes", lambda url: None)
    lbl = rmod._AsyncImageLabel("https://example.com/x.png", "alt text", 480)
    lbl._apply_bytes(None)                    # a failed/empty fetch
    assert lbl.pixmap().isNull()              # still no image
    assert "alt text" in lbl.text()           # placeholder retained


def test_fetch_image_bytes_rejects_non_http(qapp):
    from astral_client.renderer import _fetch_image_bytes

    # scheme-guarded: data:/ftp:/empty never hit urlopen (return None, no raise)
    assert _fetch_image_bytes("") is None
    assert _fetch_image_bytes("ftp://nope") is None
    assert _fetch_image_bytes("data:image/png;base64,AAAA") is None


def test_plotly_chart_renders_from_traces(qapp):
    w = render({"type": "plotly_chart", "title": "Fig",
                "data": [{"x": [1, 2, 3], "y": [4, 5, 6], "type": "bar"}]}, _ctx())
    assert isinstance(w, QWidget)


def test_plotly_chart_malformed_does_not_raise(qapp):
    for comp in ({"type": "plotly_chart"},
                 {"type": "plotly_chart", "data": "oops"},
                 {"type": "plotly_chart", "data": [{"no": "series"}]}):
        w = render(comp, _ctx())
        assert isinstance(w, QWidget)


# Drift guard: the backend's published primitive vocabulary is the committed
# UI-protocol manifest (backend/shared/ui_protocol.json, feature 044), which the
# backend's own tests keep equal to `webrender.allowed_primitive_types()`. This
# test therefore breaks when a backend primitive is added without either a
# native desktop renderer OR an explicit degradation entry below.
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_MANIFEST = _Path(__file__).resolve().parents[2] / "backend" / "shared" / "ui_protocol.json"
BACKEND_TYPES = frozenset(_json.loads(_MANIFEST.read_text(encoding="utf-8"))["component_types"])

# Backend primitives intentionally NOT rendered natively on the desktop target
# (they fall back to a labeled placeholder). Each must have a deliberate reason;
# adding a type here is an explicit decision to degrade it on desktop.
KNOWN_DEGRADED = frozenset({
    "audio",         # no native audio playback widget yet
    # image + plotly_chart now render natively (feature 044 T028): image decodes
    # data:/http(s) into a QPixmap; plotly_chart draws its traces via QtCharts.
    # color_picker + theme_apply render natively (feature 043 Theme surface).
    "generative",    # flag-gated web-only generative grammar renderer
})


def test_no_silent_backend_vocabulary_drift():
    # Every backend primitive must be either natively rendered on desktop or
    # explicitly listed as degraded — nothing silently degrades.
    missing = BACKEND_TYPES - set(supported_types())
    assert missing <= KNOWN_DEGRADED, (
        f"backend primitives with no desktop renderer and not in KNOWN_DEGRADED: "
        f"{sorted(missing - KNOWN_DEGRADED)}"
    )


def test_known_degraded_are_real_backend_types():
    # Guard the guard: a stale degradation entry (type no longer in the backend
    # vocabulary, or one we since added a renderer for) should be cleaned up.
    assert KNOWN_DEGRADED <= BACKEND_TYPES
    assert not (KNOWN_DEGRADED & set(supported_types()))


# --------------------------------------------------------------------------- #
# container `direction:"row"` + minimal css (settings-surface parity)
# --------------------------------------------------------------------------- #

_SWATCH = {"type": "container", "children": [],
           "css": {"background": "#22C55E", "height": "22px", "flex": "1"}}


def test_container_css_swatch_leaf_renders_colored_box(qapp):
    # A childless css-styled container (a Theme preset swatch cell) is a fixed-
    # height colored frame — never blank space (web/Android parity).
    w = render(dict(_SWATCH), _ctx())
    assert isinstance(w, QFrame)
    assert w.maximumHeight() == 22 and w.minimumHeight() == 22
    assert "#22C55E" in w.styleSheet()


def test_container_css_height_tolerates_garbage(qapp):
    bad = {"type": "container", "children": [],
           "css": {"background": "#111111", "height": "tall"}}
    w = render(bad, _ctx())
    assert w.maximumHeight() == 22  # default height kept


def test_container_row_direction_is_horizontal(qapp):
    from PySide6.QtWidgets import QHBoxLayout
    w = render({"type": "container", "direction": "row", "children": [
        {"type": "button", "label": "Soul", "action": "chrome_open"},
        {"type": "button", "label": "Memory", "action": "chrome_open"}]}, _ctx())
    lay = w.layout()
    assert isinstance(lay, QHBoxLayout)
    # two buttons + the left-aligning stretch
    assert sum(1 for i in range(lay.count()) if lay.itemAt(i).widget()) == 2


def test_container_swatch_row_stretches_proportionally(qapp):
    w = render({"type": "container", "direction": "row",
                "children": [dict(_SWATCH), dict(_SWATCH), dict(_SWATCH)]}, _ctx())
    lay = w.layout()
    widgets = [i for i in range(lay.count()) if lay.itemAt(i).widget()]
    assert len(widgets) == 3
    assert all(lay.stretch(i) == 1 for i in widgets)


def test_container_default_stays_vertical(qapp):
    from PySide6.QtWidgets import QVBoxLayout
    w = render({"type": "container", "children": [
        {"type": "text", "content": "hi"}]}, _ctx())
    assert isinstance(w.layout(), QVBoxLayout)


def test_button_label_ampersand_renders_literally(qapp):
    # Qt eats a lone "&" as a mnemonic marker; server labels must show it
    # verbatim ("Attachments & files") like the web/Android renderers do.
    w = render({"type": "button", "label": "Attachments & files", "action": "x"}, _ctx())
    assert isinstance(w, QPushButton)
    assert w.text() == "Attachments && files"  # the Qt escape for a literal &
