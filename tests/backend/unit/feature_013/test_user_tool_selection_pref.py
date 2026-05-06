"""Feature 013 / US4 — per-user tool-selection preference helpers.

Verifies the get/set/clear round-trip for the in-chat tool picker
preference stored under user_preferences.tool_selection.<agent_id>.
"""
from __future__ import annotations

import os
import sys
import unittest
import uuid

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from shared.database import Database  # noqa: E402


class TestUserToolSelectionPref(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database()
        self.user_id = f"u-013-{uuid.uuid4()}"
        self.agent_a = f"agent-a-{uuid.uuid4()}"
        self.agent_b = f"agent-b-{uuid.uuid4()}"

    def tearDown(self) -> None:
        try:
            self.db.execute(
                "DELETE FROM user_preferences WHERE user_id = ?", (self.user_id,)
            )
        except Exception:
            pass

    def test_unset_returns_none(self) -> None:
        self.assertIsNone(self.db.get_user_tool_selection(self.user_id, self.agent_a))

    def test_set_then_get(self) -> None:
        self.db.set_user_tool_selection(self.user_id, self.agent_a, ["t1", "t2"])
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, self.agent_a),
            ["t1", "t2"],
        )

    def test_per_agent_isolation(self) -> None:
        self.db.set_user_tool_selection(self.user_id, self.agent_a, ["t1"])
        self.db.set_user_tool_selection(self.user_id, self.agent_b, ["t2", "t3"])
        self.assertEqual(self.db.get_user_tool_selection(self.user_id, self.agent_a), ["t1"])
        self.assertEqual(self.db.get_user_tool_selection(self.user_id, self.agent_b), ["t2", "t3"])

    def test_set_overwrites(self) -> None:
        self.db.set_user_tool_selection(self.user_id, self.agent_a, ["t1"])
        self.db.set_user_tool_selection(self.user_id, self.agent_a, ["t2", "t3"])
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, self.agent_a),
            ["t2", "t3"],
        )

    def test_clear_only_targets_agent(self) -> None:
        self.db.set_user_tool_selection(self.user_id, self.agent_a, ["t1"])
        self.db.set_user_tool_selection(self.user_id, self.agent_b, ["t2"])
        self.assertTrue(self.db.clear_user_tool_selection(self.user_id, self.agent_a))
        self.assertIsNone(self.db.get_user_tool_selection(self.user_id, self.agent_a))
        self.assertEqual(self.db.get_user_tool_selection(self.user_id, self.agent_b), ["t2"])

    def test_clear_is_idempotent_returns_false_when_absent(self) -> None:
        self.assertFalse(self.db.clear_user_tool_selection(self.user_id, self.agent_a))

    def test_does_not_clobber_unrelated_prefs(self) -> None:
        # Pre-existing unrelated pref under the same user must survive
        # set/clear of tool_selection.
        self.db.set_user_preferences(self.user_id, {"theme": "dark"})
        self.db.set_user_tool_selection(self.user_id, self.agent_a, ["t1"])
        self.assertEqual(
            self.db.get_user_preferences(self.user_id).get("theme"),
            "dark",
        )
        self.db.clear_user_tool_selection(self.user_id, self.agent_a)
        self.assertEqual(
            self.db.get_user_preferences(self.user_id).get("theme"),
            "dark",
        )


if __name__ == "__main__":
    unittest.main()
