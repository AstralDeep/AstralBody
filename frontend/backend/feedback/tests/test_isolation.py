"""End-to-end per-user isolation test (FR-009 / FR-031, SC-004).

Two distinct users submit feedback. User A MUST NOT be able to read,
retract, or amend user B's records. Cross-user attempts return responses
indistinguishable from "not found".
"""
from __future__ import annotations

import asyncio

import pytest

from feedback.recorder import FeedbackNotFound, Recorder
from feedback.repository import FeedbackRepository
from shared.database import Database


@pytest.fixture(scope="module")
def repo():
    return FeedbackRepository(Database())


@pytest.fixture
def recorder(repo):
    return Recorder(repo)


@pytest.fixture
def two_users(repo):
    a = "test_isolation_alice"
    b = "test_isolation_bob"
    yield a, b
    conn = repo._db._get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM component_feedback WHERE user_id IN (%s, %s)", (a, b))
        conn.commit()
    finally:
        conn.close()


def _submit(recorder, user, **overrides):
    base = dict(
        actor_user_id=user,
        auth_principal=user,
        conversation_id=None,
        correlation_id="iso-dispatch",
        source_agent="agent-x",
        source_tool="tool-y",
        component_id=None,
        sentiment="negative",
        category="wrong-data",
        comment="iso comment",
    )
    base.update(overrides)
    return asyncio.run(recorder.submit(**base)).feedback


def test_repository_get_is_per_user(recorder, repo, two_users):
    alice, bob = two_users
    alice_fb = _submit(recorder, alice)
    bob_fb = _submit(recorder, bob)

    # Alice can fetch her own; Bob's fetch returns None
    assert repo.get_for_user(alice, alice_fb.id) is not None
    assert repo.get_for_user(bob, alice_fb.id) is None

    # Symmetric
    assert repo.get_for_user(bob, bob_fb.id) is not None
    assert repo.get_for_user(alice, bob_fb.id) is None


def test_recorder_retract_is_per_user(recorder, two_users):
    alice, bob = two_users
    alice_fb = _submit(recorder, alice)

    # Bob attempting to retract Alice's row must raise FeedbackNotFound,
    # indistinguishable from "the id never existed".
    with pytest.raises(FeedbackNotFound):
        asyncio.run(recorder.retract(bob, bob, alice_fb.id))

    # Alice can still retract her own
    updated = asyncio.run(recorder.retract(alice, alice, alice_fb.id))
    assert updated.lifecycle == "retracted"


def test_recorder_amend_is_per_user(recorder, two_users):
    alice, bob = two_users
    alice_fb = _submit(recorder, alice)

    with pytest.raises(FeedbackNotFound):
        asyncio.run(recorder.amend(
            bob, bob, alice_fb.id,
            sentiment="positive", category=None, comment=None, comment_explicit=False,
        ))


def test_list_returns_only_own_rows(recorder, repo, two_users):
    alice, bob = two_users
    a1 = _submit(recorder, alice)
    a2 = _submit(recorder, alice)
    b1 = _submit(recorder, bob)

    alice_rows, _ = repo.list_for_user(alice, lifecycle="active")
    alice_ids = {r.id for r in alice_rows}
    assert a1.id in alice_ids and a2.id in alice_ids
    assert b1.id not in alice_ids

    bob_rows, _ = repo.list_for_user(bob, lifecycle="active")
    bob_ids = {r.id for r in bob_rows}
    assert b1.id in bob_ids
    assert a1.id not in bob_ids and a2.id not in bob_ids
