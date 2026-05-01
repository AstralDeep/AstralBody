"""Tests for the canonical tutorial-step seed (features 005 + 008).

These run the real ``seed_tutorial_steps`` loader against the live
``tutorial_step`` table. Steps are seeded with ``ON CONFLICT (slug)
DO NOTHING`` so the assertions can rely on canonical rows being
present without truncating admin edits.
"""
from __future__ import annotations

import pytest

from onboarding.seed import seed_tutorial_steps


@pytest.fixture
def fresh_seed(database):
    """Apply (or re-apply, idempotently) the canonical seed before assertions."""
    seed_tutorial_steps(database)
    yield database


def _fetch_step(database, slug: str) -> dict | None:
    conn = database._get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT slug, audience, display_order, target_kind, target_key, "
            "title, body FROM tutorial_step WHERE slug = %s",
            (slug,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    keys = ["slug", "audience", "display_order", "target_kind", "target_key", "title", "body"]
    return dict(zip(keys, row))


# ---------------------------------------------------------------------------
# Feature 008-llm-text-only-chat (T022 + T023): the seed must include the
# 'enable-agents' user step that nudges users to turn on agents.
# ---------------------------------------------------------------------------

def test_seed_creates_enable_agents_step(fresh_seed):
    """The canonical seed exposes the 'enable-agents' step at display
    order 35 (between 'open-agents-panel' at 30 and 'open-audit-log' at
    40), pointing to the agents sidebar entry."""
    row = _fetch_step(fresh_seed, "enable-agents")
    assert row is not None, "tutorial seed must create the 'enable-agents' step"
    assert row["audience"] == "user"
    assert row["display_order"] == 35
    assert row["target_kind"] == "static"
    assert row["target_key"] == "sidebar.agents"


def test_enable_agents_step_body_tells_users_to_turn_agents_on(fresh_seed):
    """The body of the new step must explicitly tell users how to enable
    agents — that is the user-stated requirement from the clarification
    round (`Can you add a part to the tutorial to tell users to turn on
    agents`)."""
    row = _fetch_step(fresh_seed, "enable-agents")
    assert row is not None
    body_lower = row["body"].lower()
    assert "agent" in body_lower
    # Allow 'turn on', 'switch on', 'enable' — any phrasing of the action.
    assert any(phrase in body_lower for phrase in ("turn", "switch on", "enable")), (
        f"step body must instruct the user to turn on an agent: {row['body']!r}"
    )


def test_enable_agents_step_ordered_between_existing_user_steps(fresh_seed):
    """Sanity check that the new step doesn't collide with siblings: it
    sits strictly between 'open-agents-panel' and 'open-audit-log'."""
    panel = _fetch_step(fresh_seed, "open-agents-panel")
    enable = _fetch_step(fresh_seed, "enable-agents")
    audit = _fetch_step(fresh_seed, "open-audit-log")
    assert panel and enable and audit
    assert panel["display_order"] < enable["display_order"] < audit["display_order"]
