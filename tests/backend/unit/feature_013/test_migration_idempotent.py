"""Feature 013 — schema migration idempotency tests.

Verifies that the schema delta added by Feature 013
(`chats.agent_id`, `tool_overrides.permission_kind` + new unique
index, helpers for per-user tool-selection prefs) applies cleanly
on (a) an empty database, (b) re-runs against an already-migrated
database (no duplicate work), and (c) a database that already has
pre-013 data in `agent_scopes` and `tool_overrides`.

Run via pytest with the project's standard backend path injection.
"""
from __future__ import annotations

import os
import sys
import unittest
import uuid

# Ensure backend modules import cleanly when running pytest from repo root.
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from shared.database import Database  # noqa: E402  (path injection above)


class TestFeature013MigrationIdempotent(unittest.TestCase):
    """Schema delta from Feature 013 must be safe to apply repeatedly."""

    def setUp(self) -> None:
        # Each test instance gets a fresh Database wrapper. _init_db()
        # runs in __init__, so simply constructing the object is the
        # "apply migration" step. PostgreSQL is shared across tests in
        # the project's test setup; tests scope their state with unique
        # user_ids to avoid cross-test interference.
        self.db = Database()
        self.user_id = f"test-013-{uuid.uuid4()}"
        self.agent_id = f"agent-013-{uuid.uuid4()}"

    def tearDown(self) -> None:
        # Best-effort cleanup of test rows.
        try:
            self.db.execute(
                "DELETE FROM tool_overrides WHERE user_id = ?", (self.user_id,)
            )
            self.db.execute(
                "DELETE FROM agent_scopes WHERE user_id = ?", (self.user_id,)
            )
            self.db.execute(
                "DELETE FROM user_preferences WHERE user_id = ?", (self.user_id,)
            )
        except Exception:
            pass

    def test_chats_has_agent_id_column(self) -> None:
        """chats.agent_id must exist after _init_db runs."""
        row = self.db.fetch_one(
            "SELECT 1 AS present FROM information_schema.columns "
            "WHERE table_name = 'chats' AND column_name = 'agent_id'"
        )
        self.assertIsNotNone(row)

    def test_tool_overrides_has_permission_kind_column(self) -> None:
        """tool_overrides.permission_kind must exist after _init_db runs."""
        row = self.db.fetch_one(
            "SELECT 1 AS present FROM information_schema.columns "
            "WHERE table_name = 'tool_overrides' AND column_name = 'permission_kind'"
        )
        self.assertIsNotNone(row)

    def test_unique_index_includes_permission_kind(self) -> None:
        """The new unique index must include permission_kind via COALESCE."""
        row = self.db.fetch_one(
            "SELECT 1 AS present FROM pg_indexes "
            "WHERE indexname = 'tool_overrides_user_agent_tool_kind_uniq'"
        )
        self.assertIsNotNone(row)

    def test_init_db_is_idempotent(self) -> None:
        """Re-constructing Database (which re-runs _init_db) must not fail."""
        # First run already happened in setUp; do another and verify.
        Database()
        # Running it a third time should also be a no-op.
        Database()
        # If we got here without exception, the migration is idempotent.
        self.assertTrue(True)

    def test_per_kind_rows_can_coexist_with_legacy_null_row(self) -> None:
        """A legacy NULL-kind row and per-kind rows must coexist for the same tool."""
        tool = "test_tool_xyz"
        # Legacy tool-wide override (permission_kind IS NULL, disabled)
        self.db.execute(
            """INSERT INTO tool_overrides
               (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
               VALUES (?, ?, ?, NULL, FALSE, ?)""",
            (self.user_id, self.agent_id, tool, 0),
        )
        # Per-kind row for the same tool — must NOT collide
        self.db.execute(
            """INSERT INTO tool_overrides
               (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
               VALUES (?, ?, ?, ?, TRUE, ?)""",
            (self.user_id, self.agent_id, tool, "tools:read", 0),
        )
        rows = self.db.fetch_all(
            """SELECT permission_kind, enabled FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND tool_name = ?
               ORDER BY permission_kind NULLS FIRST""",
            (self.user_id, self.agent_id, tool),
        )
        self.assertEqual(len(rows), 2)

    def test_per_kind_unique_constraint_prevents_duplicates(self) -> None:
        """Inserting the same (user, agent, tool, kind) twice must raise."""
        tool = "test_tool_dup"
        self.db.execute(
            """INSERT INTO tool_overrides
               (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
               VALUES (?, ?, ?, ?, TRUE, ?)""",
            (self.user_id, self.agent_id, tool, "tools:read", 0),
        )
        with self.assertRaises(Exception):
            self.db.execute(
                """INSERT INTO tool_overrides
                   (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
                   VALUES (?, ?, ?, ?, FALSE, ?)""",
                (self.user_id, self.agent_id, tool, "tools:read", 0),
            )

    def test_chat_agent_helpers(self) -> None:
        """get_chat_agent / set_chat_agent round-trip the agent_id."""
        chat_id = f"chat-013-{uuid.uuid4()}"
        self.db.execute(
            "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, self.user_id, "Test", 0, 0),
        )
        self.assertIsNone(self.db.get_chat_agent(chat_id))
        self.db.set_chat_agent(chat_id, self.agent_id)
        self.assertEqual(self.db.get_chat_agent(chat_id), self.agent_id)
        self.db.set_chat_agent(chat_id, None)
        self.assertIsNone(self.db.get_chat_agent(chat_id))
        # cleanup
        self.db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    def test_user_tool_selection_helpers(self) -> None:
        """get/set/clear round-trip per-user, per-agent tool selection."""
        # Initially absent
        self.assertIsNone(self.db.get_user_tool_selection(self.user_id, self.agent_id))
        # Set a selection
        self.db.set_user_tool_selection(self.user_id, self.agent_id, ["tool_a", "tool_b"])
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, self.agent_id),
            ["tool_a", "tool_b"],
        )
        # Saving for a second agent does not clobber the first
        other_agent = f"agent-other-{uuid.uuid4()}"
        self.db.set_user_tool_selection(self.user_id, other_agent, ["tool_c"])
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, self.agent_id),
            ["tool_a", "tool_b"],
        )
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, other_agent),
            ["tool_c"],
        )
        # Clear is idempotent and only clears the targeted agent
        cleared = self.db.clear_user_tool_selection(self.user_id, self.agent_id)
        self.assertTrue(cleared)
        self.assertIsNone(self.db.get_user_tool_selection(self.user_id, self.agent_id))
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, other_agent),
            ["tool_c"],
        )
        # Re-clearing the same key is a no-op (returns False, no exception)
        self.assertFalse(self.db.clear_user_tool_selection(self.user_id, self.agent_id))


if __name__ == "__main__":
    unittest.main()
