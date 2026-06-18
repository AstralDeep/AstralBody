"""Feature 033 (capability C-D10) — level-of-detail ladder wired into ROTE.

Author a component's narrative once as an ``lod`` ladder (L1 index / L2 summary
/ L3 detail); when ``FF_LOD_LADDER`` is on, ``ComponentAdapter.adapt`` collapses
it to the rung the device warrants BEFORE per-type adaptation runs — a watch
gets the one-line index, a phone the summary, a browser the full detail. With
the flag OFF the ladder is ignored and the component passes through unchanged.

These tests drive the REAL ``ComponentAdapter.adapt`` against real
``DeviceProfile`` objects (no DB, no network).
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote.adapter import ComponentAdapter  # noqa: E402
from rote.capabilities import DeviceCapabilities, DeviceProfile  # noqa: E402


def _profile(device_type: str) -> DeviceProfile:
    return DeviceProfile._derive(DeviceCapabilities(device_type=device_type))


BROWSER = _profile("browser")
MOBILE = _profile("mobile")
WATCH = _profile("watch")
TABLET = _profile("tablet")

# A text component authored once as a full L1/L2/L3 ladder. Short rungs so the
# watch's max_text_chars=120 truncation never confuses the assertions.
_LADDER_TEXT = {
    "type": "text",
    "variant": "body",
    "content": "fallback plain",
    "lod": {
        "l1": "Sales up",
        "l2": "Sales up 12% MoM",
        "l3": "Sales up 12% month-over-month across all regions.",
    },
}


def _only(result):
    assert len(result) == 1, f"expected one component, got {len(result)}: {result}"
    return result[0]


# ───────────────────────── flag default OFF ──────────────────────────────────

def test_flag_default_off_passes_through(monkeypatch):
    """Default env (flag absent): the ladder is NOT applied — the component (and
    its ``lod`` dict) reach the renderer unchanged on a browser passthrough."""
    monkeypatch.delenv("FF_LOD_LADDER", raising=False)
    out = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], BROWSER))
    # Browser is a no-op passthrough at adapt() level → the original survives.
    assert out["content"] == "fallback plain"
    assert "lod" in out  # ladder untouched when flag off


def test_flag_off_on_small_screen_keeps_plain_content(monkeypatch):
    """Flag OFF on a phone: per-type adaptation runs but the ladder is ignored,
    so the component keeps its original plain content (and its lod dict)."""
    monkeypatch.setenv("FF_LOD_LADDER", "false")
    out = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], MOBILE))
    assert out["content"] == "fallback plain"
    assert "lod" in out


# ───────────────────────── flag ON: per-device rung ──────────────────────────

def test_browser_gets_full_detail_l3(monkeypatch):
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    out = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], BROWSER))
    assert out["content"] == "Sales up 12% month-over-month across all regions."
    assert "lod" not in out  # consumed rung is stripped before the renderer


def test_mobile_gets_summary_l2(monkeypatch):
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    out = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], MOBILE))
    assert out["content"] == "Sales up 12% MoM"
    assert "lod" not in out


def test_watch_gets_index_l1(monkeypatch):
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    out = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], WATCH))
    assert out["content"] == "Sales up"
    assert "lod" not in out


def test_small_screen_content_differs_from_browser(monkeypatch):
    """The headline assertion: ON, the small-screen rung is shorter than the
    browser rung for the SAME authored component."""
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    phone = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], MOBILE))["content"]
    watch = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], WATCH))["content"]
    browser = _only(ComponentAdapter.adapt([dict(_LADDER_TEXT)], BROWSER))["content"]
    assert len(watch) < len(phone) < len(browser)
    assert watch != browser


# ───────────────────────── ladder-down fallback ──────────────────────────────

def test_ladder_falls_down_when_rung_missing(monkeypatch):
    """A component that only authored l1/l2: a browser (wants L3) falls down the
    ladder to l2 — the deepest authored rung."""
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    comp = {"type": "text", "variant": "body", "content": "plain",
            "lod": {"l1": "idx", "l2": "summary only"}}
    out = _only(ComponentAdapter.adapt([comp], BROWSER))
    assert out["content"] == "summary only"


# ───────────────────────── nesting + non-ladder safety ───────────────────────

def test_lod_applies_inside_container(monkeypatch):
    """A ladder on a child inside a card is resolved per-device too; the card's
    own child LIST is never clobbered."""
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    card = {"type": "card", "title": "Report", "content": [dict(_LADDER_TEXT)]}
    out = _only(ComponentAdapter.adapt([card], MOBILE))
    assert out["type"] == "card"
    assert isinstance(out["content"], list)
    child = out["content"][0]
    assert child["content"] == "Sales up 12% MoM"
    assert "lod" not in child


def test_component_without_ladder_unchanged(monkeypatch):
    """A component with no ``lod`` dict is structurally untouched when the flag
    is on (the ladder is opt-in per component)."""
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    comp = {"type": "text", "variant": "body", "content": "no ladder here"}
    out = _only(ComponentAdapter.adapt([comp], MOBILE))
    assert out["content"] == "no ladder here"


def test_metric_ladder_resolves_on_small(monkeypatch):
    """A non-text component (metric) carrying a ladder still collapses: the
    resolved rung lands in ``content`` and the lod dict is dropped."""
    monkeypatch.setenv("FF_LOD_LADDER", "true")
    metric = {"type": "metric", "title": "Revenue", "value": "$5M",
              "lod": {"l1": "up", "l3": "up sharply this quarter"}}
    out = _only(ComponentAdapter.adapt([metric], WATCH))
    # Watch → L1; only l1/l3 authored so L1 is exact.
    assert out["content"] == "up"
    assert out["value"] == "$5M"  # tool data preserved
    assert "lod" not in out
