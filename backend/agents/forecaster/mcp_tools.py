#!/usr/bin/env python3
"""MCP tools for the Timeseries Forecaster Agent.

Curated tool set per ``contracts/forecaster-tools.md``:

- ``train_forecaster`` (long-running)
- ``generate_forecast`` (long-running)
- ``get_results_summary``
- ``get_recommendations``
- ``_credentials_check`` (internal probe)
"""
import logging
import os
import sys
from typing import Any, Dict, Set

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

logger = logging.getLogger("ForecasterAgentMCPTools")

AGENT_ID = "forecaster-1"

LONG_RUNNING_TOOLS: Set[str] = {"train_forecaster", "generate_forecast"}


def _ui(components, data=None):
    serialized = []
    for c in components:
        if hasattr(c, "to_json"):
            serialized.append(c.to_json())
        else:
            serialized.append(c)
    return {"_ui_components": serialized, "_data": data}


class ForecasterHttpClient:
    """Per-call wrapper over ``shared.external_http`` scoped to one credential pair."""

    def __init__(self, credentials: Dict[str, str]):
        self.api_key = credentials.get("FORECASTER_API_KEY", "")
        raw = credentials.get("FORECASTER_URL", "")
        self.base_url = normalize_url(raw) if raw else ""

    def validate(self):
        if not self.base_url:
            raise ValueError(
                "Forecaster Service URL is not configured. Open the agent's settings to add it."
            )
        if not self.api_key:
            raise ValueError(
                "Forecaster API Key is not configured. Open the agent's settings to add it."
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


def _build_client(kwargs: Dict[str, Any]) -> ForecasterHttpClient:
    credentials = kwargs.get("_credentials", {})
    if not credentials:
        raise ValueError(
            "Timeseries Forecaster is not configured. Save your Service URL and API key in the agent's settings."
        )
    client = ForecasterHttpClient(credentials)
    client.validate()
    return client


def _verdict_for_exception(exc: Exception) -> Dict[str, str]:
    if isinstance(exc, AuthFailedError):
        return {"credential_test": "auth_failed", "detail": str(exc)}
    if isinstance(exc, (ServiceUnreachableError, EgressBlockedError, RateLimitedError)):
        return {"credential_test": "unreachable", "detail": str(exc)}
    return {"credential_test": "unexpected", "detail": str(exc)}


def _user_facing_error(exc: Exception, service: str = "Forecaster") -> str:
    if isinstance(exc, AuthFailedError):
        return f"The saved {service} API key was rejected. Update it in the agent's settings."
    if isinstance(exc, ServiceUnreachableError):
        return f"{service} is unreachable. Try again later."
    if isinstance(exc, RateLimitedError):
        return f"{service} is rate-limiting requests or temporarily unavailable. Try again in a moment."
    if isinstance(exc, EgressBlockedError):
        return f"{service} URL is not allowed: {exc}"
    if isinstance(exc, BadRequestError):
        return f"{service} rejected the request: {exc}"
    return f"{service} call failed: {exc}"


def _credentials_check(**kwargs) -> Dict[str, Any]:
    """Cheap GET to confirm the saved Forecaster URL and API key work.

    Forecaster has no dedicated /health route; the lightest authenticated
    endpoint is /download-model with a sentinel parameter. A 200 or 404 (the
    sentinel model doesn't exist, but auth was accepted) both indicate
    credentials are good.
    """
    try:
        client = _build_client(kwargs)
    except ValueError as e:
        return {"credential_test": "unexpected", "detail": str(e)}
    try:
        client.get("/download-model", params={"probe": "true"})
        return {"credential_test": "ok"}
    except BadRequestError:
        # 4xx-non-auth: the route is reachable and authentication succeeded.
        return {"credential_test": "ok"}
    except ExternalHttpError as e:
        return _verdict_for_exception(e)


def _make_results_poll(client: "ForecasterHttpClient", user_uuid: str, dataset_name: str):
    """Build a sync callable that probes /generate-results-summary for terminality.

    Forecaster's app.py exposes results via S3-existence; the simplest cross-deployment
    probe is to call /generate-results-summary and treat any 200 as "succeeded".
    During training the endpoint typically returns 4xx (no results yet) which we map
    to "in_progress".
    """
    def _poll():
        try:
            resp = client.post(
                "/generate-results-summary",
                json_body={"user_uuid": user_uuid, "dataset_name": dataset_name},
            )
        except BadRequestError:
            return {"status": "in_progress", "message": "Job is still running."}
        try:
            payload = resp.json() if resp.content else {}
        except ValueError:
            payload = {}
        if isinstance(payload, dict) and payload.get("summary"):
            return {
                "status": "succeeded",
                "percentage": 100,
                "message": "Job complete.",
                "result": payload,
            }
        return {"status": "in_progress", "message": "Job is still running."}
    return _poll


def _upload_csv_to_forecaster(client: "ForecasterHttpClient", local_path: str,
                              user_uuid: str, dataset_name: str) -> None:
    """Upload a CSV to the Forecaster's parse-retrain endpoint."""
    with open(local_path, "rb") as fh:
        client.post(
            "/parse_retrain_file",
            files={"file": (os.path.basename(local_path), fh, "text/csv")},
            data={"user_uuid": user_uuid, "dataset_name": dataset_name},
        )


def train_forecaster(file_handle: str, dataset_name: str, parameters: Dict[str, Any] = None,
                     **kwargs):
    """Train forecasting models on a previously-uploaded CSV.

    Resolves ``file_handle`` to a local path, uploads it to the Forecaster
    service, then kicks off the training job. Returns immediately with the
    upstream task_id; the agent's :class:`JobPoller` pushes progress and
    final summary into the chat.
    """
    try:
        client = _build_client(kwargs)
        user_uuid = kwargs.get("user_id", "")
        if not user_uuid:
            raise ValueError("user_id is required to resolve attachments")
        local_path = resolve_attachment_path(file_handle, user_uuid)
        _upload_csv_to_forecaster(client, local_path, user_uuid, dataset_name)
        body = {
            "user_uuid": user_uuid,
            "dataset_name": dataset_name,
            "parameters": parameters or {},
        }
        resp = client.post("/train", json_body=body)
        payload = resp.json() if resp.content else {}
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        runtime = kwargs.get("_runtime")
        if runtime is not None and task_id:
            runtime.start_long_running_job(_make_results_poll(client, user_uuid, dataset_name))
        return _ui(
            [Card(
                title="Forecaster training started",
                content=[Text(content=f"Task ID: {task_id}\nDataset: {dataset_name}\nProgress will appear here automatically.")],
            )],
            data={"task_id": task_id, "dataset_name": dataset_name, "status": "started"},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def generate_forecast(dataset_name: str, parameters: Dict[str, Any] = None, **kwargs):
    """Start an N-step forecast against an already-trained dataset. Returns a task_id."""
    try:
        client = _build_client(kwargs)
        user_uuid = kwargs.get("user_id", "")
        body = {
            "user_uuid": user_uuid,
            "dataset_name": dataset_name,
            "parameters": parameters or {},
        }
        resp = client.post("/generate-new-forecasts", json_body=body)
        payload = resp.json() if resp.content else {}
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        runtime = kwargs.get("_runtime")
        if runtime is not None and task_id:
            runtime.start_long_running_job(_make_results_poll(client, user_uuid, dataset_name))
        return _ui(
            [Card(
                title="Forecast generation started",
                content=[Text(content=f"Task ID: {task_id}\nDataset: {dataset_name}\nProgress will appear here automatically.")],
            )],
            data={"task_id": task_id, "dataset_name": dataset_name, "status": "started"},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_results_summary(dataset_name: str, **kwargs):
    """Fetch the LLM-generated summary of a completed forecast run."""
    try:
        client = _build_client(kwargs)
        body = {"user_uuid": kwargs.get("user_id", ""), "dataset_name": dataset_name}
        resp = client.post("/generate-results-summary", json_body=body)
        payload = resp.json() if resp.content else {}
        summary = payload.get("summary", "") if isinstance(payload, dict) else str(payload)
        return _ui(
            [Card(title=f"Forecast results — {dataset_name}", content=[Text(content=summary or "(no summary)")])],
            data=payload,
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_recommendations(dataset_name: str, **kwargs):
    """Get model recommendations for an already-completed forecast run."""
    try:
        client = _build_client(kwargs)
        body = {"user_uuid": kwargs.get("user_id", ""), "dataset_name": dataset_name}
        resp = client.post("/generate-recommendations", json_body=body)
        payload = resp.json() if resp.content else {}
        recs = payload.get("recommendations", []) if isinstance(payload, dict) else []
        body_text = "\n".join(
            f"• {r.get('model', '?')}: {r.get('rationale', '')}"
            for r in recs if isinstance(r, dict)
        ) or "(no recommendations returned)"
        return _ui(
            [Card(title=f"Recommendations — {dataset_name}", content=[Text(content=body_text)])],
            data={"recommendations": recs},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "_credentials_check": {
        "function": _credentials_check,
        "description": "Internal: probe the saved URL + API key with a cheap authenticated GET.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "scope": "tools:read",
    },
    "train_forecaster": {
        "function": train_forecaster,
        "description": "Train forecasting models on an uploaded CSV. Returns a task_id immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_handle": {"type": "string", "description": "Handle of a CSV uploaded via AstralBody."},
                "dataset_name": {"type": "string", "description": "Name to register the dataset under."},
                "parameters": {"type": "object", "description": "Forecasting parameters: time column, value column, frequency, horizon, model selections."},
            },
            "required": ["file_handle", "dataset_name"],
        },
        "scope": "tools:write",
    },
    "generate_forecast": {
        "function": generate_forecast,
        "description": "Run an N-step forecast against an already-trained dataset. Returns a task_id immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string"},
                "parameters": {"type": "object", "description": "Forecast parameters: horizon, model selection, optional confidence levels."},
            },
            "required": ["dataset_name"],
        },
        "scope": "tools:write",
    },
    "get_results_summary": {
        "function": get_results_summary,
        "description": "Fetch the LLM-generated summary of a completed forecast run.",
        "input_schema": {
            "type": "object",
            "properties": {"dataset_name": {"type": "string"}},
            "required": ["dataset_name"],
        },
        "scope": "tools:read",
    },
    "get_recommendations": {
        "function": get_recommendations,
        "description": "Return model recommendations based on an already-completed forecast run.",
        "input_schema": {
            "type": "object",
            "properties": {"dataset_name": {"type": "string"}},
            "required": ["dataset_name"],
        },
        "scope": "tools:read",
    },
}
