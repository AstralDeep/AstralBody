#!/usr/bin/env python3
"""MCP tools for the CLASSify Agent.

Exposes a curated set of tools that wrap the user-supplied CLASSify deployment
(see ``contracts/classify-tools.md`` in this feature's spec directory):

- ``train_classifier`` (long-running)
- ``retest_model`` (long-running)
- ``get_training_status``
- ``get_class_column_values``
- ``get_ml_options``
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


def _ui(components, data=None):
    """Build an MCP tool response with UI components + structured data."""
    serialized = []
    for c in components:
        if hasattr(c, "to_json"):
            serialized.append(c.to_json())
        else:
            serialized.append(c)
    return {"_ui_components": serialized, "_data": data}

logger = logging.getLogger("ClassifyAgentMCPTools")

AGENT_ID = "classify-1"

LONG_RUNNING_TOOLS: Set[str] = {"train_classifier", "retest_model"}


# ---------------------------------------------------------------------------
# HTTP client (per-call; credentials come from kwargs["_credentials"])
# ---------------------------------------------------------------------------


class ClassifyHttpClient:
    """Thin wrapper over ``shared.external_http`` scoped to one set of credentials."""

    def __init__(self, credentials: Dict[str, str]):
        self.api_key = credentials.get("CLASSIFY_API_KEY", "")
        raw_url = credentials.get("CLASSIFY_URL", "")
        self.base_url = normalize_url(raw_url) if raw_url else ""

    def validate(self):
        if not self.base_url:
            raise ValueError(
                "CLASSify Service URL is not configured. Open the agent's settings to add it."
            )
        if not self.api_key:
            raise ValueError(
                "CLASSify API Key is not configured. Open the agent's settings to add it."
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


def _build_client(kwargs: Dict[str, Any]) -> ClassifyHttpClient:
    credentials = kwargs.get("_credentials", {})
    if not credentials:
        raise ValueError(
            "CLASSify is not configured. Save your Service URL and API key in the agent's settings."
        )
    client = ClassifyHttpClient(credentials)
    client.validate()
    return client


def _verdict_for_exception(exc: Exception) -> Dict[str, str]:
    """Map an HTTP-egress exception to the standard credential-test verdict."""
    if isinstance(exc, AuthFailedError):
        return {"credential_test": "auth_failed", "detail": str(exc)}
    if isinstance(exc, (ServiceUnreachableError, EgressBlockedError, RateLimitedError)):
        return {"credential_test": "unreachable", "detail": str(exc)}
    return {"credential_test": "unexpected", "detail": str(exc)}


def _user_facing_error(exc: Exception, service: str = "CLASSify") -> str:
    """Map an HTTP-egress exception to the user-facing chat-rendered string."""
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


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _credentials_check(**kwargs) -> Dict[str, Any]:
    """Cheap GET to confirm the saved URL and API key work."""
    try:
        client = _build_client(kwargs)
    except ValueError as e:
        return {"credential_test": "unexpected", "detail": str(e)}
    try:
        resp = client.get("/get-ml-options")
        if resp.status_code == 200:
            return {"credential_test": "ok"}
        return {"credential_test": "unexpected", "detail": f"HTTP {resp.status_code}"}
    except ExternalHttpError as e:
        return _verdict_for_exception(e)


def get_ml_options(**kwargs):
    """List supported hyperparameter options for CLASSify training."""
    try:
        client = _build_client(kwargs)
        resp = client.get("/get-ml-options")
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text[:1000]}
        return _ui(
            [Card(title="CLASSify hyperparameter options", content=[Text(content=str(payload))])],
            data=payload,
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_class_column_values(filename: str, class_column: str, **kwargs):
    """List distinct values found in a class column of a previously-uploaded dataset."""
    try:
        client = _build_client(kwargs)
        resp = client.post(
            "/get_class_column_values",
            json_body={"filename": filename, "class_column": class_column},
        )
        payload = resp.json() if resp.content else {}
        values = payload.get("values", []) if isinstance(payload, dict) else []
        return _ui(
            [Card(
                title=f"Distinct values in '{class_column}' ({filename})",
                content=[Text(content=", ".join(map(str, values)) or "(no values returned)")],
            )],
            data={"values": values, "count": len(values)},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_training_status(task_id: str, **kwargs):
    """Probe the upstream service for a single training task's status."""
    try:
        client = _build_client(kwargs)
        resp = client.get("/get_training_status", params={"task_id": task_id})
        payload = resp.json() if resp.content else {}
        status = payload.get("status", "unknown") if isinstance(payload, dict) else "unknown"
        percentage = payload.get("percentage") if isinstance(payload, dict) else None
        return _ui(
            [Card(title=f"Job {task_id}", content=[Text(content=f"Status: {status}")])],
            data={"task_id": task_id, "status": status, "percentage": percentage,
                  "message": payload.get("message", "") if isinstance(payload, dict) else ""},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def _make_status_poll(client: "ClassifyHttpClient", task_id: str):
    """Build a sync callable that probes /get_training_status for a single task."""
    def _poll():
        resp = client.get("/get_training_status", params={"task_id": task_id})
        try:
            payload = resp.json() if resp.content else {}
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        # Normalize upstream status into the JobPoller's expected vocabulary.
        upstream_status = (payload.get("status") or "").lower()
        if upstream_status in ("completed", "complete", "done", "success", "succeeded"):
            status = "succeeded"
        elif upstream_status in ("failed", "error"):
            status = "failed"
        elif upstream_status in ("started", "queued", "pending"):
            status = "started"
        else:
            status = "in_progress"
        return {
            "status": status,
            "percentage": payload.get("percentage"),
            "message": payload.get("message", "") or f"Job {task_id}: {upstream_status or 'in progress'}",
            "result": payload.get("result"),
        }
    return _poll


def _upload_csv_to_classify(client: "ClassifyHttpClient", local_path: str,
                            class_column: str = None) -> str:
    """Upload a CSV via multipart/form-data and return the upstream filename."""
    filename = os.path.basename(local_path)
    with open(local_path, "rb") as fh:
        data = {}
        if class_column:
            data["class_column"] = class_column
        resp = client.post(
            "/upload_testset",
            files={"file": (filename, fh, "text/csv")},
            data=data,
        )
    payload = resp.json() if resp.content else {}
    upstream_name = payload.get("filename") if isinstance(payload, dict) else None
    return upstream_name or filename


def train_classifier(file_handle: str, class_column: str, options: Dict[str, Any] = None,
                     **kwargs):
    """Train a CLASSify Random Forest classifier on a previously-uploaded CSV.

    Resolves ``file_handle`` (an AstralBody attachment_id) to a local path,
    uploads the CSV to CLASSify, then kicks off training. Returns
    immediately with the upstream task_id; the agent's :class:`JobPoller`
    pushes progress + final result into the chat as the job runs.
    """
    try:
        client = _build_client(kwargs)
        user_id = kwargs.get("user_id")
        if not user_id:
            raise ValueError("user_id is required to resolve attachments")
        local_path = resolve_attachment_path(file_handle, user_id)
        upstream_name = _upload_csv_to_classify(client, local_path, class_column)
        body = {
            "file_directory": upstream_name,
            "class_column": class_column,
            "options": options or {},
        }
        resp = client.post("/train", json_body=body)
        payload = resp.json() if resp.content else {}
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        runtime = kwargs.get("_runtime")
        if runtime is not None and task_id:
            runtime.start_long_running_job(_make_status_poll(client, task_id))
        return _ui(
            [Card(
                title="CLASSify training started",
                content=[Text(content=f"Task ID: {task_id}\nProgress will be posted in this chat as the job runs.")],
            )],
            data={"task_id": task_id, "status": "started", "filename": upstream_name,
                  "message": "Training started. Progress will appear here automatically."},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def retest_model(file_handle: str, model_id: str, **kwargs):
    """Re-evaluate a trained classifier on a new test CSV."""
    try:
        client = _build_client(kwargs)
        user_id = kwargs.get("user_id")
        if not user_id:
            raise ValueError("user_id is required to resolve attachments")
        local_path = resolve_attachment_path(file_handle, user_id)
        upstream_name = _upload_csv_to_classify(client, local_path)
        body = {"file_directory": upstream_name, "model_id": model_id}
        resp = client.post("/retest_model", json_body=body)
        payload = resp.json() if resp.content else {}
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        runtime = kwargs.get("_runtime")
        if runtime is not None and task_id:
            runtime.start_long_running_job(_make_status_poll(client, task_id))
        return _ui(
            [Card(
                title="CLASSify retest started",
                content=[Text(content=f"Task ID: {task_id}\nProgress will be posted in this chat as the job runs.")],
            )],
            data={"task_id": task_id, "status": "started", "filename": upstream_name,
                  "message": "Retest started. Progress will appear here automatically."},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "_credentials_check": {
        "function": _credentials_check,
        "description": "Internal: probe the saved URL + API key with a cheap authenticated GET.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "scope": "tools:read",
    },
    "get_ml_options": {
        "function": get_ml_options,
        "description": "List supported hyperparameter options for CLASSify training.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "scope": "tools:read",
    },
    "get_class_column_values": {
        "function": get_class_column_values,
        "description": "List the distinct values present in a class column of a previously-uploaded CSV.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename of the previously-uploaded dataset."},
                "class_column": {"type": "string", "description": "Name of the class column to inspect."},
            },
            "required": ["filename", "class_column"],
        },
        "scope": "tools:read",
    },
    "get_training_status": {
        "function": get_training_status,
        "description": "Synchronously probe the status of a CLASSify training task by task_id.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        "scope": "tools:read",
    },
    "train_classifier": {
        "function": train_classifier,
        "description": "Start a CLASSify Random Forest training run on an uploaded CSV. Returns a task_id immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_handle": {"type": "string", "description": "Handle of a CSV uploaded via AstralBody."},
                "class_column": {"type": "string", "description": "Name of the column to classify on."},
                "options": {"type": "object", "description": "Hyperparameter overrides; see get_ml_options."},
            },
            "required": ["file_handle", "class_column"],
        },
        "scope": "tools:write",
    },
    "retest_model": {
        "function": retest_model,
        "description": "Re-evaluate a previously-trained classifier on a new test CSV. Returns a task_id immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_handle": {"type": "string"},
                "model_id": {"type": "string", "description": "Identifier of the trained model."},
            },
            "required": ["file_handle", "model_id"],
        },
        "scope": "tools:write",
    },
}
