"""Feature 033 (capability C-D10) — tiered level-of-detail ladder + modality routing.

Author a component's narrative once as L1 index / L2 summary / L3 detail; ROTE
pulls the right rung per device and picks the primary modality per surface.
These tests cover the feature flag, the per-device level mapping (incl. the
``is_small`` fallback and the unknown→L3 default), ladder-down content fallback,
plain-content fallback, the modality mapping, and ``resolve()`` composition with
its ``offer_detail`` flag.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote import lod  # noqa: E402


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("FF_LOD_LADDER", raising=False)
    assert lod.lod_enabled() is False


def test_flag_on_variants(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "On", "  on  "):
        monkeypatch.setenv("FF_LOD_LADDER", val)
        assert lod.lod_enabled() is True


def test_flag_off_variants(monkeypatch):
    for val in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("FF_LOD_LADDER", val)
        assert lod.lod_enabled() is False


# ---------------------------------------------------------------------------
# level_for_device
# ---------------------------------------------------------------------------

def test_level_watch_and_voice_are_l1():
    assert lod.level_for_device({"device_type": "watch"}) == lod.L1
    assert lod.level_for_device({"device_type": "voice"}) == lod.L1


def test_level_mobile_is_l2():
    assert lod.level_for_device({"device_type": "mobile"}) == lod.L2


def test_level_tablet_browser_tv_are_l3():
    assert lod.level_for_device({"device_type": "tablet"}) == lod.L3
    assert lod.level_for_device({"device_type": "browser"}) == lod.L3
    # TV is visual-first but still gets full detail.
    assert lod.level_for_device({"device_type": "tv"}) == lod.L3


def test_level_unknown_and_none_default_to_l3():
    assert lod.level_for_device({"device_type": "hologram"}) == lod.L3
    assert lod.level_for_device(None) == lod.L3
    assert lod.level_for_device({}) == lod.L3


def test_level_is_small_without_type_is_l2():
    assert lod.level_for_device({"is_small": True}) == lod.L2
    # An explicit device_type takes precedence over is_small.
    assert lod.level_for_device({"device_type": "browser", "is_small": True}) == lod.L3


def test_level_case_insensitive_device_type():
    assert lod.level_for_device({"device_type": "WATCH"}) == lod.L1
    assert lod.level_for_device({"device_type": " Mobile "}) == lod.L2


# ---------------------------------------------------------------------------
# pick_content
# ---------------------------------------------------------------------------

_FULL_LOD = {"l1": "Sales up", "l2": "Sales up 12% MoM", "l3": "Full breakdown: ..."}


def test_pick_content_exact_level_when_present():
    comp = {"lod": dict(_FULL_LOD)}
    assert lod.pick_content(comp, {"device_type": "watch"}) == "Sales up"
    assert lod.pick_content(comp, {"device_type": "mobile"}) == "Sales up 12% MoM"
    assert lod.pick_content(comp, {"device_type": "browser"}) == "Full breakdown: ..."


def test_pick_content_falls_down_ladder_when_level_missing():
    # Device wants L3 (browser) but only l1/l2 authored → returns l2.
    comp = {"lod": {"l1": "Sales up", "l2": "Sales up 12% MoM"}}
    assert lod.pick_content(comp, {"device_type": "browser"}) == "Sales up 12% MoM"


def test_pick_content_falls_all_the_way_to_l1():
    # Device wants L3 but only l1 authored → returns l1.
    comp = {"lod": {"l1": "Sales up"}}
    assert lod.pick_content(comp, {"device_type": "tablet"}) == "Sales up"


def test_pick_content_l2_device_with_only_l1():
    # Mobile wants L2; only l1 present → falls down to l1.
    comp = {"lod": {"l1": "Sales up"}}
    assert lod.pick_content(comp, {"device_type": "mobile"}) == "Sales up"


def test_pick_content_falls_back_to_plain_content_keys():
    # No lod dict → use content, then text, then value.
    assert lod.pick_content({"content": "plain"}, {"device_type": "browser"}) == "plain"
    assert lod.pick_content({"text": "as text"}, {"device_type": "watch"}) == "as text"
    assert lod.pick_content({"value": 42}, {"device_type": "mobile"}) == "42"


def test_pick_content_empty_when_nothing_present():
    assert lod.pick_content({}, {"device_type": "browser"}) == ""
    assert lod.pick_content({"lod": {}}, {"device_type": "watch"}) == ""
    # Never raises on junk.
    assert lod.pick_content(None, None) == ""
    assert lod.pick_content({"lod": "not-a-dict"}, {"device_type": "mobile"}) == ""


def test_pick_content_lod_takes_precedence_over_plain():
    comp = {"lod": {"l1": "ladder"}, "content": "plain"}
    assert lod.pick_content(comp, {"device_type": "watch"}) == "ladder"


# ---------------------------------------------------------------------------
# primary_modality
# ---------------------------------------------------------------------------

def test_modality_voice_is_voice():
    assert lod.primary_modality({"device_type": "voice"}) == lod.VOICE


def test_modality_tv_is_visual():
    assert lod.primary_modality({"device_type": "tv"}) == lod.VISUAL


def test_modality_watch_is_text():
    assert lod.primary_modality({"device_type": "watch"}) == lod.TEXT


def test_modality_browser_and_tablet_are_visual():
    assert lod.primary_modality({"device_type": "browser"}) == lod.VISUAL
    assert lod.primary_modality({"device_type": "tablet"}) == lod.VISUAL


def test_modality_mobile_visual_unless_small():
    assert lod.primary_modality({"device_type": "mobile"}) == lod.VISUAL
    assert lod.primary_modality({"device_type": "mobile", "is_small": True}) == lod.TEXT


def test_modality_unknown_defaults():
    assert lod.primary_modality(None) == lod.VISUAL
    assert lod.primary_modality({}) == lod.VISUAL
    assert lod.primary_modality({"is_small": True}) == lod.TEXT


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

def test_resolve_composes_browser():
    comp = {"lod": dict(_FULL_LOD)}
    r = lod.resolve(comp, {"device_type": "browser"})
    assert r == lod.Resolved(
        level=lod.L3,
        modality=lod.VISUAL,
        content="Full breakdown: ...",
        offer_detail=False,
    )


def test_resolve_offer_detail_true_on_watch_with_deeper_lod():
    comp = {"lod": dict(_FULL_LOD)}
    r = lod.resolve(comp, {"device_type": "watch"})
    assert r.level == lod.L1
    assert r.modality == lod.TEXT
    assert r.content == "Sales up"
    # L1 surface, but l2/l3 exist → signal "ask for more".
    assert r.offer_detail is True


def test_resolve_offer_detail_true_on_voice():
    comp = {"lod": dict(_FULL_LOD)}
    r = lod.resolve(comp, {"device_type": "voice"})
    assert r.level == lod.L1
    assert r.modality == lod.VOICE
    assert r.content == "Sales up"
    assert r.offer_detail is True


def test_resolve_offer_detail_false_at_l3():
    comp = {"lod": dict(_FULL_LOD)}
    r = lod.resolve(comp, {"device_type": "tablet"})
    assert r.level == lod.L3
    # Already at full detail → never offers more.
    assert r.offer_detail is False


def test_resolve_offer_detail_false_when_no_deeper_level():
    # Watch (L1) but the component only authored l1 → nothing deeper to offer.
    comp = {"lod": {"l1": "Sales up"}}
    r = lod.resolve(comp, {"device_type": "watch"})
    assert r.level == lod.L1
    assert r.content == "Sales up"
    assert r.offer_detail is False


def test_resolve_offer_detail_true_on_mobile_with_l3():
    # Mobile resolves to L2; l3 exists → offer detail.
    comp = {"lod": dict(_FULL_LOD)}
    r = lod.resolve(comp, {"device_type": "mobile"})
    assert r.level == lod.L2
    assert r.content == "Sales up 12% MoM"
    assert r.offer_detail is True


def test_resolve_offer_detail_false_on_mobile_without_l3():
    # Mobile (L2) with only l1/l2 → no deeper rung to offer.
    comp = {"lod": {"l1": "Sales up", "l2": "Sales up 12% MoM"}}
    r = lod.resolve(comp, {"device_type": "mobile"})
    assert r.level == lod.L2
    assert r.content == "Sales up 12% MoM"
    assert r.offer_detail is False


def test_resolve_is_frozen():
    r = lod.resolve({"content": "x"}, None)
    try:
        r.level = 99  # type: ignore[misc]
    except Exception as exc:  # FrozenInstanceError subclasses Exception
        assert exc is not None
    else:
        raise AssertionError("Resolved should be immutable (frozen dataclass)")


def test_resolve_plain_content_no_lod_unknown_device():
    r = lod.resolve({"text": "hello"}, None)
    assert r.level == lod.L3
    assert r.modality == lod.VISUAL
    assert r.content == "hello"
    assert r.offer_detail is False
