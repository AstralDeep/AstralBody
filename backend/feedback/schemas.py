"""Pydantic / dataclass DTOs for the component-feedback subsystem.

Wire shapes (REST + WebSocket) are documented in
``specs/004-component-feedback-loop/contracts/``. The DB row shapes match
``data-model.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enum-like literals (kept as plain strings so they round-trip cleanly via
# JSONB columns, the wire, and Pydantic). Validators enforce the closed set.
# ---------------------------------------------------------------------------

SENTIMENTS = ("positive", "negative")
Sentiment = str  # one of SENTIMENTS

CATEGORIES = ("wrong-data", "irrelevant", "layout-broken", "too-slow", "other", "unspecified")
Category = str  # one of CATEGORIES

LIFECYCLES = ("active", "superseded", "retracted")
Lifecycle = str

COMMENT_SAFETIES = ("clean", "quarantined")
CommentSafety = str

QUALITY_STATUSES = ("healthy", "insufficient-data", "underperforming")
QualityStatus = str

PROPOSAL_STATUSES = ("pending", "accepted", "applied", "rejected", "superseded")
ProposalStatus = str

QUARANTINE_DETECTORS = ("inline", "loop_pre_pass")
QuarantineDetector = str

QUARANTINE_STATUSES = ("held", "released", "dismissed")
QuarantineStatus = str

# Hard length cap on free-text comment; matches contracts.
COMMENT_MAX_CHARS = 2048
RATIONALE_MAX_CHARS = 2048

# Default 10 s per-(user, correlation_id, component_id) dedup window.
DEFAULT_DEDUP_WINDOW_SECONDS = 10

# Default 24 h retract / amend lock.
DEFAULT_EDIT_WINDOW_SECONDS = 24 * 3600


# ---------------------------------------------------------------------------
# Wire DTOs
# ---------------------------------------------------------------------------

class FeedbackSubmitRequest(BaseModel):
    """Inbound submit payload (REST body or WS ``component_feedback`` payload)."""

    correlation_id: Optional[str] = None
    component_id: Optional[str] = None
    source_agent: Optional[str] = None
    source_tool: Optional[str] = None
    sentiment: str
    category: str = "unspecified"
    comment: Optional[str] = None

    @field_validator("sentiment")
    @classmethod
    def _check_sentiment(cls, v: str) -> str:
        if v not in SENTIMENTS:
            raise ValueError(f"unknown sentiment: {v!r}")
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"unknown category: {v!r}")
        return v

    @field_validator("comment")
    @classmethod
    def _check_comment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("comment must be a string")
        if len(v) > COMMENT_MAX_CHARS:
            raise ValueError(
                f"comment exceeds {COMMENT_MAX_CHARS} chars; truncate or summarize"
            )
        return v


class FeedbackAmendRequest(BaseModel):
    """Subset of submit fields permitted for an amendment.

    Any field omitted is inherited from the prior version; passing
    ``comment=null`` explicitly clears the comment.
    """

    sentiment: Optional[str] = None
    category: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("sentiment")
    @classmethod
    def _check_sentiment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in SENTIMENTS:
            raise ValueError(f"unknown sentiment: {v!r}")
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in CATEGORIES:
            raise ValueError(f"unknown category: {v!r}")
        return v

    @field_validator("comment")
    @classmethod
    def _check_comment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) > COMMENT_MAX_CHARS:
            raise ValueError(
                f"comment exceeds {COMMENT_MAX_CHARS} chars; truncate or summarize"
            )
        return v


class FeedbackSubmitAck(BaseModel):
    feedback_id: str
    status: str  # "recorded" | "quarantined"
    deduped: bool = False


class FeedbackError(BaseModel):
    code: str
    message: str


# ---------------------------------------------------------------------------
# Read-side row DTOs
# ---------------------------------------------------------------------------

@dataclass
class ComponentFeedbackDTO:
    """Read-side row from the ``component_feedback`` table."""

    id: str
    user_id: str
    conversation_id: Optional[str]
    correlation_id: Optional[str]
    source_agent: Optional[str]
    source_tool: Optional[str]
    component_id: Optional[str]
    sentiment: str
    category: str
    comment_raw: Optional[str]
    comment_safety: str
    comment_safety_reason: Optional[str]
    lifecycle: str
    superseded_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    def to_user_view(self) -> Dict[str, Any]:
        """Serializer for ``GET /api/feedback`` (the user's own view)."""
        return {
            "id": str(self.id),
            "conversation_id": self.conversation_id,
            "correlation_id": self.correlation_id,
            "source_agent": self.source_agent,
            "source_tool": self.source_tool,
            "component_id": self.component_id,
            "sentiment": self.sentiment,
            "category": self.category,
            # The owner always sees their own raw comment regardless of
            # safety status — quarantining only excludes the text from
            # the synthesizer's LLM input, not from the user's own view.
            "comment": self.comment_raw,
            "comment_safety": self.comment_safety,
            "lifecycle": self.lifecycle,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


@dataclass
class ToolQualitySignalDTO:
    id: str
    agent_id: str
    tool_name: str
    window_start: datetime
    window_end: datetime
    dispatch_count: int
    failure_count: int
    negative_feedback_count: int
    failure_rate: float
    negative_feedback_rate: float
    status: str
    computed_at: datetime
    category_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_admin_view(self, *, flagged_at: Optional[datetime] = None,
                       pending_proposal_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "window_start": _iso(self.window_start),
            "window_end": _iso(self.window_end),
            "dispatch_count": self.dispatch_count,
            "failure_count": self.failure_count,
            "negative_feedback_count": self.negative_feedback_count,
            "failure_rate": self.failure_rate,
            "negative_feedback_rate": self.negative_feedback_rate,
            "category_breakdown": self.category_breakdown,
            "flagged_at": _iso(flagged_at) if flagged_at else None,
            "pending_proposal_id": pending_proposal_id,
            "status": self.status,
        }


@dataclass
class KnowledgeUpdateProposalDTO:
    id: str
    agent_id: str
    tool_name: str
    artifact_path: str
    diff_payload: str
    artifact_sha_at_gen: str
    evidence: Dict[str, Any]
    status: str
    reviewer_user_id: Optional[str]
    reviewed_at: Optional[datetime]
    reviewer_rationale: Optional[str]
    applied_at: Optional[datetime]
    generated_at: datetime


@dataclass
class QuarantineEntryDTO:
    feedback_id: str
    reason: str
    detector: str
    detected_at: datetime
    status: str
    actor_user_id: Optional[str]
    actioned_at: Optional[datetime]


def _iso(dt: Optional[datetime]) -> Optional[str]:
    """Render a datetime as RFC 3339 / ISO 8601 with 'Z' suffix."""
    if dt is None:
        return None
    return dt.isoformat()
