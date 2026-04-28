"""Per-tool quality-signal computation and `tool_flagged` / `tool_recovered`
audit-event emission.

A daily background job calls :func:`compute_for_window` once per 24 h
(scheduled in :mod:`backend.orchestrator.orchestrator`'s startup). The
function aggregates the prior 14-day window per ``(agent, tool)``,
classifies each tool as ``healthy`` / ``insufficient-data`` /
``underperforming`` per the operator-configurable thresholds, persists a
snapshot row, and emits audit events on transitions.

Defaults (FR-010 / FR-011 / FR-012):

* window = 14 days
* min eligibility dispatch count = 25
* flag if ``failure_rate >= 0.20 OR negative_feedback_rate >= 0.30``
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Optional

from audit.recorder import get_recorder, make_correlation_id, now_utc
from audit.schemas import AuditEventCreate

from .repository import FeedbackRepository
from .schemas import ToolQualitySignalDTO

logger = logging.getLogger("Feedback.Quality")


WINDOW_DAYS_ENV = "FEEDBACK_QUALITY_WINDOW_DAYS"
MIN_DISPATCH_ENV = "FEEDBACK_QUALITY_MIN_DISPATCH"
FAIL_RATE_ENV = "FEEDBACK_QUALITY_FAILURE_RATE_THRESHOLD"
NEG_FB_RATE_ENV = "FEEDBACK_QUALITY_NEGATIVE_FB_RATE_THRESHOLD"

DEFAULT_WINDOW_DAYS = 14
DEFAULT_MIN_DISPATCH = 25
DEFAULT_FAIL_RATE = 0.20
DEFAULT_NEG_FB_RATE = 0.30


def _read_thresholds():
    return (
        int(os.getenv(WINDOW_DAYS_ENV, str(DEFAULT_WINDOW_DAYS))),
        int(os.getenv(MIN_DISPATCH_ENV, str(DEFAULT_MIN_DISPATCH))),
        float(os.getenv(FAIL_RATE_ENV, str(DEFAULT_FAIL_RATE))),
        float(os.getenv(NEG_FB_RATE_ENV, str(DEFAULT_NEG_FB_RATE))),
    )


def classify_status(
    *, dispatch_count: int, failure_rate: float, negative_feedback_rate: float,
    min_dispatch: int = DEFAULT_MIN_DISPATCH,
    fail_rate_threshold: float = DEFAULT_FAIL_RATE,
    neg_fb_rate_threshold: float = DEFAULT_NEG_FB_RATE,
) -> str:
    if dispatch_count < min_dispatch:
        return "insufficient-data"
    if failure_rate >= fail_rate_threshold or negative_feedback_rate >= neg_fb_rate_threshold:
        return "underperforming"
    return "healthy"


async def compute_for_window(
    repo: FeedbackRepository,
    *,
    now: Optional[datetime] = None,
    window_days: Optional[int] = None,
    min_dispatch: Optional[int] = None,
    fail_rate_threshold: Optional[float] = None,
    neg_fb_rate_threshold: Optional[float] = None,
) -> List[ToolQualitySignalDTO]:
    """Compute snapshots for the prior window and emit transition audit events.

    Returns the list of computed snapshots. Caller is responsible for
    handing them to the proposal generator if it wants to (the synthesizer
    runs on its own cadence).
    """
    cfg_window, cfg_min, cfg_fail, cfg_neg = _read_thresholds()
    window_days = window_days or cfg_window
    min_dispatch = min_dispatch if min_dispatch is not None else cfg_min
    fail_rate_threshold = fail_rate_threshold if fail_rate_threshold is not None else cfg_fail
    neg_fb_rate_threshold = neg_fb_rate_threshold if neg_fb_rate_threshold is not None else cfg_neg

    window_end = now or datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=window_days)

    rows = repo.aggregate_window(window_start, window_end)
    snapshots: List[ToolQualitySignalDTO] = []

    for r in rows:
        agent_id = r["agent_id"]
        tool_name = r["tool_name"]
        dispatch_count = int(r["dispatch_count"])
        failure_count = int(r["failure_count"])
        negative_feedback_count = int(r["negative_feedback_count"])
        failure_rate = (failure_count / dispatch_count) if dispatch_count else 0.0
        negative_feedback_rate = (
            negative_feedback_count / dispatch_count if dispatch_count else 0.0
        )
        status = classify_status(
            dispatch_count=dispatch_count,
            failure_rate=failure_rate,
            negative_feedback_rate=negative_feedback_rate,
            min_dispatch=min_dispatch,
            fail_rate_threshold=fail_rate_threshold,
            neg_fb_rate_threshold=neg_fb_rate_threshold,
        )

        prior = repo.latest_quality_signal(agent_id, tool_name)

        new_dto = ToolQualitySignalDTO(
            id="",
            agent_id=agent_id,
            tool_name=tool_name,
            window_start=window_start,
            window_end=window_end,
            dispatch_count=dispatch_count,
            failure_count=failure_count,
            negative_feedback_count=negative_feedback_count,
            failure_rate=failure_rate,
            negative_feedback_rate=negative_feedback_rate,
            status=status,
            computed_at=window_end,
        )
        persisted = repo.insert_quality_signal(new_dto)
        snapshots.append(persisted)

        # Transition detection (FR-012a)
        prior_status = prior.status if prior else None
        if status == "underperforming" and prior_status != "underperforming":
            await _emit_transition_event(
                event="tool_flagged", dto=persisted,
                fail_rate_threshold=fail_rate_threshold,
                neg_fb_rate_threshold=neg_fb_rate_threshold,
            )
        elif prior_status == "underperforming" and status != "underperforming":
            await _emit_transition_event(
                event="tool_recovered", dto=persisted,
                fail_rate_threshold=fail_rate_threshold,
                neg_fb_rate_threshold=neg_fb_rate_threshold,
            )

    return snapshots


async def _emit_transition_event(
    *,
    event: str,  # "tool_flagged" | "tool_recovered"
    dto: ToolQualitySignalDTO,
    fail_rate_threshold: float,
    neg_fb_rate_threshold: float,
) -> None:
    rec = get_recorder()
    if rec is None:
        return
    try:
        await rec.record(AuditEventCreate(
            actor_user_id="system",
            auth_principal="system:feedback.quality_job",
            agent_id=dto.agent_id,
            event_class="tool_quality",
            action_type=event,
            description=(
                f"Tool {dto.tool_name} on agent {dto.agent_id} "
                f"{'flagged underperforming' if event == 'tool_flagged' else 'recovered'}"
            ),
            correlation_id=make_correlation_id(),
            outcome="success",
            inputs_meta={
                "tool_name": dto.tool_name,
                "agent_id": dto.agent_id,
                "window_days": (dto.window_end - dto.window_start).days,
                "dispatch_count": dto.dispatch_count,
                "failure_rate": round(dto.failure_rate, 4),
                "negative_feedback_rate": round(dto.negative_feedback_rate, 4),
                "fail_rate_threshold": fail_rate_threshold,
                "neg_fb_rate_threshold": neg_fb_rate_threshold,
            },
            started_at=now_utc(),
        ))
    except Exception as exc:  # pragma: no cover
        logger.warning("tool_quality audit emit failed (%s): %s", event, exc)
