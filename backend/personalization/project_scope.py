"""Scoped / project memory boundary — 033 Wave-5 (C-U9).

A ``project_id`` namespace that groups chats + files + instructions + an isolated
memory slice, so work on one project doesn't bleed personalization into another.
Deterministic helpers only — the persistence keys/filters; the stores
(memory_item, chats, attachments) gain an optional ``project_id`` column wired
separately.

* :func:`scope_key` — the namespaced key for a (user, project) slice.
* :func:`filter_to_project` — isolate a project's rows (an item with no
  ``project_id`` is GLOBAL and visible in every project; an item tagged to a
  project is visible only there).
* :func:`layer_instructions` — project instructions layer on top of the global
  ones (project overrides on conflict).

Pure, stdlib only. **No new dependency.** Flag ``FF_PROJECT_MEMORY`` (default
OFF) — off means everything is the single global scope (today's behavior).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

#: The reserved id for "no project" — the global personalization slice.
GLOBAL = "__global__"


def project_scope_enabled() -> bool:
    """FF_PROJECT_MEMORY feature flag (default OFF; feature 033 C-U9)."""
    return os.getenv("FF_PROJECT_MEMORY", "false").strip().lower() in ("1", "true", "yes", "on")


def normalize_project(project_id: Optional[str]) -> str:
    """An empty / None project id collapses to the GLOBAL slice."""
    pid = (project_id or "").strip()
    return pid or GLOBAL


def scope_key(user_id: str, project_id: Optional[str]) -> str:
    """The namespaced scope key for a (user, project) memory slice."""
    return f"{user_id}\x1f{normalize_project(project_id)}"


def filter_to_project(items: List[Dict[str, Any]], project_id: Optional[str], *,
                      key: str = "project_id", include_global: bool = True) -> List[Dict[str, Any]]:
    """Return the items visible in ``project_id``: those tagged to it, plus
    (when ``include_global``) the untagged/global items. With ``project_id``
    None/global, only global items are returned (a project's private items stay
    out of the global view)."""
    target = normalize_project(project_id)
    out: List[Dict[str, Any]] = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        item_pid = normalize_project(it.get(key))
        if item_pid == target:
            out.append(it)
        elif include_global and item_pid == GLOBAL and target != GLOBAL:
            out.append(it)
    return out


def visible_in(item: Dict[str, Any], project_id: Optional[str], *, key: str = "project_id") -> bool:
    """Whether a single item is visible from ``project_id`` (its own project, or
    a global item viewed from inside a project)."""
    target = normalize_project(project_id)
    item_pid = normalize_project(item.get(key) if isinstance(item, dict) else None)
    return item_pid == target or (item_pid == GLOBAL and target != GLOBAL)


def layer_instructions(global_instructions: str, project_instructions: str) -> str:
    """Compose effective instructions for a project turn: the global steering
    with the project's appended after (project context wins on conflict because
    it comes last / closest to the task)."""
    g = (global_instructions or "").strip()
    p = (project_instructions or "").strip()
    if not p:
        return g
    if not g:
        return p
    return f"{g}\n\n## Project context\n{p}"
