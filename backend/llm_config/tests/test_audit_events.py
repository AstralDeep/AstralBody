"""T016 — audit-event helper unit tests.

Verifies that the helpers reject any payload that contains an API key,
either as a literal ``api_key`` field or as a key-shaped substring in a
free-form value, and that they emit the right shape via the recorder.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_config.audit_events import (
    _assert_no_api_key,
    record_llm_call,
    record_llm_config_change,
    record_llm_unconfigured,
)
from llm_config.types import CredentialSource, ResolvedConfig


class TestAssertNoApiKey:
    def test_raises_on_literal_api_key_field(self):
        with pytest.raises(ValueError, match="api_key"):
            _assert_no_api_key({"api_key": "sk-anything"})

    def test_raises_on_nested_api_key_field(self):
        with pytest.raises(ValueError, match="api_key"):
            _assert_no_api_key({"outer": {"api_key": "sk-anything"}})

    def test_raises_on_openai_key_substring_in_free_text(self):
        with pytest.raises(ValueError, match="API key"):
            _assert_no_api_key(
                {"description": "user said: my key is sk-1234567890abcdef1234"}
            )

    def test_accepts_clean_payload(self):
        _assert_no_api_key({"action": "created", "base_url": "https://x.example/v1", "model": "m"})

    def test_short_strings_starting_with_sk_dash_are_not_flagged(self):
        # The pattern requires {20,} chars after the prefix to avoid
        # over-zealous matches on benign words like "sk-test".
        _assert_no_api_key({"note": "sk-test"})


@pytest.fixture
def fake_recorder():
    rec = MagicMock()
    rec.record = AsyncMock()
    return rec


def _captured_events(rec) -> List:
    return [call.args[0] for call in rec.record.await_args_list]


class TestRecordLLMConfigChange:
    @pytest.mark.asyncio
    async def test_created_action(self, fake_recorder):
        await record_llm_config_change(
            fake_recorder,
            actor_user_id="u1",
            auth_principal="u1",
            action="created",
            base_url="https://x.example/v1",
            model="model-a",
            transport="ws",
        )
        ev = _captured_events(fake_recorder)[0]
        assert ev.event_class == "llm_config_change"
        assert ev.action_type == "llm_config.created"
        assert ev.outcome == "success"
        assert ev.inputs_meta == {
            "action": "created",
            "transport": "ws",
            "base_url": "https://x.example/v1",
            "model": "model-a",
        }
        assert ev.outputs_meta == {}

    @pytest.mark.asyncio
    async def test_tested_failure_records_outcome_failure(self, fake_recorder):
        await record_llm_config_change(
            fake_recorder,
            actor_user_id="u1",
            auth_principal="u1",
            action="tested",
            base_url="x",
            model="m",
            transport="rest",
            result="failure",
            error_class="auth_failed",
        )
        ev = _captured_events(fake_recorder)[0]
        assert ev.outcome == "failure"
        assert ev.outputs_meta == {"result": "failure", "error_class": "auth_failed"}

    @pytest.mark.asyncio
    async def test_cleared_action_omits_base_url_when_none(self, fake_recorder):
        await record_llm_config_change(
            fake_recorder,
            actor_user_id="u1",
            auth_principal="u1",
            action="cleared",
            base_url=None,
            model=None,
            transport="ws",
        )
        ev = _captured_events(fake_recorder)[0]
        assert "base_url" not in ev.inputs_meta
        assert "model" not in ev.inputs_meta

    @pytest.mark.asyncio
    async def test_unknown_action_raises(self, fake_recorder):
        with pytest.raises(ValueError):
            await record_llm_config_change(
                fake_recorder,
                actor_user_id="u",
                auth_principal="u",
                action="rotated",  # not in the allowed set
                base_url="x",
                model="m",
                transport="ws",
            )

    @pytest.mark.asyncio
    async def test_tested_requires_result(self, fake_recorder):
        with pytest.raises(ValueError):
            await record_llm_config_change(
                fake_recorder,
                actor_user_id="u",
                auth_principal="u",
                action="tested",
                base_url="x",
                model="m",
                transport="rest",
                result=None,
            )


class TestRecordLLMUnconfigured:
    @pytest.mark.asyncio
    async def test_emits_failure_event(self, fake_recorder):
        await record_llm_unconfigured(
            fake_recorder,
            actor_user_id="u1",
            auth_principal="u1",
            feature="tool_dispatch",
        )
        ev = _captured_events(fake_recorder)[0]
        assert ev.event_class == "llm_unconfigured"
        assert ev.outcome == "failure"
        assert ev.inputs_meta == {
            "feature": "tool_dispatch",
            "reason": "no_user_config_no_env_default",
        }


class TestRecordLLMCall:
    @pytest.mark.asyncio
    async def test_user_credential_source_success(self, fake_recorder):
        await record_llm_call(
            fake_recorder,
            actor_user_id="u1",
            auth_principal="u1",
            feature="tool_dispatch",
            credential_source=CredentialSource.USER,
            resolved=ResolvedConfig(base_url="https://x.example/v1", model="m"),
            total_tokens=247,
            outcome="success",
        )
        ev = _captured_events(fake_recorder)[0]
        assert ev.event_class == "llm_call"
        assert ev.inputs_meta["credential_source"] == "user"
        assert ev.inputs_meta["base_url"] == "https://x.example/v1"
        assert ev.outputs_meta == {"total_tokens": 247}
        assert ev.outcome == "success"

    @pytest.mark.asyncio
    async def test_operator_default_failure_records_error_class(self, fake_recorder):
        await record_llm_call(
            fake_recorder,
            actor_user_id="u1",
            auth_principal="u1",
            feature="tool_summary",
            credential_source=CredentialSource.OPERATOR_DEFAULT,
            resolved=ResolvedConfig(base_url="https://x", model="m"),
            total_tokens=None,
            outcome="failure",
            upstream_error_class="rate_limit",
        )
        ev = _captured_events(fake_recorder)[0]
        assert ev.outcome == "failure"
        assert ev.outputs_meta == {"upstream_error_class": "rate_limit"}
        assert "total_tokens" not in ev.outputs_meta

    @pytest.mark.asyncio
    async def test_unknown_outcome_raises(self, fake_recorder):
        with pytest.raises(ValueError):
            await record_llm_call(
                fake_recorder,
                actor_user_id="u",
                auth_principal="u",
                feature="x",
                credential_source=CredentialSource.USER,
                resolved=ResolvedConfig(base_url="x", model="m"),
                total_tokens=None,
                outcome="partial",
            )
