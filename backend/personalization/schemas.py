"""Pydantic schemas for personalization (feature 025, US1/US3)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class PersonalitySpec(BaseModel):
    """The user's personality/"soul" — style only, subordinate to compliance."""
    tone: Optional[str] = Field(default=None, max_length=40)
    directness: Optional[str] = Field(default=None, max_length=40)
    humor: Optional[str] = Field(default=None, max_length=40)
    verbosity: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=500)


class ProfileResponse(BaseModel):
    """Shape returned by GET /api/personalization/profile."""
    profession: Optional[str] = None
    goals: List[str] = Field(default_factory=list)
    personality: Dict[str, Any] = Field(default_factory=dict)
    dreaming_enabled: bool = True


class ProfileUpdateRequest(BaseModel):
    """Partial update — only provided fields change."""
    profession: Optional[str] = Field(default=None, max_length=200)
    goals: Optional[List[str]] = None
    personality: Optional[PersonalitySpec] = None
    dreaming_enabled: Optional[bool] = None

    @field_validator("goals")
    @classmethod
    def _validate_goals(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("at most 20 goals")
        for g in v:
            if not isinstance(g, str) or len(g) > 140:
                raise ValueError("each goal must be a string of at most 140 characters")
        return v


class ValueRejected(BaseModel):
    """422 body when a value is rejected by the PHI gate (non-PHI reason)."""
    error: str = "value_rejected"
    field: str
    reason: str = "looks like protected health information"
