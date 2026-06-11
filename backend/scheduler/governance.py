"""Scheduled-job governance for multi-tenant safety (feature 025, T045/FR-038).

Pure validation helpers (no I/O) so they are unit-testable: a per-user cap on
active jobs and a minimum recurring-interval floor (no sub-minute jobs). The
runtime-concurrency limit is handled by reusing the existing
``BackgroundTaskManager`` cap in the runner, not here.
"""
from __future__ import annotations

from .cron import interval_seconds


class GovernanceError(ValueError):
    """Raised when a job would violate a governance limit."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def check_job_cap(active_job_count: int, max_active: int) -> None:
    """Raise if creating another active job exceeds the per-user cap."""
    if active_job_count >= max_active:
        raise GovernanceError(
            "job_cap_reached",
            f"You already have the maximum of {max_active} active scheduled jobs.",
            limit=max_active,
        )


def check_interval_floor(schedule_kind: str, schedule_expr: str, min_interval_seconds: int) -> None:
    """Raise if a recurring interval is below the minimum floor.

    Only applies to ``interval`` schedules; cron schedules are minute-resolution
    by construction (the scheduler tick), and one-shots have no recurrence.
    """
    secs = interval_seconds(schedule_kind, schedule_expr)
    if secs is None:
        return
    if secs < min_interval_seconds:
        raise GovernanceError(
            "interval_too_small",
            f"Recurring jobs must be at least {min_interval_seconds} seconds apart.",
            min_interval_seconds=min_interval_seconds,
        )


def validate_new_job(
    *,
    active_job_count: int,
    max_active: int,
    schedule_kind: str,
    schedule_expr: str,
    min_interval_seconds: int,
) -> None:
    """Run all create-time governance checks. Raises GovernanceError/ScheduleError."""
    check_job_cap(active_job_count, max_active)
    check_interval_floor(schedule_kind, schedule_expr, min_interval_seconds)
