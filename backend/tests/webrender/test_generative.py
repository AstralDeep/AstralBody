"""Feature 033 (C-N2) — gated generative primitives: grammar validator + safe render."""
from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from webrender import generative as gen  # noqa: E402


# ───────────────────────── flag ──────────────────────────────────────────────

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("FF_GENERATIVE_PRIMITIVES", raising=False)
    assert gen.generative_enabled() is False
    monkeypatch.setenv("FF_GENERATIVE_PRIMITIVES", "on")
    assert gen.generative_enabled() is True


# ───────────────────────── validate ──────────────────────────────────────────

def test_valid_composition():
    spec = {"t": "col", "children": [
        {"t": "label", "text": "Score"},
        {"t": "bar", "value": 0.7, "variant": "success"},
        {"t": "row", "children": [{"t": "badge", "text": "A"}, {"t": "value", "value": "42"}]},
    ]}
    ok, errors = gen.validate(spec)
    assert ok is True and errors == []


def test_disallowed_type_rejected():
    ok, errors = gen.validate({"t": "script", "text": "x"})
    assert ok is False and any("disallowed node type" in e for e in errors)


def test_container_requires_children_list():
    ok, errors = gen.validate({"t": "col"})
    assert ok is False and any("children list" in e for e in errors)


def test_bar_value_must_be_unit_interval():
    assert gen.validate({"t": "bar", "value": 1.5})[0] is False
    assert gen.validate({"t": "bar", "value": "x"})[0] is False
    assert gen.validate({"t": "bar", "value": True})[0] is False  # bool excluded
    assert gen.validate({"t": "bar", "value": 0.5})[0] is True


def test_disallowed_variant():
    ok, errors = gen.validate({"t": "badge", "text": "x", "variant": "rainbow"})
    assert ok is False and any("variant" in e for e in errors)


def test_depth_bound():
    node: dict = {"t": "text", "text": "deep"}
    for _ in range(8):
        node = {"t": "col", "children": [node]}
    assert gen.validate(node)[0] is False


def test_children_count_bound():
    spec = {"t": "row", "children": [{"t": "text", "text": str(i)} for i in range(30)]}
    ok, errors = gen.validate(spec)
    assert ok is False and any("children" in e for e in errors)


def test_node_count_bound():
    spec = {"t": "col", "children": [{"t": "col", "children": [
        {"t": "text", "text": str(i)} for i in range(20)]} for _ in range(10)]}
    ok, errors = gen.validate(spec)
    assert ok is False and any("node count" in e for e in errors)


def test_non_dict_node_rejected():
    assert gen.validate("not a node")[0] is False
    assert gen.validate({"t": "row", "children": ["x"]})[0] is False


# ───────────────────────── render (escape-by-default) ────────────────────────

def test_render_valid_wraps_and_classes():
    out = gen.render({"t": "col", "children": [{"t": "label", "text": "Hi"}]})
    assert out.startswith('<div class="astral-generative">')
    assert 'class="gen-col gen-default"' in out and "gen-label" in out


def test_render_escapes_text():
    out = gen.render({"t": "text", "text": '<script>alert(1)</script>'})
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_render_bar_width():
    out = gen.render({"t": "bar", "value": 0.5})
    assert "width:50.0%" in out


def test_render_invalid_is_failsafe_notice():
    out = gen.render({"t": "iframe", "src": "evil"})
    assert "could not be safely displayed" in out
    assert "<iframe" not in out and "evil" not in out


def test_render_clamps_bar_and_no_inline_injection():
    # even a wild value renders bounded; model cannot inject style/script
    out = gen.render({"t": "col", "children": [{"t": "bar", "value": 1.0}]})
    assert "width:100.0%" in out and "<script" not in out
