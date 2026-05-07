"""Unit tests for the Forecaster agent's `_credentials_check` and curated tools."""
import socket
from unittest.mock import patch

import pytest

from agents.forecaster import mcp_tools
from shared.tests._http_mock import HttpMock


SAFE_HOST = "forecaster.example.com"
BASE_URL = f"https://{SAFE_HOST}"
GOOD_CREDS = {"FORECASTER_URL": BASE_URL, "FORECASTER_API_KEY": "sentinel-api-key"}


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


def test_credentials_check_ok_on_200(rmock: HttpMock) -> None:
    rmock.add("GET", f"{BASE_URL}/download-model", status=200, json={"model": "x"})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result == {"credential_test": "ok"}


def test_credentials_check_ok_on_404(rmock: HttpMock) -> None:
    """A 404 from /download-model means auth was accepted but the probe model doesn't exist."""
    rmock.add("GET", f"{BASE_URL}/download-model", status=404, json={"detail": "no probe"})
    result = mcp_tools._credentials_check(_credentials=GOOD_CREDS)
    assert result == {"credential_test": "ok"}


def test_credentials_check_auth_failed(rmock: HttpMock) -> None:
    rmock.add("GET", f"{BASE_URL}/download-model", status=401, body=b"{}")
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


def test_train_forecaster_returns_task_id(rmock: HttpMock, tmp_path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_text("date,value\n2026-01-01,1\n")
    rmock.add("POST", f"{BASE_URL}/parse_retrain_file", status=200, json={"ok": True})
    rmock.add("POST", f"{BASE_URL}/train", status=200, json={"task_id": "fc-42"})
    result = mcp_tools.train_forecaster(
        file_handle=str(csv),
        dataset_name="sales",
        _credentials=GOOD_CREDS,
        user_id="alice",
    )
    assert result["_data"]["task_id"] == "fc-42"
    assert result["_data"]["status"] == "started"


def test_get_results_summary_renders(rmock: HttpMock) -> None:
    rmock.add("POST", f"{BASE_URL}/generate-results-summary",
              status=200, json={"summary": "ARIMA wins by RMSE"})
    result = mcp_tools.get_results_summary(dataset_name="sales", _credentials=GOOD_CREDS)
    assert result["_ui_components"][0].get("variant") != "error"
    assert "ARIMA" in str(result["_data"])


def test_long_running_tools_set_correct() -> None:
    assert mcp_tools.LONG_RUNNING_TOOLS == {"train_forecaster", "generate_forecast"}


def test_tool_registry_has_required_entries() -> None:
    expected = {
        "_credentials_check", "train_forecaster", "generate_forecast",
        "get_results_summary", "get_recommendations",
    }
    assert set(mcp_tools.TOOL_REGISTRY.keys()) == expected
