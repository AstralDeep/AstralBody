#!/usr/bin/env python3
"""MCP tools for the LLM-Factory Agent.

The agent wraps an :doc:`LLM-Factory Router <https://github.com/AstralDeep/LLM-Factory-Router-2>`
deployment — a pure OpenAI-compatible reverse proxy. Curated tool surface
per ``contracts/llm-factory-tools.md``:

- ``list_models``        — GET /v1/models
- ``chat_with_model``    — POST /v1/chat/completions (synchronous)
- ``create_embedding``   — POST /v1/embeddings
- ``transcribe_audio``   — POST /v1/audio/transcriptions (multipart)
- ``_credentials_check`` — internal probe (GET /v1/models)

All tools are synchronous; Router-2 exposes no long-running operations
suitable for chat use, so ``LONG_RUNNING_TOOLS`` is empty.
"""
import logging
import os
import sys
from typing import Any, Dict, List, Set, Union

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared import external_http
from shared.attachment_resolver import resolve_attachment_path
from shared.external_http import (
    AuthFailedError,
    BadRequestError,
    EgressBlockedError,
    ExternalHttpError,
    RateLimitedError,
    ServiceUnreachableError,
    normalize_url,
)
from shared.primitives import Alert, Card, Text

logger = logging.getLogger("LlmFactoryAgentMCPTools")

AGENT_ID = "llm-factory-1"

LONG_RUNNING_TOOLS: Set[str] = set()


def _ui(components, data=None, retryable: bool = True):
    """Build an MCP tool response with UI components + structured data.

    ``retryable`` controls whether the orchestrator should auto-retry on the
    error branch. Pass ``retryable=False`` after catching an upstream or
    input-shape error to stop the orchestrator from wasting attempts on
    calls that won't succeed on a fresh try.
    """
    serialized = []
    for c in components:
        if hasattr(c, "to_json"):
            serialized.append(c.to_json())
        else:
            serialized.append(c)
    return {"_ui_components": serialized, "_data": data, "_retryable": retryable}


class LlmFactoryHttpClient:
    """Per-call wrapper over ``shared.external_http`` scoped to one credential pair."""

    def __init__(self, credentials: Dict[str, str]):
        self.api_key = credentials.get("LLM_FACTORY_API_KEY", "")
        raw = credentials.get("LLM_FACTORY_URL", "")
        base = normalize_url(raw) if raw else ""
        # Tolerate users who paste the OpenAI-style base URL (with /v1
        # suffix) — every tool path here already starts with /v1, so a
        # trailing /v1 on base_url would double-prefix into /v1/v1/models
        # and 404. Strip it.
        if base.endswith("/v1"):
            base = base[:-3]
        self.base_url = base

    def validate(self):
        if not self.base_url:
            raise ValueError(
                "LLM-Factory Service URL is not configured. Open the agent's settings to add it."
            )
        if not self.api_key:
            raise ValueError(
                "LLM-Factory API Key is not configured. Open the agent's settings to add it."
            )

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def get(self, path: str, params: Dict[str, Any] = None):
        return external_http.request("GET", self._url(path), api_key=self.api_key, params=params)

    def post(self, path: str, json_body: Any = None, files: Dict[str, Any] = None,
             data: Dict[str, Any] = None):
        return external_http.request(
            "POST", self._url(path),
            api_key=self.api_key, json_body=json_body, files=files, data=data,
        )


def _build_client(kwargs: Dict[str, Any]) -> LlmFactoryHttpClient:
    credentials = kwargs.get("_credentials", {})
    if not credentials:
        if kwargs.get("_credentials_stale"):
            raise ValueError(
                "Saved LLM-Factory credentials could not be decrypted (the agent's "
                "encryption key has changed since they were saved). Open the agent's "
                "settings and save your Service URL and API key again."
            )
        raise ValueError(
            "LLM-Factory is not configured. Save your Service URL and API key in the agent's settings."
        )
    client = LlmFactoryHttpClient(credentials)
    client.validate()
    return client


def _verdict_for_exception(exc: Exception) -> Dict[str, str]:
    if isinstance(exc, AuthFailedError):
        return {"credential_test": "auth_failed", "detail": str(exc)}
    if isinstance(exc, (ServiceUnreachableError, EgressBlockedError, RateLimitedError)):
        return {"credential_test": "unreachable", "detail": str(exc)}
    return {"credential_test": "unexpected", "detail": str(exc)}


def _user_facing_error(exc: Exception, service: str = "LLM-Factory") -> str:
    if isinstance(exc, AuthFailedError):
        return f"The saved {service} API key was rejected. Update it in the agent's settings."
    if isinstance(exc, ServiceUnreachableError):
        return f"{service} is unreachable. Try again later."
    if isinstance(exc, RateLimitedError):
        # Carries either a real rate-limit (429) or a 5xx server error — the
        # exception message includes the upstream status and body snippet, so
        # surface it verbatim instead of the legacy "rate-limiting" wording
        # that misled the LLM into endless retries.
        return f"{service} call failed: {exc}"
    if isinstance(exc, EgressBlockedError):
        return f"{service} URL is not allowed: {exc}"
    if isinstance(exc, BadRequestError):
        return f"{service} rejected the request: {exc}"
    return f"{service} call failed: {exc}"


def _credentials_check(**kwargs) -> Dict[str, Any]:
    """Probe ``GET /v1/models`` — Router-2 always serves this when auth is valid."""
    try:
        client = _build_client(kwargs)
    except ValueError as e:
        return {"credential_test": "unexpected", "detail": str(e)}
    try:
        resp = client.get("/v1/models")
        if resp.status_code == 200:
            return {"credential_test": "ok"}
        return {"credential_test": "unexpected", "detail": f"HTTP {resp.status_code}"}
    except ExternalHttpError as e:
        return _verdict_for_exception(e)


def list_models(**kwargs):
    """List models served by the user's LLM-Factory Router deployment.

    Surfaces the richer Router-2 fields (``id``, ``owned_by``,
    ``max_model_len``) when the upstream provides them.
    """
    try:
        client = _build_client(kwargs)
        resp = client.get("/v1/models")
        payload = resp.json() if resp.content else {}
        models = payload.get("data", []) if isinstance(payload, dict) else []
        lines = []
        for m in models:
            if not isinstance(m, dict):
                continue
            pieces = [m.get("id") or m.get("name") or "?"]
            if m.get("owned_by"):
                pieces.append(f"({m['owned_by']})")
            if m.get("max_model_len"):
                pieces.append(f"context={m['max_model_len']}")
            lines.append("• " + " ".join(pieces))
        body = "\n".join(lines) or "(no models registered)"
        return _ui(
            [Card(title="LLM-Factory models", content=[Text(content=body)])],
            data={"models": models},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def chat_with_model(model_id: str, messages: List[Dict[str, str]],
                    options: Dict[str, Any] = None, **kwargs):
    """Send a synchronous chat completion to the user's chosen Router-2 model."""
    try:
        client = _build_client(kwargs)
        body = {
            "model": model_id,
            "messages": messages,
        }
        if options:
            body.update(options)
        resp = client.post("/v1/chat/completions", json_body=body)
        payload = resp.json() if resp.content else {}
        choices = payload.get("choices", []) if isinstance(payload, dict) else []
        content = ""
        if choices and isinstance(choices[0], dict):
            content = (choices[0].get("message", {}) or {}).get("content", "") or ""
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        return _ui(
            [Card(title=f"Reply from {model_id}", content=[Text(content=content or "(empty reply)")])],
            data={"content": content, "model_id": model_id, "usage": usage},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def create_embedding(model_id: str, input: Union[str, List[str]], **kwargs):
    """Compute embeddings for ``input`` using the named model.

    Mirrors the OpenAI ``/v1/embeddings`` shape: pass a single string or a
    list of strings, get back a list of vectors plus the upstream usage.
    """
    try:
        client = _build_client(kwargs)
        if input is None or (isinstance(input, str) and not input.strip()):
            raise ValueError("'input' is required and must not be empty.")
        body = {"model": model_id, "input": input}
        resp = client.post("/v1/embeddings", json_body=body)
        payload = resp.json() if resp.content else {}
        data = payload.get("data", []) if isinstance(payload, dict) else []
        embeddings = [d.get("embedding") for d in data if isinstance(d, dict)]
        dim = len(embeddings[0]) if embeddings and isinstance(embeddings[0], list) else 0
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        summary = (
            f"Model: {model_id}\n"
            f"Vectors: {len(embeddings)}\n"
            f"Dimension: {dim}"
        )
        return _ui(
            [Card(title="Embeddings created", content=[Text(content=summary)])],
            data={
                "embeddings": embeddings,
                "model_id": model_id,
                "usage": usage,
                "dimension": dim,
                "count": len(embeddings),
            },
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def transcribe_audio(model_id: str, file_handle: str,
                     language: str = None, **kwargs):
    """Transcribe an uploaded audio file using the named transcription model.

    Resolves ``file_handle`` to a real on-disk path via the AstralBody
    attachments helper (per-user ownership enforced) and submits the file
    as ``multipart/form-data`` to ``/v1/audio/transcriptions``.
    """
    try:
        client = _build_client(kwargs)
        user_id = kwargs.get("user_id")
        if not user_id:
            raise ValueError("user_id is required to resolve attachments")
        local_path = resolve_attachment_path(file_handle, user_id)
        form = {"model": model_id}
        if language:
            form["language"] = language
        with open(local_path, "rb") as fh:
            files = {"file": (os.path.basename(local_path), fh, "application/octet-stream")}
            resp = client.post(
                "/v1/audio/transcriptions",
                files=files,
                data=form,
            )
        payload = resp.json() if resp.content else {}
        text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
        return _ui(
            [Card(title=f"Transcription from {model_id}",
                  content=[Text(content=text or "(empty transcription)")])],
            data={"text": text, "model_id": model_id, "filename": os.path.basename(local_path)},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "_credentials_check": {
        "function": _credentials_check,
        "description": "Internal: probe the saved URL + API key with a cheap authenticated GET.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "scope": "tools:read",
    },
    "list_models": {
        "function": list_models,
        "description": "List models served by your LLM-Factory Router deployment.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "scope": "tools:read",
    },
    "chat_with_model": {
        "function": chat_with_model,
        "description": "Send a synchronous chat completion to a chosen LLM-Factory Router model (OpenAI-compatible).",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Identifier of a model served by the Router."},
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                },
                "options": {"type": "object", "description": "OpenAI-compatible parameters: temperature, max_tokens, etc."},
            },
            "required": ["model_id", "messages"],
        },
        "scope": "tools:write",
    },
    "create_embedding": {
        "function": create_embedding,
        "description": "Compute embedding vectors for a string or list of strings using a chosen model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Identifier of an embedding-capable model."},
                "input": {
                    "description": "Either a single string or a list of strings to embed.",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["model_id", "input"],
        },
        "scope": "tools:write",
    },
    "transcribe_audio": {
        "function": transcribe_audio,
        "description": "Transcribe an uploaded audio file (multipart) using a chosen transcription model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Identifier of a transcription-capable model (e.g. whisper-1)."},
                "file_handle": {"type": "string", "description": "AstralBody attachment_id of the audio file."},
                "language": {"type": "string", "description": "Optional ISO-639-1 language hint (e.g. 'en')."},
            },
            "required": ["model_id", "file_handle"],
        },
        "scope": "tools:write",
    },
}
