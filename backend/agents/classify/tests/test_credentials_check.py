"""Unit tests for the CLASSify agent's `_credentials_check` and curated tools."""
import socket
from unittest.mock import patch

import pytest

from agents.classify import mcp_tools
from shared.tests._http_mock import HttpMock


SAFE_HOST = "classify.example.com"
BASE_URL = f"https://{SAFE_HOST}"
GOOD_CREDS = {"CLASSIFY_URL": BASE_URL, "CLASSIFY_API_KEY": "sentinel-api-key"}


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


def test_credentials_check_ok(rmock: HttpMock) -> None:
    rmock.add("GET", f"{BASE_URL}/get-ml-options", status=200, json={"options": {}})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result == {"credential_test": "ok"}


def test_credentials_check_auth_failed(rmock: HttpMock) -> None:
    rmock.add("GET", f"{BASE_URL}/get-ml-options", status=401, body=b"{}")
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


def test_get_ml_options_renders_card(rmock: HttpMock) -> None:
    rmock.add("GET", f"{BASE_URL}/get-ml-options", status=200, json={"options": ["rf", "xgb"]})
    result = mcp_tools.get_ml_options(_credentials=GOOD_CREDS)
    assert "_ui_components" in result
    assert result["_ui_components"][0].get("variant") != "error"


def test_get_ml_options_renders_alert_on_auth_failure(rmock: HttpMock) -> None:
    rmock.add("GET", f"{BASE_URL}/get-ml-options", status=401, body=b"{}")
    result = mcp_tools.get_ml_options(_credentials=GOOD_CREDS)
    assert result["_ui_components"][0]["variant"] == "error"
    assert "rejected" in result["_ui_components"][0]["message"].lower()


def test_train_classifier_returns_task_id(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("a,b,target\n1,2,X\n")
    rmock.add("POST", f"{BASE_URL}/upload_testset", status=200, json={"filename": "data.csv"})
    rmock.add("POST", f"{BASE_URL}/train", status=200, json={"task_id": "task-42"})
    result = mcp_tools.train_classifier(
        file_handle=str(csv), class_column="target",
        _credentials=GOOD_CREDS, user_id="alice",
    )
    assert result["_data"]["task_id"] == "task-42"
    assert result["_data"]["status"] == "started"


def test_long_running_tools_set_correct() -> None:
    assert mcp_tools.LONG_RUNNING_TOOLS == {"train_classifier", "retest_model"}


def test_tool_registry_has_required_entries() -> None:
    expected = {
        "_credentials_check", "get_ml_options", "get_class_column_values",
        "get_training_status", "train_classifier", "retest_model",
    }
    assert set(mcp_tools.TOOL_REGISTRY.keys()) == expected


def test_no_api_key_in_response_data(rmock: HttpMock) -> None:
    """Constitution Principle X / SC-006 — API key never reaches response payload."""
    rmock.add("GET", f"{BASE_URL}/get-ml-options", status=200, json={"options": ["rf"]})
    result = mcp_tools.get_ml_options(_credentials=GOOD_CREDS)
    serialized = str(result)
    assert "sentinel-api-key" not in serialized
