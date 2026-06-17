"""Feature 033 (capability C-U6) — provenance / grounding surfacing.

Each top-level canvas component gets a subtle footer marking whether its
content is GROUNDED (traces to an agent tool) or AI-GENERATED (model-authored
designer garnish), so a hallucinated card no longer looks identical to a
verified one. Surfaced selectively (skipped on decorative types and
watch/voice surfaces) and strictly fail-open (flag off ⇒ legacy markup).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from webrender import renderer  # noqa: E402
from webrender.renderer import (  # noqa: E402
    provenance_of,
    render_component_fragment,
    render_workspace,
)


def _profile(device_type):
    return types.SimpleNamespace(device_type=types.SimpleNamespace(value=device_type))


# ───────────────────────── flag ──────────────────────────────────────────────

def test_provenance_enabled_default_on(monkeypatch):
    monkeypatch.delenv("FF_PROVENANCE_SURFACING", raising=False)
    assert renderer.provenance_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_provenance_flag_off_values(monkeypatch, value):
    monkeypatch.setenv("FF_PROVENANCE_SURFACING", value)
    assert renderer.provenance_enabled() is False


# ───────────────────────── provenance_of ─────────────────────────────────────

def test_tool_source_is_grounded():
    assert provenance_of({"type": "table", "_source_tool": "list_patients"}) == "grounded"


def test_no_source_is_generated():
    assert provenance_of({"type": "text", "content": "hello"}) == "generated"


def test_nested_tool_source_is_grounded():
    # a designed garnish container wrapping a tool ref reads as grounded
    comp = {"type": "card", "title": "Summary", "content": [
        {"type": "metric", "_source_tool": "avg_age", "value": "42"}]}
    assert provenance_of(comp) == "grounded"


def test_explicit_attribute_wins():
    assert provenance_of({"type": "metric", "provenance": "verified"}) == "grounded"
    assert provenance_of({"type": "metric", "provenance": "estimated"}) == "estimated"
    assert provenance_of({"type": "metric", "provenance": "model",
                          "_source_tool": "x"}) == "generated"


def test_unknown_explicit_falls_back_to_derivation():
    assert provenance_of({"type": "t", "provenance": "weird",
                          "_source_tool": "x"}) == "grounded"
    assert provenance_of({"type": "t", "provenance": "weird"}) == "generated"


def test_non_dict_is_generated():
    assert provenance_of("nope") == "generated"


# ───────────────────────── footer rendering ──────────────────────────────────

def test_grounded_component_gets_tool_footer():
    out = render_component_fragment({
        "type": "table", "component_id": "c1", "headers": ["x"], "rows": [["1"]],
        "_source_tool": "list_patients", "_source_agent": "agent-x"})
    assert "astral-provenance--grounded" in out
    assert "tool data" in out
    assert "agent-x" in out  # the tooltip names the source


def test_generated_garnish_gets_ai_footer():
    out = render_component_fragment({
        "type": "text", "component_id": "dgABC", "content": "AI narrative"})
    assert "astral-provenance--generated" in out
    assert "AI-generated" in out


def test_estimated_explicit_footer():
    out = render_component_fragment({"type": "metric", "component_id": "c2",
                                     "provenance": "estimated", "value": "~50"})
    assert "astral-provenance--estimated" in out
    assert "estimated" in out


def test_decorative_type_gets_no_footer():
    out = render_component_fragment({"type": "divider", "component_id": "d1"})
    assert "astral-provenance" not in out


def test_flag_off_is_legacy_markup(monkeypatch):
    monkeypatch.setenv("FF_PROVENANCE_SURFACING", "false")
    comp = {"type": "table", "component_id": "c1", "headers": ["x"], "rows": [["1"]],
            "_source_tool": "t"}
    out = render_component_fragment(comp)
    assert "astral-provenance" not in out
    # still the normal identity wrapper
    assert 'data-component-id="c1"' in out


def test_footer_skipped_on_watch_and_voice():
    comp = {"type": "table", "component_id": "c1", "headers": ["x"], "rows": [["1"]],
            "_source_tool": "t"}
    assert "astral-provenance" not in render_component_fragment(comp, _profile("watch"))
    assert "astral-provenance" not in render_component_fragment(comp, _profile("voice"))
    # but present on a full browser surface
    assert "astral-provenance" in render_component_fragment(comp, _profile("browser"))


def test_footer_present_when_no_profile():
    comp = {"type": "metric", "component_id": "c1", "_source_tool": "t", "value": "9"}
    assert "astral-provenance" in render_component_fragment(comp, None)


# ───────────────────────── workspace threads profile ─────────────────────────

def test_workspace_threads_profile_to_fragments():
    comps = [{"type": "metric", "component_id": "c1", "_source_tool": "t", "value": "9"}]
    assert "astral-provenance" in render_workspace(comps, _profile("browser"))
    assert "astral-provenance" not in render_workspace(comps, _profile("watch"))
