"""Tests for feedback.repository — dedup window, lifecycle, per-user filter."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from feedback.repository import FeedbackRepository
from shared.database import Database


@pytest.fixture(scope="module")
def db():
    # Uses the test environment's PostgreSQL; relies on _init_db having
    # already created the four feature-004 tables.
    return Database()


@pytest.fixture
def repo(db):
    return FeedbackRepository(db)


@pytest.fixture
def fresh_user(db):
    """Return a unique user_id for the test and clean up its rows on teardown."""
    user = f"test_repo_{datetime.now(timezone.utc).timestamp():.6f}"
    yield user
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM component_feedback WHERE user_id = %s", (user,))
        conn.commit()
    finally:
        conn.close()


def _insert_kwargs(**overrides):
    base = dict(
        conversation_id=None,
        correlation_id="dispatch-1",
        source_agent="agent-x",
        source_tool="tool-y",
        component_id="comp-1",
        sentiment="negative",
        category="wrong-data",
        comment_raw=None,
        comment_safety="clean",
        comment_safety_reason=None,
    )
    base.update(overrides)
    return base


def test_insert_and_get_for_user(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs())
    fetched = repo.get_for_user(fresh_user, inserted.id)
    assert fetched is not None
    assert fetched.id == inserted.id
    assert fetched.user_id == fresh_user


def test_get_for_other_user_returns_none(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs())
    assert repo.get_for_user("someone-else", inserted.id) is None


def test_dedup_window_finds_recent_active(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs())
    found = repo.find_in_dedup_window(fresh_user, "dispatch-1", "comp-1", window_seconds=60)
    assert found is not None and found.id == inserted.id


def test_dedup_window_misses_old_records(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs())
    # Use a tiny window
    found = repo.find_in_dedup_window(fresh_user, "dispatch-1", "comp-1", window_seconds=0)
    assert found is None or found.id != inserted.id


def test_supersession_chain(repo, fresh_user):
    first = repo.insert(fresh_user, **_insert_kwargs(comment_raw="first"))
    second = repo.insert(
        fresh_user,
        supersedes_id=first.id,
        **_insert_kwargs(comment_raw="second"),
    )
    refreshed_first = repo.get_for_user(fresh_user, first.id)
    assert refreshed_first.lifecycle == "superseded"
    assert refreshed_first.superseded_by == str(second.id)
    assert second.lifecycle == "active"


def test_update_in_window_replaces_in_place(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs(sentiment="negative"))
    updated = repo.update_in_window(
        fresh_user, inserted.id,
        sentiment="positive", category="other",
        comment_raw="changed", comment_safety="clean",
        comment_safety_reason=None,
    )
    assert updated is not None
    assert updated.id == inserted.id
    assert updated.sentiment == "positive"
    assert updated.comment_raw == "changed"


def test_update_in_window_rejects_cross_user(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs())
    blocked = repo.update_in_window(
        "someone-else", inserted.id,
        sentiment="positive", category="other",
        comment_raw="x", comment_safety="clean", comment_safety_reason=None,
    )
    assert blocked is None


def test_retract_marks_only_own_record(repo, fresh_user):
    inserted = repo.insert(fresh_user, **_insert_kwargs())
    refreshed = repo.retract(fresh_user, inserted.id)
    assert refreshed is not None
    assert refreshed.lifecycle == "retracted"

    # Cross-user retract MUST return None
    assert repo.retract("someone-else", inserted.id) is None


def test_list_for_user_filters_lifecycle(repo, fresh_user):
    a = repo.insert(fresh_user, **_insert_kwargs(comment_raw="a"))
    repo.retract(fresh_user, a.id)
    b = repo.insert(fresh_user, **_insert_kwargs(comment_raw="b"))

    active, _ = repo.list_for_user(fresh_user, lifecycle="active")
    assert any(r.id == b.id for r in active)
    assert not any(r.id == a.id for r in active)

    retracted, _ = repo.list_for_user(fresh_user, lifecycle="retracted")
    assert any(r.id == a.id for r in retracted)
