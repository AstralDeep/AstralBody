"""Feature 040 (US2) — owner-safe marking + permission baseline.

Covers: the safe baseline flips deny→allow for a fresh user, an explicit
opt-out wins over the safe default, a non-safe agent stays default-deny,
admin/owner gating on mark_safe, and reset-on-revision. Audited transitions are
exercised through the real ``agent_trust`` storage path.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _can_connect_to_db() -> bool:
    try:
        import psycopg2
        from shared.database import _build_database_url

        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(), reason="Postgres unavailable in this environment"
)


@pytest.fixture(scope="module")
def db():
    from orchestrator.history import HistoryManager

    history = HistoryManager(data_dir=f"/tmp/trust-test-{uuid.uuid4().hex[:8]}")
    return history.db


@pytest.fixture
def pm(db):
    from orchestrator.tool_permissions import ToolPermissionManager

    return ToolPermissionManager(db=db)


def _fresh_ids():
    suffix = uuid.uuid4().hex[:10]
    return f"pytest-user-{suffix}", f"pytest-safe-agent-{suffix}"


def test_safe_agent_allows_fresh_user(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    # Fresh user, no scope rows: the safe baseline allows.
    assert pm.is_tool_allowed(user_id, agent_id, "some_tool") is True


def test_non_safe_agent_defaults_deny(db, pm):
    user_id, agent_id = _fresh_ids()
    # Never marked safe → legacy default-deny for a fresh user.
    assert pm.is_tool_allowed(user_id, agent_id, "some_tool") is False


def test_explicit_optout_wins_over_safe(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    # User explicitly disables the tool's scope → opt-out must win.
    pm.set_agent_scopes(user_id, agent_id, {"tools:read": False})
    assert pm.is_tool_allowed(user_id, agent_id, "some_tool") is False


def test_safe_public_agent_allows_fresh_user(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=True)
    # Safe + PUBLIC: the deny→allow baseline flip applies for a fresh user.
    assert pm.is_tool_allowed(user_id, agent_id, "some_tool") is True
    # Call again to hit the 30s _safe_flip_allowed cache.
    assert pm.is_tool_allowed(user_id, agent_id, "some_tool") is True


def test_safe_private_agent_denies_fresh_user(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=False)
    # Safe but PRIVATE: an owner cannot fleet-expose by marking safe — the flip
    # is withheld, so a fresh user without an explicit grant is still denied.
    assert pm.is_tool_allowed(user_id, agent_id, "some_tool") is False


# ── Feature 040 ∩ RFC 8693: the safe baseline must mirror into the ─────────
# ── delegation-token scope derivation (empty-scope regression) ─────────────


def test_safe_agent_scope_names_for_fresh_user(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=True)
    pm.register_tool_scopes(
        agent_id, {"web_search": "tools:search", "fetch_page": "tools:read"})
    # Fresh user, no rows: dispatch allows via the safe flip, so the
    # delegation mint must request the tool-map scopes — never scope="".
    assert pm.is_tool_allowed(user_id, agent_id, "web_search") is True
    assert pm.get_enabled_scope_names(user_id, agent_id) == [
        "tools:read", "tools:search"]


def test_safe_agent_scope_names_respect_explicit_optout(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=True)
    pm.register_tool_scopes(
        agent_id, {"web_search": "tools:search", "fetch_page": "tools:read"})
    # An explicit opt-out row blocks its scope's tools at dispatch, so the
    # token must not assert that scope either; row-absent scopes keep the
    # safe default.
    pm.set_agent_scopes(user_id, agent_id, {"tools:search": False})
    assert pm.is_tool_allowed(user_id, agent_id, "web_search") is False
    assert pm.get_enabled_scope_names(user_id, agent_id) == ["tools:read"]


def test_safe_agent_scope_names_respect_per_tool_optout(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=True)
    pm.register_tool_scopes(
        agent_id, {"post_data": "tools:write", "fetch_page": "tools:read"})
    # Per-tool opt-out on the ONLY write tool: dispatch blocks it, so the
    # minted token must not carry tools:write — the attenuation belongs in
    # the token, not only in the gate.
    pm.set_skill_enabled(user_id, agent_id, "post_data", False)
    assert pm.is_tool_allowed(user_id, agent_id, "post_data") is False
    assert pm.get_enabled_scope_names(user_id, agent_id) == ["tools:read"]


def test_per_tool_grant_without_scope_row_yields_scope(db, pm):
    user_id, agent_id = _fresh_ids()
    # Feature 013: enabling a single skill in the picker writes a per-(tool,
    # kind) row and NO agent_scopes row. Dispatch allows the tool, so the mint
    # must assert its scope — otherwise the exchange goes out empty.
    pm.register_tool_scopes(
        agent_id, {"web_search": "tools:search", "post_data": "tools:write"})
    pm.set_skill_enabled(user_id, agent_id, "web_search", True)
    assert pm.is_tool_allowed(user_id, agent_id, "web_search") is True
    assert pm.get_enabled_scope_names(user_id, agent_id) == ["tools:search"]


def test_non_safe_agent_scope_names_stay_empty(db, pm):
    user_id, agent_id = _fresh_ids()
    pm.register_tool_scopes(agent_id, {"web_search": "tools:search"})
    assert pm.get_enabled_scope_names(user_id, agent_id) == []


def test_safe_private_agent_scope_names_stay_empty(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=False)
    pm.register_tool_scopes(agent_id, {"web_search": "tools:search"})
    # Safe but PRIVATE: the flip is withheld at dispatch, so the mint must
    # not manufacture scopes either.
    assert pm.get_enabled_scope_names(user_id, agent_id) == []


def test_safe_agent_scope_names_default_read_without_tool_map(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=True)
    # No registered tool map: dispatch defaults unmapped tools to tools:read,
    # so the mint mirrors that.
    assert pm.get_enabled_scope_names(user_id, agent_id) == ["tools:read"]


def test_unknown_declared_scope_denied_and_unminted(db, pm):
    user_id, agent_id = _fresh_ids()
    db.upsert_agent_safe(agent_id, True, marked_by="pytest")
    db.set_agent_ownership(agent_id, "o@e.com", is_public=True)
    # A typo'd scope has no grantable permission surface (registration warns
    # it "will be denied") and no scope the mint could assert. Dispatch and
    # mint must agree — otherwise the gate admits a call the token can never
    # carry authority for.
    pm.register_tool_scopes(agent_id, {"weird_tool": "tools:bogus"})
    assert pm.is_tool_allowed(user_id, agent_id, "weird_tool") is False
    assert pm.get_enabled_scope_names(user_id, agent_id) == []


def test_explicit_enabled_scope_names_unchanged(db, pm):
    user_id, agent_id = _fresh_ids()
    pm.set_agent_scopes(
        user_id, agent_id, {"tools:read": True, "tools:write": True})
    assert pm.get_enabled_scope_names(user_id, agent_id) == [
        "tools:read", "tools:write"]


@pytest.mark.asyncio
async def test_mark_safe_requires_admin(db):
    from orchestrator import agent_trust

    _, agent_id = _fresh_ids()
    denied = await agent_trust.mark_safe(db, agent_id, True, "alice", roles=[])
    assert denied["ok"] is False and denied["error"] == "forbidden"
    assert await asyncio.to_thread(db.get_agent_is_safe, agent_id) is False

    ok = await agent_trust.mark_safe(db, agent_id, True, "admin-user", roles=["admin"])
    assert ok["ok"] is True and ok["is_safe"] is True
    assert await asyncio.to_thread(db.get_agent_is_safe, agent_id) is True


@pytest.mark.asyncio
async def test_reset_on_revision_clears_marker(db):
    from orchestrator import agent_trust

    _, agent_id = _fresh_ids()
    await agent_trust.mark_safe(db, agent_id, True, "admin-user", roles=["admin"])
    assert await asyncio.to_thread(db.get_agent_is_safe, agent_id) is True

    res = await agent_trust.reset_on_revision(db, agent_id, actor_user="reviser")
    assert res["reset"] is True
    assert await asyncio.to_thread(db.get_agent_is_safe, agent_id) is False


@pytest.mark.asyncio
async def test_seed_safe_idempotent(db):
    from orchestrator import agent_trust

    _, agent_id = _fresh_ids()
    first = await agent_trust.seed_safe(db, [agent_id])
    assert agent_id in first
    second = await agent_trust.seed_safe(db, [agent_id])
    assert agent_id not in second  # already safe → not re-seeded
