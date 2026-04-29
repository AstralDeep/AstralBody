"""Pure factory that resolves a per-call LLM client from the available
credential sources (feature 006-user-llm-config).

Decision rule (research.md §R2 + spec FR-003 / FR-004 / FR-010):

1. If the user's :class:`SessionCreds` are present (i.e. all three fields
   non-empty), build the OpenAI client from them and tag the resolution
   as :attr:`CredentialSource.USER`.
2. Otherwise, if the operator's ``.env`` defaults are complete, build
   from those and tag as :attr:`CredentialSource.OPERATOR_DEFAULT`.
3. Otherwise, raise :class:`LLMUnavailable`. Callers handle this by
   emitting an ``llm_unconfigured`` audit event and surfacing the
   "LLM unavailable" UI prompt (FR-004a).

The factory is a pure function; it does not cache clients, so
:func:`backend.llm_config.session_creds.SessionCredentialStore.clear`
is observed on the very next call (FR-012).

NEVER falls back to the operator default WHEN the user had session
credentials present — even if the upstream call later fails. The
"upstream failed → bill operator" path is explicitly forbidden by
FR-009 and is enforced by the caller, not here.
"""
from __future__ import annotations

from typing import Optional, Tuple

from openai import OpenAI

from .operator_creds import OperatorDefaultCreds
from .session_creds import SessionCreds
from .types import CredentialSource, LLMUnavailable, ResolvedConfig


def build_llm_client(
    session_creds: Optional[SessionCreds],
    default_creds: OperatorDefaultCreds,
    *,
    timeout: Optional[float] = None,
) -> Tuple[OpenAI, CredentialSource, ResolvedConfig]:
    """Build an :class:`OpenAI` client from the appropriate credential set.

    Args:
        session_creds: The user's per-WebSocket credentials, or ``None``
            if the user has not configured personal credentials. A
            partially-filled ``SessionCreds`` cannot reach this function
            — :class:`SessionCredentialStore.set` rejects partials.
        default_creds: The operator's ``.env``-supplied default credentials.
            Always passed (never ``None``); use ``OperatorDefaultCreds(None, None, None)``
            to represent an absent default.
        timeout: Optional per-request timeout in seconds (passed to
            ``OpenAI(timeout=…)``).

    Returns:
        A 3-tuple ``(client, source, resolved)`` where:

        * ``client`` is the configured :class:`OpenAI` client to use for
          this call.
        * ``source`` indicates which credential set was used (audited as
          ``credential_source`` on the ``llm_call`` event).
        * ``resolved`` carries the non-sensitive ``base_url`` and ``model``
          for inclusion in audit-event payloads.

    Raises:
        LLMUnavailable: When neither the user's session credentials nor
            the operator default are complete.
    """
    if session_creds is not None:
        # SessionCredentialStore.set has already enforced that all three
        # fields are non-empty, so this branch is always usable.
        kwargs = {"api_key": session_creds.api_key, "base_url": session_creds.base_url}
        if timeout is not None:
            kwargs["timeout"] = timeout
        client = OpenAI(**kwargs)
        return (
            client,
            CredentialSource.USER,
            ResolvedConfig(base_url=session_creds.base_url, model=session_creds.model),
        )

    if default_creds.is_complete:
        kwargs = {"api_key": default_creds.api_key, "base_url": default_creds.base_url}
        if timeout is not None:
            kwargs["timeout"] = timeout
        client = OpenAI(**kwargs)
        # type-narrowed by is_complete check above
        assert default_creds.base_url is not None and default_creds.model is not None
        return (
            client,
            CredentialSource.OPERATOR_DEFAULT,
            ResolvedConfig(base_url=default_creds.base_url, model=default_creds.model),
        )

    raise LLMUnavailable(
        "No LLM credentials available: the user has not configured personal "
        "credentials and the operator's .env default credentials are not set."
    )
