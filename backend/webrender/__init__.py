"""Feature 026 — the orchestrator's server-side render layer.

astralprims defines primitives + the structured representation; this package
renders them into a client target's output (web HTML now); ROTE adapts per
device upstream. New targets are added via :func:`register_target`.
"""
from .renderer import render, render_one, esc, safe_url  # noqa: F401
from .registry import (  # noqa: F401
    render_for_target,
    register_target,
    get_renderer,
    TARGET_RENDERERS,
    PRIMITIVE_RENDERERS,
)

__all__ = [
    "render",
    "render_one",
    "render_for_target",
    "register_target",
    "get_renderer",
    "esc",
    "safe_url",
    "TARGET_RENDERERS",
    "PRIMITIVE_RENDERERS",
]
