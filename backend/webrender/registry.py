"""Feature 026 — renderer registry & client-target dispatch.

This is the seam that makes new client targets additive (FR-011, SC-005): a new
target registers a renderer here; primitive definitions (``astralprims``) and
agent code never change. The web renderer is the only target implemented now.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .renderer import PRIMITIVE_RENDERERS, render as render_web
from .voice import render_voice

logger = logging.getLogger("webrender")

# Client target -> renderer callable(components, profile) -> target output.
# 033 Wave-3 (C-D4): the `voice` target renders structured SSML for TTS.
TARGET_RENDERERS: Dict[str, Callable[[List[Dict[str, Any]], Any], Any]] = {
    "web": render_web,
    "voice": render_voice,
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

    Unknown/unsupported targets are handled predictably (FR-013): we log a
    non-silent warning and fall back to the default (web) renderer rather than
    failing the response.
    """
    key = (target or DEFAULT_TARGET).lower()
    fn = TARGET_RENDERERS.get(key)
    if fn is None:
        logger.warning("webrender: unknown client target %r — falling back to %r", target, DEFAULT_TARGET)
        fn = TARGET_RENDERERS[DEFAULT_TARGET]
    return fn(components, profile)
