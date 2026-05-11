"""Unit tests for the CLASSify agent's `_credentials_check` and curated tools."""
import json
import socket
from unittest.mock import patch

import pytest

from agents.classify import mcp_tools
from shared.tests._http_mock import HttpMock


SAFE_HOST = "classify.example.com"
BASE_URL = f"https://{SAFE_HOST}"
GOOD_CREDS = {"CLASSIFY_URL": BASE_URL, "CLASSIFY_API_KEY": "sentinel-api-key"}

ML_OPTS_URL = f"{BASE_URL}/reports/get-ml-opts"
SUBMIT_URL = f"{BASE_URL}/reports/submit"
SET_COLS_URL = f"{BASE_URL}/reports/set-column-changes"
START_JOB_URL = f"{BASE_URL}/reports/start-training-job"
JOB_STATUS_URL = f"{BASE_URL}/reports/get-job-status"
RESULTS_URL = f"{BASE_URL}/result/get-results"
OUTPUT_LOG_URL = f"{BASE_URL}/result/get-output-log"
DELETE_URL = f"{BASE_URL}/reports/delete"


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


def test_credentials_check_ok(rmock: HttpMock) -> None:
    rmock.add("GET", ML_OPTS_URL, status=200, json={"parameters": {}})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result == {"credential_test": "ok"}
    # Confirms we hit the right path with the expected query string.
    assert rmock.calls[-1]["url"] == ML_OPTS_URL
    assert rmock.calls[-1].get("params") == {"unsstate": 0}


def test_credentials_check_auth_failed(rmock: HttpMock) -> None:
    rmock.add("GET", ML_OPTS_URL, status=401, body=b"{}")
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
    result = mcp_tools._credentials_check(_credentials={"CLASSIFY_URL": BASE_URL})
    assert result["credential_test"] == "unexpected"


# ---------------------------------------------------------------------------
# get_ml_options
# ---------------------------------------------------------------------------


def test_get_ml_options_renders_card(rmock: HttpMock) -> None:
    rmock.add("GET", ML_OPTS_URL, status=200, json={"parameters": {"train_group": {"default": ["random_forest"]}}})
    result = mcp_tools.get_ml_options(_credentials=GOOD_CREDS)
    assert "_ui_components" in result
    assert result["_ui_components"][0].get("variant") != "error"
    assert result["_data"]["parameters"]["train_group"]["default"] == ["random_forest"]


def test_get_ml_options_renders_alert_on_auth_failure(rmock: HttpMock) -> None:
    rmock.add("GET", ML_OPTS_URL, status=401, body=b"{}")
    result = mcp_tools.get_ml_options(_credentials=GOOD_CREDS)
    assert result["_ui_components"][0]["variant"] == "error"
    assert "rejected" in result["_ui_components"][0]["message"].lower()


def test_get_ml_options_passes_unsstate(rmock: HttpMock) -> None:
    rmock.add("GET", ML_OPTS_URL, status=200, json={"parameters": {}})
    mcp_tools.get_ml_options(unsstate=1, _credentials=GOOD_CREDS)
    assert rmock.calls[-1].get("params") == {"unsstate": 1}


# ---------------------------------------------------------------------------
# submit_dataset
# ---------------------------------------------------------------------------


def test_submit_dataset_returns_uuid(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("a,b,target\n1,2,X\n")
    rmock.add("POST", SUBMIT_URL, status=200, json={
        "report_uuid": "rpt-1",
        "column_types": {"data_types": {"a": "integer", "b": "integer", "target": "string"}},
    })
    result = mcp_tools.submit_dataset(
        file_handle=str(csv), _credentials=GOOD_CREDS, user_id="alice",
    )
    assert result["_data"]["report_uuid"] == "rpt-1"
    assert result["_data"]["column_types"] == {
        "a": "integer", "b": "integer", "target": "string",
    }


def test_submit_dataset_missing_user_id_returns_error(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("a\n1\n")
    result = mcp_tools.submit_dataset(file_handle=str(csv), _credentials=GOOD_CREDS)
    # No user_id → ValueError → rendered as error Alert
    assert result["_ui_components"][0]["variant"] == "error"


# ---------------------------------------------------------------------------
# set_column_types
# ---------------------------------------------------------------------------


def test_set_column_types_posts_form_encoded(rmock: HttpMock) -> None:
    rmock.add("POST", SET_COLS_URL, status=200, json={"ok": True})
    column_changes = [
        {"column": "a", "data_type": "integer", "checked": True, "missing": None, "fill_value": None},
        {"column": "target", "data_type": "string", "checked": True, "missing": None,
         "fill_value": None, "class": True},
    ]
    mcp_tools.set_column_types(
        report_uuid="rpt-1", column_changes=column_changes,
        _credentials=GOOD_CREDS,
    )
    call = rmock.calls[-1]
    assert call["url"] == SET_COLS_URL
    # Form-encoded body — column_changes must be a JSON string, not nested JSON.
    sent = call.get("data") or {}
    assert sent.get("report_uuid") == "rpt-1"
    parsed = json.loads(sent["column_changes"])
    assert parsed == column_changes


def test_set_column_types_auto_flags_class_column(rmock: HttpMock) -> None:
    rmock.add("POST", SET_COLS_URL, status=200, json={"ok": True})
    # Note: no entry has 'class: True' — set_column_types should add it.
    column_changes = [
        {"column": "a", "data_type": "integer", "checked": True},
        {"column": "target", "data_type": "string", "checked": True},
    ]
    mcp_tools.set_column_types(
        report_uuid="rpt-1", column_changes=column_changes,
        class_column="target", _credentials=GOOD_CREDS,
    )
    sent_changes = json.loads(rmock.calls[-1]["data"]["column_changes"])
    target_entry = next(c for c in sent_changes if c["column"] == "target")
    assert target_entry.get("class") is True


def test_set_column_types_rejects_non_list() -> None:
    result = mcp_tools.set_column_types(
        report_uuid="rpt-1", column_changes={"not": "a list"},
        _credentials=GOOD_CREDS,
    )
    assert result["_ui_components"][0]["variant"] == "error"


# ---------------------------------------------------------------------------
# start_training_job
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self):
        self.scheduled = []

    def start_long_running_job(self, poll_fn):
        self.scheduled.append(poll_fn)


def test_start_training_job_returns_report_uuid_and_starts_poller(rmock: HttpMock) -> None:
    rmock.add("POST", START_JOB_URL, status=200, json={"queued": True})
    runtime = _FakeRuntime()
    result = mcp_tools.start_training_job(
        report_uuid="rpt-1", class_column="target",
        options=[{"name": "parameter_tune", "value": False}],
        _credentials=GOOD_CREDS, _runtime=runtime,
    )
    assert result["_data"]["report_uuid"] == "rpt-1"
    assert result["_data"]["status"] == "started"
    assert len(runtime.scheduled) == 1
    # Verify required entries (report_uuid, class_column, supervised, autodetermineclusters)
    # are appended to the options list before being sent upstream.
    sent_options = json.loads(rmock.calls[-1]["data"]["options"])
    names_to_values = {entry["name"]: entry["value"] for entry in sent_options}
    assert names_to_values["report_uuid"] == "rpt-1"
    assert names_to_values["class_column"] == "target"
    assert names_to_values["supervised"] is True
    assert names_to_values["autodetermineclusters"] is False
    assert names_to_values["parameter_tune"] is False


def test_start_training_job_without_runtime_still_returns_ack(rmock: HttpMock) -> None:
    rmock.add("POST", START_JOB_URL, status=200, json={})
    result = mcp_tools.start_training_job(
        report_uuid="rpt-1", class_column="target",
        _credentials=GOOD_CREDS,  # no _runtime
    )
    assert result["_data"]["status"] == "started"


# ---------------------------------------------------------------------------
# _make_status_poll
# ---------------------------------------------------------------------------


def test_status_poll_processed_fetches_results(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Processed"})
    rmock.add("GET", RESULTS_URL, status=200, json={"accuracy": 0.92})
    client = mcp_tools.ClassifyHttpClient(GOOD_CREDS)
    poll = mcp_tools._make_status_poll(client, "rpt-1")
    out = poll()
    assert out["status"] == "succeeded"
    assert out["percentage"] == 100
    assert out["result"] == {"accuracy": 0.92}


def test_status_poll_partial_progress_extracts_percentage(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "3/10 Processed"})
    client = mcp_tools.ClassifyHttpClient(GOOD_CREDS)
    out = mcp_tools._make_status_poll(client, "rpt-1")()
    assert out["status"] == "in_progress"
    assert out["percentage"] == 30
    assert out["message"] == "3/10 Processed"


def test_status_poll_processing_in_progress(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "Processing"})
    client = mcp_tools.ClassifyHttpClient(GOOD_CREDS)
    out = mcp_tools._make_status_poll(client, "rpt-1")()
    assert out["status"] == "in_progress"
    assert out["percentage"] is None


def test_status_poll_unknown_status_treated_as_failure(rmock: HttpMock) -> None:
    rmock.add("GET", JOB_STATUS_URL, status=200, json={"status": "ERROR: bad CSV"})
    client = mcp_tools.ClassifyHttpClient(GOOD_CREDS)
    out = mcp_tools._make_status_poll(client, "rpt-1")()
    assert out["status"] == "failed"
    assert "bad CSV" in out["message"]


# ---------------------------------------------------------------------------
# get_results, get_output_log, delete_dataset
# ---------------------------------------------------------------------------


def test_get_results_renders_card(rmock: HttpMock) -> None:
    rmock.add("GET", RESULTS_URL, status=200, json={"accuracy": 0.85, "f1": 0.81})
    result = mcp_tools.get_results(report_uuid="rpt-1", _credentials=GOOD_CREDS)
    assert result["_ui_components"][0].get("variant") != "error"
    assert result["_data"]["results"] == {"accuracy": 0.85, "f1": 0.81}


def test_get_output_log_truncates_long_text(rmock: HttpMock) -> None:
    big = b"x" * 10000
    rmock.add("GET", OUTPUT_LOG_URL, status=200, body=big)
    result = mcp_tools.get_output_log(report_uuid="rpt-1", _credentials=GOOD_CREDS)
    rendered = result["_ui_components"][0]
    text_blocks = rendered.get("content", []) if isinstance(rendered, dict) else []
    # The card content was truncated to ~4 KB
    if text_blocks and isinstance(text_blocks, list):
        rendered_text = next((b.get("content", "") for b in text_blocks if isinstance(b, dict)), "")
        assert len(rendered_text) <= 4100  # 4000 + truncation marker tolerance


def test_delete_dataset_posts_report_uuid(rmock: HttpMock) -> None:
    rmock.add("POST", DELETE_URL, status=200, json={"ok": True})
    mcp_tools.delete_dataset(report_uuid="rpt-1", _credentials=GOOD_CREDS)
    call = rmock.calls[-1]
    assert call["url"] == DELETE_URL
    assert call.get("data") == {"report_uuid": "rpt-1"}


# ---------------------------------------------------------------------------
# Registry / metadata invariants
# ---------------------------------------------------------------------------


def test_long_running_tools_set_correct() -> None:
    assert mcp_tools.LONG_RUNNING_TOOLS == {"start_training_job"}


def test_tool_registry_has_required_entries() -> None:
    expected = {
        "_credentials_check",
        "submit_dataset",
        "set_column_types",
        "get_ml_options",
        "start_training_job",
        "get_job_status",
        "get_results",
        "get_output_log",
        "delete_dataset",
    }
    assert set(mcp_tools.TOOL_REGISTRY.keys()) == expected


def test_no_api_key_in_response_data(rmock: HttpMock) -> None:
    """Constitution Principle X / SC-006 — API key never reaches response payload."""
    rmock.add("GET", ML_OPTS_URL, status=200, json={"parameters": {}})
    result = mcp_tools.get_ml_options(_credentials=GOOD_CREDS)
    serialized = str(result)
    assert "sentinel-api-key" not in serialized
