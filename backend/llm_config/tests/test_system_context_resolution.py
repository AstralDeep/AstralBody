"""Feature 054 — system-context credential resolution (factory level).

Successor to the retired ``test_background_jobs_use_operator_default.py``
(feature 006 FR-011): background/server-initiated work now uses the
admin-managed SYSTEM record exclusively — the operator-default env path
is gone. Orchestrator-level resolution (websocket → context) is covered
in ``test_call_llm_credential_resolution.py``; this file stays at the
store + factory level.
"""
from __future__ import annotations

import pytest

from llm_config.audit_events import record_llm_call
from llm_config.client_factory import build_llm_client
from llm_config.types import CredentialSource, LLMUnavailable, ResolvedConfig

SYSTEM_KEY = "sk-system-abcdef1234567890abcdef"


def _seed_system(store):
    store.set_system_sync(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        api_key=SYSTEM_KEY,
        updated_by="admin-1",
    )


def test_system_record_builds_system_client(store):
    _seed_system(store)
    cfg = store.get_system_sync()
    client, source, resolved = build_llm_client(cfg, CredentialSource.SYSTEM)
    assert source is CredentialSource.SYSTEM
    assert client.api_key == SYSTEM_KEY
    assert resolved.base_url == "https://api.openai.com/v1"
    assert resolved.model == "gpt-4o"


def test_absent_system_record_raises_llmunavailable(store):
    """No admin credential ⇒ honest degradation, never a silent success
    (US4-AS1/AS2, FR-020)."""
    assert store.get_system_sync() is None
    with pytest.raises(LLMUnavailable, match="system credential"):
        build_llm_client(None, CredentialSource.SYSTEM)


def test_system_context_never_borrows_a_user_record(store):
    """Even with users fully configured, the system context resolves the
    system table only — absent ⇒ LLMUnavailable (no fallback)."""
    store.set_sync("alice", provider="custom",
                   base_url="https://userA.example/v1", model="a-model",
                   api_key="sk-userA-1234567890abcdef")
    store.set_sync("bob", provider="custom",
                   base_url="https://userB.example/v1", model="b-model",
                   api_key="sk-userB-1234567890abcdef")
    assert store.get_system_sync() is None
    with pytest.raises(LLMUnavailable):
        build_llm_client(store.get_system_sync(), CredentialSource.SYSTEM)


def test_cleared_system_record_regates_next_resolution(store):
    _seed_system(store)
    assert store.get_system_sync() is not None
    assert store.clear_system_sync() is True
    with pytest.raises(LLMUnavailable):
        build_llm_client(store.get_system_sync(), CredentialSource.SYSTEM)


async def test_system_call_audits_credential_source_system(fake_recorder):
    """FR-021: the llm_call audit vocabulary handles SYSTEM — value
    "system", description labelled "system credential"."""
    await record_llm_call(
        fake_recorder,
        actor_user_id="system",
        auth_principal="system",
        feature="scheduled_job",
        credential_source=CredentialSource.SYSTEM,
        resolved=ResolvedConfig(base_url="https://api.openai.com/v1",
                                model="gpt-4o"),
        total_tokens=128,
        outcome="success",
    )
    ev = fake_recorder.record.await_args.args[0]
    assert ev.event_class == "llm_call"
    assert ev.inputs_meta["credential_source"] == "system"
    assert "system credential" in ev.description
    assert SYSTEM_KEY not in ev.model_dump_json()
