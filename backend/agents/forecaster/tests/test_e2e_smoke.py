"""End-to-end smoke test for Forecaster against the live service (T047).

Skipped by default. Enable by exporting:
    FORECASTER_E2E_URL=https://forecaster.ai.uky.edu/
    FORECASTER_E2E_API_KEY=<your real key>
"""
import os

import pytest

from agents.forecaster import mcp_tools

E2E_URL = os.getenv("FORECASTER_E2E_URL")
E2E_KEY = os.getenv("FORECASTER_E2E_API_KEY")


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="FORECASTER_E2E_URL and FORECASTER_E2E_API_KEY env vars must be set",
)
def test_credentials_check_against_live_service() -> None:
    creds = {"FORECASTER_URL": E2E_URL, "FORECASTER_API_KEY": E2E_KEY}
    result = mcp_tools._credentials_check(_credentials=creds)
    assert result["credential_test"] == "ok", (
        f"Live Forecaster probe did not return 'ok': {result}"
    )
