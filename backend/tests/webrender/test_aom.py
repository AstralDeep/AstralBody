"""Feature 033 (capability C-D5) — the AOM / semantic-tree renderer.

Verifies the structural (role / name / state) render target: flag gating, role
mapping (incl. heading-vs-text by variant), accessible-name precedence, state
extraction, recursion through children/content, the table summary + per-tab
children, the depth cap, non-dict degradation, and JSON-serializability of the
document envelope (with no leaked HTML markup).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from webrender import aom  # noqa: E402


# ───────────────────────── flag gating ───────────────────────────────────────

def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("FF_AOM_RENDERER", raising=False)
    assert aom.aom_enabled() is False


def test_flag_enabled_truthy_values(monkeypatch):
    for raw in ("1", "true", "TRUE", "Yes", "on", "  on  "):
        monkeypatch.setenv("FF_AOM_RENDERER", raw)
        assert aom.aom_enabled() is True


def test_flag_disabled_falsy_values(monkeypatch):
    for raw in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("FF_AOM_RENDERER", raw)
        assert aom.aom_enabled() is False


# ───────────────────────── role mapping ──────────────────────────────────────

def test_role_mapping_for_known_types():
    cases = {
        "card": "group",
        "container": "group",
        "collapsible": "group",
        "grid": "group",
        "table": "table",
        "list": "list",
        "alert": "status",
        "button": "button",
        "input": "textbox",
        "image": "img",
        "metric": "figure",
        "tabs": "tablist",
        "hero": "banner",
        "timeline": "list",
        "badge": "note",
    }
    for type_name, role in cases.items():
        node = aom.to_semantic_node({"type": type_name})
        assert node["role"] == role, (type_name, node["role"])


def test_plain_text_is_role_text():
    assert aom.to_semantic_node({"type": "text", "content": "hi"})["role"] == "text"


def test_text_with_heading_variant_is_role_heading():
    for variant in ("h1", "h2", "h3"):
        node = aom.to_semantic_node({"type": "text", "variant": variant, "content": "T"})
        assert node["role"] == "heading", variant


def test_unknown_type_is_generic():
    assert aom.to_semantic_node({"type": "wizbang"})["role"] == "generic"


# ───────────────────────── semantic_name ─────────────────────────────────────

def test_name_precedence_title_first():
    comp = {"type": "card", "title": "T", "label": "L", "content": "C"}
    assert aom.semantic_name(comp) == "T"


def test_name_falls_back_to_label():
    comp = {"type": "button", "label": "Save", "content": "ignored-no-title"}
    # label beats text/content/value when title is absent
    assert aom.semantic_name({"type": "button", "label": "Save"}) == "Save"
    assert aom.semantic_name(comp) == "Save"


def test_name_falls_back_to_text_then_value_then_type():
    assert aom.semantic_name({"type": "text", "content": "hello"}) == "hello"
    assert aom.semantic_name({"type": "metric", "value": 42}) == "42"
    assert aom.semantic_name({"type": "divider"}) == "divider"


def test_name_is_trimmed_to_cap():
    long = "x" * 500
    name = aom.semantic_name({"type": "text", "content": long})
    assert len(name) <= 120
    assert name.endswith("…")


def test_name_non_dict_is_empty_string():
    assert aom.semantic_name(None) == ""
    assert aom.semantic_name("just a string") == ""


# ───────────────────────── semantic_state ────────────────────────────────────

def test_state_includes_variant_and_value():
    state = aom.semantic_state({"type": "alert", "variant": "warning", "value": "5"})
    assert state["variant"] == "warning"
    assert state["value"] == "5"


def test_state_includes_heading_level():
    assert aom.semantic_state({"type": "text", "variant": "h2"})["level"] == 2
    assert aom.semantic_state({"type": "text", "variant": "h1"})["level"] == 1


def test_state_includes_selected_and_disabled():
    state = aom.semantic_state({"type": "button", "selected": True, "disabled": False})
    assert state["selected"] is True
    assert state["disabled"] is False


def test_state_omits_absent_keys():
    state = aom.semantic_state({"type": "text", "content": "plain"})
    assert state == {}
    assert "variant" not in state and "value" not in state and "level" not in state


# ───────────────────────── recursion ─────────────────────────────────────────

def test_recurses_through_content_children():
    comp = {
        "type": "card",
        "title": "Status",
        "content": [
            {"type": "metric", "title": "CPU", "value": "9%"},
            {"type": "text", "content": "all good"},
        ],
    }
    node = aom.to_semantic_node(comp)
    assert node["role"] == "group" and node["name"] == "Status"
    assert [c["name"] for c in node["children"]] == ["CPU", "all good"]
    assert node["children"][0]["role"] == "figure"


def test_recurses_through_children_key():
    comp = {"type": "container", "children": [{"type": "badge", "label": "new"}]}
    node = aom.to_semantic_node(comp)
    assert len(node["children"]) == 1
    assert node["children"][0]["role"] == "note" and node["children"][0]["name"] == "new"


def test_tabs_produce_per_tab_children():
    comp = {
        "type": "tabs",
        "tabs": [
            {"label": "Overview", "content": [{"type": "text", "content": "hi"}]},
            {"label": "Details"},
        ],
    }
    node = aom.to_semantic_node(comp)
    assert node["role"] == "tablist"
    assert [c["role"] for c in node["children"]] == ["tab", "tab"]
    assert [c["name"] for c in node["children"]] == ["Overview", "Details"]


def test_table_produces_summary_child_with_counts():
    comp = {
        "type": "table",
        "title": "Q",
        "headers": ["Name", "Rev"],
        "rows": [["Alice", "10"], ["Bob", "20"], ["Cy", "30"]],
    }
    node = aom.to_semantic_node(comp)
    assert node["role"] == "table"
    assert len(node["children"]) == 1
    summary = node["children"][0]["name"]
    assert "3 rows" in summary and "2 columns" in summary


def test_depth_cap_truncates_deep_nesting():
    # Build a chain deeper than the cap (12).
    comp: dict = {"type": "container", "title": "leaf-name"}
    for _ in range(20):
        comp = {"type": "container", "content": [comp]}
    node = aom.to_semantic_node(comp)
    # Walk down to the truncated leaf.
    depth = 0
    cur = node
    while cur["children"]:
        cur = cur["children"][0]
        depth += 1
    assert cur["role"] == "generic" and cur["name"] == "…"
    assert depth <= 12


def test_non_dict_is_generic_node():
    assert aom.to_semantic_node("nope") == {
        "role": "generic",
        "name": "",
        "state": {},
        "children": [],
    }
    assert aom.to_semantic_node(None)["role"] == "generic"


# ───────────────────────── document envelope ─────────────────────────────────

def test_render_aom_wraps_in_document():
    out = aom.render_aom([{"type": "text", "content": "hello"}])
    assert out["role"] == "document"
    assert out["name"] == "canvas"
    assert len(out["children"]) == 1
    assert out["children"][0]["name"] == "hello"


def test_render_aom_device_names_document():
    out = aom.render_aom([], device="screenreader")
    assert out["name"] == "screenreader"
    out2 = aom.render_aom([], device=None)
    assert out2["name"] == "canvas"


def test_render_aom_skips_non_dicts():
    out = aom.render_aom([{"type": "badge", "label": "a"}, "junk", None, 5])
    assert len(out["children"]) == 1
    assert out["children"][0]["name"] == "a"


def test_render_aom_is_json_serializable_no_html():
    comp = {
        "type": "card",
        "title": "Report x and y",
        "content": [
            {"type": "text", "variant": "h1", "content": "Heading"},
            {"type": "table", "headers": ["a", "b"], "rows": [["1", "2"]]},
            {"type": "tabs", "tabs": [{"label": "T1"}]},
        ],
    }
    out = aom.render_aom([comp], device="voice")
    blob = json.dumps(out)  # must not raise
    assert isinstance(blob, str)
    # The semantic tree is structure, not markup: it emits no HTML element tags.
    assert "<" not in blob
    assert "<table" not in blob and "<div" not in blob and "<span" not in blob
