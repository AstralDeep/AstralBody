"""FR-019 regression test (feature 054 successor of the 006 FR-009 rule):
no runtime fallback ACROSS credential contexts, in either direction.

Feature 006's rule was "a user's failed call never silently retries on the
operator `.env` default". Feature 054 removed the operator default entirely;
the successor invariant is stricter and structural:

* A **user-context** resolution (live user socket) reads ONLY the caller's
  persisted ``user_llm_config`` record. When that record is absent, the
  resolution raises :class:`LLMUnavailable` — it must NEVER consult or
  consume the admin-managed system record, even when one exists.
* A **system-context** resolution (``websocket is None`` / scheduled-turn
  ``VirtualWebSocket``) reads ONLY the system record and never any user's.

The tests bind the REAL ``Orchestrator._resolve_llm_client_for`` /
``_llm_context_user_id`` onto a bare instance with an instrumented store,
so the invariant is proven against the shipped resolution code without a
database or network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_config.client_factory import build_llm_client
from llm_config.types import CredentialSource, LLMUnavailable
from llm_config.user_store import PersistedLLMConfig
from orchestrator.orchestrator import Orchestrator


def _system_config() -> PersistedLLMConfig:
    return PersistedLLMConfig(
        provider="custom",
        base_url="https://system.example/v1",
        model="sys-model",
        api_key="sk-system1234567890abcdef",
    )


def _user_config() -> PersistedLLMConfig:
    return PersistedLLMConfig(
        provider="custom",
        base_url="https://user.example/v1",
        model="user-model",
        api_key="sk-userkey1234567890abcdef",
    )


def _bare_orch(*, user_record=None, system_record=None):
    """A bare Orchestrator with the real resolver and a spy store."""
    orch = Orchestrator.__new__(Orchestrator)
    orch._CredentialSource = CredentialSource
    orch._LLMUnavailable = LLMUnavailable
    orch._build_llm_client = build_llm_client
    orch.ui_sessions = {}
    store = MagicMock()
    store.get = AsyncMock(return_value=user_record)
    store.get_system = AsyncMock(return_value=system_record)
    store.pop_discard_note = MagicMock(return_value=None)
    orch._llm_store = store
    return orch


def _user_ws(orch, user_id="u1"):
    ws = MagicMock()
    orch.ui_sessions[ws] = {"sub": user_id, "preferred_username": user_id}
    return ws


@pytest.mark.asyncio
async def test_user_context_without_record_never_falls_back_to_system():
    """Seed ONLY the system record: resolving for a live user socket raises
    LLMUnavailable and never even READS the system record."""
    orch = _bare_orch(user_record=None, system_record=_system_config())
    ws = _user_ws(orch)

    with pytest.raises(LLMUnavailable):
        await orch._resolve_llm_client_for(ws)

    orch._llm_store.get.assert_awaited_once_with("u1")
    orch._llm_store.get_system.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_context_resolves_only_the_callers_record():
    """With a user record present, resolution is tagged USER and carries the
    user's endpoint/model — the system record stays untouched."""
    orch = _bare_orch(user_record=_user_config(),
                      system_record=_system_config())
    ws = _user_ws(orch)

    client, source, resolved = await orch._resolve_llm_client_for(ws)

    assert source == CredentialSource.USER
    assert resolved.base_url == "https://user.example/v1"
    assert resolved.model == "user-model"
    orch._llm_store.get_system.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_context_never_reads_user_records():
    """websocket=None (background/system work) resolves the SYSTEM record and
    never touches any per-user record."""
    orch = _bare_orch(user_record=_user_config(),
                      system_record=_system_config())

    client, source, resolved = await orch._resolve_llm_client_for(None)

    assert source == CredentialSource.SYSTEM
    assert resolved.base_url == "https://system.example/v1"
    orch._llm_store.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_context_without_record_is_unavailable_not_user_fallback():
    """Seed ONLY a user record: a system-context resolution raises
    LLMUnavailable rather than borrowing any user's credentials."""
    orch = _bare_orch(user_record=_user_config(), system_record=None)

    with pytest.raises(LLMUnavailable):
        await orch._resolve_llm_client_for(None)

    orch._llm_store.get.assert_not_awaited()


def test_factory_refuses_retired_operator_default_source():
    """No new call may carry the retired OPERATOR_DEFAULT source — the
    factory itself rejects it, making the old fallback unrepresentable."""
    with pytest.raises(ValueError):
        build_llm_client(_user_config(), CredentialSource.OPERATOR_DEFAULT)


@pytest.mark.asyncio
async def test_scheduled_turn_virtualwebsocket_is_system_context():
    """A scheduled-turn VirtualWebSocket resolves the SYSTEM record (never a
    user record), matching the runner's documented context rule."""
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket

    orch = _bare_orch(user_record=_user_config(),
                      system_record=_system_config())
    vws = VirtualWebSocket(BackgroundTask(task_id="t1", chat_id="", user_id="u1"))

    client, source, resolved = await orch._resolve_llm_client_for(vws)

    assert source == CredentialSource.SYSTEM
    orch._llm_store.get.assert_not_awaited()
