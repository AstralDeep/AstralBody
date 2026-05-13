#!/usr/bin/env python3
"""MCP tools for the Timeseries Forecaster Agent.

Wraps the user-supplied Forecaster deployment (e.g. ``forecaster.ai.uky.edu``)
following its documented API contract (see ``forecaster-api-docs.md``):

- ``submit_dataset``     — POST /dataset/submit               (returns uuid + columns)
- ``set_column_roles``   — POST /dataset/save-columns         (maps columns to one of 7 roles)
- ``start_training_job`` — POST /dataset/start-training-job   (LONG-RUNNING)
- ``get_job_status``     — GET  /dataset/get-job-status       (sync status probe)
- ``get_results``        — GET  /results/get-metrics          (metrics + output_log)
- ``delete_dataset``     — POST /dataset/delete               (cleanup)
- ``_credentials_check`` — GET  /dataset/get-job-status?uuid=probe-credentials-check
                            (internal auth probe; 401/403 → auth_failed, anything else → ok)

The training pipeline is split into three steps (submit → set-roles → start)
so the chat LLM can converse with the user between steps (e.g. confirm which
column is the time component, which is the target, which are covariates)
before kicking off the long-running training job.
"""
import json
import logging
import os
import sys
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

logger = logging.getLogger("ForecasterAgentMCPTools")

AGENT_ID = "forecaster-1"

LONG_RUNNING_TOOLS: Set[str] = {"start_training_job"}

# Roles the Forecaster service requires for column categorization (see
# forecaster-api-docs.md). Any column not assigned to one of these falls into
# `not-included` by default.
COLUMN_ROLES: List[str] = [
    "not-included",
    "time-component",
    "grouping",
    "target",
    "past-covariates",
    "future-covariates",
    "static-covariates",
]

# Documented defaults from forecaster-api-docs.md. The agent sends *only* the
# caller's overrides (sparse dict); the upstream uses its own defaults for any
# key not present. This dict is here for documentation + as a fallback so the
# LLM/UI can show users what the defaults are if they ask.
DEFAULT_TRAINING_OPTIONS: Dict[str, Any] = {
    "test-size": 0.2,
    "expanding-window": False,
    "expanding-window-forecast-horizon": 6,
    "expanding-window-stride": 6,
    "visualize": True,
    "generate-real-predictions": False,
    "real-prediction-length": 12,
    "fill-future-covariates": False,
    "probabilistic": False,
    "probabilistic-likelihood": "quantile",
    "probabilistic-num-samples": 100,
    "models": [
        "arima", "exponential-smoothing", "linear-regression", "xgboost",
        "random-forest", "lgbm", "nlinear", "tft",
    ],
    "arima-p": 12,
    "arima-d": 1,
    "arima-q": 6,
    "lags": 12,
    "lags-future": 0,
    "output-chunk-length": 6,
    "epochs": 10,
}


def _ui(components, data=None, retryable: bool = True):
    """Build an MCP tool response with UI components + structured data.

    ``retryable`` controls whether the orchestrator should auto-retry on the
    error branch (only consulted when one of the UI components is a variant
    "error" Alert). Tools pass ``retryable=False`` after catching an upstream
    or input-shape error to stop the orchestrator from retrying calls that
    won't succeed on a fresh attempt.
    """
    serialized = []
    for c in components:
        if hasattr(c, "to_json"):
            serialized.append(c.to_json())
        else:
            serialized.append(c)
    return {"_ui_components": serialized, "_data": data, "_retryable": retryable}


# ---------------------------------------------------------------------------
# HTTP client (per-call; credentials come from kwargs["_credentials"])
# ---------------------------------------------------------------------------


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
        # Carries either a real 429 rate-limit or a 5xx server error; the
        # exception message already includes upstream status + body snippet.
        return f"{service} call failed: {exc}"
    if isinstance(exc, EgressBlockedError):
        return f"{service} URL is not allowed: {exc}"
    if isinstance(exc, BadRequestError):
        return f"{service} rejected the request: {exc}"
    return f"{service} call failed: {exc}"


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
    """Cheap GET to confirm the saved Forecaster URL and API key work.

    Calls ``GET /dataset/get-job-status`` with **no parameters**. The live
    forecaster.ai.uky.edu service returns 200 with ``{success: false,
    "message": "A UUID must be provded"}`` in that case — authentication has
    already been verified by then (a bogus key returns 401 before any body
    handling). Sending no uuid avoids the upstream's "500 on bad uuid lookup"
    bug exhibited when you pass a sentinel uuid.
    """
    try:
        client = _build_client(kwargs)
    except ValueError as e:
        return {"credential_test": "unexpected", "detail": str(e)}
    try:
        client.get("/dataset/get-job-status")
        return {"credential_test": "ok"}
    except BadRequestError:
        # 4xx-non-auth: route is reachable, auth was accepted.
        return {"credential_test": "ok"}
    except ExternalHttpError as e:
        return _verdict_for_exception(e)


def submit_dataset(file_handle: str, **kwargs):
    """Upload a CSV dataset to the Forecaster service.

    Returns the upstream ``uuid`` plus the list of column names. The chat
    LLM uses the returned columns to converse with the user about which
    column is the time component, which is the target, and which (if any)
    are past/future/static covariates before calling ``set_column_roles``.
    """
    try:
        client = _build_client(kwargs)
        user_id = kwargs.get("user_id")
        if not user_id:
            raise ValueError("user_id is required to resolve attachments.")
        local_path = resolve_attachment_path(file_handle, user_id)
        filename = os.path.basename(local_path)
        with open(local_path, "rb") as fh:
            resp = client.post(
                "/dataset/submit",
                files={"file": (filename, fh, "text/csv")},
            )
        payload = _safe_json(resp)
        uuid = payload.get("uuid")
        columns = payload.get("columns") or []
        if not isinstance(columns, list):
            columns = []
        header = (
            f"Dataset UUID: `{uuid}`\n\n"
            f"Detected **{len(columns)} column(s)**. Next, call "
            "`set_column_roles` to map each column to a role "
            "(time-component, target, past-covariates, etc.)."
        )
        columns_table = Table(
            headers=["#", "Column"],
            rows=[[str(i + 1), col] for i, col in enumerate(columns)],
        )
        return _ui(
            [Card(
                title=f"Dataset uploaded: {filename}",
                content=[Text(content=header), columns_table],
            )],
            data={
                "uuid": uuid,
                "columns": columns,
                "filename": filename,
                "allowed_roles": COLUMN_ROLES,
            },
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def _build_categorized_string(column_roles: Dict[str, str]) -> Dict[str, List[str]]:
    """Convert ``{column_name: role}`` to the role-keyed shape Forecaster wants.

    The upstream API expects ``categorizedString`` as a JSON-encoded dict keyed
    by role, with each value being the list of columns assigned to that role.
    The LLM-facing tool accepts the much friendlier inverse (one entry per
    column) and we convert here.

    Validates every role; unknown roles raise ``ValueError`` so the LLM gets a
    targeted error instead of a 4xx from upstream.
    """
    if not isinstance(column_roles, dict) or not column_roles:
        raise ValueError(
            "column_roles must be a non-empty dict of {column_name: role}."
        )
    categorized: Dict[str, List[str]] = {role: [] for role in COLUMN_ROLES}
    for col, role in column_roles.items():
        if role not in categorized:
            raise ValueError(
                f"Unknown column role {role!r} for column {col!r}. "
                f"Allowed roles: {', '.join(COLUMN_ROLES)}."
            )
        categorized[role].append(col)
    return categorized


def set_column_roles(uuid: str, column_roles: Dict[str, str], **kwargs):
    """Assign each column to one of the seven roles Forecaster understands.

    ``column_roles`` is a friendly ``{column_name: role}`` dict; the agent
    internally converts it to the role-keyed JSON shape required by
    ``POST /dataset/save-columns``. Columns omitted from ``column_roles``
    fall into ``not-included`` by upstream default.

    Allowed roles: ``not-included``, ``time-component``, ``grouping``,
    ``target``, ``past-covariates``, ``future-covariates``, ``static-covariates``.
    """
    try:
        client = _build_client(kwargs)
        categorized = _build_categorized_string(column_roles)
        resp = client.post(
            "/dataset/save-columns",
            data={
                "categorizedString": json.dumps(categorized),
                "uuid": uuid,
            },
        )
        payload = _safe_json(resp)
        # Summarize for the chat: list every role that has at least one
        # column assigned, biggest first.
        nonempty = {role: cols for role, cols in categorized.items() if cols}
        rows = [[role, ", ".join(cols)] for role, cols in nonempty.items()]
        summary_table = Table(headers=["Role", "Columns"], rows=rows)
        return _ui(
            [Card(
                title="Column roles saved",
                content=[
                    Text(content=f"Saved column roles for dataset `{uuid}`."),
                    summary_table,
                ],
            )],
            data={
                "uuid": uuid,
                "categorized": categorized,
                "response": payload,
            },
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def _make_status_poll(client: "ForecasterHttpClient", uuid: str):
    """Build a sync callable that probes ``/dataset/get-job-status`` for one job.

    Normalizes the upstream status string into the JobPoller's vocabulary:
        "Completed"           → succeeded (+ fetches /results/get-metrics)
        contains "Training"   → in_progress
        any other non-empty   → in_progress (defensive — covers "Initializing"/"Queued"/etc.)
        empty / missing       → failed
    """
    def _poll():
        resp = client.get("/dataset/get-job-status", params={"uuid": uuid})
        payload = _safe_json(resp)
        raw = (payload.get("status") or "").strip()
        if raw == "Completed":
            try:
                metrics_resp = client.get("/results/get-metrics", params={"uuid": uuid})
                metrics_payload = _safe_json(metrics_resp) or metrics_resp.text
            except Exception:
                metrics_payload = None
            return {
                "status": "succeeded",
                "percentage": 100,
                "message": "Training complete.",
                "result": metrics_payload,
            }
        if "Training" in raw:
            return {"status": "in_progress", "percentage": None, "message": raw}
        if raw:
            return {"status": "in_progress", "percentage": None, "message": raw}
        return {
            "status": "failed",
            "percentage": None,
            "message": "Empty or missing status from upstream.",
            "result": None,
        }
    return _poll


def start_training_job(uuid: str, options: Optional[Dict[str, Any]] = None, **kwargs):
    """Start a Forecaster training job and register the JobPoller.

    Returns immediately with the ``uuid`` and ``status: "started"``. The
    agent's :class:`JobPoller` posts ``tool_progress`` messages into the chat
    as the job runs and a terminal message with metrics on completion.

    ``options`` is a sparse dict of overrides over the upstream defaults
    (which are documented in ``DEFAULT_TRAINING_OPTIONS`` and in the
    forecaster-api-docs.md). The agent passes the dict through unchanged;
    the upstream applies its own defaults for any unspecified key. To run a
    fast smoke test, pass e.g. ``{"models": ["linear-regression"], "epochs": 1}``.
    """
    try:
        client = _build_client(kwargs)
        body_data: Dict[str, Any] = {"uuid": uuid}
        if options is not None:
            if not isinstance(options, dict):
                raise ValueError("options must be a dict of parameter overrides.")
            body_data["options"] = json.dumps(options)
        else:
            body_data["options"] = json.dumps({})
        resp = client.post("/dataset/start-training-job", data=body_data)
        payload = _safe_json(resp)
        runtime = kwargs.get("_runtime")
        if runtime is not None:
            runtime.start_long_running_job(_make_status_poll(client, uuid))
        return _ui(
            [Card(
                title="Forecaster training started",
                content=[Text(content=(
                    f"Dataset UUID: {uuid}\n"
                    "Progress will be posted in this chat as the job runs."
                ))],
            )],
            data={
                "uuid": uuid,
                "status": "started",
                "options": options or {},
                "upstream_response": payload,
                "message": "Training started. Progress will appear here automatically.",
            },
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def get_job_status(uuid: str, **kwargs):
    """Synchronously probe the status of a Forecaster job by UUID."""
    try:
        client = _build_client(kwargs)
        poll = _make_status_poll(client, uuid)
        result = poll()
        return _ui(
            [Card(
                title=f"Job {uuid}",
                content=[Text(content=(
                    f"Status: {result['status']}\n"
                    f"Message: {result.get('message') or '(none)'}"
                    + (f"\nPercentage: {result['percentage']}%" if result.get("percentage") is not None else "")
                ))],
            )],
            data={"uuid": uuid, **result},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def _render_metric_value(value: Any) -> str:
    """Render a metric value as a tidy table cell."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.4f}" if abs(value) < 1000 else f"{value:.4g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_render_metric_value(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def get_results(uuid: str, **kwargs):
    """Fetch the final metrics + output_log for a completed Forecaster job.

    Per ``forecaster-api-docs.md``, ``/results/get-metrics`` returns:
        { "output_log": "...", "file_contents": <metrics JSON> }

    Shape-aware rendering of file_contents:
        * ``{model: {metric: value, ...}, ...}`` → one row per model, columns = metric names
        * ``{metric: value, ...}`` (flat)        → two-column Metric | Value table
        * anything else (text, mixed nesting)   → fall back to truncated JSON Text block
    """
    try:
        client = _build_client(kwargs)
        resp = client.get("/results/get-metrics", params={"uuid": uuid})
        payload = _safe_json(resp)
        output_log = payload.get("output_log", "") if isinstance(payload, dict) else ""
        metrics = payload.get("file_contents") if isinstance(payload, dict) else None
        # The live service encodes file_contents as a JSON *string*, not an
        # object. Parse it so per-model rendering works; if it's already a
        # dict (or doesn't parse), leave it alone.
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except (ValueError, TypeError):
                pass

        data = {"uuid": uuid, "output_log": output_log, "metrics": metrics}

        components: List[Any] = []

        if isinstance(metrics, dict) and metrics:
            if all(isinstance(v, dict) for v in metrics.values()):
                metric_keys: List[str] = []
                seen = set()
                for model_metrics in metrics.values():
                    for k in model_metrics.keys():
                        if k not in seen:
                            seen.add(k)
                            metric_keys.append(k)
                metric_keys.sort()
                rows = [
                    [model] + [_render_metric_value(m.get(k)) for k in metric_keys]
                    for model, m in metrics.items()
                ]
                table = Table(headers=["Model"] + metric_keys, rows=rows)
                components.append(Card(
                    title=f"Results for {uuid}",
                    content=[
                        Text(content=f"**{len(metrics)} model(s)**, **{len(metric_keys)} metric(s)**."),
                        table,
                    ],
                ))
            elif all(not isinstance(v, dict) for v in metrics.values()):
                rows = [[k, _render_metric_value(v)] for k, v in metrics.items()]
                table = Table(headers=["Metric", "Value"], rows=rows)
                components.append(Card(
                    title=f"Results for {uuid}",
                    content=[table],
                ))
            else:
                body = json.dumps(metrics, indent=2)[:4000]
                components.append(Card(
                    title=f"Results for {uuid}",
                    content=[Text(content=body)],
                ))
        else:
            body = (
                json.dumps(metrics, indent=2)[:4000]
                if metrics
                else (resp.text[:4000] if resp.content else "(no metrics returned)")
            )
            components.append(Card(
                title=f"Results for {uuid}",
                content=[Text(content=body)],
            ))

        if output_log:
            log_text = output_log if len(output_log) <= 4000 else output_log[:4000] + "\n… (truncated)"
            components.append(Card(
                title="Output log",
                content=[Text(content=log_text)],
            ))

        return _ui(components, data=data)
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


def delete_dataset(uuid: str, **kwargs):
    """Delete a Forecaster dataset and all of its associated models / artifacts."""
    try:
        client = _build_client(kwargs)
        resp = client.post("/dataset/delete", data={"uuid": uuid})
        payload = _safe_json(resp)
        return _ui(
            [Card(
                title="Dataset deleted",
                content=[Text(content=f"Dataset {uuid} has been removed from Forecaster.")],
            )],
            data={"uuid": uuid, "response": payload},
        )
    except (ExternalHttpError, ValueError) as e:
        return _ui([Alert(message=_user_facing_error(e), variant="error")], retryable=False)


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
    "submit_dataset": {
        "function": submit_dataset,
        "description": (
            "Upload a CSV time-series dataset to the Forecaster service. Returns a "
            "dataset UUID and the list of column names from the file. Use the returned "
            "columns to ask the user which column is the time component, which is the "
            "target, and which (if any) are past/future/static covariates before "
            "calling set_column_roles. file_handle should be the attachment_id from "
            "the AstralBody upload mechanism, NOT the display filename. "
            "DO NOT call read_spreadsheet/read_csv before this — submit_dataset returns "
            "the column names directly. This is the FIRST step of the Forecaster pipeline."
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
    "set_column_roles": {
        "function": set_column_roles,
        "description": (
            "Assign every column to one of the seven roles Forecaster understands. "
            "Pass column_roles as {column_name: role}. Allowed roles: "
            "'not-included', 'time-component' (the timestamp column — usually exactly one), "
            "'grouping' (e.g. region/store id if you have multiple parallel series), "
            "'target' (the value being forecast — usually exactly one), "
            "'past-covariates' (features known only up to the present), "
            "'future-covariates' (features known into the future, e.g. day-of-week), "
            "'static-covariates' (constant per series). Columns omitted from "
            "column_roles fall into 'not-included' by upstream default. "
            "Call this AFTER submit_dataset and BEFORE start_training_job."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "Dataset UUID returned by submit_dataset.",
                },
                "column_roles": {
                    "type": "object",
                    "description": (
                        "Map of column_name → role. Example: "
                        "{'Date': 'time-component', 'Volume': 'target', "
                        "'Rain': 'past-covariates', 'Temp': 'past-covariates'}."
                    ),
                    "additionalProperties": {
                        "type": "string",
                        "enum": COLUMN_ROLES,
                    },
                },
            },
            "required": ["uuid", "column_roles"],
        },
        "scope": "tools:write",
    },
    "start_training_job": {
        "function": start_training_job,
        "description": (
            "Kick off a Forecaster training job on a dataset whose columns have already "
            "been categorized via set_column_roles. options is a sparse dict of "
            "overrides; any key not present uses the upstream default. Returns "
            "immediately with the UUID and posts progress + final metrics into the "
            "chat automatically as the job runs.\n\n"
            "Documented options (defaults shown):\n"
            "  test-size: 0.2\n"
            "  expanding-window: False\n"
            "  expanding-window-forecast-horizon: 6\n"
            "  expanding-window-stride: 6\n"
            "  visualize: True\n"
            "  generate-real-predictions: False  (set True for future forecasts beyond test)\n"
            "  real-prediction-length: 12         (used when generate-real-predictions=True)\n"
            "  fill-future-covariates: False\n"
            "  probabilistic: False\n"
            "  probabilistic-likelihood: 'quantile'\n"
            "  probabilistic-num-samples: 100\n"
            "  models: ['arima','exponential-smoothing','linear-regression','xgboost',"
            "'random-forest','lgbm','nlinear','tft']\n"
            "  arima-p: 12, arima-d: 1, arima-q: 6\n"
            "  lags: 12, lags-future: 0\n"
            "  output-chunk-length: 6\n"
            "  epochs: 10"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "Dataset UUID from submit_dataset.",
                },
                "options": {
                    "type": "object",
                    "description": (
                        "Sparse override dict; only include keys you want to differ "
                        "from the upstream defaults. See the tool description for the "
                        "full list of documented options."
                    ),
                    "additionalProperties": True,
                },
            },
            "required": ["uuid"],
        },
        "scope": "tools:write",
    },
    "get_job_status": {
        "function": get_job_status,
        "description": (
            "Synchronously probe the status of a Forecaster job by UUID. The poller "
            "usually pushes updates automatically; use this only for explicit user "
            "'did my job finish?' queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"uuid": {"type": "string"}},
            "required": ["uuid"],
        },
        "scope": "tools:read",
    },
    "get_results": {
        "function": get_results,
        "description": (
            "Fetch the final metrics + output_log for a completed Forecaster job. "
            "Renders per-model metrics as a table when available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"uuid": {"type": "string"}},
            "required": ["uuid"],
        },
        "scope": "tools:read",
    },
    "delete_dataset": {
        "function": delete_dataset,
        "description": "Delete a Forecaster dataset and all of its associated models / artifacts.",
        "input_schema": {
            "type": "object",
            "properties": {"uuid": {"type": "string"}},
            "required": ["uuid"],
        },
        "scope": "tools:write",
        "metadata": {"external_target": "Forecaster"},
    },
}
