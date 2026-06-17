"""Feature 033 (capability C-D4) — the VOICE renderer (structured SSML for TTS)."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from webrender import render_for_target  # noqa: E402
from webrender.voice import render_voice  # noqa: E402


def _v(comps):
    return render_voice(comps)


# ───────────────────────── envelope + leaves ─────────────────────────────────

def test_wraps_in_speak():
    out = _v([{"type": "text", "content": "hello"}])
    assert out.startswith("<speak>") and out.endswith("</speak>")
    assert "<s>hello</s>" in out


def test_empty_is_bare_speak():
    assert _v([]) == "<speak></speak>"


def test_metric_speaks_title_and_value():
    out = _v([{"type": "metric", "title": "Revenue", "value": "9M", "subtitle": "up 4%"}])
    assert "Revenue: 9M" in out and "up 4%" in out


def test_alert_speaks_variant_and_message():
    out = _v([{"type": "alert", "variant": "warning", "message": "disk low"}])
    assert "warning: disk low" in out


def test_hero_and_badge_and_rating():
    assert "Welcome" in _v([{"type": "hero", "title": "Welcome", "subtitle": "back"}])
    assert "online" in _v([{"type": "badge", "label": "online"}])
    assert "4 out of 5" in _v([{"type": "rating", "title": "Score", "value": 4}])


# ───────────────────────── collections ───────────────────────────────────────

def test_table_speaks_rows():
    out = _v([{"type": "table", "title": "Q", "headers": ["Name", "Rev"],
               "rows": [["Alice", "10"], ["Bob", "20"]]}])
    assert "Row 1: Name Alice, Rev 10" in out
    assert "Row 2: Name Bob, Rev 20" in out


def test_table_bounds_rows():
    rows = [["r", str(i)] for i in range(20)]
    out = _v([{"type": "table", "headers": ["x", "y"], "rows": rows}])
    assert "and 12 more rows" in out  # 20 - 8 cap


def test_keyvalue_and_list():
    out = _v([{"type": "keyvalue", "title": "Stats",
               "items": [{"label": "CPU", "value": "9%"}]}])
    assert "CPU is 9%" in out
    out2 = _v([{"type": "list", "title": "Todo", "items": ["a", "b"]}])
    assert "<s>a</s>" in out2 and "<s>b</s>" in out2


def test_list_bounds_items():
    out = _v([{"type": "list", "items": [str(i) for i in range(20)]}])
    assert "and 8 more" in out  # 20 - 12 cap


def test_timeline_speaks_events():
    out = _v([{"type": "timeline", "title": "Day", "items": [
        {"time": "9am", "title": "Standup", "description": "daily"}]}])
    assert "9am. Standup. daily" in out


def test_chart_is_announced_not_read():
    out = _v([{"type": "bar_chart", "title": "Sales", "data": {"series": [1, 2, 3]}}])
    assert "A chart: Sales" in out and "1" not in out


# ───────────────────────── recursion ─────────────────────────────────────────

def test_card_recurses_into_children():
    out = _v([{"type": "card", "title": "Status", "content": [
        {"type": "metric", "title": "CPU", "value": "9%"},
        {"type": "text", "content": "all good"}]}])
    assert "Status" in out and "CPU: 9%" in out and "all good" in out


def test_tabs_speak_label_then_content():
    out = _v([{"type": "tabs", "tabs": [
        {"label": "Overview", "content": [{"type": "text", "content": "hi"}]}]}])
    assert "Overview" in out and "hi" in out


def test_decorative_types_are_silent():
    assert _v([{"type": "divider"}]) == "<speak></speak>"
    assert _v([{"type": "skeleton"}]) == "<speak></speak>"


# ───────────────────────── safety ────────────────────────────────────────────

def test_text_is_ssml_escaped():
    out = _v([{"type": "text", "content": "A & B < C > D"}])
    assert "&amp;" in out and "&lt;" in out and "&gt;" in out
    assert "A & B" not in out  # raw ampersand never leaks


def test_markdown_punctuation_stripped():
    out = _v([{"type": "text", "content": "**bold** _italic_ `code`"}])
    assert "*" not in out and "_" not in out and "`" not in out
    assert "bold" in out and "italic" in out


# ───────────────────────── registry dispatch ─────────────────────────────────

def test_render_for_target_voice_dispatches_to_ssml():
    out = render_for_target("voice", [{"type": "text", "content": "spoken"}])
    assert out.startswith("<speak>") and "spoken" in out
