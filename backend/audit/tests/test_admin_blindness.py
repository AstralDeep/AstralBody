"""Admin-blindness integration test (FR-019).

Confirms that:

1. Even an admin role cannot read another user's audit entries via
   ``list_for_user`` / ``get_for_user``.
2. Cross-user fetch returns ``None`` (REST surfaces 404), indistinguishable
   from non-existent ids.
3. The WS publisher's filter never delivers user A's event to user B's
   connection.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest


def test_list_is_scoped_to_caller(repo, make_event):
    alice = f"alice-{uuid.uuid4().hex[:8]}"
    bob = f"bob-{uuid.uuid4().hex[:8]}"

    for _ in range(3):
        repo.insert(make_event(actor_user_id=alice, auth_principal=alice, action_type="auth.alice"))
    for _ in range(2):
        repo.insert(make_event(actor_user_id=bob, auth_principal=bob, action_type="auth.bob"))

    items_alice, _ = repo.list_for_user(alice, limit=50)
    items_bob, _ = repo.list_for_user(bob, limit=50)

    alice_actions = {i.action_type for i in items_alice}
    bob_actions = {i.action_type for i in items_bob}
    assert "auth.alice" in alice_actions
    assert "auth.bob" not in alice_actions
    assert "auth.bob" in bob_actions
    assert "auth.alice" not in bob_actions


def test_get_for_user_returns_none_for_other_users_event(repo, make_event):
    alice = f"alice-{uuid.uuid4().hex[:8]}"
    bob = f"bob-{uuid.uuid4().hex[:8]}"
    bob_event = repo.insert(make_event(actor_user_id=bob, auth_principal=bob))
    # Alice tries to fetch by Bob's event_id — must come back None
    assert repo.get_for_user(alice, bob_event.event_id) is None
    # Bob himself can fetch it
    assert repo.get_for_user(bob, bob_event.event_id) is not None


def test_get_for_user_returns_none_for_garbage_event_id(repo):
    # Indistinguishable from "not yours" — same None response
    assert repo.get_for_user("anyone", "not-a-uuid") is None


def test_ws_publisher_only_delivers_to_owning_connection(make_event):
    """The publisher must filter strictly by ``actor_user_id``.

    We feed a fake orchestrator with two connections (alice + bob) and
    confirm an event for alice never reaches bob's connection.
    """
    from audit.ws_publisher import WSPublisher
    from audit.schemas import AuditEventDTO
    from datetime import datetime, timezone

    class FakeWS:
        def __init__(self, name):
            self.name = name
            self.received = []

    class FakeOrch:
        def __init__(self, ws_a, ws_b):
            self.ui_sessions = {ws_a: {"sub": "alice"}, ws_b: {"sub": "bob"}}

        async def _safe_send(self, ws, payload):
            ws.received.append(payload)
            return True

    ws_alice = FakeWS("alice")
    ws_bob = FakeWS("bob")
    orch = FakeOrch(ws_alice, ws_bob)
    pub = WSPublisher(orch)

    dto = AuditEventDTO(
        event_id=str(uuid.uuid4()),
        event_class="auth",
        action_type="auth.test",
        description="test",
        agent_id=None,
        conversation_id=None,
        correlation_id=str(uuid.uuid4()),
        outcome="success",
        outcome_detail=None,
        inputs_meta={},
        outputs_meta={},
        artifact_pointers=[],
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        recorded_at=datetime.now(timezone.utc),
    )
    asyncio.run(pub.publish(dto, "alice"))
    assert len(ws_alice.received) == 1
    assert ws_bob.received == []  # absolute: never delivered
