"""REST API for the LLM-config Test Connection probe (feature 006).

A single endpoint, ``POST /api/llm/test``, performs a real
``chat.completions.create`` call with ``max_tokens=1`` against the
caller-supplied credentials and returns whether the probe succeeded.
The credentials are used transiently to construct a one-shot
:class:`openai.OpenAI` client, then discarded — they are NOT persisted,
NOT placed in the per-WebSocket store, and NOT logged
(:class:`backend.llm_config.log_scrub.LLMKeyRedactionFilter` covers any
residual leakage paths).

Authorization: standard Keycloak JWT validation via the existing
:func:`orchestrator.auth.require_user_id` dependency. The endpoint
never accepts a ``user_id`` parameter — it always probes on behalf of
the authenticated caller alone (mirrors the per-user-isolation pattern
from feature 003).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from orchestrator.auth import get_current_user_payload, require_user_id

from .audit_events import record_llm_config_change

logger = logging.getLogger("LLMConfig.API")

llm_router = APIRouter(prefix="/api/llm", tags=["LLM"])

PROBE_TIMEOUT_SECONDS: float = 15.0


class TestConnectionRequest(BaseModel):
    """Body of ``POST /api/llm/test``.

    All three fields are required and non-empty.
    """
    api_key: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)

    @field_validator("base_url")
    @classmethod
    def _check_url_scheme(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("api_key", "model")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must be non-empty after trim")
        return v


class TestConnectionResponse(BaseModel):
    ok: bool
    model: str
    probed_at: str
    latency_ms: Optional[int] = None
    error_class: Optional[str] = None
    upstream_message: Optional[str] = None


def _classify_probe_error(exc: BaseException) -> str:
    """Map an OpenAI-SDK exception to a Test-Connection ``error_class``
    per contracts/rest-llm-test.md.
    """
    s = str(exc).lower()
    if "401" in s or "auth" in s or "api key" in s or "unauthor" in s:
        return "auth_failed"
    if "404" in s or ("model" in s and ("not" in s or "exist" in s)):
        return "model_not_found"
    if any(k in s for k in ("connection", "timeout", "network", "dns", "resolve")):
        return "transport_error"
    if "choices" in s or "schema" in s or "json" in s:
        return "contract_violation"
    return "other"


def _get_orchestrator(request: Request):
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        root_app = getattr(request.app, "_root_app", None) or request.app
        orch = getattr(root_app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orch


@llm_router.post(
    "/test",
    response_model=TestConnectionResponse,
    summary="Probe a prospective LLM configuration with a 1-token chat-completions request",
)
async def test_connection(
    body: TestConnectionRequest,
    request: Request,
    user_id: str = Depends(require_user_id),
    user_payload: dict = Depends(get_current_user_payload),
) -> TestConnectionResponse:
    """Issue a minimal ``chat.completions.create`` against the supplied
    credentials and report success/failure.

    Always returns HTTP 200 — ``ok=False`` indicates the probe ran but
    the upstream rejected it; HTTP 4xx/5xx is reserved for problems
    with THIS request itself (auth missing, body malformed).

    Audit: emits ``llm_config_change(action="tested")`` per request,
    regardless of outcome. The API key is NEVER recorded; only
    ``base_url``, ``model``, ``result``, and ``error_class``-on-failure.
    """
    orch = _get_orchestrator(request)
    auth_principal = (
        (user_payload or {}).get("preferred_username")
        or (user_payload or {}).get("sub")
        or user_id
    )

    probed_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    error_class: Optional[str] = None
    upstream_message: Optional[str] = None
    ok = False
    try:
        client = OpenAI(
            api_key=body.api_key,
            base_url=body.base_url,
            timeout=PROBE_TIMEOUT_SECONDS,
            max_retries=0,
        )
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=body.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        # Verify the contract: a chat-completions response has at least
        # one choice with a ``message`` object. If the upstream is not
        # actually OpenAI-compatible, this raises and we classify it as
        # a contract violation.
        if not getattr(response, "choices", None):
            raise ValueError("response missing 'choices' — not an OpenAI-compatible chat-completions endpoint")
        first = response.choices[0]
        if not getattr(first, "message", None):
            raise ValueError("response.choices[0] missing 'message' — not an OpenAI-compatible chat-completions endpoint")
        ok = True
    except Exception as exc:
        ok = False
        error_class = _classify_probe_error(exc)
        # Preserve the upstream message verbatim (FR-009). The log
        # scrubber catches any leaked key in the message.
        upstream_message = str(exc)[:1024]
        logger.info(
            "Test Connection failed: error_class=%s base_url=%s model=%s",
            error_class, body.base_url, body.model,
        )
    latency_ms = int((time.monotonic() - started) * 1000)

    # Audit: tested action, regardless of outcome.
    try:
        await record_llm_config_change(
            orch.audit_recorder,
            actor_user_id=user_id,
            auth_principal=auth_principal,
            action="tested",
            base_url=body.base_url,
            model=body.model,
            transport="rest",
            result="success" if ok else "failure",
            error_class=error_class if not ok else None,
        )
    except Exception as exc:  # pragma: no cover — audit is best-effort
        logger.warning(f"llm_config_change(tested) audit failed (non-fatal): {exc}")

    return TestConnectionResponse(
        ok=ok,
        model=body.model,
        probed_at=probed_at,
        latency_ms=latency_ms,
        error_class=error_class,
        upstream_message=upstream_message,
    )
