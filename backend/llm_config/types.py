"""Public types for the LLM-config module (feature 006-user-llm-config)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CredentialSource(str, Enum):
    """Which credential set served a given LLM-dependent call.

    Recorded on every ``llm_call`` audit event. Inheriting from ``str``
    makes the enum JSON-serializable in audit payloads without an explicit
    converter.

    Feature 054: ``SYSTEM`` (the admin-managed deployment credential for
    system-context calls) replaces the retired ``OPERATOR_DEFAULT`` for
    all NEW events. The ``OPERATOR_DEFAULT`` member is retained solely so
    historical audit rows keep a meaningful decode; no new event may carry
    it.
    """
    USER = "user"
    SYSTEM = "system"
    OPERATOR_DEFAULT = "operator_default"  # retired — historical rows only


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
    """Raised by :func:`build_llm_client` when the resolved credential
    record is absent.

    Feature 054: for a user-context call this means the user has not
    completed provider setup — callers emit ``llm_unconfigured`` and the
    mandatory first-run gate applies. For a system-context call it means
    the admin has not configured the deployment's system credential —
    background features degrade gracefully with honest failure reporting.
    NOT a programmer error: this is the documented fail-closed branch.
    """
