"""Headless tests: the native renderer turns SDUI component dicts into real Qt
widgets (offscreen). Mirrors the structured payloads the orchestrator sends."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QTableWidget, QTabWidget, QWidget,
)

from astral_client.renderer import RenderContext, render, supported_types


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
