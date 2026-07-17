"""Real tests for the three companion wirings:
  * voice/aom render-target dispatch (C-D4/C-D5) via target_for_profile,
  * transaction_token mint↔verify round-trip (C-S8) via mint_action_token,
  * model_router on-device lane (C-D6) surfaced as _last_route_ondevice.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _voice_profile():
    from rote.capabilities import DeviceCapabilities, DeviceProfile
    return DeviceProfile._derive(DeviceCapabilities(device_type="voice",
                                                    viewport_width=0, viewport_height=0))


# --------------------------------------------------------------------------- #
# voice / aom render-target dispatch (C-D4 / C-D5)
# --------------------------------------------------------------------------- #

def test_target_for_profile_gating(monkeypatch):
    from webrender import target_for_profile
    vp = _voice_profile()
    monkeypatch.setenv("FF_NATIVE_TARGETS", "false")
    assert target_for_profile(vp) == "web"           # default ⇒ web, unchanged
    monkeypatch.setenv("FF_NATIVE_TARGETS", "true")
    assert target_for_profile(vp) == "voice"          # voice device ⇒ SSML target


def test_target_for_profile_explicit_aom(monkeypatch):
    from webrender import target_for_profile
    monkeypatch.setenv("FF_NATIVE_TARGETS", "true")
    prof = MagicMock()
    prof.render_target = "aom"
    prof.device_type = "browser"
    assert target_for_profile(prof) == "aom"          # explicit AOM target honored


def test_voice_target_renders_ssml():
    from webrender import render_for_target
    out = render_for_target("voice", [{"type": "text", "content": "Hello there"}], _voice_profile())
    assert isinstance(out, str) and out                # voice renderer reachable, emits text
    aom = render_for_target("aom", [{"type": "text", "content": "Hi"}], None)
    assert aom is not None                             # aom renderer reachable


# --------------------------------------------------------------------------- #
# transaction_token mint ↔ verify round-trip (C-S8)
# --------------------------------------------------------------------------- #

def test_mint_action_token_round_trip(monkeypatch):
    monkeypatch.setenv("TXN_TOKEN_KEY", "test-signing-key-123")
    os.environ["OPENAI_API_KEY"] = "test-key"
    from orchestrator.orchestrator import Orchestrator
    from orchestrator import transaction_token as txn

    o = Orchestrator()
    agent, user, tool = "a-1", "u-1", "send_email"
    args = {"to": "bob@example.com", "body": "hi"}

    token = o.mint_action_token(agent, user, tool, args)
    assert token, "mint must issue a token when a signing key is configured"

    store = txn.default_store()
    ok, _ = txn.verify_and_consume(store, token, agent, user, tool, args)
    assert ok is True                                  # the gate accepts the minted token
    ok2, why = txn.verify_and_consume(store, token, agent, user, tool, args)
    assert ok2 is False                                # single-use: replay rejected


# --------------------------------------------------------------------------- #
# model_router on-device lane (C-D6) — _last_route_ondevice is set
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_model_router_ondevice_surfaced(monkeypatch):
    monkeypatch.setenv("FF_MODEL_ROUTER", "true")
    from orchestrator.orchestrator import Orchestrator
    from orchestrator import model_router

    o = await asyncio.to_thread(Orchestrator)
    o._record_llm_call = AsyncMock()
    o._record_llm_unconfigured = AsyncMock()
    # Feature 054: _call_llm resolves the socket user's PERSISTED config
    # (env vars are inert). Seed via the ASYNC set() — it offloads the DB
    # write to a thread (loop-guard safe under LOOP_GUARD_ENFORCE) and primes
    # the store's in-process cache, so the resolution below hits the cache
    # and never touches the to_thread patched to boom further down. Runs
    # BEFORE that patch is installed.
    await o._llm_store.set("companions-user", provider="custom",
                           base_url="http://test.invalid/v1",
                           model="test-model", api_key="test-key")

    def fake_route(feature, *, default_model, device_type=None, device_caps=None):
        return model_router.RouteDecision(model=default_model, tier=1, ondevice=True)

    monkeypatch.setattr("orchestrator.model_router.route", fake_route)

    # Make the actual LLM call fail fast (non-transient) AFTER the router block.
    async def boom(*a, **k):
        raise ValueError("no network in test")
    monkeypatch.setattr("orchestrator.orchestrator.asyncio.to_thread", boom)

    ws = MagicMock()
    o.ui_sessions[ws] = {"sub": "companions-user",
                         "preferred_username": "companions-user"}
    try:
        await o._call_llm(ws, [{"role": "user", "content": "hi"}])
    except Exception:
        pass
    assert getattr(o, "_last_route_ondevice", None) is True
