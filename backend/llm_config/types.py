"""Public types for the LLM-config module (feature 006-user-llm-config)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CredentialSource(str, Enum):
    """Which credential set served a given LLM-dependent call.

    Recorded on every ``llm_call`` audit event so operators can answer
    "for which users did the operator's account pay?" with a single
    audit-log query (SC-006). Inheriting from ``str`` makes the enum
    JSON-serializable in audit payloads without an explicit converter.
    """
    USER = "user"
    OPERATOR_DEFAULT = "operator_default"


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """The non-sensitive subset of a credential resolution.

    Returned alongside the OpenAI client by :func:`build_llm_client` so
    the caller can include ``base_url`` and ``model`` in audit-event
    payloads without re-reading the underlying ``SessionCreds`` /
    ``OperatorDefaultCreds`` objects (which would risk leaking
    ``api_key`` into surrounding code by accident).
    """
    base_url: str
    model: str


class LLMUnavailable(Exception):
    """Raised by :func:`build_llm_client` when neither the user's session
    credentials nor the operator's ``.env`` default credentials are
    complete.

    Callers in the orchestrator catch this and emit an
    ``llm_unconfigured`` audit event (FR-007), then surface the
    "LLM unavailable — set your own provider in settings" UI prompt
    to the originating user (FR-004a). NOT a programmer error: this
    is the documented fail-closed branch when both credential sources
    are missing.
    """
