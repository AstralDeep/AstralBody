"""Bring-your-own-LLM configuration (features 006-user-llm-config +
054-byo-llm-setup).

Feature 054 replaced 006's storage model: per-user LLM provider
configuration is now persisted server-side (``user_llm_config`` table, API
key Fernet-encrypted at rest under ``CREDENTIAL_ENCRYPTION_KEY``), and the
operator-default ``.env`` credential path was deleted outright. This module
provides:

* :class:`UserLLMConfigStore` / :class:`PersistedLLMConfig` — the persisted
  per-user + deployment-system credential store (``user_store``).
* :mod:`~llm_config.providers` — the server-owned provider preset catalog
  backing the first-run dialog's dropdown.
* :func:`build_llm_client` — pure factory that materializes an OpenAI
  client from the resolved record; raises :class:`LLMUnavailable` when the
  context has no configuration (the mandatory first-run gate for users;
  honest degradation for system work).
* Audit-event helpers (``llm_config_change`` / ``llm_unconfigured`` /
  ``llm_call``) through the existing feature-003 audit recorder.
* REST probes ``POST /api/llm/test`` and ``POST /api/llm/list-models``.
* WebSocket handlers for ``llm_config_set`` and ``llm_config_clear``.

The user's API key is decrypted only transiently for a call and never
appears in a log line, audit payload, or client-bound payload — see
:mod:`backend.llm_config.log_scrub` for the redaction enforcement.
"""

from .types import CredentialSource, LLMUnavailable, ResolvedConfig
from .client_factory import build_llm_client
from .user_store import PersistedLLMConfig, UserLLMConfigStore
from .providers import ProviderPreset, all_presets, get_preset, resolve_base_url

__all__ = [
    "CredentialSource",
    "LLMUnavailable",
    "ResolvedConfig",
    "build_llm_client",
    "PersistedLLMConfig",
    "UserLLMConfigStore",
    "ProviderPreset",
    "all_presets",
    "get_preset",
    "resolve_base_url",
]
