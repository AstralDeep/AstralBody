"""Accessibility as a render constraint — 033 Wave-3 (C-D9).

Two deterministic, dependency-free pieces:

* :func:`landmark_role` / :func:`landmark_label` — WCAG-by-construction: each
  top-level canvas component is wrapped as an ARIA landmark with a computed
  label, so a screen-reader user can navigate *between* components ("region:
  System Status", "region: Recent activity") rather than hearing one
  undifferentiated blob. Applied in ``render_component_fragment``.
* :func:`a11y_audit` — a deterministic post-validator over a component tree
  that flags WCAG issues (image without alt text, an action with no accessible
  label, an unlabelled landmark/tab, an empty heading). Pure; usable as a
  designer check or a CI gate. Never raises.

No new dependency. Kept renderer-independent (no import of the renderer) so the
renderer can import this without a cycle; escaping happens at the call site.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

#: Component type → ARIA landmark role for its top-level wrapper.
_LANDMARK_ROLES = {
    "card": "region", "container": "region", "collapsible": "region",
    "tabs": "region", "hero": "region", "timeline": "region", "list": "region",
    "table": "region", "grid": "group", "keyvalue": "group", "metric": "group",
    "alert": "status",
}


def a11y_enabled() -> bool:
    """FF_A11Y feature flag (default ON; feature 033 C-D9). When on, top-level
    components render as labelled ARIA landmarks. Off restores the bare
    identity wrapper."""
    return os.getenv("FF_A11Y", "true").strip().lower() not in ("0", "false", "no", "off")


def landmark_role(component: Dict[str, Any]) -> Optional[str]:
    """The ARIA landmark role for a top-level component, or None (decorative
    types — divider/skeleton/text — get no landmark)."""
    if not isinstance(component, dict):
        return None
    return _LANDMARK_ROLES.get(str(component.get("type", "")).strip().lower())


def landmark_label(component: Dict[str, Any]) -> str:
    """A human label for the landmark: the explicit title, else a type-derived
    name (so the landmark is never anonymous). Caller escapes."""
    if not isinstance(component, dict):
        return "section"
    title = component.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    t = str(component.get("type", "")).strip().lower()
    if t == "metric":
        val = component.get("value")
        return f"metric: {val}" if val not in (None, "") else "metric"
    if t == "alert":
        return f"{component.get('variant', 'info')} alert"
    if t == "hero":
        sub = component.get("subtitle")
        if isinstance(sub, str) and sub.strip():
            return sub.strip()
    return (t.replace("_", " ") or "section")


def _label_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def a11y_audit(components: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Deterministic WCAG-ish audit over a component tree. Returns a list of
    ``{"type", "issue"}`` findings (empty when clean). Pure; never raises."""
    issues: List[Dict[str, str]] = []

    def walk(c: Any) -> None:
        if not isinstance(c, dict):
            return
        t = str(c.get("type", "")).strip().lower()
        if t == "image" and not _label_present(c.get("alt")):
            issues.append({"type": "image", "issue": "image is missing alt text"})
        if t == "button" and not (_label_present(c.get("label"))
                                  or _label_present(c.get("aria_label"))):
            issues.append({"type": "button", "issue": "action has no accessible label"})
        if t in ("card", "collapsible", "tabs", "table") and not _label_present(c.get("title")):
            issues.append({"type": t, "issue": "landmark has no label (title)"})
        if t == "text" and str(c.get("variant", "")).lower() in ("h1", "h2", "h3") \
                and not _label_present(c.get("content")):
            issues.append({"type": "text", "issue": "empty heading"})
        for key in ("content", "children"):
            kids = c.get(key)
            if isinstance(kids, list):
                for ch in kids:
                    walk(ch)
        tabs = c.get("tabs")
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict):
                    if not _label_present(tab.get("label")):
                        issues.append({"type": "tab", "issue": "tab has no label"})
                    for ch in (tab.get("content") or []):
                        walk(ch)

    for c in (components or []):
        walk(c)
    return issues
