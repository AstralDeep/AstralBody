"""Tests for the ML Services union ``_credentials_check`` (feature 029, T024).

The union probe dispatches per-bundle (CLASSify / Forecaster / LLM-Factory),
reports three per-bundle verdicts, renders one summarizing Card+Table, and
aggregates an overall ``credential_test`` verdict over the *configured*
bundles only (all three bundles are optional).
"""
import json
import socket
from unittest.mock import patch

import pytest

from agents.ml_services import mcp_tools
from shared.tests._http_mock import HttpMock


CLASSIFY_HOST = "classify.example.com"
FORECASTER_HOST = "forecaster.example.com"
LLM_FACTORY_HOST = "llm-factory.example.com"
SAFE_HOSTS = {CLASSIFY_HOST, FORECASTER_HOST, LLM_FACTORY_HOST}

CLASSIFY_PROBE_URL = f"https://{CLASSIFY_HOST}/reports/get-ml-opts"
FORECASTER_PROBE_URL = f"https://{FORECASTER_HOST}/dataset/get-job-status"
LLM_FACTORY_PROBE_URL = f"https://{LLM_FACTORY_HOST}/v1/models"

ALL_CREDS = {
    "CLASSIFY_URL": f"https://{CLASSIFY_HOST}",
    "CLASSIFY_API_KEY": "sentinel-classify-key",
    "FORECASTER_URL": f"https://{FORECASTER_HOST}",
    "FORECASTER_API_KEY": "sentinel-forecaster-key",
    "LLM_FACTORY_URL": f"https://{LLM_FACTORY_HOST}",
    "LLM_FACTORY_API_KEY": "sentinel-llm-key",
}


@pytest.fixture
def rmock():
    with HttpMock() as m:
        yield m


@pytest.fixture(autouse=True)
def stub_dns():
    def _fake(host, *_a, **_kw):
        if host in SAFE_HOSTS:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
        raise socket.gaierror(host)
    with patch("socket.getaddrinfo", _fake):
        yield


def _add_ok_routes(rmock: HttpMock, *, classify=True, forecaster=True, llm=True):
    if classify:
        rmock.add("GET", CLASSIFY_PROBE_URL, status=200, json={"parameters": {}})
    if forecaster:
        rmock.add("GET", FORECASTER_PROBE_URL, status=200,
                  json={"success": False, "message": "A UUID must be provded"})
    if llm:
        rmock.add("GET", LLM_FACTORY_PROBE_URL, status=200, json={"data": []})


# ---------------------------------------------------------------------------
# Verdict shape
# ---------------------------------------------------------------------------


def test_reports_three_per_bundle_verdicts(rmock: HttpMock) -> None:
    _add_ok_routes(rmock)
    result = mcp_tools._credentials_check(_credentials=ALL_CREDS)
    bundles = result["_data"]["bundles"]
    assert set(bundles.keys()) == {"classify", "forecaster", "llm_factory"}
    for verdict in bundles.values():
        assert "credential_test" in verdict
        assert verdict["credential_test"] in (
            "ok", "auth_failed", "unreachable", "unexpected", "not_configured",
        )


def test_all_configured_and_ok(rmock: HttpMock) -> None:
    _add_ok_routes(rmock)
    result = mcp_tools._credentials_check(_credentials=ALL_CREDS)
    data = result["_data"]
    assert data["credential_test"] == "ok"
    assert data["bundles"]["classify"]["credential_test"] == "ok"
    assert data["bundles"]["forecaster"]["credential_test"] == "ok"
    assert data["bundles"]["llm_factory"]["credential_test"] == "ok"


def test_renders_one_card_with_three_row_status_table(rmock: HttpMock) -> None:
    _add_ok_routes(rmock)
    result = mcp_tools._credentials_check(_credentials=ALL_CREDS)
    comps = result["_ui_components"]
    assert len(comps) == 1
    card = comps[0]
    assert card["type"] == "card"
    table = next(c for c in card["content"] if isinstance(c, dict) and c.get("type") == "table")
    assert table["headers"] == ["Service", "Status", "Detail"]
    assert [r[0] for r in table["rows"]] == ["CLASSify", "Forecaster", "LLM-Factory"]
    assert all(r[1] == "ok" for r in table["rows"])
    # Status output is informational, never an error Alert — the save-time
    # probe path must read the aggregate verdict from _data, not an error.
    assert card.get("variant") != "error"


# ---------------------------------------------------------------------------
# Optional-bundle semantics
# ---------------------------------------------------------------------------


def test_unconfigured_bundles_excluded_from_aggregate(rmock: HttpMock) -> None:
    """Only classify configured + ok ⇒ aggregate ok; others not_configured."""
    rmock.add("GET", CLASSIFY_PROBE_URL, status=200, json={"parameters": {}})
    creds = {
        "CLASSIFY_URL": f"https://{CLASSIFY_HOST}",
        "CLASSIFY_API_KEY": "sentinel-classify-key",
    }
    result = mcp_tools._credentials_check(_credentials=creds)
    data = result["_data"]
    assert data["credential_test"] == "ok"
    assert data["bundles"]["classify"]["credential_test"] == "ok"
    assert data["bundles"]["forecaster"]["credential_test"] == "not_configured"
    assert data["bundles"]["llm_factory"]["credential_test"] == "not_configured"
    # No upstream traffic for unconfigured bundles.
    urls = {c["url"] for c in rmock.calls}
    assert urls == {CLASSIFY_PROBE_URL}


def test_partial_bundle_counts_as_not_configured(rmock: HttpMock) -> None:
    """URL without key (or vice versa) is not a configured bundle."""
    rmock.add("GET", CLASSIFY_PROBE_URL, status=200, json={"parameters": {}})
    creds = {
        "CLASSIFY_URL": f"https://{CLASSIFY_HOST}",
        "CLASSIFY_API_KEY": "sentinel-classify-key",
        "FORECASTER_URL": f"https://{FORECASTER_HOST}",  # no FORECASTER_API_KEY
    }
    result = mcp_tools._credentials_check(_credentials=creds)
    assert result["_data"]["bundles"]["forecaster"]["credential_test"] == "not_configured"
    assert result["_data"]["credential_test"] == "ok"


def test_nothing_configured_is_unexpected() -> None:
    result = mcp_tools._credentials_check(_credentials={})
    data = result["_data"]
    assert data["credential_test"] == "unexpected"
    assert "configured" in data["detail"].lower()
    assert all(
        v["credential_test"] == "not_configured" for v in data["bundles"].values()
    )


def test_no_credentials_kwarg_at_all() -> None:
    result = mcp_tools._credentials_check()
    assert result["_data"]["credential_test"] == "unexpected"


# ---------------------------------------------------------------------------
# Aggregate precedence
# ---------------------------------------------------------------------------


def test_auth_failed_outranks_ok(rmock: HttpMock) -> None:
    rmock.add("GET", CLASSIFY_PROBE_URL, status=200, json={"parameters": {}})
    rmock.add("GET", FORECASTER_PROBE_URL, status=401, body=b"{}")
    rmock.add("GET", LLM_FACTORY_PROBE_URL, status=200, json={"data": []})
    result = mcp_tools._credentials_check(_credentials=ALL_CREDS)
    data = result["_data"]
    assert data["bundles"]["forecaster"]["credential_test"] == "auth_failed"
    assert data["credential_test"] == "auth_failed"
    # The detail names every bundle's verdict so the save-time response is
    # actionable.
    assert "CLASSify: ok" in data["detail"]
    assert "Forecaster: auth_failed" in data["detail"]
    assert "LLM-Factory: ok" in data["detail"]


def test_all_unreachable_aggregates_unreachable() -> None:
    import requests
    with patch("requests.request", side_effect=requests.ConnectionError("nope")):
        result = mcp_tools._credentials_check(_credentials=ALL_CREDS)
    assert result["_data"]["credential_test"] == "unreachable"
    assert all(
        v["credential_test"] == "unreachable"
        for v in result["_data"]["bundles"].values()
    )


def test_unreachable_outranks_ok(rmock: HttpMock) -> None:
    """A configured-but-unroutable bundle degrades the aggregate to unreachable."""
    rmock.add("GET", CLASSIFY_PROBE_URL, status=200, json={"parameters": {}})
    rmock.add("GET", LLM_FACTORY_PROBE_URL, status=200, json={"data": []})
    creds = dict(ALL_CREDS)
    creds["FORECASTER_URL"] = "https://not-in-dns.example.invalid"
    result = mcp_tools._credentials_check(_credentials=creds)
    data = result["_data"]
    assert data["bundles"]["classify"]["credential_test"] == "ok"
    assert data["bundles"]["forecaster"]["credential_test"] in ("unreachable", "unexpected")
    assert data["credential_test"] == data["bundles"]["forecaster"]["credential_test"]


# ---------------------------------------------------------------------------
# Registry exposure + secrecy
# ---------------------------------------------------------------------------


def test_registered_once_in_union_registry() -> None:
    entry = mcp_tools.TOOL_REGISTRY["_credentials_check"]
    assert entry["function"] is mcp_tools._credentials_check
    assert entry["scope"] == "tools:read"
    assert entry["input_schema"] == {
        "type": "object", "properties": {}, "additionalProperties": True,
    }


def test_no_api_keys_in_response(rmock: HttpMock) -> None:
    _add_ok_routes(rmock)
    result = mcp_tools._credentials_check(_credentials=ALL_CREDS)
    serialized = json.dumps(result, default=str)
    assert "sentinel-classify-key" not in serialized
    assert "sentinel-forecaster-key" not in serialized
    assert "sentinel-llm-key" not in serialized
