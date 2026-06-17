"""Async/parallel fresh-context fan-out — 033 Wave-2 (C-N8).

A controller decomposes a multi-item task, scatters the items to isolated
sub-runs (one item per fresh context), self-verifies, and gathers the
results back together. This fixes the known ">8 items get fabricated"
failure: a single context, asked to produce many items at once, starts
inventing items past roughly eight. Fanning one item out per context and
verifying the produced count against the expected count prevents the model
from filling a quota with hallucinated entries.

This module is the PURE planning + gather/verify logic only. It performs no
DB, network, LLM, or async work — the actual concurrency (spawning the
isolated sub-runs) lives in the orchestrator's task layer and consumes the
plans / verification helpers defined here. Keeping the decision and
reconciliation logic side-effect free makes it deterministic and trivially
testable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

# Beyond this many items in a single context, the model tends to fabricate
# entries to satisfy the requested count. Fan out above it.
FABRICATION_THRESHOLD = 8


def fanout_enabled() -> bool:
    """Return True when the async fan-out feature flag is enabled.

    Controlled by the ``FF_ASYNC_FANOUT`` environment variable. Anything in
    the truthy set (``1``/``true``/``yes``/``on``, case-insensitive) enables
    it; the default ("false") and everything else leaves it off.
    """
    return os.getenv("FF_ASYNC_FANOUT", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def should_fan_out(item_count: int, *, threshold: int = 8) -> bool:
    """Return True when ``item_count`` exceeds the fabrication cliff.

    Fan-out is worthwhile only once a single context would be asked to
    produce more items than it can reliably enumerate (the default
    ``threshold`` of 8). At or below the threshold a single context is fine.
    """
    return item_count > threshold


def decompose(items: List[Any], *, max_parallel: int = 8) -> List[List[Any]]:
    """Split ``items`` into ordered chunks of at most ``max_parallel`` each.

    Order is preserved across and within chunks, and no empty chunk is ever
    produced (an empty ``items`` yields ``[]``). A non-positive
    ``max_parallel`` is treated as 1 so the function can never divide work
    into zero- or negative-sized chunks.
    """
    if max_parallel <= 0:
        max_parallel = 1
    return [items[i : i + max_parallel] for i in range(0, len(items), max_parallel)]


@dataclass(frozen=True)
class GatherResult:
    """Outcome of reconciling fanned-out sub-run results.

    Attributes:
        items: The unique gathered items, in first-seen order.
        expected: How many distinct items the task was supposed to produce.
        complete: True iff nothing is missing (``missing == 0``).
        missing: How many expected items are still absent
            (``max(0, expected - unique_count)``).
        duplicates: How many gathered entries were repeats of an item already
            seen (``total - unique_count``).
    """

    items: List[Any]
    expected: int
    complete: bool
    missing: int
    duplicates: int


def _flatten(results: List[Any]) -> List[Any]:
    """Flatten one level: list/tuple entries are expanded, others kept as-is.

    Sub-runs may each return a single item or a small batch (a list/tuple);
    flattening one level lets ``gather`` accept either shape uniformly.
    Strings/bytes are treated as scalar items, never iterated.
    """
    flat: List[Any] = []
    for entry in results:
        if isinstance(entry, (list, tuple)):
            flat.extend(entry)
        else:
            flat.append(entry)
    return flat


def gather(
    results: List[Any],
    *,
    expected: int,
    key: Optional[Callable[[Any], Any]] = None,
) -> GatherResult:
    """Collect and deduplicate fanned-out ``results`` against ``expected``.

    Each entry in ``results`` may be a single item or a list/tuple batch;
    both are flattened one level. Items are deduplicated by ``key`` (default:
    identity via ``str(item)``), preserving first-seen order. ``missing`` is
    ``max(0, expected - unique_count)`` and ``duplicates`` is
    ``total - unique_count``; ``complete`` is True iff ``missing == 0``.
    """
    key_fn: Callable[[Any], Any] = key if key is not None else (lambda x: str(x))

    flat = _flatten(results)
    seen: set = set()
    unique: List[Any] = []
    for item in flat:
        k = key_fn(item)
        if k in seen:
            continue
        seen.add(k)
        unique.append(item)

    unique_count = len(unique)
    duplicates = len(flat) - unique_count
    missing = max(0, expected - unique_count)
    return GatherResult(
        items=unique,
        expected=expected,
        complete=(missing == 0),
        missing=missing,
        duplicates=duplicates,
    )


def verify_count(expected: int, produced: List[Any]) -> bool:
    """Return True iff at least ``expected`` items were produced.

    This is the fabrication-shortfall guard: a fanned-out task must yield no
    fewer items than expected. It does NOT check for duplicates — pair it
    with :func:`gather` (which deduplicates) to confirm the unique count.
    """
    return len(produced) >= expected
