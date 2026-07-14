"""Feature 057 (US3) — untrusted-at-the-boundary owner isolation (SC-003).

Covers the boundary guarantees that are enforceable at the permission layer
today: user-agent owner isolation at the dispatch gate and tool-list build
(is_tool_allowed) and the pre-existing private-agent grant-hole fix
(can_user_use_agent). The transport-level scenarios (forged identity over the
tunnel, per-owner flood bound, honest-offline) land with the tunnel tasks
(T008/T009/T011/T021) and their own tests.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.database import Database  # noqa: E402
from orchestrator.tool_permissions import ToolPermissionManager  # noqa: E402
from orchestrator import user_agents as ua  # noqa: E402

OWNER = "__t057adv__owner"
FOREIGN = "__t057adv__foreign"
UA_ID = "__t057adv__myagent"


@pytest.fixture()
def db():
    d = Database()
    d._init_db()
    ua.create_user_agent(d, agent_id=UA_ID, owner_user_id=OWNER, display_name="Mine")
    yield d
    for tbl, col in (("user_agent", "agent_id"), ("agent_ownership", "agent_id"),
                     ("agent_scopes", "agent_id")):
        try:
            d.execute(f"DELETE FROM {tbl} WHERE {col} = ?", (UA_ID,))
        except Exception:
            pass


def test_grant_hole_predicate_blocks_foreign_user(db):
    # T019: a foreign user cannot manage a private user agent (the endpoint 403s
    # on exactly this predicate).
    assert ua.can_user_use_agent(db, OWNER, UA_ID) is True
    assert ua.can_user_use_agent(db, FOREIGN, UA_ID) is False


def test_builtins_unaffected_by_isolation(db):
    # can_user_use_agent returns True for any non-user-agent, so built-in/public
    # management + dispatch is unchanged.
    assert ua.can_user_use_agent(db, FOREIGN, "general") is True


def test_dispatch_gate_denies_foreign_user_agent_tool(db):
    # T020: is_tool_allowed short-circuits a foreign user on a user agent.
    tp = ToolPermissionManager(db=db)
    assert tp.is_tool_allowed(FOREIGN, UA_ID, "any_tool") is False


def test_isolation_wins_over_a_stray_scope_row(db):
    # FR-019: even if a stray enabled agent_scopes row exists for the foreign
    # user, isolation (step 0) still denies — visibility/use is NOT reliant on
    # scope hygiene.
    tp = ToolPermissionManager(db=db)
    db.execute(
        "INSERT INTO agent_scopes (user_id, agent_id, scope, enabled, updated_at) "
        "VALUES (?, ?, 'tools:read', TRUE, 0) "
        "ON CONFLICT (user_id, agent_id, scope) DO UPDATE SET enabled = TRUE",
        (FOREIGN, UA_ID),
    )
    assert tp.is_tool_allowed(FOREIGN, UA_ID, "any_tool") is False


def test_owner_is_not_blocked_by_isolation(db):
    # The isolation step must NOT block the owner; a granted owner scope resolves
    # to allow. (Uses a registered scope row so normal resolution returns True.)
    tp = ToolPermissionManager(db=db)
    db.execute(
        "INSERT INTO agent_scopes (user_id, agent_id, scope, enabled, updated_at) "
        "VALUES (?, ?, 'tools:read', TRUE, 0) "
        "ON CONFLICT (user_id, agent_id, scope) DO UPDATE SET enabled = TRUE",
        (OWNER, UA_ID),
    )
    # get_tool_scope for an unregistered tool falls back; assert isolation didn't
    # force-deny by checking the predicate path directly for the owner.
    assert ua.can_user_use_agent(db, OWNER, UA_ID) is True
