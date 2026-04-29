"""T033 — POST /api/llm/test integration tests.

Builds a minimal FastAPI app with the llm_router mounted, stubs:

* The Keycloak JWT dependency to return a fixed test user.
* The orchestrator dependency to provide an audit recorder.
* The OpenAI client constructor to return a controllable fake.

Then verifies the response shape, error_class taxonomy, and audit emission.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_config.api import llm_router


@pytest.fixture
def fake_recorder():
    rec = MagicMock()
    rec.record = AsyncMock()
    return rec


@pytest.fixture
def app(fake_recorder):
    app = FastAPI()
    app.include_router(llm_router)
    # Minimal orchestrator stand-in — the endpoint reads `audit_recorder`.
    app.state.orchestrator = SimpleNamespace(audit_recorder=fake_recorder)
    # Override Keycloak dependencies
    from orchestrator.auth import require_user_id, get_current_user_payload
    app.dependency_overrides[require_user_id] = lambda: "test_user"
    app.dependency_overrides[get_current_user_payload] = lambda: {
        "sub": "test_user",
        "preferred_username": "test_user",
    }
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _success_response():
    """A minimal stand-in for an OpenAI ChatCompletion response."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok"),
                index=0,
                finish_reason="length",
            )
        ],
        usage=SimpleNamespace(total_tokens=1, prompt_tokens=1, completion_tokens=0),
    )


# ============================================================================
# Validation
# ============================================================================


def test_missing_field_returns_422(client):
    r = client.post("/api/llm/test", json={"api_key": "x", "base_url": "https://x/v1"})
    assert r.status_code == 422


def test_non_http_base_url_returns_422(client):
    r = client.post("/api/llm/test", json={
        "api_key": "x", "base_url": "ftp://x/v1", "model": "m",
    })
    assert r.status_code == 422


def test_empty_after_trim_returns_422(client):
    r = client.post("/api/llm/test", json={
        "api_key": "  ", "base_url": "https://x/v1", "model": "m",
    })
    assert r.status_code == 422


# ============================================================================
# Success path
# ============================================================================


def test_success_returns_ok_true(client, fake_recorder):
    fake = MagicMock()
    fake.chat.completions.create = MagicMock(return_value=_success_response())
    with patch("llm_config.api.OpenAI", return_value=fake):
        r = client.post("/api/llm/test", json={
            "api_key": "sk-realkey1234567890abcd",
            "base_url": "https://x.example/v1",
            "model": "model-a",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model"] == "model-a"
    assert body["error_class"] is None
    assert body["latency_ms"] is not None
    # Audit emitted with action=tested, result=success
    assert fake_recorder.record.await_count == 1
    ev = fake_recorder.record.await_args.args[0]
    assert ev.event_class == "llm_config_change"
    assert ev.inputs_meta["action"] == "tested"
    assert ev.outputs_meta["result"] == "success"
    # API key NEVER in payload
    serialised = ev.model_dump_json()
    assert "sk-realkey1234567890abcd" not in serialised


# ============================================================================
# Failure classification taxonomy
# ============================================================================


@pytest.mark.parametrize("exc_message,expected_class", [
    ("Incorrect API key provided. (HTTP 401)", "auth_failed"),
    ("model 'gpt-9' does not exist (HTTP 404)", "model_not_found"),
    ("Connection refused", "transport_error"),
    ("Read timeout", "transport_error"),
    ("response missing 'choices' — not OpenAI-compatible", "contract_violation"),
])
def test_failure_classifies_error_class(client, fake_recorder, exc_message, expected_class):
    fake = MagicMock()
    fake.chat.completions.create = MagicMock(side_effect=Exception(exc_message))
    with patch("llm_config.api.OpenAI", return_value=fake):
        r = client.post("/api/llm/test", json={
            "api_key": "sk-x1234567890abcdefghij",
            "base_url": "https://x.example/v1",
            "model": "m",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error_class"] == expected_class
    assert body["upstream_message"] == exc_message
    # Audit emitted with result=failure
    ev = fake_recorder.record.await_args.args[0]
    assert ev.outputs_meta["result"] == "failure"
    assert ev.outputs_meta["error_class"] == expected_class


def test_contract_violation_when_choices_missing(client, fake_recorder):
    """Endpoint that returns 200 but without the OpenAI-compatible
    ``choices`` shape should be classified as contract_violation, not
    success."""
    fake = MagicMock()
    bogus = SimpleNamespace(choices=None)  # not OpenAI-compatible
    fake.chat.completions.create = MagicMock(return_value=bogus)
    with patch("llm_config.api.OpenAI", return_value=fake):
        r = client.post("/api/llm/test", json={
            "api_key": "sk-x1234567890abcdefghij",
            "base_url": "https://x.example/v1",
            "model": "m",
        })
    body = r.json()
    assert body["ok"] is False
    assert body["error_class"] == "contract_violation"


# ============================================================================
# Defence in depth — API key never recorded under ANY action
# ============================================================================


def test_failure_audit_does_not_contain_api_key(client, fake_recorder):
    fake = MagicMock()
    fake.chat.completions.create = MagicMock(side_effect=Exception("arbitrary error"))
    with patch("llm_config.api.OpenAI", return_value=fake):
        r = client.post("/api/llm/test", json={
            "api_key": "sk-mostsensitive1234567890abcdef",
            "base_url": "https://x.example/v1",
            "model": "m",
        })
    assert r.status_code == 200
    ev = fake_recorder.record.await_args.args[0]
    serialised = ev.model_dump_json()
    assert "sk-mostsensitive1234567890abcdef" not in serialised
