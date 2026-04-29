"""User-Configurable LLM Subscription (feature 006-user-llm-config).

This module is the server-side counterpart to the per-device LLM-credentials
flow defined in specs/006-user-llm-config/. It provides:

* :class:`SessionCreds` and :class:`SessionCredentialStore` — per-WebSocket
  in-memory credentials. Never persisted server-side; cleared on disconnect.
* :class:`OperatorDefaultCreds` — the operator's ``.env``-supplied LLM
  credentials, used as the fallback for users who have not configured
  their own.
* :func:`build_llm_client` — pure factory that picks the user's session
  credentials when present, otherwise the operator default; raises
  :class:`LLMUnavailable` when neither is usable.
* Audit-event helpers that emit ``llm_config_change``, ``llm_unconfigured``,
  and ``llm_call`` events through the existing feature-003 audit recorder.
* A REST endpoint ``POST /api/llm/test`` that performs a real
  ``chat.completions.create(max_tokens=1)`` probe against a user's
  prospective configuration.
* WebSocket handlers for ``llm_config_set`` and ``llm_config_clear``.

The user's API key is held only in browser localStorage and in the
per-WebSocket :class:`SessionCredentialStore`. It is never written to a
database row, log line, or audit-event payload — see
:mod:`backend.llm_config.log_scrub` for the redaction enforcement.
"""

from .types import CredentialSource, LLMUnavailable, ResolvedConfig
from .session_creds import SessionCreds, SessionCredentialStore
from .operator_creds import OperatorDefaultCreds
from .client_factory import build_llm_client

__all__ = [
    "CredentialSource",
    "LLMUnavailable",
    "ResolvedConfig",
    "SessionCreds",
    "SessionCredentialStore",
    "OperatorDefaultCreds",
    "build_llm_client",
]
