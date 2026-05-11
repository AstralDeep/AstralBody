#!/usr/bin/env python3
"""MCP tools for the CLASSify Agent.

Exposes a curated set of tools that wrap the user-supplied CLASSify deployment
(see ``contracts/classify-tools.md`` and ``classify_api_docs.html``):

- ``submit_dataset``      — POST /reports/submit
- ``set_column_types``    — POST /reports/set-column-changes
- ``get_ml_options``      — GET  /reports/get-ml-opts
- ``start_training_job``  — POST /reports/start-training-job  (long-running)
- ``get_job_status``      — GET  /reports/get-job-status
- ``get_results``         — GET  /result/get-results
- ``get_output_log``      — GET  /result/get-output-log
- ``delete_dataset``      — POST /reports/delete
- ``_credentials_check``  — internal auth probe (GET /reports/get-ml-opts)

The training pipeline is intentionally split across multiple tools so the
chat LLM can converse with the user between steps (e.g. confirm the class
column, choose how to handle missing values, pick which models to train)
before kicking off the long-running job.
"""
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
from shared.primitives import Alert, Card, Table, Text


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

LONG_RUNNING_TOOLS: Set[str] = {"start_training_job"}


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


def _format_default_value(value: Any, max_length: int = 30) -> str:
    """Render a parameter default value as a compact, table-cell-friendly string."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (list, tuple)):
        text = ", ".join(str(v) for v in value)
    else:
        text = str(value)
    if len(text) > max_length:
        text = text[: max_length - 1] + "…"
    return text


def _format_models_list(models: Any, max_visible: int = 3) -> str:
    """Render a 'Applies to' cell, showing the first few entries + a count."""
    if not isinstance(models, (list, tuple)) or not models:
        return "—"
    visible = list(models)[:max_visible]
    rendered = ", ".join(str(m) for m in visible)
    if len(models) > max_visible:
        rendered += f", … and {len(models) - max_visible} more"
    return rendered


_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_path_segment(value: Optional[str], fallback: str) -> str:
    """Make a string safe to use as a single filesystem path segment."""
    if not value:
        return fallback
    cleaned = _SAFE_SEGMENT_RE.sub("_", str(value)).strip("._")
    return cleaned or fallback


def _save_debug_copy(local_path: str, filename: str,
                     user_id: Optional[str], session_id: Optional[str]) -> Optional[str]:
    """Save a copy of the CSV being sent to CLASSify under ``/tmp/<user>/<session>/``.

    Returns the saved path on success, or ``None`` if the copy could not be
    written for any reason — failures are logged but never propagated, so a
    debug-copy problem can't break the actual upload.
    """
    try:
        user_dir = _sanitize_path_segment(user_id, "unknown_user")
        session_dir = _sanitize_path_segment(session_id, "unknown_session")
        target_dir = Path("/tmp") / user_dir / session_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        shutil.copyfile(local_path, target)
        logger.info("CLASSify debug-copy written: %s", target)
        return str(target)
    except Exception as e:
        logger.warning("Failed to write CLASSify debug-copy: %s", e)
        return None


def _safe_json(resp) -> Dict[str, Any]:
    """Parse a JSON response defensively; return {} on any failure."""
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


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
        resp = client.get("/reports/get-ml-opts", params={"unsstate": 0})
        if resp.status_code == 200:
            return {"credential_test": "ok"}
        return {"credential_test": "unexpected", "detail": f"HTTP {resp.status_code}"}
    except ExternalHttpError as e:
        return _verdict_for_exception(e)


def submit_dataset(file_handle: str, **kwargs):
    """Upload a CSV dataset to CLASSify.

    Returns the upstream ``report_uuid`` plus the inferred column data types.
    The chat LLM uses the returned column types to converse with the user
    about which column is the class, which columns to drop, and how to
    handle missing values, before calling ``set_column_types``.
    """
    try:
        client = _build_client(kwargs)
        user_id = kwargs.get("user_id")
        if not user_id:
            raise ValueError("user_id is required to resolve attachments")
        local_path = resolve_attachment_path(file_handle, user_id)
        filename = os.path.basename(local_path)
        # Save a verbatim copy of what we're about to stream upstream so the
        # bytes that left our process can be inspected if CLASSify reports
        # corruption. Best-effort: never breaks the upload.
        debug_copy_path = _save_debug_copy(
            local_path, filename, user_id, kwargs.get("session_id"),
        )
        with open(local_path, "rb") as fh:
            resp = client.post(
                "/reports/submit",
                files={"file": (filename, fh, "text/csv")},
            )
        payload = _safe_json(resp)
        report_uuid = payload.get("report_uuid")
        column_types_block = payload.get("column_types") or {}
        column_types = column_types_block.get("data_types") if isinstance(column_types_block, dict) else {}
        if not isinstance(column_types, dict):
            column_types = {}
        header_text = (
            f"Report UUID: `{report_uuid}`\n\n"
            f"Detected **{len(column_types)} column(s)**:"
        )
        columns_table = Table(
            headers=["Column", "Detected type"],
            rows=[[col, dtype] for col, dtype in column_types.items()],
        )
        return _ui(
            [Card(
                title=f"Dataset uploaded: {filename}",
                content=[Text(content=header_text), columns_table],
            )],
            data={
                "report_uuid": report_uuid,
                "column_types": column_types,
                "filename": filename,
                "debug_copy_path": debug_copy_path,
            },
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def set_column_types(report_uuid: str, column_changes: List[Dict[str, Any]],
                     class_column: Optional[str] = None, **kwargs):
    """Apply column-type / missing-value / class-column choices to a submitted dataset.

    ``column_changes`` is a list of per-column dicts of the shape:
        {"column": "feature1", "data_type": "bool", "checked": True,
         "missing": None | "synthetic" | "constant", "fill_value": None,
         "class": True}   # optional, set on exactly one entry

    Called after ``submit_dataset`` once the user has confirmed how each
    column should be treated.
    """
    try:
        client = _build_client(kwargs)
        if not isinstance(column_changes, list):
            raise ValueError("column_changes must be a list of per-column dicts.")
        # Defensive: if the LLM passed class_column but didn't flag any entry,
        # mark the matching one.
        if class_column and not any(
            isinstance(c, dict) and c.get("class") is True for c in column_changes
        ):
            for entry in column_changes:
                if isinstance(entry, dict) and entry.get("column") == class_column:
                    entry["class"] = True
                    break
        resp = client.post(
            "/reports/set-column-changes",
            data={
                "report_uuid": report_uuid,
                "column_changes": json.dumps(column_changes),
            },
        )
        payload = _safe_json(resp)
        return _ui(
            [Card(
                title="Column types saved",
                content=[Text(content=(
                    f"Configured {len(column_changes)} column(s) for report {report_uuid}."
                ))],
            )],
            data={"report_uuid": report_uuid, "response": payload,
                  "column_changes": column_changes},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_ml_options(unsstate: int = 0, **kwargs):
    """List supported hyperparameter options for CLASSify training.

    ``unsstate`` is 0 for supervised learning (default) or 1 for unsupervised.
    The returned ``parameters`` dict can be shown to the user so they can
    pick which models to train and tweak hyperparameters before
    ``start_training_job``.
    """
    try:
        client = _build_client(kwargs)
        resp = client.get("/reports/get-ml-opts", params={"unsstate": int(unsstate)})
        payload = _safe_json(resp)
        parameters = payload.get("parameters") if isinstance(payload, dict) else None
        if not isinstance(parameters, dict) or not parameters:
            # Fallback: response didn't match the expected shape — show the raw JSON.
            return _ui(
                [Card(
                    title="CLASSify hyperparameter options",
                    content=[Text(content=json.dumps(payload, indent=2)[:4000])],
                )],
                data=payload,
            )

        header_parts = [f"**{len(parameters)} parameter(s) available** (unsstate={int(unsstate)})"]
        if isinstance(payload.get("message"), str) and payload["message"].strip():
            header_parts.append(payload["message"].strip())
        if payload.get("success") is False:
            header_parts.append("_Upstream reported success: false._")
        header = "\n\n".join(header_parts)

        rows = []
        for name, meta in parameters.items():
            if not isinstance(meta, dict):
                rows.append([name, "—", _format_default_value(meta), "—", ""])
                continue
            rows.append([
                name,
                str(meta.get("type", "")),
                _format_default_value(meta.get("default")),
                _format_models_list(meta.get("models")),
                str(meta.get("help", "")),
            ])
        params_table = Table(
            headers=["Parameter", "Type", "Default", "Applies to", "Description"],
            rows=rows,
        )
        return _ui(
            [Card(
                title="CLASSify hyperparameter options",
                content=[Text(content=header), params_table],
            )],
            data=payload,
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def _make_status_poll(client: "ClassifyHttpClient", report_uuid: str):
    """Build a sync callable that probes /reports/get-job-status for one job.

    Normalizes the upstream status string into the JobPoller's vocabulary:
        "Processed"           → succeeded (+ fetches /result/get-results)
        "Processing"          → in_progress
        "N/M Processed"       → in_progress with percentage = N/M
        anything else         → failed
    """
    def _poll():
        resp = client.get("/reports/get-job-status", params={"report_uuid": report_uuid})
        payload = _safe_json(resp)
        raw = (payload.get("status") or "").strip()
        if raw == "Processed":
            try:
                results_resp = client.get(
                    "/result/get-results", params={"report_uuid": report_uuid}
                )
                results = _safe_json(results_resp) or results_resp.text
            except Exception:
                results = None
            return {
                "status": "succeeded",
                "percentage": 100,
                "message": "Training complete.",
                "result": results,
            }
        if raw == "Processing":
            return {"status": "in_progress", "percentage": None, "message": raw}
        m = re.match(r"^(\d+)\s*/\s*(\d+)\s+Processed$", raw)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            percentage = int(done * 100 / total) if total else None
            return {"status": "in_progress", "percentage": percentage, "message": raw}
        return {
            "status": "failed",
            "percentage": None,
            "message": raw or "Unknown error",
            "result": None,
        }
    return _poll


def start_training_job(report_uuid: str, class_column: str,
                       options: Optional[List[Dict[str, Any]]] = None,
                       supervised: bool = True,
                       autodetermineclusters: bool = False, **kwargs):
    """Start a CLASSify training job and register the JobPoller.

    Returns immediately with the ``report_uuid`` and ``status: "started"``.
    The agent's :class:`JobPoller` posts ``tool_progress`` messages into the
    chat as the job runs and a terminal message with metrics on completion.

    ``options`` is a list of ``{"name": ..., "value": ...}`` pairs the LLM
    composes from the parameter set returned by ``get_ml_options`` (filtered
    to the user's chosen models / overridden hyperparameters). The four
    required entries (``report_uuid``, ``class_column``, ``supervised``,
    ``autodetermineclusters``) are appended here so the LLM doesn't have to
    remember them.
    """
    try:
        client = _build_client(kwargs)
        args: List[Dict[str, Any]] = []
        if options:
            if not isinstance(options, list):
                raise ValueError("options must be a list of {'name','value'} dicts.")
            args.extend(options)
        args.append({"name": "report_uuid", "value": report_uuid})
        args.append({"name": "class_column", "value": class_column})
        args.append({"name": "supervised", "value": bool(supervised)})
        args.append({"name": "autodetermineclusters", "value": bool(autodetermineclusters)})
        resp = client.post(
            "/reports/start-training-job",
            data={
                "report_uuid": report_uuid,
                "options": json.dumps(args),
            },
        )
        payload = _safe_json(resp)
        runtime = kwargs.get("_runtime")
        if runtime is not None:
            runtime.start_long_running_job(_make_status_poll(client, report_uuid))
        return _ui(
            [Card(
                title="CLASSify training started",
                content=[Text(content=(
                    f"Report UUID: {report_uuid}\n"
                    "Progress will be posted in this chat as the job runs."
                ))],
            )],
            data={
                "report_uuid": report_uuid,
                "status": "started",
                "class_column": class_column,
                "upstream_response": payload,
                "message": "Training started. Progress will appear here automatically.",
            },
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_job_status(report_uuid: str, **kwargs):
    """Synchronously probe the status of a CLASSify job by report_uuid."""
    try:
        client = _build_client(kwargs)
        poll = _make_status_poll(client, report_uuid)
        result = poll()
        return _ui(
            [Card(
                title=f"Job {report_uuid}",
                content=[Text(content=(
                    f"Status: {result['status']}\n"
                    f"Message: {result.get('message') or '(none)'}"
                    + (f"\nPercentage: {result['percentage']}%" if result.get("percentage") is not None else "")
                ))],
            )],
            data={"report_uuid": report_uuid, **result},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def _render_metric_value(value: Any) -> str:
    """Render a metric value as a tidy table cell."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        # Show 4 sig-figs-ish for typical 0-1 scores; full precision for big floats.
        return f"{value:.4f}" if abs(value) < 1000 else f"{value:.4g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_render_metric_value(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def get_results(report_uuid: str, **kwargs):
    """Fetch the final performance metrics for a completed CLASSify job.

    Shape-detected rendering:
      * ``{model: {metric: value, ...}, ...}``  → one row per model, columns = metric names
      * ``{metric: value, ...}`` (flat)         → two-column Metric | Value table
      * anything else (text, mixed nesting)     → fall back to a truncated JSON Text block
    """
    try:
        client = _build_client(kwargs)
        resp = client.get("/result/get-results", params={"report_uuid": report_uuid})
        payload = _safe_json(resp)
        data = {"report_uuid": report_uuid, "results": payload or (resp.text if resp.content else "")}

        if isinstance(payload, dict) and payload:
            if all(isinstance(v, dict) for v in payload.values()):
                # Per-model metrics shape.
                metric_keys: List[str] = []
                seen = set()
                for model_metrics in payload.values():
                    for k in model_metrics.keys():
                        if k not in seen:
                            seen.add(k)
                            metric_keys.append(k)
                metric_keys.sort()
                rows = [
                    [model] + [_render_metric_value(metrics.get(k)) for k in metric_keys]
                    for model, metrics in payload.items()
                ]
                table = Table(headers=["Model"] + metric_keys, rows=rows)
                return _ui(
                    [Card(
                        title=f"Results for {report_uuid}",
                        content=[
                            Text(content=f"**{len(payload)} model(s)**, **{len(metric_keys)} metric(s)**."),
                            table,
                        ],
                    )],
                    data=data,
                )
            if all(not isinstance(v, dict) for v in payload.values()):
                # Flat metrics shape.
                rows = [[k, _render_metric_value(v)] for k, v in payload.items()]
                table = Table(headers=["Metric", "Value"], rows=rows)
                return _ui(
                    [Card(
                        title=f"Results for {report_uuid}",
                        content=[table],
                    )],
                    data=data,
                )

        # Fallback: not a dict, mixed nesting, or non-JSON body.
        body = (
            json.dumps(payload, indent=2)[:4000]
            if payload
            else (resp.text[:4000] if resp.content else "(empty)")
        )
        return _ui(
            [Card(
                title=f"Results for {report_uuid}",
                content=[Text(content=body)],
            )],
            data=data,
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def get_output_log(report_uuid: str, **kwargs):
    """Fetch the output log for a CLASSify job (most useful when a job failed)."""
    try:
        client = _build_client(kwargs)
        resp = client.get("/result/get-output-log", params={"report_uuid": report_uuid})
        # Log is generally plain text; fall back to a JSON dump if it's not.
        text = resp.text if resp.content else ""
        if len(text) > 4000:
            text = text[:4000] + "\n… (truncated)"
        return _ui(
            [Card(
                title=f"Output log for {report_uuid}",
                content=[Text(content=text or "(empty)")],
            )],
            data={"report_uuid": report_uuid, "log": resp.text if resp.content else ""},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


def delete_dataset(report_uuid: str, **kwargs):
    """Delete a CLASSify dataset and all of its associated models / files."""
    try:
        client = _build_client(kwargs)
        resp = client.post("/reports/delete", data={"report_uuid": report_uuid})
        payload = _safe_json(resp)
        return _ui(
            [Card(
                title="Dataset deleted",
                content=[Text(content=f"Report {report_uuid} has been removed from CLASSify.")],
            )],
            data={"report_uuid": report_uuid, "response": payload},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")])


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


_COLUMN_CHANGE_ITEM_DESCRIPTION = (
    "Per-column config. Fields: 'column' (str, required), "
    "'data_type' (str: 'integer'|'float'|'bool'|'string', required), "
    "'checked' (bool, include in final dataset, required), "
    "'missing' (null|'synthetic'|'constant', how to handle missing cells), "
    "'fill_value' (any, used when missing='constant'), "
    "'class' (bool, set True on exactly one entry to mark the class column)."
)


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "_credentials_check": {
        "function": _credentials_check,
        "description": "Internal: probe the saved URL + API key with a cheap authenticated GET.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "scope": "tools:read",
    },
    "submit_dataset": {
        "function": submit_dataset,
        "description": (
            "Upload a CSV dataset to CLASSify. Returns a report_uuid and the inferred "
            "column data types. Use the returned types to converse with the user about "
            "which column is the class, which to drop, and how to fill missing values "
            "before calling set_column_types."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_handle": {
                    "type": "string",
                    "description": "Handle of a CSV uploaded via AstralBody's file mechanism.",
                },
            },
            "required": ["file_handle"],
        },
        "scope": "tools:write",
    },
    "set_column_types": {
        "function": set_column_types,
        "description": (
            "Apply per-column data-type, missing-value, and class-column choices to a "
            "submitted dataset. Call after the user has confirmed how each column should "
            "be handled. Use the column_types returned by submit_dataset as the source of "
            "names + default data types."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_uuid": {
                    "type": "string",
                    "description": "Report UUID returned by submit_dataset.",
                },
                "column_changes": {
                    "type": "array",
                    "description": "List of per-column config dicts. " + _COLUMN_CHANGE_ITEM_DESCRIPTION,
                    "items": {"type": "object"},
                },
                "class_column": {
                    "type": "string",
                    "description": (
                        "Optional. Name of the class column. If provided and no entry in "
                        "column_changes has 'class: true', the matching entry is flagged "
                        "automatically."
                    ),
                },
            },
            "required": ["report_uuid", "column_changes"],
        },
        "scope": "tools:write",
    },
    "get_ml_options": {
        "function": get_ml_options,
        "description": (
            "Return the parameters dict the user can override before training. "
            "unsstate=0 for supervised learning (default), 1 for unsupervised."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "unsstate": {
                    "type": "integer",
                    "description": "0 for supervised (default), 1 for unsupervised.",
                    "default": 0,
                },
            },
            "additionalProperties": False,
        },
        "scope": "tools:read",
    },
    "start_training_job": {
        "function": start_training_job,
        "description": (
            "Kick off CLASSify training on a previously-configured dataset. Returns the "
            "report_uuid immediately and posts progress + final results into the chat "
            "automatically as the job runs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_uuid": {"type": "string", "description": "Report UUID from submit_dataset."},
                "class_column": {"type": "string", "description": "Name of the class column."},
                "options": {
                    "type": "array",
                    "description": (
                        "List of {'name','value'} entries derived from get_ml_options. "
                        "Names should be the parameter keys returned by get_ml_options, "
                        "plus the model identifiers under 'train_group'."
                    ),
                    "items": {"type": "object"},
                },
                "supervised": {
                    "type": "boolean",
                    "description": "Default True. Set False for unsupervised clustering.",
                    "default": True,
                },
                "autodetermineclusters": {
                    "type": "boolean",
                    "description": "Only meaningful when supervised=False.",
                    "default": False,
                },
            },
            "required": ["report_uuid", "class_column"],
        },
        "scope": "tools:write",
    },
    "get_job_status": {
        "function": get_job_status,
        "description": (
            "Synchronously probe the status of a CLASSify job by report_uuid. The poller "
            "usually pushes updates automatically; use this only for explicit user "
            "'did my job finish?' queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"report_uuid": {"type": "string"}},
            "required": ["report_uuid"],
        },
        "scope": "tools:read",
    },
    "get_results": {
        "function": get_results,
        "description": "Fetch the final performance metrics for a completed CLASSify job.",
        "input_schema": {
            "type": "object",
            "properties": {"report_uuid": {"type": "string"}},
            "required": ["report_uuid"],
        },
        "scope": "tools:read",
    },
    "get_output_log": {
        "function": get_output_log,
        "description": "Fetch the output log for a CLASSify job (helpful when a job failed).",
        "input_schema": {
            "type": "object",
            "properties": {"report_uuid": {"type": "string"}},
            "required": ["report_uuid"],
        },
        "scope": "tools:read",
    },
    "delete_dataset": {
        "function": delete_dataset,
        "description": "Delete a CLASSify dataset and all of its associated models / files.",
        "input_schema": {
            "type": "object",
            "properties": {"report_uuid": {"type": "string"}},
            "required": ["report_uuid"],
        },
        "scope": "tools:write",
    },
}
