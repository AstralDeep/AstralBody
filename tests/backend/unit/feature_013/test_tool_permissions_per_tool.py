"""Feature 013 / US3 — per-tool, per-permission-kind permission resolution.

Covers the new ``is_tool_allowed`` resolution order:
  1. Per-(tool, kind) row > legacy NULL-kind override > agent_scopes fallback.

Plus ``set_tool_permission``, ``get_effective_tool_permissions``, and
``backfill_per_tool_rows`` (FR-015 1:1 carry-forward).
"""
from __future__ import annotations

import os
import sys
import unittest
import uuid

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from orchestrator.tool_permissions import ToolPermissionManager  # noqa: E402
from shared.database import Database  # noqa: E402


class TestPerToolPermissions(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database()
        self.user_id = f"u-013-{uuid.uuid4()}"
        self.agent_id = f"agent-013-{uuid.uuid4()}"
        self.tpm = ToolPermissionManager(db=self.db)
        # Register an agent with a mix of tools across all four kinds.
        self.tpm.register_tool_scopes(self.agent_id, {
            "search_web": "tools:search",
            "read_file": "tools:read",
            "send_email": "tools:write",
            "ping": "tools:system",
        })

    def tearDown(self) -> None:
        try:
            self.db.execute("DELETE FROM tool_overrides WHERE user_id = ?", (self.user_id,))
            self.db.execute("DELETE FROM agent_scopes WHERE user_id = ?", (self.user_id,))
        except Exception:
            pass

    # ── is_tool_allowed resolution order ────────────────────────────────

    def test_default_state_is_blocked(self) -> None:
        """No rows + no scope state ⇒ tool is blocked (default-deny)."""
        self.assertFalse(self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email"))

    def test_falls_back_to_scope_when_no_per_tool_row(self) -> None:
        """Scope enabled but no per-tool row ⇒ tool is allowed."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": True})
        self.assertTrue(self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email"))

    def test_per_tool_row_overrides_scope_off(self) -> None:
        """Scope disabled, per-tool row enabled ⇒ tool is allowed (per-tool wins)."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": False})
        self.tpm.set_tool_permission(
            self.user_id, self.agent_id, "send_email", "tools:write", True
        )
        self.assertTrue(self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email"))

    def test_per_tool_row_overrides_scope_on(self) -> None:
        """Scope enabled, per-tool row disabled ⇒ tool is blocked (per-tool wins)."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": True})
        self.tpm.set_tool_permission(
            self.user_id, self.agent_id, "send_email", "tools:write", False
        )
        self.assertFalse(self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email"))

    def test_legacy_null_kind_override_blocks(self) -> None:
        """Legacy tool-wide override (permission_kind IS NULL, enabled=False) blocks the tool."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": True})
        # Insert a legacy NULL-kind disable row directly.
        self.db.execute(
            """INSERT INTO tool_overrides
               (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
               VALUES (?, ?, ?, NULL, FALSE, ?)""",
            (self.user_id, self.agent_id, "send_email", 0),
        )
        self.assertFalse(self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email"))

    def test_per_tool_row_takes_priority_over_legacy_null_row(self) -> None:
        """If both a legacy NULL row (disabled) and a per-kind row exist, per-kind wins."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": False})
        self.db.execute(
            """INSERT INTO tool_overrides
               (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
               VALUES (?, ?, ?, NULL, FALSE, ?)""",
            (self.user_id, self.agent_id, "send_email", 0),
        )
        self.tpm.set_tool_permission(
            self.user_id, self.agent_id, "send_email", "tools:write", True
        )
        self.assertTrue(self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email"))

    def test_set_tool_permission_validates_kind(self) -> None:
        with self.assertRaises(ValueError):
            self.tpm.set_tool_permission(
                self.user_id, self.agent_id, "send_email", "tools:bogus", True
            )

    # ── get_effective_tool_permissions ─────────────────────────────────

    def test_effective_map_has_only_applicable_kinds_per_tool(self) -> None:
        """FR-014 — only the kind that applies to each tool appears."""
        self.tpm.set_agent_scopes(
            self.user_id, self.agent_id,
            {"tools:read": True, "tools:write": False, "tools:search": True, "tools:system": False},
        )
        eff = self.tpm.get_effective_tool_permissions(self.user_id, self.agent_id)
        self.assertEqual(set(eff.keys()), {"search_web", "read_file", "send_email", "ping"})
        self.assertEqual(set(eff["search_web"].keys()), {"tools:search"})
        self.assertEqual(set(eff["send_email"].keys()), {"tools:write"})
        self.assertTrue(eff["read_file"]["tools:read"])
        self.assertFalse(eff["send_email"]["tools:write"])

    # ── backfill_per_tool_rows (FR-015) ────────────────────────────────

    def test_backfill_carries_forward_scope_state_to_per_tool_rows(self) -> None:
        """FR-015 — per-tool row is ON iff its scope was previously enabled."""
        self.tpm.set_agent_scopes(
            self.user_id, self.agent_id,
            {"tools:read": True, "tools:write": False, "tools:search": True, "tools:system": False},
        )
        inserted = self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        self.assertEqual(inserted, 4)  # one per registered tool
        rows = self.db.fetch_all(
            """SELECT tool_name, permission_kind, enabled FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND permission_kind IS NOT NULL
               ORDER BY tool_name""",
            (self.user_id, self.agent_id),
        )
        by_tool = {r["tool_name"]: (r["permission_kind"], bool(r["enabled"])) for r in rows}
        self.assertEqual(by_tool["read_file"], ("tools:read", True))
        self.assertEqual(by_tool["search_web"], ("tools:search", True))
        self.assertEqual(by_tool["send_email"], ("tools:write", False))
        self.assertEqual(by_tool["ping"], ("tools:system", False))

    def test_backfill_is_idempotent(self) -> None:
        """Subsequent calls insert no additional rows."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:read": True})
        first = self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        second = self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        third = self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        self.assertEqual(first, 4)
        self.assertEqual(second, 0)
        self.assertEqual(third, 0)

    def test_backfill_does_not_widen(self) -> None:
        """Per-tool row pre-existing as False stays False even if scope is True afterward."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": False})
        # Pre-existing per-tool row says False.
        self.tpm.set_tool_permission(
            self.user_id, self.agent_id, "send_email", "tools:write", False
        )
        # Scope flips to True.
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:write": True})
        # Backfill MUST NOT clobber the existing per-tool row.
        self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        self.assertFalse(
            self.tpm.is_tool_allowed(self.user_id, self.agent_id, "send_email")
        )


if __name__ == "__main__":
    unittest.main()
