"""Feature 030 — wiring/onboarding fixes (walkthrough findings).

Covers:
* welcome canvas consent card (``welcome_components(tools_available=...)``)
* ToolPermissionManager.has_any_enabled_scope / scopes_required_by_tools
* Orchestrator._enable_recommended_agent_scopes (consent bulk enable)
* Orchestrator._text_only_cta_components (deterministic enable affordance)
* Orchestrator._is_draft_agent public-ownership short-circuit (etf false positive)
* Orchestrator._delegation_required (Constitution VII fail-closed posture)
* Database._migrate_agent_visibility_030 (idempotent visibility backfill)

Run inside the astralbody container:
    python -m pytest tests/test_wiring_030.py -q
"""
import sys
import types
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.orchestrator import Orchestrator  # noqa: E402
from orchestrator.tool_permissions import ToolPermissionManager  # noqa: E402
from orchestrator.welcome import enable_agents_card, welcome_components  # noqa: E402


def _can_connect_to_db() -> bool:
    try:
        import psycopg2
        from shared.database import _build_database_url

        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


_DB_OK = _can_connect_to_db()
needs_db = pytest.mark.skipif(not _DB_OK, reason="Postgres unavailable in this environment")


# ---------------------------------------------------------------------------
# Welcome canvas consent card
# ---------------------------------------------------------------------------


def _component_types(components):
    return [c.get("type") for c in components]


def test_welcome_default_has_no_enable_card():
    components = welcome_components()
    assert all("Agents are off" not in str(c.get("title", "")) for c in components)
    assert _component_types(components)[0] == "hero"


def test_welcome_tools_available_true_has_no_enable_card():
    components = welcome_components(tools_available=True)
    assert all("Agents are off" not in str(c.get("title", "")) for c in components)


def test_welcome_without_tools_prepends_enable_card_after_hero():
    components = welcome_components(tools_available=False)
    assert components[0]["type"] == "hero"
    card = components[1]
    assert card["type"] == "card"
    assert "Agents are off" in card["title"]
    actions = [child.get("action") for child in card["content"]
               if child.get("type") == "button"]
    assert actions == ["enable_recommended_agents", "chrome_open"]
    # The chrome_open button must target the agents surface.
    chrome_btn = [c for c in card["content"]
                  if c.get("action") == "chrome_open"][0]
    assert chrome_btn["payload"] == {"surface": "agents"}


def test_enable_agents_card_never_promises_write_access():
    card = enable_agents_card()
    text = str(card)
    assert "never write access" in text


# ---------------------------------------------------------------------------
# ToolPermissionManager helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def perms():
    from shared.database import Database

    manager = ToolPermissionManager(db=Database())
    user_id = f"pytest-030-{uuid.uuid4().hex[:12]}"
    yield manager, user_id
    manager.db.execute("DELETE FROM agent_scopes WHERE user_id = ?", (user_id,))


@needs_db
def test_has_any_enabled_scope_false_for_fresh_user(perms):
    manager, user_id = perms
    assert manager.has_any_enabled_scope(user_id) is False


@needs_db
def test_has_any_enabled_scope_false_when_all_rows_disabled(perms):
    manager, user_id = perms
    manager.set_agent_scopes(user_id, "agent-x", {"tools:read": False})
    assert manager.has_any_enabled_scope(user_id) is False


@needs_db
def test_has_any_enabled_scope_true_after_grant(perms):
    manager, user_id = perms
    manager.set_agent_scopes(user_id, "agent-x", {"tools:read": True})
    assert manager.has_any_enabled_scope(user_id) is True


@needs_db
def test_scopes_required_by_tools_excludes_write(perms):
    manager, _ = perms
    manager.register_tool_scopes("agent-w", {
        "fetch": "tools:read", "search": "tools:search",
        "mutate": "tools:write", "cpu": "tools:system",
    })
    assert manager.scopes_required_by_tools("agent-w") == [
        "tools:read", "tools:search", "tools:system"]


@needs_db
def test_scopes_required_by_tools_defaults_to_read_for_unmapped_agent(perms):
    manager, _ = perms
    assert manager.scopes_required_by_tools("never-registered") == ["tools:read"]


# ---------------------------------------------------------------------------
# Orchestrator._enable_recommended_agent_scopes (fake-self pattern)
# ---------------------------------------------------------------------------


def _enable_fake(manager, agent_ids, ownership_rows, drafts=()):
    fake = types.SimpleNamespace(
        agent_cards={aid: object() for aid in agent_ids},
        history=types.SimpleNamespace(db=types.SimpleNamespace(
            get_all_agent_ownership=lambda: ownership_rows)),
        tool_permissions=manager,
        _is_draft_agent=lambda aid: aid in drafts,
    )
    fake._enable_recommended_agent_scopes = types.MethodType(
        Orchestrator._enable_recommended_agent_scopes, fake)
    return fake


@needs_db
def test_consent_enable_grants_nonwrite_scopes_for_public_agents(perms):
    manager, user_id = perms
    manager.register_tool_scopes("pub-1", {"get": "tools:read", "put": "tools:write"})
    fake = _enable_fake(manager, ["pub-1", "priv-1"], [
        {"agent_id": "pub-1", "is_public": True},
        {"agent_id": "priv-1", "is_public": False},
    ])
    enabled = fake._enable_recommended_agent_scopes(user_id)
    assert enabled == ["pub-1"]
    scopes = manager.get_agent_scopes(user_id, "pub-1")
    assert scopes["tools:read"] is True
    assert scopes["tools:write"] is False  # never granted by consent enable
    assert manager.get_agent_scopes(user_id, "priv-1")["tools:read"] is False


@needs_db
def test_consent_enable_skips_drafts_and_honors_requested_subset(perms):
    manager, user_id = perms
    fake = _enable_fake(manager, ["pub-1", "pub-2", "draft-1"], [
        {"agent_id": "pub-1", "is_public": True},
        {"agent_id": "pub-2", "is_public": True},
        {"agent_id": "draft-1", "is_public": True},
    ], drafts={"draft-1"})
    enabled = fake._enable_recommended_agent_scopes(user_id, ["pub-2", "draft-1", "nope"])
    assert enabled == ["pub-2"]
    assert manager.get_agent_scopes(user_id, "pub-1")["tools:read"] is False
    assert manager.get_agent_scopes(user_id, "draft-1")["tools:read"] is False


# ---------------------------------------------------------------------------
# Orchestrator._text_only_cta_components
# ---------------------------------------------------------------------------


def _cta_fake(has_any: bool):
    fake = types.SimpleNamespace(tool_permissions=types.SimpleNamespace(
        has_any_enabled_scope=lambda user_id: has_any))
    fake._text_only_cta_components = types.MethodType(
        Orchestrator._text_only_cta_components, fake)
    return fake


def test_text_only_cta_empty_when_user_has_enabled_scopes():
    assert _cta_fake(True)._text_only_cta_components("u1") == []


def test_text_only_cta_components_for_never_configured_user():
    components = _cta_fake(False)._text_only_cta_components("u1")
    assert _component_types(components) == ["alert", "button", "button"]
    assert components[1]["action"] == "enable_recommended_agents"
    assert components[2]["action"] == "chrome_open"
    assert components[2]["payload"] == {"surface": "agents"}


def test_text_only_cta_fails_safe_on_permission_error():
    fake = types.SimpleNamespace(tool_permissions=types.SimpleNamespace(
        has_any_enabled_scope=lambda user_id: (_ for _ in ()).throw(RuntimeError)))
    fake._text_only_cta_components = types.MethodType(
        Orchestrator._text_only_cta_components, fake)
    assert fake._text_only_cta_components("u1") == []


# ---------------------------------------------------------------------------
# Orchestrator._is_draft_agent — public ownership short-circuit
# ---------------------------------------------------------------------------


def _draft_fake(draft, ownership):
    fake = types.SimpleNamespace(
        lifecycle_manager=types.SimpleNamespace(
            _find_draft_by_agent_id=lambda aid: draft),
        history=types.SimpleNamespace(db=types.SimpleNamespace(
            get_agent_ownership=lambda aid: ownership)),
    )
    fake._is_draft_agent = types.MethodType(Orchestrator._is_draft_agent, fake)
    return fake


def test_public_agent_never_hidden_by_stale_draft_row():
    fake = _draft_fake({"status": "error"}, {"is_public": True})
    assert fake._is_draft_agent("etf-tracker-1-1") is False


def test_private_agent_with_non_live_draft_row_stays_hidden():
    fake = _draft_fake({"status": "testing"}, {"is_public": False})
    assert fake._is_draft_agent("draft-being-tested-1") is True


def test_live_draft_row_is_not_hidden():
    fake = _draft_fake({"status": "live"}, {"is_public": False})
    assert fake._is_draft_agent("promoted-agent-1") is False


# ---------------------------------------------------------------------------
# Orchestrator._delegation_required — Constitution VII posture
# ---------------------------------------------------------------------------


def _delegation_required(monkeypatch, astral_env, override):
    if astral_env is None:
        monkeypatch.delenv("ASTRAL_ENV", raising=False)
    else:
        monkeypatch.setenv("ASTRAL_ENV", astral_env)
    if override is None:
        monkeypatch.delenv("DELEGATION_REQUIRED", raising=False)
    else:
        monkeypatch.setenv("DELEGATION_REQUIRED", override)
    fake = types.SimpleNamespace()
    return types.MethodType(Orchestrator._delegation_required, fake)()


def test_delegation_optional_in_development(monkeypatch):
    assert _delegation_required(monkeypatch, "development", None) is False


def test_delegation_required_in_production_posture(monkeypatch):
    assert _delegation_required(monkeypatch, None, None) is True
    assert _delegation_required(monkeypatch, "production", None) is True


def test_delegation_override_wins_both_ways(monkeypatch):
    assert _delegation_required(monkeypatch, "development", "true") is True
    assert _delegation_required(monkeypatch, "production", "false") is False


# ---------------------------------------------------------------------------
# Database._migrate_agent_visibility_030 — idempotent backfill
# ---------------------------------------------------------------------------


@needs_db
def test_visibility_migration_flips_only_listed_agents_and_is_idempotent():
    import psycopg2
    from shared.database import Database, _build_database_url

    listed = f"pytest-030-listed-{uuid.uuid4().hex[:8]}"
    unlisted = f"pytest-030-unlisted-{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(_build_database_url())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO agent_ownership (agent_id, owner_email, is_public) "
            "VALUES (%s, %s, FALSE), (%s, %s, FALSE)",
            (listed, "op@test", unlisted, "op@test"),
        )
        fake_db = types.SimpleNamespace(_FIRST_PARTY_PUBLIC_AGENT_IDS=(listed,))
        migrate = types.MethodType(Database._migrate_agent_visibility_030, fake_db)
        for _ in range(2):  # idempotent on re-run
            migrate(cursor)
        cursor.execute(
            "SELECT agent_id, is_public FROM agent_ownership "
            "WHERE agent_id IN (%s, %s)", (listed, unlisted))
        state = dict(cursor.fetchall())
        assert state[listed] is True
        assert state[unlisted] is False
        conn.commit()
    finally:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM agent_ownership WHERE agent_id IN (%s, %s)",
                       (listed, unlisted))
        conn.commit()
        conn.close()


@needs_db
def test_first_party_catalog_constants_match_post_029_catalog():
    from shared.database import Database

    ids = set(Database._FIRST_PARTY_PUBLIC_AGENT_IDS)
    # The two 029 plug-and-play agents the walkthrough found invisible MUST
    # be in the visibility backfill.
    assert {"web-research-1", "summarizer-1"} <= ids
    # Drafts / retired ids must never be listed.
    assert not any(a in ids for a in Database._RETIRED_AGENT_IDS)
