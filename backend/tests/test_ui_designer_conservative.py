"""Feature 039 (capability 033 C-U2) — conservative adaptation tests.

The designer should not churn a persisted canvas for a marginal gain (Todi et
al., CHI'21). Covers the pure ``should_adopt`` decision and its fail-open
integration into ``design_round`` via the new ``current_layout`` argument.

Pure Python — no DB, no network; the LLM is always a stub.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import ui_designer  # noqa: E402
from orchestrator.ui_designer import design_round, should_adopt  # noqa: E402

ALLOWED = {"container", "text", "card", "grid", "tabs", "hero", "metric", "ref",
           "table", "line_chart"}
RT = {"A": "table", "B": "line_chart"}

_GOOD = [{"type": "hero", "title": "Overview"},
         {"type": "grid", "columns": 2, "children": [
             {"type": "ref", "component_id": "A"}, {"type": "ref", "component_id": "B"}]}]
_FLAT_LAYOUT = [{"type": "ref", "component_id": "A"}, {"type": "ref", "component_id": "B"}]


# ───────────────────────── flag + margin ─────────────────────────────────────

def test_conservative_enabled_default_on(monkeypatch):
    monkeypatch.delenv("FF_UI_DESIGNER_CONSERVATIVE", raising=False)
    assert ui_designer.conservative_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_conservative_flag_off(monkeypatch, value):
    monkeypatch.setenv("FF_UI_DESIGNER_CONSERVATIVE", value)
    assert ui_designer.conservative_enabled() is False


def test_adopt_margin_default_and_override(monkeypatch):
    monkeypatch.delenv("UI_DESIGNER_ADOPT_MARGIN", raising=False)
    assert ui_designer.adopt_margin() == 0.5
    monkeypatch.setenv("UI_DESIGNER_ADOPT_MARGIN", "1.25")
    assert ui_designer.adopt_margin() == 1.25
    monkeypatch.setenv("UI_DESIGNER_ADOPT_MARGIN", "garbage")
    assert ui_designer.adopt_margin() == 0.5
    monkeypatch.setenv("UI_DESIGNER_ADOPT_MARGIN", "-3")
    assert ui_designer.adopt_margin() == 0.5


# ───────────────────────── should_adopt ──────────────────────────────────────

def test_should_adopt_no_current():
    assert should_adopt(_FLAT_LAYOUT, None, ref_types=RT) is True
    assert should_adopt(_FLAT_LAYOUT, [], ref_types=RT) is True


def test_should_adopt_different_content():
    # different component set → not a re-arrangement; place the new one
    other = [{"type": "ref", "component_id": "C"}]
    assert should_adopt(_GOOD, other, ref_types=RT) is True


def test_should_adopt_keeps_when_not_better():
    # same components, new (flat) is worse than current (good) → keep current
    assert should_adopt(_FLAT_LAYOUT, _GOOD, ref_types=RT) is False


def test_should_adopt_when_meaningfully_better():
    # same components, new (good) beats current (flat) by > margin → adopt
    assert should_adopt(_GOOD, _FLAT_LAYOUT, ref_types=RT) is True


def test_should_adopt_respects_margin():
    # good scores 3.0, flat 0.0 — a margin of 5 makes the gain insufficient
    assert should_adopt(_GOOD, _FLAT_LAYOUT, ref_types=RT, margin=5.0) is False


# ───────────────────────── driver integration ────────────────────────────────

_COMPS = [
    {"type": "table", "component_id": "A", "title": "Tbl", "_source_agent": "a", "_source_tool": "t"},
    {"type": "line_chart", "component_id": "B", "title": "Chart", "_source_agent": "a", "_source_tool": "t"},
]
_DRAFT = json.dumps({"layout": [
    {"type": "hero", "title": "Overview"},
    {"type": "grid", "columns": 2, "children": [
        {"type": "ref", "component_id": "A"}, {"type": "ref", "component_id": "B"}]}]})
_FLAT = json.dumps({"layout": [
    {"type": "ref", "component_id": "A"}, {"type": "ref", "component_id": "B"}]})


def _stub_llm(replies):
    it = iter(replies)

    async def _call(_messages):
        try:
            return next(it)
        except StopIteration:
            return "DONE"
    return _call


async def test_driver_keeps_existing_when_redesign_not_better(monkeypatch):
    monkeypatch.setenv("FF_UI_DESIGNER_CONSERVATIVE", "true")
    monkeypatch.setenv("FF_UI_DESIGNER_SCORER", "true")
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="cc1", layout_key="lk1", allowed_types=ALLOWED,
        llm_call=_stub_llm([_FLAT, "DONE"]), current_layout=_GOOD,
        timeout_s=5, max_rounds=2)
    assert any(n.get("type") == "hero" for n in out)  # kept the better existing layout


async def test_driver_conservative_off_adopts_new(monkeypatch):
    monkeypatch.setenv("FF_UI_DESIGNER_CONSERVATIVE", "false")
    monkeypatch.setenv("FF_UI_DESIGNER_SCORER", "true")
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="cc2", layout_key="lk2", allowed_types=ALLOWED,
        llm_call=_stub_llm([_FLAT, "DONE"]), current_layout=_GOOD,
        timeout_s=5, max_rounds=2)
    assert not any(n.get("type") == "hero" for n in out)  # churned to the new flat layout


async def test_driver_adopts_when_redesign_is_better(monkeypatch):
    monkeypatch.setenv("FF_UI_DESIGNER_CONSERVATIVE", "true")
    monkeypatch.setenv("FF_UI_DESIGNER_SCORER", "true")
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="cc3", layout_key="lk3", allowed_types=ALLOWED,
        llm_call=_stub_llm([_DRAFT, "DONE"]), current_layout=_FLAT_LAYOUT,
        timeout_s=5, max_rounds=2)
    assert any(n.get("type") == "hero" for n in out)  # better → adopted


async def test_driver_no_current_layout_adopts(monkeypatch):
    monkeypatch.setenv("FF_UI_DESIGNER_CONSERVATIVE", "true")
    monkeypatch.setenv("FF_UI_DESIGNER_SCORER", "true")
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="cc4", layout_key="lk4", allowed_types=ALLOWED,
        llm_call=_stub_llm([_DRAFT, "DONE"]), current_layout=None,
        timeout_s=5, max_rounds=2)
    assert any(n.get("type") == "hero" for n in out)
