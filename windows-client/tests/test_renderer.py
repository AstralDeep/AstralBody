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


# Drift guard: the backend's published primitive vocabulary is
# `webrender.allowed_primitive_types()` (PRIMITIVE_RENDERERS.keys()). We embed a
# checked-in snapshot of it here so this test breaks when a backend primitive is
# added without either a native desktop renderer OR an explicit degradation
# entry below. Refresh BACKEND_TYPES from backend/webrender/registry.py /
# renderer.py when the vocabulary legitimately changes.
BACKEND_TYPES = frozenset({
    "container", "text", "button", "input", "param_picker", "card", "table",
    "list", "alert", "progress", "metric", "code", "image", "grid", "tabs",
    "divider", "collapsible", "bar_chart", "line_chart", "pie_chart",
    "plotly_chart", "color_picker", "theme_apply", "file_upload",
    "file_download", "audio", "badge", "hero", "keyvalue", "timeline",
    "rating", "skeleton", "chat_history", "download_card", "generative",
})

# Backend primitives intentionally NOT rendered natively on the desktop target
# (they fall back to a labeled placeholder). Each must have a deliberate reason;
# adding a type here is an explicit decision to degrade it on desktop.
KNOWN_DEGRADED = frozenset({
    "image",         # no native image fetch/decode pipeline yet
    "audio",         # no native audio playback widget yet
    "plotly_chart",  # Plotly is web/JS-only; native uses QtCharts bar/line/pie
    # color_picker + theme_apply now render natively (feature 043 Theme surface).
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
