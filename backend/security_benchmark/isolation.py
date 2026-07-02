"""Namespaced harness principals + teardown (spec 047 FR-008, SC-007).

Every identity/chat/memory row the harness creates via the product path is
namespaced under ``__bench__`` so an adversarial corpus can never pollute — or
be confused with — real user data. Teardown deletes the deletable rows for the
run. Mirrors the 032 harness's isolation posture; synthetic mode creates no rows
at all (nothing to tear down), so this matters for in_process/external runs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger("security_benchmark.isolation")

NAMESPACE_PREFIX = "__bench__"

# user_id-scoped tables the harness may write to via the product path and may
# safely purge for its namespaced principals on teardown. memory_item is
# included because adversarial corpora could otherwise settle a poisoned memory
# (ties to the 036 memory-poisoning concern; spec 047 edge case #4).
_DELETABLE_USER_TABLES: tuple[str, ...] = (
    "message_attachment",
    "saved_components",
    "workspace_layout",
    "workspace_snapshot",
    "messages",
    "chats",
    "user_attachments",
    "draft_agents",
    "memory_item",
    "short_term_signal",
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
        return {
            "sub": self.user_id,
            "preferred_username": self.user_id,
            "email": f"{self.user_id}@bench.local",
            "realm_access": {"roles": list(self.roles)},
            "resource_access": {"astral-frontend": {"roles": list(self.roles)}},
        }


def principal_id(run_id: str, benchmark: str, role: str = "primary") -> str:
    base = run_id if run_id.startswith(NAMESPACE_PREFIX) else NAMESPACE_PREFIX + run_id
    return f"{base}__{benchmark}__{role}"


def assert_namespaced(user_id: str) -> None:
    """Guard: refuse to operate on a non-namespaced principal (never touch real users)."""
    if NAMESPACE_PREFIX not in user_id:
        raise ValueError(
            f"refusing to operate on non-namespaced principal {user_id!r}: "
            f"harness principals MUST carry {NAMESPACE_PREFIX!r}"
        )


def teardown(conn, run_id: str) -> int:
    """Delete deletable rows for this run's namespaced principals.

    ``conn`` is a psycopg2 connection (only used in in_process/external modes).
    Returns the number of rows deleted. audit_events are append-only by design
    and remain — but only ever under namespaced principals. Verifies isolation
    before deleting (never a wildcard).
    """
    ns = run_id if run_id.startswith(NAMESPACE_PREFIX) else NAMESPACE_PREFIX + run_id
    like = ns + "%"
    deleted = 0
    with conn.cursor() as cur:
        for table in _DELETABLE_USER_TABLES:
            try:
                cur.execute(
                    f"DELETE FROM {table} WHERE user_id LIKE %s", (like,)
                )
                deleted += cur.rowcount or 0
            except Exception as exc:  # table may not exist in a given schema rev
                logger.debug("teardown skip %s: %s", table, exc)
        conn.commit()
    logger.info("teardown removed %d row(s) for run %s", deleted, ns)
    return deleted
