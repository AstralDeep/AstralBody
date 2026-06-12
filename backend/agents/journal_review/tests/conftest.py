"""Shared fixtures for the Journal Review agent test suite.

Follows the web_research/summarizer test pattern: ``HttpMock`` stubs the
single ``requests.request`` call site used by ``shared.external_http``
(which also proves all egress goes through the gated helper — the old
direct ``requests.get`` path would bypass the mock entirely); DNS is
stubbed so the SSRF guard resolves the API hosts deterministically.
No network anywhere.
"""
import socket
from unittest.mock import patch

import pytest

from agents.journal_review import mcp_tools
from shared.tests._http_mock import HttpMock

# Public hosts the agent talks to (resolve to a public address in tests).
SAFE_HOSTS = {"api.openalex.org", "api.crossref.org"}

EHJ_ID = "https://openalex.org/S64187185"


@pytest.fixture
def rmock():
    with HttpMock() as m:
        yield m


@pytest.fixture(autouse=True)
def stub_dns():
    def _fake(host, *_a, **_kw):
        if host in SAFE_HOSTS:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.0.1", 0))]
        raise socket.gaierror(host)
    with patch("socket.getaddrinfo", _fake):
        yield


@pytest.fixture(autouse=True)
def clear_cache():
    """The module keeps a 10-minute response cache; isolate every test."""
    mcp_tools._CACHE.clear()
    yield
    mcp_tools._CACHE.clear()


def make_source(**over):
    """A realistic OpenAlex source record (European Heart Journal-ish).

    The real EHJ has a 2-yr mean citedness around 35 — the value OpenAlex
    itself publishes, which is what the agent must surface (never a
    home-grown "impact factor" approximation).
    """
    src = {
        "id": EHJ_ID,
        "display_name": "European Heart Journal",
        "issn": ["0195-668X", "1522-9645"],
        "issn_l": "0195-668X",
        "host_organization_name": "Oxford University Press",
        "type": "journal",
        "is_oa": False,
        "apc_usd": 4990,
        "homepage_url": "https://academic.oup.com/eurheartj",
        "works_count": 35000,
        "cited_by_count": 900000,
        "country_code": "GB",
        "summary_stats": {
            "h_index": 350,
            "i10_index": 12000,
            "2yr_mean_citedness": 35.456,
        },
        "counts_by_year": [
            {"year": 2026, "works_count": 1200, "cited_by_count": 90000},
            {"year": 2025, "works_count": 1300, "cited_by_count": 95000},
        ],
        "topics": [
            {"display_name": "Cardiology"},
            {"display_name": "Heart Failure"},
        ],
    }
    src.update(over)
    return src


def make_works_payload(source_ids):
    """An OpenAlex /works payload whose papers were published in source_ids."""
    return {
        "results": [
            {"primary_location": {"source": {"id": sid, "type": "journal"}}}
            for sid in source_ids
        ]
    }
