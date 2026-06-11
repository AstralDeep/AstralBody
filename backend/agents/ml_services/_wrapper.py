#!/usr/bin/env python3
"""Shared external-service foundation for the ML Services agent.

Extracted from the three predecessor agents (classify, forecaster,
llm_factory), which carried byte-identical copies of:

- the ``requests``-tolerant retry-classification shim that used to live at the
  top of each ``mcp_server.py``;
- the ``_ui`` MCP response builder;
- the per-call HTTP client over :mod:`shared.external_http` (one credential
  pair per call, ``Bearer`` auth, URL normalization);
- the exception → credential-verdict and exception → user-facing-error
  mappings;
- defensive JSON parsing and metric-cell rendering helpers.

Each service is described by a :class:`CredentialBundle` (credential key
names + error-message labels), so the per-service tool modules stay thin.
All HTTP egress goes through ``shared.external_http`` exactly as in the
sources (SSRF/private-host gating, bounded responses).
"""
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared import external_http
from shared.external_http import (
    AuthFailedError,
    BadRequestError,
    EgressBlockedError,
    RateLimitedError,
    ServiceUnreachableError,
    normalize_url,
)

# ---------------------------------------------------------------------------
# Retry shim (formerly duplicated at classify/mcp_server.py:18-19 ==
# llm_factory/mcp_server.py:18-19 == forecaster/mcp_server.py:18-19)
# ---------------------------------------------------------------------------

RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError, json.JSONDecodeError, OSError)
try:
    import requests
    RETRYABLE_EXCEPTIONS = RETRYABLE_EXCEPTIONS + (requests.exceptions.RequestException,)
except ImportError:
    pass

NON_RETRYABLE_EXCEPTIONS = (TypeError, KeyError, ValueError, AttributeError)


def is_retryable_error(exc: Exception) -> bool:
    """Classify an exception as retryable or not for MCP error responses.

    Args:
        exc: The exception raised by a tool function.

    Returns:
        ``True`` when the exception is transient (connection/timeout/HTTP
        plumbing) or unknown, ``False`` for programming/input-shape errors
        (``TypeError``/``KeyError``/``ValueError``/``AttributeError``).
    """
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
        return False
    return True


# ---------------------------------------------------------------------------
# Credential bundles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CredentialBundle:
    """Describes one external service's credential pair and error labels.

    Attributes:
        service: Short label used in error strings (e.g. ``"CLASSify"``).
        display_name: Label used in the not-configured message (e.g.
            ``"Timeseries Forecaster"``).
        url_key: Credential key holding the service base URL.
        api_key_key: Credential key holding the Bearer API key.
        strip_v1_suffix: Strip a trailing ``/v1`` from the base URL (the
            LLM-Factory Router quirk — users paste OpenAI-style base URLs).
    """

    service: str
    display_name: str
    url_key: str
    api_key_key: str
    strip_v1_suffix: bool = False


CLASSIFY_BUNDLE = CredentialBundle(
    service="CLASSify",
    display_name="CLASSify",
    url_key="CLASSIFY_URL",
    api_key_key="CLASSIFY_API_KEY",
)

FORECASTER_BUNDLE = CredentialBundle(
    service="Forecaster",
    display_name="Timeseries Forecaster",
    url_key="FORECASTER_URL",
    api_key_key="FORECASTER_API_KEY",
)

LLM_FACTORY_BUNDLE = CredentialBundle(
    service="LLM-Factory",
    display_name="LLM-Factory",
    url_key="LLM_FACTORY_URL",
    api_key_key="LLM_FACTORY_API_KEY",
    strip_v1_suffix=True,
)


def bundle_configured(credentials: Dict[str, str], bundle: CredentialBundle) -> bool:
    """Report whether both of a bundle's credential keys are present and non-empty.

    Args:
        credentials: The decrypted per-user credential map for the agent.
        bundle: The service bundle to check.

    Returns:
        ``True`` when both the URL and API-key entries have non-empty values.
    """
    if not isinstance(credentials, dict):
        return False
    return bool(credentials.get(bundle.url_key)) and bool(credentials.get(bundle.api_key_key))


# ---------------------------------------------------------------------------
# HTTP client (per-call; credentials come from kwargs["_credentials"])
# ---------------------------------------------------------------------------


class ExternalServiceClient:
    """Per-call wrapper over ``shared.external_http`` scoped to one credential pair.

    Unifies the three predecessor clients (``ClassifyHttpClient``,
    ``ForecasterHttpClient``, ``LlmFactoryHttpClient``); the only behavioral
    difference between them — the LLM-Factory ``/v1`` base-URL suffix strip —
    is driven by :attr:`CredentialBundle.strip_v1_suffix`.
    """

    def __init__(self, credentials: Dict[str, str], bundle: CredentialBundle):
        """Build a client from a credential map and a service bundle.

        Args:
            credentials: Decrypted credential map (may be missing keys).
            bundle: The service bundle naming the keys and error labels.
        """
        self.bundle = bundle
        self.api_key = credentials.get(bundle.api_key_key, "")
        raw_url = credentials.get(bundle.url_key, "")
        base = normalize_url(raw_url) if raw_url else ""
        # Tolerate users who paste the OpenAI-style base URL (with /v1
        # suffix) — every LLM-Factory tool path already starts with /v1, so a
        # trailing /v1 on base_url would double-prefix into /v1/v1/models
        # and 404. Strip it.
        if bundle.strip_v1_suffix and base.endswith("/v1"):
            base = base[:-3]
        self.base_url = base

    def validate(self):
        """Raise ``ValueError`` with a settings hint when URL or key is missing."""
        if not self.base_url:
            raise ValueError(
                f"{self.bundle.service} Service URL is not configured. "
                "Open the agent's settings to add it."
            )
        if not self.api_key:
            raise ValueError(
                f"{self.bundle.service} API Key is not configured. "
                "Open the agent's settings to add it."
            )

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def get(self, path: str, params: Dict[str, Any] = None):
        """Issue an egress-gated GET against the service.

        Args:
            path: Path relative to the configured base URL.
            params: Optional query parameters.

        Returns:
            The ``requests.Response``-compatible object from ``external_http``.
        """
        return external_http.request("GET", self._url(path), api_key=self.api_key, params=params)

    def post(self, path: str, json_body: Any = None, files: Dict[str, Any] = None,
             data: Dict[str, Any] = None):
        """Issue an egress-gated POST against the service.

        Args:
            path: Path relative to the configured base URL.
            json_body: Optional JSON body.
            files: Optional multipart file map.
            data: Optional form-encoded body.

        Returns:
            The ``requests.Response``-compatible object from ``external_http``.
        """
        return external_http.request(
            "POST", self._url(path),
            api_key=self.api_key, json_body=json_body, files=files, data=data,
        )


def build_client(kwargs: Dict[str, Any], bundle: CredentialBundle) -> ExternalServiceClient:
    """Resolve per-call credentials from tool kwargs into a validated client.

    Args:
        kwargs: The tool call's ``**kwargs`` (carries ``_credentials`` and,
            when decryption failed upstream, ``_credentials_stale``).
        bundle: The service bundle to resolve.

    Returns:
        A validated :class:`ExternalServiceClient`.

    Raises:
        ValueError: When credentials are absent, stale, or incomplete.
    """
    credentials = kwargs.get("_credentials", {})
    if not credentials:
        if kwargs.get("_credentials_stale"):
            raise ValueError(
                f"Saved {bundle.display_name} credentials could not be decrypted "
                "(the agent's encryption key has changed since they were saved). "
                "Open the agent's settings and save your Service URL and API key again."
            )
        raise ValueError(
            f"{bundle.display_name} is not configured. "
            "Save your Service URL and API key in the agent's settings."
        )
    client = ExternalServiceClient(credentials, bundle)
    client.validate()
    return client


# ---------------------------------------------------------------------------
# Error → verdict / user-facing-string mapping (identical across the sources)
# ---------------------------------------------------------------------------


def verdict_for_exception(exc: Exception) -> Dict[str, str]:
    """Map an HTTP-egress exception to the standard credential-test verdict.

    Args:
        exc: The exception raised while probing the service.

    Returns:
        ``{"credential_test": <verdict>, "detail": <message>}`` where the
        verdict is ``auth_failed``, ``unreachable``, or ``unexpected``.
    """
    if isinstance(exc, AuthFailedError):
        return {"credential_test": "auth_failed", "detail": str(exc)}
    if isinstance(exc, (ServiceUnreachableError, EgressBlockedError, RateLimitedError)):
        return {"credential_test": "unreachable", "detail": str(exc)}
    return {"credential_test": "unexpected", "detail": str(exc)}


def user_facing_error(exc: Exception, service: str) -> str:
    """Map an HTTP-egress exception to the user-facing chat-rendered string.

    Args:
        exc: The exception raised by the upstream call.
        service: Short service label for the message (e.g. ``"CLASSify"``).

    Returns:
        A one-line actionable error message.
    """
    if isinstance(exc, AuthFailedError):
        return f"The saved {service} API key was rejected. Update it in the agent's settings."
    if isinstance(exc, ServiceUnreachableError):
        return f"{service} is unreachable. Try again later."
    if isinstance(exc, RateLimitedError):
        # Carries either a real 429 rate-limit or a 5xx server error; the
        # exception message already includes upstream status + body snippet.
        return f"{service} call failed: {exc}"
    if isinstance(exc, EgressBlockedError):
        return f"{service} URL is not allowed: {exc}"
    if isinstance(exc, BadRequestError):
        return f"{service} rejected the request: {exc}"
    return f"{service} call failed: {exc}"


# ---------------------------------------------------------------------------
# MCP response + rendering helpers (identical across the sources)
# ---------------------------------------------------------------------------


def ui(components, data=None, retryable: bool = True):
    """Build an MCP tool response with UI components + structured data.

    Args:
        components: astralprims primitives (or pre-serialized dicts).
        data: Structured ``_data`` payload returned alongside the UI.
        retryable: Whether the orchestrator should auto-retry on the error
            branch (only consulted when one of the UI components is a
            variant ``"error"`` Alert). Tools pass ``retryable=False`` after
            catching an upstream or input-shape error to stop the
            orchestrator from retrying calls that won't succeed fresh.

    Returns:
        The ``{"_ui_components": [...], "_data": ..., "_retryable": ...}``
        dict the MCP server unwraps into an ``MCPResponse``.
    """
    serialized = []
    for c in components:
        if hasattr(c, "to_json"):
            serialized.append(c.to_dict())
        else:
            serialized.append(c)
    return {"_ui_components": serialized, "_data": data, "_retryable": retryable}


def safe_json(resp) -> Dict[str, Any]:
    """Parse a JSON response defensively.

    Args:
        resp: A ``requests.Response``-compatible object.

    Returns:
        The parsed dict, or ``{}`` on any parse failure / non-dict payload.
    """
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def render_metric_value(value: Any) -> str:
    """Render a metric value as a tidy table cell.

    Args:
        value: A metric value of any JSON-ish type.

    Returns:
        A compact string (floats get 4 decimals below 1000, 4 sig-figs above).
    """
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        # Show 4 sig-figs-ish for typical 0-1 scores; full precision for big floats.
        return f"{value:.4f}" if abs(value) < 1000 else f"{value:.4g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(render_metric_value(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)
