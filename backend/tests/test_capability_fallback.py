"""Feature 033 (capability C-D1) — capability-negotiated contracts + fallback ladder.

A target declares the primitive types it can render; ROTE substitutes any
unsupported type down a fixed ladder (timeline→list, chart→table→text, …) so the
SDUI contract degrades gracefully. Covers the pure ladder, the profile
capability field, and the recursive structural degradation.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote import fallback  # noqa: E402
from rote.adapter import ComponentAdapter  # noqa: E402
from rote.capabilities import DeviceProfile  # noqa: E402


def _profile(supported=None):
    p = DeviceProfile.default()
    p.supported_types = frozenset(supported) if supported is not None else None
    return p


# ───────────────────────── first_supported ───────────────────────────────────

def test_supported_type_is_unchanged():
    assert fallback.first_supported("timeline", {"timeline", "text"}) == "timeline"


def test_unsupported_walks_ladder():
    assert fallback.first_supported("timeline", {"list", "text"}) == "list"
    assert fallback.first_supported("bar_chart", {"table", "text"}) == "table"
    assert fallback.first_supported("bar_chart", {"list", "text"}) == "list"


def test_terminal_is_text():
    assert fallback.first_supported("timeline", {"text"}) == "text"
    assert fallback.first_supported("metric", {"text"}) == "text"


def test_unknown_type_falls_to_text():
    assert fallback.first_supported("flux_capacitor", {"text"}) == "text"


def test_empty_supported_renders_everything():
    # None/empty supported set = full support, no substitution
    assert fallback.first_supported("timeline", set()) == "timeline"


# ───────────────────────── profile capability field ──────────────────────────

def test_profile_default_supported_types_is_none():
    assert DeviceProfile.default().supported_types is None


def test_from_dict_parses_supported_types():
    p = DeviceProfile.from_dict({"device_type": "browser",
                                 "supported_types": ["Text", "list", " table "]})
    assert p.supported_types == frozenset({"text", "list", "table"})


def test_from_dict_without_supported_types_is_none():
    assert DeviceProfile.from_dict({"device_type": "browser"}).supported_types is None


# ───────────────────────── degradation (structural) ──────────────────────────

def _adapt(comp, supported):
    return ComponentAdapter.adapt([comp], _profile(supported))[0]


def test_none_supported_is_noop():
    comp = {"type": "timeline", "items": [{"time": "9am", "title": "Standup"}]}
    assert ComponentAdapter.adapt([comp], _profile(None)) == [comp]


def test_timeline_degrades_to_list():
    comp = {"type": "timeline", "title": "Sched", "items": [
        {"time": "9am", "title": "Standup", "description": "daily"},
        {"time": "1pm", "title": "Review"}]}
    out = _adapt(comp, {"list", "text"})
    assert out["type"] == "list" and out["title"] == "Sched"
    assert out["items"][0] == "9am — Standup — daily"
    assert out["items"][1] == "1pm — Review"


def test_keyvalue_degrades_to_table():
    comp = {"type": "keyvalue", "items": [{"label": "CPU", "value": "9%"},
                                          {"label": "Mem", "value": "40%"}]}
    out = _adapt(comp, {"table", "text"})
    assert out["type"] == "table" and out["rows"] == [["CPU", "9%"], ["Mem", "40%"]]


def test_chart_with_series_degrades_to_table():
    comp = {"type": "bar_chart", "title": "Q", "data": {
        "labels": ["Q2", "Q3"], "series": [{"name": "rev", "data": [10, 12]}]}}
    out = _adapt(comp, {"table", "text"})
    assert out["type"] == "table"
    assert out["headers"] == ["label", "rev"]
    assert out["rows"] == [["Q2", 10], ["Q3", 12]]


def test_chart_without_data_falls_through_to_text():
    comp = {"type": "line_chart", "title": "Mystery"}
    out = _adapt(comp, {"text"})  # table & list both unsupported
    assert out["type"] == "text"


def test_metric_degrades_to_text():
    out = _adapt({"type": "metric", "title": "CPU", "value": "9%"}, {"text"})
    assert out["type"] == "text" and ("CPU" in out["content"] or "9%" in out["content"])


def test_text_only_target_collapses_everything():
    for comp in [{"type": "rating", "value": 4}, {"type": "badge", "label": "ok"},
                 {"type": "hero", "title": "Hi"}]:
        assert _adapt(comp, {"text"})["type"] == "text"


# ───────────────────────── degradation (recursive) ───────────────────────────

def test_supported_container_degrades_unsupported_child():
    comp = {"type": "card", "title": "Status", "content": [
        {"type": "text", "content": "ok"},
        {"type": "timeline", "items": [{"time": "9am", "title": "Standup"}]}]}
    out = _adapt(comp, {"card", "text", "list"})
    assert out["type"] == "card"  # card itself supported
    kinds = [c["type"] for c in out["content"]]
    assert kinds == ["text", "list"]  # the nested timeline degraded


def test_unsupported_container_becomes_supported_container():
    comp = {"type": "grid", "columns": 2, "children": [
        {"type": "metric", "title": "A", "value": "1"}]}
    out = _adapt(comp, {"container", "text"})  # grid unsupported → container
    assert out["type"] == "container"
    assert out["content"][0]["type"] == "text"  # metric degraded inside


def test_tabs_content_degrades():
    comp = {"type": "tabs", "tabs": [
        {"label": "One", "content": [{"type": "timeline", "items": [{"title": "x"}]}]}]}
    out = _adapt(comp, {"tabs", "list", "text"})
    assert out["type"] == "tabs"
    assert out["tabs"][0]["content"][0]["type"] == "list"
