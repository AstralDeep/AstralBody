"""Procedural / skill memory + workflow induction — 033 Wave-2 (C-N10).

Successful multi-step tool-call traces are distilled into retrievable,
parameterized **recipes**. A trace is just the ordered list of steps the
orchestrator already executed — ``[{"tool": "read_csv", "args": {...}}, ...]`` —
and inducing a recipe captures three things:

  * ``tools``  — the ordered tool sequence to replay,
  * ``params`` — the sorted, de-duplicated set of arg KEYS seen across the trace
    (the *slots* a future replay must fill), and
  * ``trigger_keywords`` — lowercased words that, when found in a new request,
    suggest this recipe applies.

A new request is matched to the recipe with the best keyword overlap; once a
recipe is chosen the caller supplies the concrete arg values and
:func:`parameterize` builds a replay plan (one step per tool, each carrying only
the recipe's own params that were actually provided). :func:`missing_params`
names the slots still unfilled so the orchestrator can ask the user before
replaying — replay itself happens later under the **existing scopes + audit**;
this module is pure bookkeeping and introduces **no new dependency**.

Pure + deterministic; traces and recipes are plain dicts/lists/tuples — no DB,
network, or LLM. Flag ``FF_SKILL_MEMORY`` (default OFF) gates whether the
orchestrator induces/matches at all; the functions here behave the same
regardless of the flag.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

_TRUE = ("1", "true", "yes", "on")


def skill_memory_enabled() -> bool:
    """FF_SKILL_MEMORY feature flag (default OFF; feature 033 C-N10)."""
    return os.getenv("FF_SKILL_MEMORY", "false").strip().lower() in _TRUE


@dataclass(frozen=True)
class Recipe:
    """A distilled, replayable workflow.

    Attributes:
        name: Human label for the recipe.
        tools: Ordered tool sequence to replay (one entry per trace step,
            duplicates preserved).
        params: Sorted, unique arg KEYS seen across the trace — the slots a
            replay must fill.
        trigger_keywords: Lowercased words that suggest this recipe applies to a
            request.
    """

    name: str
    tools: Tuple[str, ...]
    params: Tuple[str, ...]
    trigger_keywords: Tuple[str, ...]


def induce_recipe(
    name: str,
    trace: List[Dict],
    *,
    trigger_keywords: Optional[Any] = None,
) -> Recipe:
    """Distill a successful tool-call ``trace`` into a :class:`Recipe`.

    ``tools`` is the ordered tuple of each step's ``"tool"`` (duplicates kept, in
    order). ``params`` is the sorted, de-duplicated union of every step's
    ``"args"`` keys — the slots to fill on replay. ``trigger_keywords`` come from
    the passed-in iterable (each stringified + lowercased; duplicates dropped,
    order preserved), or are empty when none is given.

    Raises:
        ValueError: if ``trace`` is empty (nothing to induce from).
    """
    if not trace:
        raise ValueError("cannot induce a recipe from an empty trace")

    tools: Tuple[str, ...] = tuple(str(step.get("tool", "")) for step in trace)

    param_set = set()
    for step in trace:
        args = step.get("args") or {}
        if isinstance(args, dict):
            param_set.update(str(k) for k in args.keys())
    params: Tuple[str, ...] = tuple(sorted(param_set))

    keywords: Tuple[str, ...] = _normalize_keywords(trigger_keywords)

    return Recipe(name=name, tools=tools, params=params, trigger_keywords=keywords)


def _normalize_keywords(trigger_keywords: Optional[Any]) -> Tuple[str, ...]:
    """Lowercase + de-duplicate (order-preserving) the trigger keywords."""
    if not trigger_keywords:
        return ()
    seen: List[str] = []
    for kw in trigger_keywords:
        norm = str(kw).strip().lower()
        if norm and norm not in seen:
            seen.append(norm)
    return tuple(seen)


def _overlap(recipe: Recipe, request_lc: str) -> int:
    """How many of ``recipe``'s trigger keywords appear in the lowercased
    request (each keyword counted at most once)."""
    return sum(1 for kw in recipe.trigger_keywords if kw and kw in request_lc)


def match_recipe(
    recipes: List[Recipe],
    request: str,
    *,
    min_overlap: int = 1,
) -> Optional[Recipe]:
    """Pick the recipe best matching ``request`` by trigger-keyword overlap.

    A recipe qualifies only if at least ``min_overlap`` of its trigger keywords
    appear in the lowercased request. Among qualifiers the one with the most
    matches wins; ties break toward the recipe with **more** trigger keywords
    (the more specific trigger), then toward earlier list order.

    Returns ``None`` when no recipe meets the threshold.
    """
    request_lc = (request or "").lower()
    best: Optional[Recipe] = None
    best_key: Optional[Tuple[int, int]] = None

    for recipe in recipes:
        score = _overlap(recipe, request_lc)
        if score < min_overlap:
            continue
        # Larger score, then more trigger keywords, then earlier order (strict >
        # keeps the first-seen recipe on a full tie).
        key = (score, len(recipe.trigger_keywords))
        if best_key is None or key > best_key:
            best, best_key = recipe, key

    return best


def parameterize(recipe: Recipe, args: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a replay plan: one step per tool in ``recipe.tools``.

    Each step is ``{"tool": t, "args": {p: args[p] ...}}`` carrying only the
    recipe's own ``params`` that are actually present in ``args`` — provided keys
    that aren't recipe params are ignored, and recipe params absent from ``args``
    are simply left out (see :func:`missing_params`).
    """
    filled = {p: args[p] for p in recipe.params if p in args}
    return [{"tool": tool, "args": dict(filled)} for tool in recipe.tools]


def missing_params(recipe: Recipe, args: Dict[str, Any]) -> List[str]:
    """Recipe params with no value in ``args`` — the slots to ask the user for
    before a replay can proceed (in the recipe's param order)."""
    return [p for p in recipe.params if p not in args]
