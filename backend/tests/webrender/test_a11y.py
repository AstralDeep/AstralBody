"""Feature 033 (capability C-D9) — accessibility as a render constraint.

Covers the WCAG landmark role/label computation, the deterministic a11y audit,
and the labelled-landmark wrapper in render_component_fragment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from webrender import a11y  # noqa: E402
from webrender.renderer import render_component_fragment  # noqa: E402


# ───────────────────────── flag ──────────────────────────────────────────────

def test_a11y_enabled_default_on(monkeypatch):
    monkeypatch.delenv("FF_A11Y", raising=False)
    assert a11y.a11y_enabled() is True


@pytest.mark.parametrize("v", ["false", "0", "no", "off"])
def test_a11y_flag_off(monkeypatch, v):
    monkeypatch.setenv("FF_A11Y", v)
    assert a11y.a11y_enabled() is False


# ───────────────────────── landmark role/label ───────────────────────────────

@pytest.mark.parametrize("ctype,role", [
    ("card", "region"), ("container", "region"), ("table", "region"),
    ("grid", "group"), ("metric", "group"), ("alert", "status"),
    ("divider", None), ("text", None), ("skeleton", None),
])
def test_landmark_role(ctype, role):
    assert a11y.landmark_role({"type": ctype}) == role


def test_landmark_label_uses_title():
    assert a11y.landmark_label({"type": "card", "title": "System Status"}) == "System Status"


def test_landmark_label_derives_when_no_title():
    assert a11y.landmark_label({"type": "metric", "value": "9%"}) == "metric: 9%"
    assert a11y.landmark_label({"type": "alert", "variant": "warning"}) == "warning alert"
    assert a11y.landmark_label({"type": "hero", "subtitle": "all good"}) == "all good"
    assert a11y.landmark_label({"type": "keyvalue"}) == "keyvalue"


# ───────────────────────── audit ─────────────────────────────────────────────

def test_audit_clean_tree_is_empty():
    assert a11y.a11y_audit([{"type": "card", "title": "OK", "content": [
        {"type": "text", "content": "hi"}]}]) == []


def test_audit_flags_image_without_alt():
    issues = a11y.a11y_audit([{"type": "image", "src": "x.png"}])
    assert any(i["type"] == "image" and "alt" in i["issue"] for i in issues)


def test_audit_flags_unlabelled_action_and_landmark():
    issues = a11y.a11y_audit([
        {"type": "card", "content": [{"type": "button"}]}])  # card no title, button no label
    kinds = {(i["type"]) for i in issues}
    assert "card" in kinds and "button" in kinds


def test_audit_flags_empty_heading_and_tab():
    issues = a11y.a11y_audit([
        {"type": "text", "variant": "h2", "content": "   "},
        {"type": "tabs", "title": "T", "tabs": [{"label": "", "content": []}]}])
    kinds = {i["type"] for i in issues}
    assert "text" in kinds and "tab" in kinds


def test_audit_recurses_and_never_raises():
    assert a11y.a11y_audit([None, "x", {"type": "grid", "children": [
        {"type": "image"}]}])  # nested image w/o alt
    assert a11y.a11y_audit(None) == []


# ───────────────────────── wrapper integration ───────────────────────────────

def test_fragment_adds_landmark_role_and_label():
    out = render_component_fragment({"type": "card", "component_id": "c1", "title": "Status"})
    assert 'role="region"' in out
    assert 'aria-label="Status"' in out
    assert 'data-component-id="c1"' in out


def test_fragment_decorative_type_gets_no_role():
    out = render_component_fragment({"type": "text", "component_id": "c1", "content": "hi"})
    assert "role=" not in out


def test_fragment_label_is_escaped():
    out = render_component_fragment({"type": "card", "component_id": "c1",
                                     "title": '"><script>'})
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_fragment_flag_off_has_no_landmark(monkeypatch):
    monkeypatch.setenv("FF_A11Y", "false")
    out = render_component_fragment({"type": "card", "component_id": "c1", "title": "Status"})
    assert "role=" not in out and "aria-label" not in out
    assert 'data-component-id="c1"' in out
