"""Namespaced principals + teardown (T007 / FR-031 / D14).

Every harness identity, chat, attachment, and draft is namespaced under a
``__verif__`` prefix so runs never collide with — or pollute — real user data.
Teardown deletes the deletable rows + blobs for a run. ``audit_events`` are
append-only by design and remain, but only ever under namespaced principals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger("verification.isolation")

NAMESPACE_PREFIX = "__verif__"

# Tables with a user_id column that the harness writes to via the product path
# and may safely purge for its namespaced principals on teardown. Order matters
# only loosely (no hard FKs across these in the schema).
_DELETABLE_USER_TABLES: tuple[str, ...] = (
    "message_attachment",
    "saved_components",
    "workspace_layout",
    "workspace_snapshot",
    "messages",
    "chats",
    "user_attachments",
    "draft_agents",
    "user_llm_config",  # 054: harness-seeded BYO-LLM rows (never the system row)
)


@dataclass
class Principal:
    """A namespaced authenticated identity used by the harness."""

    user_id: str
    roles: List[str] = field(default_factory=lambda: ["user"])

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def claims(self) -> dict:
        """JWT-shaped claims for in-process session registration."""
        return {
            "sub": self.user_id,
            "preferred_username": self.user_id,
            "email": f"{self.user_id}@verif.local",
            "realm_access": {"roles": list(self.roles)},
            "resource_access": {"astral-frontend": {"roles": list(self.roles)}},
        }


def principal_id(run_id: str, persona: str, role: str = "primary") -> str:
    """Deterministic namespaced user id for ``(run, persona, role)``."""
    safe_run = run_id.replace(NAMESPACE_PREFIX, "")
    return f"{NAMESPACE_PREFIX}{safe_run}_{persona}_{role}"


def make_principal(run_id: str, persona: str, role: str = "primary",
                   roles: List[str] | None = None) -> Principal:
    return Principal(user_id=principal_id(run_id, persona, role), roles=roles or ["user"])


def is_harness_principal(user_id: str) -> bool:
    return bool(user_id) and user_id.startswith(NAMESPACE_PREFIX)


def teardown(db, run_id: str) -> int:
    """Delete deletable rows for every principal of ``run_id``.

    Args:
        db: A ``Database``-like handle with ``execute`` (DELETE ... ?) +
            ``fetch_all``. The project DB uses ``?`` placeholders.
        run_id: The run whose namespaced rows to purge.

    Returns:
        The number of DELETE statements that ran without error (best-effort;
        never raises — a failed teardown must not fail a run).
    """
    safe_run = run_id.replace(NAMESPACE_PREFIX, "")
    like = f"{NAMESPACE_PREFIX}{safe_run}_%"
    ran = 0
    for table in _DELETABLE_USER_TABLES:
        try:
            db.execute(f"DELETE FROM {table} WHERE user_id LIKE ?", (like,))
            ran += 1
        except Exception:  # pragma: no cover - table may not exist in a given schema
            logger.debug("teardown: skipped %s", table, exc_info=True)
    return ran
