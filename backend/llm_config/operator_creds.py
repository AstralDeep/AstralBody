"""Operator-default LLM credentials (feature 006-user-llm-config).

Read once from environment variables at orchestrator startup; treated as
immutable for the life of the process. Used as the fallback whenever a
user has not configured personal credentials, AND for server-initiated
background jobs (notably the daily feedback quality / proposals job from
feature 004) where no individual user is the caller.

A user who HAS configured personal credentials never falls back to this
default — see :func:`backend.llm_config.client_factory.build_llm_client`
and FR-009 (no runtime fallback).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class OperatorDefaultCreds:
    """Operator's ``.env``-supplied LLM credentials.

    All three fields are optional because a deployment is allowed to
    omit them — in that case ``is_complete`` is ``False`` and the
    factory will only succeed for users who have configured personal
    credentials. A deployment with no operator default is the most
    privacy-respecting posture.
    """
    api_key: Optional[str]
    base_url: Optional[str]
    model: Optional[str]

    @classmethod
    def from_env(cls) -> "OperatorDefaultCreds":
        """Read ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` / ``LLM_MODEL`` from
        the process environment.

        Empty strings are treated as ``None`` so a deployment that sets
        ``OPENAI_API_KEY=`` (the common ``.env`` pattern for "leave this
        unset") behaves the same as omitting the var entirely.
        """
        def _empty_to_none(v: Optional[str]) -> Optional[str]:
            if v is None:
                return None
            v = v.strip()
            return v or None
        return cls(
            api_key=_empty_to_none(os.getenv("OPENAI_API_KEY")),
            base_url=_empty_to_none(os.getenv("OPENAI_BASE_URL")),
            model=_empty_to_none(os.getenv("LLM_MODEL")),
        )

    @property
    def is_complete(self) -> bool:
        """True iff all three fields are non-empty (i.e. usable as a
        credential set)."""
        return bool(self.api_key and self.base_url and self.model)

    def __repr__(self) -> str:
        # Elide api_key. The base_url and model are not sensitive; the
        # api_key is. Same posture as SessionCreds.
        if self.api_key is None:
            key_repr = "None"
        else:
            key_repr = "<redacted>"
        return (
            f"OperatorDefaultCreds(api_key={key_repr}, "
            f"base_url={self.base_url!r}, model={self.model!r})"
        )
