"""Dual-ledger self-correcting orchestration — 033 Wave-2 (C-N7).

A Magentic-style controller keeps **two** ledgers while driving a multi-step
task, so it can notice when it is stuck and replan instead of looping:

- **Task-Ledger** (:class:`TaskLedger`) — the *what*. It pins the original
  request alongside the facts the controller is working from, separated by
  provenance so a reader (or the audit chain) can tell ground truth from
  inference: ``given_facts`` (stated in the request), ``recalled_facts``
  (retrieved from memory/context), ``derived_facts`` (computed/inferred this
  run), and ``guesses`` (low-confidence assumptions). It also carries the
  current ``plan`` — the ordered list of step names the controller intends to
  execute. When progress stalls the plan is *revised* (see below) and the new
  Task-Ledger snapshot is persisted.

- **Progress-Ledger** (:class:`ProgressLedger`) — the *how far*. It records one
  :class:`StepRecord` per executed step (complete? stalled? a short note),
  exposes completion accounting, and tracks the **stall counter**: the number
  of *consecutive* trailing steps that made no progress. A single step that
  does make progress resets the run to zero.

**Stall → replan.** :func:`should_replan` returns ``True`` once the consecutive
stall count reaches ``stall_threshold`` (default 3). The controller's loop is
expected to react by asking the planner for a fresh ``plan`` and calling
:meth:`TaskLedger.revise_plan`, breaking the loop rather than retrying the same
failing step indefinitely.

This module is the pure, deterministic core: dataclasses, counters, and the
replan predicate. No DB, no network, no LLM — integration lives in the
orchestrator behind ``FF_DUAL_LEDGER`` (:func:`ledger_enabled`).
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def ledger_enabled() -> bool:
    """``FF_DUAL_LEDGER`` (default OFF; feature 033 C-N7).

    When on, the orchestrator maintains the dual-ledger / stall-replan loop for
    multi-step turns. Default OFF: the controller is additive, and the legacy
    single-pass path is always available.
    """
    return os.getenv("FF_DUAL_LEDGER", "false").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class TaskLedger:
    """The *what*: the request, its facts (split by provenance), and the plan.

    Keeping ``given``/``recalled``/``derived`` facts and ``guesses`` in separate
    buckets lets the controller — and anyone auditing the run — distinguish
    ground truth from inference, and lets a replan reason about what it actually
    knows versus what it merely assumed.
    """

    request: str
    given_facts: List[str] = field(default_factory=list)
    recalled_facts: List[str] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)
    guesses: List[str] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)

    @classmethod
    def from_request(
        cls,
        request: str,
        *,
        given: Optional[List[str]] = None,
        recalled: Optional[List[str]] = None,
    ) -> "TaskLedger":
        """Open a fresh Task-Ledger for ``request``.

        ``given`` (facts stated in the request) and ``recalled`` (facts pulled
        from memory/context) seed the corresponding buckets; everything else —
        derived facts, guesses, and the plan — starts empty and is filled in as
        the controller works. Inputs are copied so later mutation of the ledger
        never reaches back into the caller's lists.
        """
        return cls(
            request=request,
            given_facts=list(given) if given else [],
            recalled_facts=list(recalled) if recalled else [],
            derived_facts=[],
            guesses=[],
            plan=[],
        )

    def to_audit_dict(self) -> Dict[str, Any]:
        """A JSON-safe snapshot of every field, for the audit chain.

        Lists are copied (not aliased) so the persisted record can't be mutated
        out from under the audit log by later edits to this ledger.
        """
        return {
            "request": self.request,
            "given_facts": list(self.given_facts),
            "recalled_facts": list(self.recalled_facts),
            "derived_facts": list(self.derived_facts),
            "guesses": list(self.guesses),
            "plan": list(self.plan),
        }

    def revise_plan(self, new_plan: List[str]) -> "TaskLedger":
        """Return a *copy* of this ledger with ``plan`` replaced.

        Replanning is non-destructive: the original snapshot is left intact (so
        it can be audited as the pre-replan state) and a new ledger carrying the
        fresh plan is returned. The new plan is copied to decouple it from the
        caller's list.
        """
        return dataclasses.replace(self, plan=list(new_plan))


@dataclass
class StepRecord:
    """One executed step: did it finish, did it stall, and an optional note."""

    name: str
    complete: bool
    stalled: bool
    note: str = ""


class ProgressLedger:
    """The *how far*: an ordered log of :class:`StepRecord`s plus the stall counter."""

    def __init__(self) -> None:
        self.steps: List[StepRecord] = []

    def record(
        self,
        name: str,
        *,
        complete: bool,
        stalled: bool = False,
        note: str = "",
    ) -> None:
        """Append a :class:`StepRecord` for the step just attempted."""
        self.steps.append(
            StepRecord(name=name, complete=complete, stalled=stalled, note=note)
        )

    def completed_count(self) -> int:
        """How many recorded steps are marked complete."""
        return sum(1 for s in self.steps if s.complete)

    def is_complete(self, total_steps: int) -> bool:
        """True once at least ``total_steps`` steps have completed."""
        return self.completed_count() >= total_steps

    def consecutive_stalls(self) -> int:
        """Number of *trailing* stalled steps.

        Counts back from the most recent record and stops at the first
        non-stalled step — a single step that makes progress resets the run to
        zero. This is the signal :func:`should_replan` watches.
        """
        count = 0
        for s in reversed(self.steps):
            if s.stalled:
                count += 1
            else:
                break
        return count

    def next_incomplete(self, plan: List[str]) -> Optional[str]:
        """The first step in ``plan`` not yet completed (by name).

        Returns the earliest plan entry whose name does not appear among the
        completed records, or ``None`` when every plan step has completed.
        """
        done = {s.name for s in self.steps if s.complete}
        for step in plan:
            if step not in done:
                return step
        return None


def should_replan(progress: ProgressLedger, *, stall_threshold: int = 3) -> bool:
    """True when the controller should stop and replan.

    Fires once the consecutive-stall count reaches ``stall_threshold`` (default
    3) — i.e. that many steps in a row made no progress — signalling the loop to
    request a fresh plan rather than keep retrying the same failing step.
    """
    return progress.consecutive_stalls() >= stall_threshold
