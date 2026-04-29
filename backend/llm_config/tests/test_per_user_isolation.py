"""G2 — per-user credential isolation regression test.

Spec edge case: 'A user attempts to manipulate the request path to call
the LLM proxy with somebody else's stored credentials — the system
rejects the request because credentials are sourced exclusively from
the caller's own session, never from a stored, server-side, per-user
record.'

The system enforces this by construction: ``SessionCredentialStore``
keys on ``id(websocket)``, and the orchestrator only ever passes
``id(caller_websocket)``. There is no API surface that accepts a
``user_id`` argument when looking up session credentials. This test
demonstrates that a 'cross-user' lookup attempt MUST miss the store
and therefore fall through to the operator default (or raise
``LLMUnavailable``).
"""
from __future__ import annotations

from llm_config.client_factory import build_llm_client
from llm_config.operator_creds import OperatorDefaultCreds
from llm_config.session_creds import SessionCredentialStore
from llm_config.types import CredentialSource


def test_user_a_cannot_be_billed_for_user_b_call():
    """User A is connected on socket SA with personal creds. User B is
    connected on socket SB without personal creds. A request arriving
    on SB MUST resolve via the operator default (or LLMUnavailable),
    never via user A's creds.
    """
    store = SessionCredentialStore()
    socket_a = object()
    socket_b = object()
    store.set(id(socket_a), "sk-userA-1234567890abcdef", "https://userA/v1", "userA-model")
    # socket_b deliberately has no entry.

    operator_default = OperatorDefaultCreds(
        api_key="sk-operator-1234567890abcdef",
        base_url="https://operator/v1",
        model="op-model",
    )

    # The orchestrator's resolution path uses id(caller_websocket).
    # When caller is socket_b, the lookup misses (correctly).
    creds_for_b = store.get(id(socket_b))
    assert creds_for_b is None

    _, source, resolved = build_llm_client(creds_for_b, operator_default)
    # User A's keys are NOT borrowed.
    assert source is CredentialSource.OPERATOR_DEFAULT
    assert resolved.base_url == "https://operator/v1"
    assert resolved.base_url != "https://userA/v1"


def test_no_api_surface_accepts_external_user_id_for_cred_lookup():
    """SessionCredentialStore exposes only get(ws_id) / set(ws_id, ...) /
    clear(ws_id) / __contains__. There is NO method that takes a
    user_id parameter — by design — so an attacker cannot craft a
    request that asks for someone else's creds by ID."""
    store = SessionCredentialStore()
    # Public API surface — by construction, no user_id-keyed lookup
    public_methods = [
        m for m in dir(store)
        if not m.startswith("_")
    ]
    # Verify the public surface is exactly what we documented.
    assert set(public_methods) == {"get", "set", "clear"}
    # And the get/set/clear all take ws_id ints (or any int), never a
    # user_id string. We can't introspect the type signature at runtime
    # without inspect, but the test_session_creds.py tests cover the
    # signature shape; this test documents the design intent.


def test_session_credential_store_lookups_use_int_keys_only():
    """``id(websocket)`` is an integer. Strings (which user_ids are) cannot
    accidentally collide with id() values in the store."""
    store = SessionCredentialStore()
    socket = object()
    ws_id = id(socket)
    store.set(ws_id, "sk-x-1234567890abcdefgh", "https://x/v1", "m")
    # Looking up by user_id-shaped string just misses
    assert store.get("attacker_user_id") is None  # type: ignore[arg-type]
    assert "attacker_user_id" not in store  # type: ignore[operator]
    # The legitimate lookup still works
    assert store.get(ws_id) is not None
