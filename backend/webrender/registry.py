"""Renderer registry & client-target dispatch.

This is the seam that makes new client targets additive: a new target registers
a renderer here; primitive definitions (``astralprims``) and agent code never
change.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .renderer import PRIMITIVE_RENDERERS, render as render_web
from .voice import render_voice
from .aom import render_aom

logger = logging.getLogger("webrender")

# Client target -> renderer callable(components, profile) -> target output.
# The `voice` target renders structured SSML for TTS; the `aom` target renders a
# navigable semantic role/name/state tree (not HTML) for assistive tech.
TARGET_RENDERERS: Dict[str, Callable[[List[Dict[str, Any]], Any], Any]] = {
    "web": render_web,
    "voice": render_voice,
    "aom": render_aom,
}

DEFAULT_TARGET = "web"


def register_target(name: str, renderer: Callable[[List[Dict[str, Any]], Any], Any]) -> None:
    """Register a renderer for a new client target. Adding a target requires
    only this call + the renderer module — no change to astralprims or agents."""
    TARGET_RENDERERS[name] = renderer


def get_renderer(type_name: str) -> Optional[Callable[[Dict[str, Any]], str]]:
    """Return the web primitive renderer for a primitive ``type`` (or None)."""
    return PRIMITIVE_RENDERERS.get(type_name)


def render_for_target(target: Optional[str], components: List[Dict[str, Any]], profile: Any = None) -> Any:
    """Render the (ROTE-adapted) structured representation for a client target.

    Unknown/unsupported targets are handled predictably: we log a non-silent
    warning and fall back to the default (web) renderer rather than failing the
    response.
    """
    key = (target or DEFAULT_TARGET).lower()
    fn = TARGET_RENDERERS.get(key)
    if fn is None:
        logger.warning("webrender: unknown client target %r — falling back to %r", target, DEFAULT_TARGET)
        fn = TARGET_RENDERERS[DEFAULT_TARGET]
    return fn(components, profile)


def target_for_profile(profile: Any) -> str:
    """Pick the renderer target for a device profile.

    Default is ``web``. When ``FF_NATIVE_TARGETS`` is enabled, a VOICE device is
    routed to the structured ``voice`` (SSML) renderer, and an explicit
    ``profile.render_target`` (e.g. ``aom`` for an accessibility-object-model
    client) is honored when that target is registered. Off ⇒ always ``web``, so
    the default product is unchanged.
    """
    import os
    if os.getenv("FF_NATIVE_TARGETS", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return DEFAULT_TARGET
    explicit = getattr(profile, "render_target", None)
    if explicit and str(explicit).lower() in TARGET_RENDERERS:
        return str(explicit).lower()
    dt = getattr(profile, "device_type", None)
    dt_val = getattr(dt, "value", dt)
    if dt_val == "voice" and "voice" in TARGET_RENDERERS:
        return "voice"
    return DEFAULT_TARGET
