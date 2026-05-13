"""Unit tests for the Forecaster agent's `_credentials_check` and curated tools.

The seven tools mirror the documented Forecaster API (forecaster-api-docs.md):

- ``_credentials_check`` — probes /dataset/get-job-status with a sentinel uuid
- ``submit_dataset``     — POST /dataset/submit
- ``set_column_roles``   — POST /dataset/save-columns
- ``start_training_job`` — POST /dataset/start-training-job (LONG-RUNNING)
- ``get_job_status``     — GET  /dataset/get-job-status
- ``get_results``        — GET  /results/get-metrics
- ``delete_dataset``     — POST /dataset/delete
"""
import json
import socket
from unittest.mock import patch

import pytest

from agents.forecaster import mcp_tools
from shared.tests._http_mock import HttpMock


SAFE_HOST = "forecaster.example.com"
BASE_URL = f"https://{SAFE_HOST}"
GOOD_CREDS = {"FORECASTER_URL": BASE_URL, "FORECASTER_API_KEY": "sentinel-api-key"}

SUBMIT_URL = f"{BASE_URL}/dataset/submit"
SAVE_COLS_URL = f"{BASE_URL}/dataset/save-columns"
START_JOB_URL = f"{BASE_URL}/dataset/start-training-job"
JOB_STATUS_URL = f"{BASE_URL}/dataset/get-job-status"
RESULTS_URL = f"{BASE_URL}/results/get-metrics"
DELETE_URL = f"{BASE_URL}/dataset/delete"


@pytest.fixture
def rmock():
    with HttpMock() as m:
        yield m


@pytest.fixture(autouse=True)
def stub_dns():
    def _fake(host, *_a, **_kw):
        if host == SAFE_HOST:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
        raise socket.gaierror(host)
    with patch("socket.getaddrinfo", _fake):
        yield


# ---------------------------------------------------------------------------
# _credentials_check
# ---------------------------------------------------------------------------


def test_credentials_check_ok_on_200(rmock: HttpMock) -> None:
    """Live Forecaster returns 200 + {success: false} when no uuid is sent;
    auth was already verified by then."""
    rmock.add("GET", JOB_STATUS_URL, status=200,
              json={"success": False, "message": "A UUID must be provded"})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result == {"credential_test": "ok"}
    # Confirm we hit /dataset/get-job-status with no params (which is what
    # the live API requires for a clean response — passing a sentinel uuid
    # makes the upstream crash with a 500).
    assert rmock.calls[-1]["url"] == JOB_STATUS_URL
    assert not rmock.calls[-1].get("params")


def test_credentials_check_ok_on_4xx_non_auth(rmock: HttpMock) -> None:
    """Any 4xx that isn't 401/403 means auth was accepted but the request
    body was rejected for some other reason."""
    rmock.add("GET", JOB_STATUS_URL, status=404, json={"detail": "route not found"})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result == {"credential_test": "ok"}


def test_credentials_check_auth_failed_401(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=401, body=b"{}")
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result["credential_test"] == "auth_failed"


def test_credentials_check_auth_failed_403(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=403, body=b"{}")
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result["credential_test"] == "auth_failed"


def test_credentials_check_unreachable() -> None:
    import requests
    with patch("requests.request", side_effect=requests.ConnectionError("nope")):
        result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
        assert result["credential_test"] == "unreachable"


def test_credentials_check_missing_creds() -> None:
    result = mcp_tools._credentials_check()
    assert result["credential_test"] == "unexpected"
    assert "not configured" in result["detail"].lower()


def test_credentials_check_partial_creds() -> None:
    result = mcp_tools._credentials_check(_credentials={"FORECASTER_URL": BASE_URL})
    assert result["credential_test"] == "unexpected"


def test_no_api_key_in_response_data(rmock: HttpMock) -> None:
    """SC-006 sentinel: no part of the saved key is echoed back in the response."""
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Unknown"})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    # Serialize the full response and confirm the API key string is absent.
    assert "sentinel-api-key" not in json.dumps(result)


# ---------------------------------------------------------------------------
# submit_dataset
# ---------------------------------------------------------------------------


def test_submit_dataset_returns_uuid_and_columns(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "rides.csv"
    csv.write_text("Date,Volume,Rain,Temp\n2026-01-01,100,0,5\n")
    rmock.add("POST", SUBMIT_URL, status=200, json={
        "uuid": "ds-42",
        "columns": ["Date", "Volume", "Rain", "Temp"],
    })
    result = mcp_tools.submit_dataset(
        file_handle=str(csv), _credentials=GOOD_CREDS, user_id="alice",
    )
    assert result["_data"]["uuid"] == "ds-42"
    assert result["_data"]["columns"] == ["Date", "Volume", "Rain", "Temp"]
    assert "not-included" in result["_data"]["allowed_roles"]
    # Confirm POST went to /dataset/submit with a multipart file.
    call = rmock.calls[-1]
    assert call["url"] == SUBMIT_URL
    assert "file" in (call.get("files") or {})


def test_submit_dataset_missing_user_id_returns_error(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("Date,Value\n2026-01-01,1\n")
    result = mcp_tools.submit_dataset(file_handle=str(csv), _credentials=GOOD_CREDS)
    assert result["_ui_components"][0]["variant"] == "error"


def test_submit_dataset_handles_empty_columns(rmock: HttpMock, tmp_path) -> None:
    """Defensive: upstream returned no columns list — tool should not crash."""
    csv = tmp_path / "data.csv"
    csv.write_text("Date,Value\n2026-01-01,1\n")
    rmock.add("POST", SUBMIT_URL, status=200, json={"uuid": "ds-empty"})
    result = mcp_tools.submit_dataset(
        file_handle=str(csv), _credentials=GOOD_CREDS, user_id="alice",
    )
    assert result["_data"]["uuid"] == "ds-empty"
    assert result["_data"]["columns"] == []


def test_submit_dataset_auth_failure_renders_alert(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("Date,Value\n2026-01-01,1\n")
    rmock.add("POST", SUBMIT_URL, status=401, body=b"{}")
    result = mcp_tools.submit_dataset(
        file_handle=str(csv), _credentials=GOOD_CREDS, user_id="alice",
    )
    assert result["_ui_components"][0]["variant"] == "error"
    assert "rejected" in result["_ui_components"][0]["message"].lower()


# ---------------------------------------------------------------------------
# set_column_roles
# ---------------------------------------------------------------------------


def test_set_column_roles_builds_categorized_string(rmock: HttpMock) -> None:
    rmock.add("POST", SAVE_COLS_URL, status=200, json={"ok": True})
    column_roles = {
        "Date": "time-component",
        "Volume": "target",
        "Rain": "past-covariates",
        "Temp": "past-covariates",
    }
    result = mcp_tools.set_column_roles(
        uuid="ds-42", column_roles=column_roles, _credentials=GOOD_CREDS,
    )
    assert result["_ui_components"][0].get("variant") != "error"
    call = rmock.calls[-1]
    assert call["url"] == SAVE_COLS_URL
    sent = call.get("data") or {}
    assert sent.get("uuid") == "ds-42"
    parsed = json.loads(sent["categorizedString"])
    # Per the API doc: keyed by role, each value a list of columns.
    assert parsed["time-component"] == ["Date"]
    assert parsed["target"] == ["Volume"]
    assert sorted(parsed["past-covariates"]) == ["Rain", "Temp"]
    # Every documented role must be present (even empty ones).
    for role in mcp_tools.COLUMN_ROLES:
        assert role in parsed


def test_set_column_roles_rejects_unknown_role() -> None:
    result = mcp_tools.set_column_roles(
        uuid="ds-42",
        column_roles={"Date": "time-component", "Volume": "totally-made-up"},
        _credentials=GOOD_CREDS,
    )
    assert result["_ui_components"][0]["variant"] == "error"
    assert "totally-made-up" in result["_ui_components"][0]["message"]


def test_set_column_roles_rejects_empty_dict() -> None:
    result = mcp_tools.set_column_roles(
        uuid="ds-42", column_roles={}, _credentials=GOOD_CREDS,
    )
    assert result["_ui_components"][0]["variant"] == "error"


# ---------------------------------------------------------------------------
# start_training_job
# ---------------------------------------------------------------------------


def test_start_training_job_posts_form_encoded_options(rmock: HttpMock) -> None:
    rmock.add("POST", START_JOB_URL, status=200, json={"started": True})
    overrides = {"models": ["linear-regression"], "epochs": 1, "expanding-window": False}
    result = mcp_tools.start_training_job(
        uuid="ds-42", options=overrides, _credentials=GOOD_CREDS,
    )
    assert result["_data"]["uuid"] == "ds-42"
    assert result["_data"]["status"] == "started"
    call = rmock.calls[-1]
    assert call["url"] == START_JOB_URL
    sent = call.get("data") or {}
    assert sent.get("uuid") == "ds-42"
    # options must be a JSON string per the API doc.
    parsed = json.loads(sent["options"])
    assert parsed == overrides


def test_start_training_job_with_no_options_sends_empty_dict(rmock: HttpMock) -> None:
    """Calling start without options should still POST options as JSON '{}'."""
    rmock.add("POST", START_JOB_URL, status=200, json={"started": True})
    mcp_tools.start_training_job(uuid="ds-42", _credentials=GOOD_CREDS)
    sent = rmock.calls[-1].get("data") or {}
    assert json.loads(sent["options"]) == {}


def test_start_training_job_rejects_non_dict_options() -> None:
    result = mcp_tools.start_training_job(
        uuid="ds-42", options=["models", "lin"], _credentials=GOOD_CREDS,
    )
    assert result["_ui_components"][0]["variant"] == "error"


def test_start_training_job_registers_long_running(rmock: HttpMock) -> None:
    rmock.add("POST", START_JOB_URL, status=200, json={"started": True})
    seen = {}

    class _FakeRuntime:
        def start_long_running_job(self, poll_fn, **_kw):
            seen["poll_fn"] = poll_fn
    runtime = _FakeRuntime()
    mcp_tools.start_training_job(
        uuid="ds-42", _credentials=GOOD_CREDS, _runtime=runtime,
    )
    assert callable(seen.get("poll_fn"))


# ---------------------------------------------------------------------------
# Status poller (used by JobPoller and by get_job_status)
# ---------------------------------------------------------------------------


def test_status_poll_maps_completed_to_succeeded(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Completed"})
    rmock.add("GET", RESULTS_URL, status=200, json={
        "output_log": "ok",
        "file_contents": {"linear-regression": {"rmse": 0.42}},
    })
    client = mcp_tools.ForecasterHttpClient(GOOD_CREDS)
    poll = mcp_tools._make_status_poll(client, "ds-42")
    res = poll()
    assert res["status"] == "succeeded"
    assert res["percentage"] == 100
    assert res["result"]["file_contents"]["linear-regression"]["rmse"] == 0.42


def test_status_poll_maps_training_to_in_progress(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Training: epoch 3/10"})
    client = mcp_tools.ForecasterHttpClient(GOOD_CREDS)
    poll = mcp_tools._make_status_poll(client, "ds-42")
    res = poll()
    assert res["status"] == "in_progress"
    assert "Training" in res["message"]


def test_status_poll_unknown_nonempty_status_is_in_progress(rmock: HttpMock) -> None:
    """Defensive: any non-empty status that isn't 'Completed' is treated as
    in-progress until proven otherwise (matches the JobPoller's tolerance for
    upstream status strings like 'Initializing' or 'Queued')."""
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Initializing"})
    client = mcp_tools.ForecasterHttpClient(GOOD_CREDS)
    poll = mcp_tools._make_status_poll(client, "ds-42")
    res = poll()
    assert res["status"] == "in_progress"


def test_status_poll_empty_status_is_failed(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": ""})
    client = mcp_tools.ForecasterHttpClient(GOOD_CREDS)
    poll = mcp_tools._make_status_poll(client, "ds-42")
    res = poll()
    assert res["status"] == "failed"


# ---------------------------------------------------------------------------
# get_job_status (synchronous wrapper around the poller)
# ---------------------------------------------------------------------------


def test_get_job_status_renders_card(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Training: epoch 5/10"})
    result = mcp_tools.get_job_status(uuid="ds-42", _credentials=GOOD_CREDS)
    assert result["_data"]["status"] == "in_progress"
    assert result["_ui_components"][0].get("variant") != "error"


# ---------------------------------------------------------------------------
# get_results
# ---------------------------------------------------------------------------


def test_get_results_renders_per_model_table(rmock: HttpMock) -> None:
    rmock.add("GET", RESULTS_URL, status=200, json={
        "output_log": "training complete",
        "file_contents": {
            "linear-regression": {"rmse": 0.42, "mae": 0.18},
            "random-forest":     {"rmse": 0.36, "mae": 0.15},
        },
    })
    result = mcp_tools.get_results(uuid="ds-42", _credentials=GOOD_CREDS)
    cards = result["_ui_components"]
    # First card: metrics table
    contents = cards[0].get("content", [])
    types = [c.get("type") for c in contents if isinstance(c, dict)]
    assert "table" in types
    table = next(c for c in contents if isinstance(c, dict) and c.get("type") == "table")
    assert table["headers"][0] == "Model"
    row_names = sorted(r[0] for r in table["rows"])
    assert row_names == ["linear-regression", "random-forest"]
    # Output log appears as its own card after the metrics card.
    assert any(c.get("title") == "Output log" for c in cards if isinstance(c, dict))


def test_get_results_renders_flat_metrics_table(rmock: HttpMock) -> None:
    rmock.add("GET", RESULTS_URL, status=200, json={
        "output_log": "",
        "file_contents": {"rmse": 0.42, "mae": 0.18},
    })
    result = mcp_tools.get_results(uuid="ds-42", _credentials=GOOD_CREDS)
    card = result["_ui_components"][0]
    contents = card.get("content", [])
    table = next(c for c in contents if isinstance(c, dict) and c.get("type") == "table")
    assert table["headers"] == ["Metric", "Value"]


def test_get_results_parses_string_encoded_file_contents(rmock: HttpMock) -> None:
    """The live forecaster.ai.uky.edu service returns file_contents as a
    JSON-encoded *string*, not a nested object. The tool must parse it so
    the per-model table renders correctly."""
    inner = {
        "linear-regression": {"Normalized MAE": 0.118, "R-squared": 0.348},
        "Baseline Average Prediction": {"Normalized MAE": 0.286, "R-squared": -2.25},
    }
    rmock.add("GET", RESULTS_URL, status=200, json={
        "success": True,
        "message": "Metrics retrieved",
        "file_contents": json.dumps(inner),
        "output_log": "training done",
    })
    result = mcp_tools.get_results(uuid="ds-42", _credentials=GOOD_CREDS)
    # Should pick the per-model table branch, not the JSON fallback.
    card = result["_ui_components"][0]
    contents = card.get("content", [])
    types = [c.get("type") for c in contents if isinstance(c, dict)]
    assert "table" in types
    table = next(c for c in contents if isinstance(c, dict) and c.get("type") == "table")
    assert table["headers"][0] == "Model"
    # _data.metrics must be the parsed dict, not the original string.
    assert isinstance(result["_data"]["metrics"], dict)
    assert "linear-regression" in result["_data"]["metrics"]


def test_get_results_auth_failure_renders_alert(rmock: HttpMock) -> None:
    rmock.add("GET", RESULTS_URL, status=401, body=b"{}")
    result = mcp_tools.get_results(uuid="ds-42", _credentials=GOOD_CREDS)
    assert result["_ui_components"][0]["variant"] == "error"


# ---------------------------------------------------------------------------
# delete_dataset
# ---------------------------------------------------------------------------


def test_delete_dataset_posts_uuid(rmock: HttpMock) -> None:
    rmock.add("POST", DELETE_URL, status=200, json={"deleted": True})
    result = mcp_tools.delete_dataset(uuid="ds-42", _credentials=GOOD_CREDS)
    assert result["_ui_components"][0].get("variant") != "error"
    call = rmock.calls[-1]
    assert call["url"] == DELETE_URL
    assert (call.get("data") or {}).get("uuid") == "ds-42"


# ---------------------------------------------------------------------------
# Registry / metadata sanity
# ---------------------------------------------------------------------------


def test_long_running_tools_set_correct() -> None:
    """Only start_training_job is long-running; everything else is sync."""
    assert mcp_tools.LONG_RUNNING_TOOLS == {"start_training_job"}


def test_tool_registry_has_required_entries() -> None:
    expected = {
        "_credentials_check",
        "submit_dataset",
        "set_column_roles",
        "start_training_job",
        "get_job_status",
        "get_results",
        "delete_dataset",
    }
    assert set(mcp_tools.TOOL_REGISTRY.keys()) == expected


def test_column_roles_match_docs() -> None:
    """The seven roles in mcp_tools.COLUMN_ROLES must match the API docs exactly."""
    assert mcp_tools.COLUMN_ROLES == [
        "not-included",
        "time-component",
        "grouping",
        "target",
        "past-covariates",
        "future-covariates",
        "static-covariates",
    ]
