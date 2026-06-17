"""Tiered level-of-detail ladder + modality routing — 033 Wave-3 (C-D10).

Author a component's narrative ONCE as a three-rung ladder — L1 index (a
glanceable headline), L2 summary (a sentence or two), L3 detail (the full
breakdown) — and let ROTE pull the right depth for the surface it is rendering
on. A watch or a voice assistant gets the L1 rung; a phone gets L2; a tablet,
desktop browser, or a large TV gets the full L3.

Alongside depth, each surface has a *primary modality* — the channel the answer
should lead with. A voice assistant leads with spoken text (one sentence, then
offers to say more); a TV or large display leads with visuals; a tiny watch
leads with terse text. ``resolve()`` combines both decisions and, on a terse
surface where richer detail exists, raises an ``offer_detail`` flag so the
caller can append a "ask me for the full breakdown" affordance.

Pure, deterministic, stdlib-only. A missing rung falls *down* the ladder
(L3 → L2 → L1) and finally to the component's plain content; nothing here ever
raises on malformed input.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


def lod_enabled() -> bool:
    """Return True when the level-of-detail ladder feature flag is on.

    Controlled by ``FF_LOD_LADDER`` (default off). Accepts the usual truthy
    spellings so an operator can flip it with ``1``/``true``/``yes``/``on``.
    """
    return os.getenv("FF_LOD_LADDER", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ---------------------------------------------------------------------------
# Levels — the three rungs of the detail ladder.
# ---------------------------------------------------------------------------
# L1 = index    : a glanceable headline ("Sales up").
# L2 = summary  : a sentence or two ("Sales up 12% MoM").
# L3 = detail   : the full breakdown.
L1, L2, L3 = 1, 2, 3

# The ordered fallback chain for each level: try the exact rung, then walk
# *down* toward the index. Authoring L3 alone, or only L1, both work.
_FALLBACK_CHAIN: Dict[int, tuple] = {
    L3: (L3, L2, L1),
    L2: (L2, L1),
    L1: (L1,),
}

# The lod-dict key for each level ("l1"/"l2"/"l3").
_LOD_KEY: Dict[int, str] = {L1: "l1", L2: "l2", L3: "l3"}

# Plain-content keys probed (in order) when a component carries no lod dict.
_PLAIN_KEYS = ("content", "text", "value")


def _device_type(device: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract a normalized ``device_type`` string, or None."""
    if not isinstance(device, dict):
        return None
    dt = device.get("device_type")
    if isinstance(dt, str):
        dt = dt.strip().lower()
        return dt or None
    return None


def _is_small(device: Optional[Dict[str, Any]]) -> bool:
    """Return True when the device explicitly flags itself as a small screen."""
    if not isinstance(device, dict):
        return False
    return bool(device.get("is_small"))


def level_for_device(device: Optional[Dict[str, Any]]) -> int:
    """Pick the detail rung (L1/L2/L3) for a device.

    Mapping:
      * watch, voice            → L1 (index — a glance or one spoken line)
      * mobile                  → L2 (summary — a sentence or two on a phone)
      * tablet, browser, tv     → L3 (detail — full breakdown; TV is visual-first)
      * unknown / None          → L3 (full, the safe default)
      * no device_type but the device flags ``is_small`` → L2
    """
    dt = _device_type(device)
    if dt in ("watch", "voice"):
        return L1
    if dt == "mobile":
        return L2
    if dt in ("tablet", "browser", "tv"):
        return L3
    # Unknown / missing device_type.
    if dt is None and _is_small(device):
        return L2
    return L3


def _lod_dict(component: Any) -> Dict[str, Any]:
    """Return the component's ``lod`` mapping, or an empty dict."""
    if isinstance(component, dict):
        lod = component.get("lod")
        if isinstance(lod, dict):
            return lod
    return {}


def _plain_content(component: Any) -> str:
    """Return the component's plain content/text/value as a string, or ''."""
    if isinstance(component, dict):
        for key in _PLAIN_KEYS:
            val = component.get(key)
            if val is not None:
                return str(val)
    return ""


def _has_lod_value(lod: Dict[str, Any], level: int) -> bool:
    """True when the lod dict carries a non-None value for ``level``."""
    return lod.get(_LOD_KEY[level]) is not None


def pick_content(component: Any, device: Optional[Dict[str, Any]]) -> str:
    """Return the best content string for the device's detail level.

    Resolves the device level, then walks *down* the fallback chain for that
    level (L3 → L2 → L1) returning the first rung the component actually
    authored. If the component carries no usable ``lod`` rung, falls back to its
    plain ``content``/``text``/``value``; if nothing is present, returns "".

    Never raises — malformed components and devices degrade to "".
    """
    level = level_for_device(device)
    lod = _lod_dict(component)
    for candidate in _FALLBACK_CHAIN.get(level, (level,)):
        if _has_lod_value(lod, candidate):
            return str(lod[_LOD_KEY[candidate]])
    return _plain_content(component)


# ---------------------------------------------------------------------------
# Modality routing — the primary channel a surface leads with.
# ---------------------------------------------------------------------------
VISUAL, VOICE, TEXT = "visual", "voice", "text"


def primary_modality(device: Optional[Dict[str, Any]]) -> str:
    """Choose the primary modality (channel) a surface should lead with.

    Mapping:
      * voice                   → VOICE  (audio-only — speak it)
      * tv                      → VISUAL (large screen — visual-first)
      * watch                   → TEXT   (tiny screen — terse text, no rich visuals)
      * tablet, browser         → VISUAL (room for rich components)
      * mobile                  → VISUAL normally, TEXT when it flags ``is_small``
      * unknown / None          → VISUAL when ``is_small`` is False, else TEXT
    """
    dt = _device_type(device)
    if dt == "voice":
        return VOICE
    if dt == "tv":
        return VISUAL
    if dt == "watch":
        return TEXT
    if dt in ("tablet", "browser"):
        return VISUAL
    if dt == "mobile":
        return TEXT if _is_small(device) else VISUAL
    # Unknown / missing device_type: a small surface leads with terse text.
    return TEXT if _is_small(device) else VISUAL


@dataclass(frozen=True)
class Resolved:
    """The resolved presentation for a component on a specific surface.

    Attributes:
        level: the chosen detail rung (L1/L2/L3).
        modality: the primary channel to lead with (VISUAL/VOICE/TEXT).
        content: the content string for ``level`` (with ladder fallback).
        offer_detail: True on a terse surface (level < L3) when a deeper lod
            rung exists — a hint to append an "ask me for more" affordance.
    """

    level: int
    modality: str
    content: str
    offer_detail: bool


def _deeper_lod_exists(component: Any, level: int) -> bool:
    """True when the component authored any lod rung deeper than ``level``."""
    lod = _lod_dict(component)
    return any(_has_lod_value(lod, deeper) for deeper in range(level + 1, L3 + 1))


def resolve(component: Any, device: Optional[Dict[str, Any]]) -> Resolved:
    """Resolve depth + modality + content for ``component`` on ``device``.

    Combines :func:`level_for_device`, :func:`primary_modality`, and
    :func:`pick_content`. ``offer_detail`` is True only on a terse surface
    (``level < L3``) where the component actually authored a deeper rung — i.e.
    richer detail is available but withheld for the surface, so the caller can
    signal "ask for more". Never raises.
    """
    level = level_for_device(device)
    modality = primary_modality(device)
    content = pick_content(component, device)
    offer_detail = level < L3 and _deeper_lod_exists(component, level)
    return Resolved(
        level=level,
        modality=modality,
        content=content,
        offer_detail=offer_detail,
    )
