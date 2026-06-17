"""Declarative multi-objective adaptation — 033 Wave-3 (C-D3).

Replaces per-component-type adaptation branches with a small set of
weighted, declarative *objectives*. Each objective is a pure scoring
function mapping ``(component, device) -> float`` in ``[0, 1]`` where a
higher score means "this component, on this device, is a better fit for
that objective". A weighted sum (``score_adaptation``) collapses the four
objectives into a single device-fit score so the UI designer can rank
candidate arrangements and pick the device-best one (``best_adaptation``).

The four objectives are:

* ``width_fit``        — does the component's natural width fit the surface?
* ``interaction_cost`` — inverse cost of interacting with the component here.
* ``glanceability``    — how quickly digestible is the component at a glance?
* ``speakability``     — how well does the component read aloud (voice)?

This module is **pure and deterministic**: stdlib only, no I/O beyond the
single env-var feature flag, no LLM/VLM. A perceptual/semantic *judge*
(LLM or VLM) is an *optional injected* component elsewhere and is never
called from here.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

# ---------------------------------------------------------------------------
# Component-type vocabularies (declarative — the heart of C-D3).
#
# Instead of an if/elif ladder per component type, each objective consults
# these frozensets/maps. Adding a new component type is a data edit, not a
# code branch. Types not named anywhere fall back to neutral/medium scores.
# ---------------------------------------------------------------------------

# Types whose *natural* render width is large: they want horizontal room.
_WIDE_TYPES: frozenset = frozenset(
    {
        "table",
        "grid",
        "plotly_chart",
        "line_chart",
        "bar_chart",
        "chart",
        "dataframe",
        "code",
        "timeline",
    }
)

# Types that are intrinsically narrow / fluid and fit anywhere.
_NARROW_TYPES: frozenset = frozenset(
    {
        "text",
        "metric",
        "badge",
        "alert",
        "rating",
        "keyvalue",
    }
)

# Interactive types — they cost the user an action (tap / type / pick / drop).
_INTERACTIVE_TYPES: frozenset = frozenset(
    {
        "button",
        "input",
        "param_picker",
        "file_upload",
        "select",
        "form",
        "slider",
    }
)

# Glanceability tiers: how fast the human eye extracts the gist.
_HIGH_GLANCE_TYPES: frozenset = frozenset(
    {"metric", "badge", "hero", "rating", "alert"}
)
_LOW_GLANCE_TYPES: frozenset = frozenset(
    {"table", "code", "plotly_chart", "dataframe", "grid"}
)

# Speakability tiers: how cleanly the content reads aloud.
_HIGH_SPEAK_TYPES: frozenset = frozenset(
    {"text", "alert", "list", "list_", "metric", "keyvalue"}
)
_LOW_SPEAK_TYPES: frozenset = frozenset(
    {
        "chart",
        "line_chart",
        "bar_chart",
        "plotly_chart",
        "table",
        "image",
        "code",
        "grid",
        "dataframe",
    }
)


DEFAULT_WEIGHTS: Dict[str, float] = {
    "width_fit": 0.35,
    "interaction_cost": 0.2,
    "glanceability": 0.25,
    "speakability": 0.2,
}


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
def objectives_enabled() -> bool:
    """Return whether declarative multi-objective adaptation is enabled.

    Driven by the ``FF_ADAPTIVE_OBJECTIVES`` env var (default off / fail
    safe). Accepted truthy spellings: ``1``, ``true``, ``yes``, ``on``
    (case-insensitive, surrounding whitespace ignored).
    """
    return os.getenv("FF_ADAPTIVE_OBJECTIVES", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ---------------------------------------------------------------------------
# Device model
# ---------------------------------------------------------------------------
def _device(d: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Normalize a device mapping to the three fields the scorers read.

    Missing keys default to a full desktop browser:
    ``max_grid_columns=12``, ``is_voice=False``, ``is_small=False``.
    """
    d = d or {}
    try:
        max_cols = int(d.get("max_grid_columns", 12))
    except (TypeError, ValueError):
        max_cols = 12
    return {
        "max_grid_columns": max_cols,
        "is_voice": bool(d.get("is_voice", False)),
        "is_small": bool(d.get("is_small", False)),
    }


def _ctype(component: Mapping[str, Any]) -> str:
    """Extract a component's lowercased ``type`` (empty string if absent)."""
    if not isinstance(component, Mapping):
        return ""
    return str(component.get("type", "")).strip().lower()


def _clamp01(x: float) -> float:
    """Clamp ``x`` into the closed unit interval ``[0, 1]``."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


# ---------------------------------------------------------------------------
# Objective scorers
# ---------------------------------------------------------------------------
def width_fit(component: Mapping[str, Any], device: Optional[Mapping[str, Any]]) -> float:
    """How well the component's natural width fits the device. Higher = better.

    Heuristic:

    * **Wide** types (table, grid, charts, code, …) want horizontal room.
      They score high on a wide surface but drop sharply on a small screen
      and bottom out on a voice surface (no width at all). The penalty also
      scales with how narrow ``max_grid_columns`` is.
    * **Narrow** types (text, metric, badge, alert, …) fit anywhere and
      score near the top on every surface.
    * Unknown types are treated as medium and lightly penalized on small /
      voice surfaces.
    """
    dev = _device(device)
    ctype = _ctype(component)

    # Voice has no visual width: wide content cannot be shown meaningfully.
    if dev["is_voice"]:
        if ctype in _WIDE_TYPES:
            return 0.1
        if ctype in _NARROW_TYPES:
            return 0.9
        return 0.5

    # Visual surface: scale by available grid columns (12 == roomy desktop).
    # roominess in [0, 1]; <=2 cols is effectively no room, >=12 is full room.
    roominess = _clamp01((dev["max_grid_columns"] - 2) / 10.0)

    if ctype in _WIDE_TYPES:
        # Wide types: poor when cramped, good when roomy. On a flagged-small
        # device, cap the upside even if column count is generous.
        score = 0.2 + 0.8 * roominess
        if dev["is_small"]:
            score = min(score, 0.45)
        return _clamp01(score)

    if ctype in _NARROW_TYPES:
        # Narrow types fit everywhere; the tiniest surfaces still read fine.
        return _clamp01(0.85 + 0.15 * roominess)

    # Unknown / medium types: mild sensitivity to available room.
    score = 0.55 + 0.35 * roominess
    if dev["is_small"]:
        score = min(score, 0.7)
    return _clamp01(score)


def interaction_cost(
    component: Mapping[str, Any], device: Optional[Mapping[str, Any]]
) -> float:
    """Inverse interaction cost — higher = *cheaper* / easier to interact with.

    Heuristic:

    * **Interactive** types (button, input, param_picker, file_upload, …)
      are hardest to operate by voice (no pointer / no keyboard), so they
      score low there; fiddly on small touch targets, so they score
      mid-low on a flagged-small device; and cheap on a full browser.
    * **Non-interactive** types impose no interaction cost and score high
      on every surface.
    """
    dev = _device(device)
    ctype = _ctype(component)

    if ctype in _INTERACTIVE_TYPES:
        if dev["is_voice"]:
            return 0.1  # essentially un-actionable without a screen/pointer
        if dev["is_small"]:
            return 0.5  # fiddly but possible on touch
        return 0.95  # full browser: pointer + keyboard, cheap to use

    # Non-interactive content costs the user nothing to "interact" with.
    return 1.0


def glanceability(
    component: Mapping[str, Any], device: Optional[Mapping[str, Any]]
) -> float:
    """How quickly the component is digestible at a glance. Higher = faster.

    Heuristic (mostly device-independent, with a small-surface boost):

    * **High-glance** types (metric, badge, hero, rating, alert) convey
      their gist instantly.
    * **Low-glance** types (table, code, charts, dataframe, grid) require
      study before the user extracts meaning.
    * Everything else is medium.

    On a small or voice surface, simple/high-glance types get a small extra
    boost (they are exactly what you want when attention is scarce) while
    dense low-glance types get nudged down further.
    """
    dev = _device(device)
    ctype = _ctype(component)
    constrained = dev["is_small"] or dev["is_voice"]

    if ctype in _HIGH_GLANCE_TYPES:
        base = 0.9
        if constrained:
            base = min(1.0, base + 0.1)
        return _clamp01(base)

    if ctype in _LOW_GLANCE_TYPES:
        base = 0.3
        if constrained:
            base = max(0.0, base - 0.1)
        return _clamp01(base)

    # Medium types: a touch above the midpoint, lightly boosted when scarce.
    base = 0.6
    if constrained:
        base = min(1.0, base + 0.05)
    return _clamp01(base)


def speakability(
    component: Mapping[str, Any], device: Optional[Mapping[str, Any]]
) -> float:
    """How well the component reads aloud. Higher = better for a voice surface.

    Heuristic:

    * Only matters on a **voice** device. When the device is *not* voice
      this returns a neutral ``1.0`` so it never penalizes a perfectly good
      visual arrangement.
    * On voice: **high-speak** types (text, alert, list, metric, keyvalue)
      narrate cleanly; **low-speak** types (charts, table, image, code)
      do not survive being read aloud and score low; others are medium.
    """
    dev = _device(device)
    if not dev["is_voice"]:
        return 1.0  # neutral — speakability is irrelevant off-voice

    ctype = _ctype(component)
    if ctype in _HIGH_SPEAK_TYPES:
        return 0.95
    if ctype in _LOW_SPEAK_TYPES:
        return 0.1
    return 0.5


# Registry mapping objective name -> scorer. Keeps score_adaptation declarative
# and ensures the weight keys and scorer names stay in lock-step.
_OBJECTIVES = {
    "width_fit": width_fit,
    "interaction_cost": interaction_cost,
    "glanceability": glanceability,
    "speakability": speakability,
}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def score_adaptation(
    component: Mapping[str, Any],
    device: Optional[Mapping[str, Any]],
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Weighted sum of the four objectives, normalized by total weight.

    ``weights`` defaults to :data:`DEFAULT_WEIGHTS`. Any missing or unknown
    weight key falls back to the corresponding ``DEFAULT_WEIGHTS`` value, so
    callers may pass a partial dict (e.g. ``{"speakability": 1.0}``) to
    emphasize a single objective without restating the rest. The result is
    the weighted average of the per-objective scores and therefore stays in
    ``[0, 1]``.
    """
    weights = weights or {}
    total_weight = 0.0
    weighted_sum = 0.0
    for name, scorer in _OBJECTIVES.items():
        try:
            w = float(weights.get(name, DEFAULT_WEIGHTS[name]))
        except (TypeError, ValueError):
            w = DEFAULT_WEIGHTS[name]
        if w <= 0.0:
            continue
        weighted_sum += w * scorer(component, device)
        total_weight += w

    if total_weight <= 0.0:
        return 0.0
    return _clamp01(weighted_sum / total_weight)


def best_adaptation(
    candidates: List[Mapping[str, Any]],
    device: Optional[Mapping[str, Any]],
    weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Return the candidate component with the highest adaptation score.

    ``candidates`` is a list of component dicts. Ties resolve to the
    earliest candidate in list order (stable / deterministic). Raises
    ``ValueError`` if ``candidates`` is empty.
    """
    if not candidates:
        raise ValueError("best_adaptation requires a non-empty candidate list")

    best = candidates[0]
    best_score = score_adaptation(best, device, weights)
    for candidate in candidates[1:]:
        s = score_adaptation(candidate, device, weights)
        if s > best_score:
            best, best_score = candidate, s
    return dict(best)
