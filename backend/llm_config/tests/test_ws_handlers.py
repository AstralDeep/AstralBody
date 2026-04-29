"""T031 + T032 — register_ui llm_config seeding + ws_handlers tests.

Exercises:

* ``populate_from_register_ui`` — happy path, malformed payload silently
  ignored, audit emitted on success.
* ``handle_llm_config_set`` — happy path, malformed payload returns
  llm_config_invalid error and does NOT mutate state, ack on success.
* ``handle_llm_config_clear`` — clears, audits only when prior entry
  existed, acks unconditionally.

API key MUST never appear in any captured audit-event payload.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_config.session_creds import SessionCredentialStore
from llm_config.ws_handlers import (
    handle_llm_config_clear,
    handle_llm_config_set,
    populate_from_register_ui,
)


@pytest.fixture
def fake_recorder():
    rec = MagicMock()
    rec.record = AsyncMock()
    return rec


@pytest.fixture
def safe_send():
    return AsyncMock()


@pytest.fixture
def store():
    return SessionCredentialStore()


def _ws():
    """A unique-id sentinel for id(websocket) keying. The store keys on
    id() so any object will do."""
    return object()


def _captured(rec):
    return [c.args[0] for c in rec.record.await_args_list]


def _no_api_key_in(events, plaintext):
    for ev in events:
        body = json.dumps({
            "inputs_meta": ev.inputs_meta,
            "outputs_meta": ev.outputs_meta,
            "description": ev.description,
        })
        assert plaintext not in body, f"API key leaked into audit payload: {body}"


# ============================================================================
# populate_from_register_ui
# ============================================================================


@pytest.mark.asyncio
async def test_register_ui_with_valid_llm_config_seeds_store(store, fake_recorder):
    ws = _ws()
    await populate_from_register_ui(
        websocket=ws,
        llm_config={
            "api_key": "sk-realkey1234567890abcd",
            "base_url": "https://x.example/v1",
            "model": "model-a",
        },
        actor_user_id="u1",
        auth_principal="u1",
        creds_store=store,
        recorder=fake_recorder,
    )
    creds = store.get(id(ws))
    assert creds is not None
    assert creds.api_key == "sk-realkey1234567890abcd"
    assert creds.base_url == "https://x.example/v1"
    assert creds.model == "model-a"

    # Exactly one llm_config_change(action=created) emitted, no key in payload.
    events = _captured(fake_recorder)
    assert len(events) == 1
    assert events[0].event_class == "llm_config_change"
    assert events[0].inputs_meta["action"] == "created"
    _no_api_key_in(events, "sk-realkey1234567890abcd")


@pytest.mark.asyncio
async def test_register_ui_partial_payload_silently_ignored(store, fake_recorder):
    ws = _ws()
    await populate_from_register_ui(
        websocket=ws,
        llm_config={"api_key": "sk-x", "base_url": "", "model": "m"},
        actor_user_id="u1",
        auth_principal="u1",
        creds_store=store,
        recorder=fake_recorder,
    )
    assert store.get(id(ws)) is None
    assert _captured(fake_recorder) == []


@pytest.mark.asyncio
async def test_register_ui_no_llm_config_is_noop(store, fake_recorder):
    ws = _ws()
    await populate_from_register_ui(
        websocket=ws, llm_config=None,
        actor_user_id="u1", auth_principal="u1",
        creds_store=store, recorder=fake_recorder,
    )
    assert store.get(id(ws)) is None
    assert _captured(fake_recorder) == []


# ============================================================================
# handle_llm_config_set
# ============================================================================


@pytest.mark.asyncio
async def test_set_happy_path_sends_ack_and_audits_created(store, fake_recorder, safe_send):
    ws = _ws()
    await handle_llm_config_set(
        safe_send=safe_send,
        websocket=ws,
        config={
            "api_key": "sk-mykey1234567890abcdef",
            "base_url": "https://api.example/v1",
            "model": "m",
        },
        actor_user_id="u",
        auth_principal="u",
        creds_store=store,
        recorder=fake_recorder,
    )
    assert store.get(id(ws)).api_key == "sk-mykey1234567890abcdef"
    # Ack sent
    safe_send.assert_called_once()
    sent = json.loads(safe_send.call_args[0][1])
    assert sent == {"type": "llm_config_ack", "ok": True}
    # Audit created (no prior entry on this socket)
    events = _captured(fake_recorder)
    assert len(events) == 1
    assert events[0].inputs_meta["action"] == "created"
    _no_api_key_in(events, "sk-mykey1234567890abcdef")


@pytest.mark.asyncio
async def test_set_replaces_emits_updated(store, fake_recorder, safe_send):
    ws = _ws()
    store.set(id(ws), "old-key-1234567890abcdef", "https://old/v1", "old-model")
    await handle_llm_config_set(
        safe_send=safe_send, websocket=ws,
        config={"api_key": "new-key-1234567890abcd", "base_url": "https://new/v1", "model": "new-model"},
        actor_user_id="u", auth_principal="u",
        creds_store=store, recorder=fake_recorder,
    )
    events = _captured(fake_recorder)
    assert events[0].inputs_meta["action"] == "updated"
    assert events[0].inputs_meta["model"] == "new-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [
    {"api_key": "", "base_url": "https://x", "model": "m"},
    {"api_key": "k", "base_url": "", "model": "m"},
    {"api_key": "k", "base_url": "https://x", "model": ""},
    {},
    "not-a-dict",
])
async def test_set_malformed_returns_error_and_does_not_mutate(
    store, fake_recorder, safe_send, config
):
    ws = _ws()
    await handle_llm_config_set(
        safe_send=safe_send, websocket=ws,
        config=config,  # type: ignore[arg-type]
        actor_user_id="u", auth_principal="u",
        creds_store=store, recorder=fake_recorder,
    )
    # No mutation
    assert store.get(id(ws)) is None
    # No audit emission
    assert _captured(fake_recorder) == []
    # error reply sent
    sent = json.loads(safe_send.call_args[0][1])
    assert sent["type"] == "error"
    assert sent["code"] == "llm_config_invalid"


# ============================================================================
# handle_llm_config_clear
# ============================================================================


@pytest.mark.asyncio
async def test_clear_with_prior_entry_emits_audit(store, fake_recorder, safe_send):
    ws = _ws()
    store.set(id(ws), "k1234567890abcdefghij", "https://x/v1", "m")
    await handle_llm_config_clear(
        safe_send=safe_send, websocket=ws,
        actor_user_id="u", auth_principal="u",
        creds_store=store, recorder=fake_recorder,
    )
    assert store.get(id(ws)) is None
    events = _captured(fake_recorder)
    assert len(events) == 1
    assert events[0].inputs_meta["action"] == "cleared"
    # Cleared events do NOT include base_url/model (we cleared first)
    assert "base_url" not in events[0].inputs_meta
    sent = json.loads(safe_send.call_args[0][1])
    assert sent == {"type": "llm_config_ack", "ok": True}


@pytest.mark.asyncio
async def test_clear_without_prior_entry_is_silent_noop_but_acks(store, fake_recorder, safe_send):
    ws = _ws()
    await handle_llm_config_clear(
        safe_send=safe_send, websocket=ws,
        actor_user_id="u", auth_principal="u",
        creds_store=store, recorder=fake_recorder,
    )
    # No audit (we did not have a prior entry, nothing to record)
    assert _captured(fake_recorder) == []
    # But still ack — clients should not have to special-case this
    sent = json.loads(safe_send.call_args[0][1])
    assert sent == {"type": "llm_config_ack", "ok": True}
