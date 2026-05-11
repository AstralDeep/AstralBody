"""End-to-end smoke test for LLM-Factory against the live service (T048).

Skipped by default. Enable by exporting:
    LLM_FACTORY_E2E_URL=https://llm-factory.ai.uky.edu/
    LLM_FACTORY_E2E_API_KEY=<your real key>
"""
import os

import pytest

from agents.llm_factory import mcp_tools

E2E_URL = os.getenv("LLM_FACTORY_E2E_URL")
E2E_KEY = os.getenv("LLM_FACTORY_E2E_API_KEY")


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="LLM_FACTORY_E2E_URL and LLM_FACTORY_E2E_API_KEY env vars must be set",
)
def test_credentials_check_against_live_service() -> None:
    creds = {"LLM_FACTORY_URL": E2E_URL, "LLM_FACTORY_API_KEY": E2E_KEY}
    result = mcp_tools._credentials_check(_credentials=creds)
    assert result["credential_test"] == "ok", (
        f"Live LLM-Factory probe did not return 'ok': {result}"
    )


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="LLM_FACTORY_E2E_URL and LLM_FACTORY_E2E_API_KEY env vars must be set",
)
def test_list_models_returns_payload() -> None:
    creds = {"LLM_FACTORY_URL": E2E_URL, "LLM_FACTORY_API_KEY": E2E_KEY}
    result = mcp_tools.list_models(_credentials=creds)
    assert "_data" in result
    assert "models" in result["_data"]
