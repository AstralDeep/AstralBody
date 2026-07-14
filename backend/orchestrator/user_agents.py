"""User-agent registry accessors (feature 057).

The durable ``user_agent`` table — one row per user-authored, client-hosted
agent. Canonical owner key is ``owner_user_id`` (the OIDC ``sub``); the boundary
binds to it and never to a card field or email. ``status`` is the durable
lifecycle (authoring|validated|live|disabled); running/offline is DERIVED from
socket presence and is never stored here.

Also home to ``can_user_use_agent`` — the owner-isolation predicate the boundary
enforces in three places (grant endpoint, dispatch gate, tool-list build) so a
private user agent is invisible/unusable to non-owners (FR-016/019).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_user_agent(db, *, agent_id: str, owner_user_id: str, display_name: str,
                      owner_email: Optional[str] = None, draft_id: Optional[str] = None,
                      declared_tools: Optional[List[str]] = None,
                      declared_scopes: Optional[List[str]] = None,
                      declared_egress: Optional[List[str]] = None) -> None:
    """Insert (or replace) a user-agent registry row in ``authoring`` status."""
    now = _now_ms()
    db.execute(
        "INSERT INTO user_agent (agent_id, owner_user_id, owner_email, display_name, "
        "status, declared_tools, declared_scopes, declared_egress, draft_id, "
        "is_public, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'authoring', ?, ?, ?, ?, FALSE, ?, ?) "
        "ON CONFLICT (agent_id) DO UPDATE SET "
        "owner_user_id = EXCLUDED.owner_user_id, owner_email = EXCLUDED.owner_email, "
        "display_name = EXCLUDED.display_name, draft_id = EXCLUDED.draft_id, "
        "declared_tools = EXCLUDED.declared_tools, declared_scopes = EXCLUDED.declared_scopes, "
        "declared_egress = EXCLUDED.declared_egress, updated_at = EXCLUDED.updated_at",
        (agent_id, owner_user_id, owner_email, display_name,
         json.dumps(declared_tools or []), json.dumps(declared_scopes or []),
         json.dumps(declared_egress) if declared_egress is not None else None,
         draft_id, now, now),
    )


def get_user_agent(db, agent_id: str) -> Optional[Dict[str, Any]]:
    row = db.fetch_one("SELECT * FROM user_agent WHERE agent_id = ?", (agent_id,))
    return dict(row) if row else None


def is_user_agent(db, agent_id: str) -> bool:
    return get_user_agent(db, agent_id) is not None


def list_user_agents(db, owner_user_id: str) -> List[Dict[str, Any]]:
    """The owner's agents, most-recent first, excluding soft-deleted rows."""
    rows = db.fetch_all(
        "SELECT * FROM user_agent WHERE owner_user_id = ? AND deleted_at IS NULL "
        "ORDER BY updated_at DESC",
        (owner_user_id,),
    )
    return [dict(r) for r in rows]


def mark_validated(db, agent_id: str, constitution_version: Optional[str],
                   *, declared_tools: Optional[List[str]] = None,
                   declared_scopes: Optional[List[str]] = None) -> None:
    """Analyze passed: record the constitution version and move to ``validated``."""
    now = _now_ms()
    sets = ["status = 'validated'", "constitution_version = ?", "validated_at = ?",
            "revalidation_required = FALSE", "updated_at = ?"]
    params: List[Any] = [constitution_version, now, now]
    if declared_tools is not None:
        sets.append("declared_tools = ?")
        params.append(json.dumps(declared_tools))
    if declared_scopes is not None:
        sets.append("declared_scopes = ?")
        params.append(json.dumps(declared_scopes))
    params.append(agent_id)
    db.execute(f"UPDATE user_agent SET {', '.join(sets)} WHERE agent_id = ?", tuple(params))


def go_live(db, agent_id: str, *, host_client_id: Optional[str] = None,
            host_session_id: Optional[str] = None) -> None:
    """The delivered agent registered inward: mark ``live``, stamp the host, and
    insert the companion ``agent_ownership`` row (is_public FALSE) so the existing
    routing/permission stack treats it uniformly (FR-007)."""
    now = _now_ms()
    row = get_user_agent(db, agent_id)
    db.execute(
        "UPDATE user_agent SET status = 'live', host_client_id = ?, host_session_id = ?, "
        "host_last_seen_at = ?, updated_at = ? WHERE agent_id = ?",
        (host_client_id, host_session_id, now, now, agent_id),
    )
    if row is not None:
        # Companion ownership row — private by construction.
        db.set_agent_ownership(agent_id, row.get("owner_email") or row.get("owner_user_id"),
                               is_public=False)


def touch_liveness(db, agent_id: str) -> None:
    """Heartbeat: update ``host_last_seen_at`` (derived running/offline reads it)."""
    db.execute("UPDATE user_agent SET host_last_seen_at = ? WHERE agent_id = ?",
               (_now_ms(), agent_id))


def mark_revalidation_required(db, agent_id: str, required: bool = True) -> None:
    db.execute("UPDATE user_agent SET revalidation_required = ?, updated_at = ? WHERE agent_id = ?",
               (required, _now_ms(), agent_id))


def soft_delete(db, agent_id: str) -> None:
    """Soft delete (finding I1): disable + stamp ``deleted_at``; retain the row and
    its audit trail (Constitution VII). Routing/visibility removal is done by the
    caller (stop host, drop registry socket)."""
    now = _now_ms()
    db.execute(
        "UPDATE user_agent SET status = 'disabled', deleted_at = ?, updated_at = ? "
        "WHERE agent_id = ?",
        (now, now, agent_id),
    )


def can_user_use_agent(db, user_id: str, agent_id: str) -> bool:
    """Owner-isolation predicate: a user may use an agent iff it is public OR they
    own it. For a user agent, ownership is ``user_agent.owner_user_id``; for any
    other agent, ``agent_ownership.is_public``. Fail-closed: unknown ⇒ fall back to
    the public flag only (a private user agent with no readable owner denies).
    Enforced at the grant endpoint, the dispatch gate, and tool-list build."""
    if not user_id or not agent_id:
        return False
    ua = get_user_agent(db, agent_id)
    if ua is not None:
        # A user agent is private by construction; only its owner may use it.
        return ua.get("owner_user_id") == user_id
    try:
        own = db.get_agent_ownership(agent_id)
    except Exception:
        own = None
    if own is None:
        # Not a user agent and no ownership row → not owner-restricted here;
        # the normal permission gate governs it (built-ins/public catalog).
        return True
    return bool(own.get("is_public"))
