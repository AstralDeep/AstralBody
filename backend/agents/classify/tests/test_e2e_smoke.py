"""End-to-end smoke test for CLASSify against the live service (T046).

Skipped by default. Enable by exporting:
    CLASSIFY_E2E_URL=https://classify.ai.uky.edu/
    CLASSIFY_E2E_API_KEY=<your real key>

The test only invokes a read-only call (`get_ml_options` via
`_credentials_check`) so it cannot spawn upstream training jobs accidentally.
"""
import os

import pytest

from agents.classify import mcp_tools

E2E_URL = os.getenv("CLASSIFY_E2E_URL")
E2E_KEY = os.getenv("CLASSIFY_E2E_API_KEY")


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="CLASSIFY_E2E_URL and CLASSIFY_E2E_API_KEY env vars must be set",
)
def test_credentials_check_against_live_service() -> None:
    creds = {"CLASSIFY_URL": E2E_URL, "CLASSIFY_API_KEY": E2E_KEY}
    result = mcp_tools._credentials_check(_credentials=creds)
    assert result["credential_test"] == "ok", (
        f"Live CLASSify probe did not return 'ok': {result}"
    )


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="CLASSIFY_E2E_URL and CLASSIFY_E2E_API_KEY env vars must be set",
)
def test_get_ml_options_returns_payload() -> None:
    creds = {"CLASSIFY_URL": E2E_URL, "CLASSIFY_API_KEY": E2E_KEY}
    result = mcp_tools.get_ml_options(_credentials=creds)
    assert "_data" in result
    assert result["_ui_components"][0].get("variant") != "error"
