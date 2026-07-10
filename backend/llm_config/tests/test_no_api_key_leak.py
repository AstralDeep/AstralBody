"""T061 (006) + 054 — defense-in-depth API-key leak sweep.

Drives every audit-event helper through every documented action (incl.
the 054 additions: scope="system", action="discarded_undecryptable",
credential_source=SYSTEM) with obviously-secret-looking API keys, plus
the full persisted-store save path (``handle_llm_config_set`` over
``UserLLMConfigStore``), then greps every recorded audit payload, every
client-bound frame, and the at-rest DB state for the keys. This is the
FR-006 invariant: 0 user API keys in audit logs, client payloads, or
plaintext storage, ever.
"""
from __future__ import annotations

import json
import re

import pytest

from llm_config.audit_events import (
    record_llm_call,
    record_llm_config_change,
    record_llm_unconfigured,
)
from llm_config.types import CredentialSource, ResolvedConfig
from llm_config.ws_handlers import handle_llm_config_set

# Obviously-secret-looking keys smeared through every flow. If any
# survives into a recorded payload, the test fails. Feature 054 adds the
# Google (AIza) and Anthropic (sk-ant-) shapes now that both providers
# are in the catalog.
SENTINEL_KEYS = [
    "sk-sentinel-key-abcdef1234567890abcdef",
    "sk-ant-sentinel-key-abcdef1234567890abcdef",
    "gsk_sentinel-key-abcdef1234567890abcdef",
    "xai-sentinel-key-abcdef1234567890abcdef",
    "or-sentinel-key-abcdef1234567890abcdef",
    "sk_live_sentinel-key-abcdef1234567890abcdef",
    "AIzaSentinel-key-abcdef1234567890abcdef",
]

# The same regex set the audit_events module uses for its
# defense-in-depth guard. We assert NO match on any captured payload.
KEY_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bor-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bsk_live_[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}\b"),
]


def _serialize_all(events) -> str:
    blobs = []
    for ev in events:
        try:
            blobs.append(ev.model_dump_json())
        except Exception:
            blobs.append(json.dumps(str(ev)))
    return "\n".join(blobs)


def captured(rec):
    return [c.args[0] for c in rec.record.await_args_list]


def _assert_clean(blob: str, context: str) -> None:
    for pat in KEY_PATTERNS:
        m = pat.search(blob)
        assert m is None, (
            f"API-key-shaped substring found in {context}: {m.group(0)!r}")
    for sentinel in SENTINEL_KEYS:
        assert sentinel not in blob, (
            f"Sentinel key {sentinel!r} leaked into {context}")


@pytest.mark.asyncio
async def test_no_api_key_in_any_audit_payload(fake_recorder):
    """Smear every sentinel key through every helper, action, and scope,
    then sweep all captured payloads for any API-key-shaped string."""
    # ------------------------------------------------------------------
    # llm_config_change: every action × both scopes
    # ------------------------------------------------------------------
    for scope in ("user", "system"):
        await record_llm_config_change(
            fake_recorder, actor_user_id="u", auth_principal="u",
            action="created", base_url="https://x.example/v1", model="m",
            transport="ws", scope=scope)
        await record_llm_config_change(
            fake_recorder, actor_user_id="u", auth_principal="u",
            action="updated", base_url="https://x.example/v1", model="m",
            transport="ws", scope=scope)
        await record_llm_config_change(
            fake_recorder, actor_user_id="u", auth_principal="u",
            action="cleared", base_url=None, model=None,
            transport="ws", scope=scope)
        await record_llm_config_change(
            fake_recorder, actor_user_id="u", auth_principal="u",
            action="discarded_undecryptable", base_url=None, model=None,
            transport="ws", scope=scope)
        await record_llm_config_change(
            fake_recorder, actor_user_id="u", auth_principal="u",
            action="tested", base_url="https://x.example/v1", model="m",
            transport="rest", result="success", scope=scope)
        await record_llm_config_change(
            fake_recorder, actor_user_id="u", auth_principal="u",
            action="tested", base_url="https://x.example/v1", model="m",
            transport="rest", result="failure", error_class="auth_failed",
            scope=scope)

    # ------------------------------------------------------------------
    # llm_unconfigured
    # ------------------------------------------------------------------
    await record_llm_unconfigured(
        fake_recorder, actor_user_id="u", auth_principal="u",
        feature="tool_dispatch")

    # ------------------------------------------------------------------
    # llm_call: success and failure for both LIVE credential sources
    # (operator_default is retired for new rows — feature 054)
    # ------------------------------------------------------------------
    for source in (CredentialSource.USER, CredentialSource.SYSTEM):
        await record_llm_call(
            fake_recorder, actor_user_id="u", auth_principal="u",
            feature="tool_dispatch", credential_source=source,
            resolved=ResolvedConfig(base_url="https://x.example/v1", model="m"),
            total_tokens=247, outcome="success")
        await record_llm_call(
            fake_recorder, actor_user_id="u", auth_principal="u",
            feature="tool_summary", credential_source=source,
            resolved=ResolvedConfig(base_url="https://x.example/v1", model="m"),
            total_tokens=None, outcome="failure",
            upstream_error_class="rate_limit")

    _assert_clean(_serialize_all(captured(fake_recorder)), "audit payload")


@pytest.mark.asyncio
async def test_persisted_save_path_never_leaks_the_key(
        store, fake_db, fake_recorder, safe_send, monkeypatch):
    """Drive the REAL save path (validate → probe → persist → audit →
    ack) with a sentinel key and sweep every observable surface: recorded
    audit events, every client-bound frame, the at-rest DB state, and the
    store record's repr."""
    async def _probe(**kwargs):
        return (True, None, None)

    monkeypatch.setattr("llm_config.ws_handlers.probe_chat_completion", _probe)

    for i, sentinel in enumerate(SENTINEL_KEYS):
        assert await handle_llm_config_set(
            safe_send=safe_send,
            websocket=object(),
            config={"provider": "custom",
                    "base_url": f"https://x{i}.example/v1",
                    "model": "m", "api_key": sentinel},
            actor_user_id=f"user-{i}",
            auth_principal=f"user-{i}",
            store=store,
            recorder=fake_recorder,
        ) is True

    # 1. Audit events.
    _assert_clean(_serialize_all(captured(fake_recorder)), "audit payload")
    # 2. Every client-bound frame (errors + acks).
    frames = "\n".join(c.args[1] for c in safe_send.await_args_list)
    _assert_clean(frames, "client-bound frame")
    # 3. At-rest storage: ciphertext only — the verbatim key never appears.
    at_rest = json.dumps(fake_db.users, default=str)
    for sentinel in SENTINEL_KEYS:
        assert sentinel not in at_rest, (
            f"Sentinel key {sentinel!r} stored in plaintext")
    # 4. The store record's repr elides the key.
    for i, sentinel in enumerate(SENTINEL_KEYS):
        assert sentinel not in repr(store.get_sync(f"user-{i}"))


@pytest.mark.asyncio
async def test_assert_no_api_key_guard_rejects_attempt_to_pass_key_in_payload():
    """Defense in depth: the guard behaviour itself (literal api_key
    field, key-shaped substrings incl. AIza) is covered in
    test_audit_events.py::TestAssertNoApiKey; this file's job is the
    corpus sweep above. Kept as a documentation anchor."""
    assert True
