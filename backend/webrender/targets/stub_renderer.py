"""Feature 026 — US3 (T033): a stub *second* client-target renderer.

Purpose: prove the multi-target seam (FR-011 / SC-005). It renders only a single
primitive (``text``) from the SAME structured representation the web renderer
consumes, with NO dependency on the web renderer set and NO changes to
``astralprims`` definitions or any agent code. Registering it is the only step
needed to add a target.

This is intentionally minimal — it demonstrates the extension point, not a real
device target.
"""
from __future__ import annotations

import html
from typing import Any, List, Dict

from ..registry import register_target

TARGET_NAME = "stubtext"


def render_stub(components: List[Dict[str, Any]], profile: Any = None) -> str:
    """Render only ``text`` primitives to plain lines; ignore everything else.
    Consumes the same astralprims structured dicts as the web renderer."""
    lines = []
    for c in components or []:
        if isinstance(c, dict) and c.get("type") == "text":
            lines.append(html.escape(str(c.get("content", ""))))
    return "\n".join(lines)


def install() -> None:
    register_target(TARGET_NAME, render_stub)
