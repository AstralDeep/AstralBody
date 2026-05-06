"""Feature 013 follow-up — per-user agent disable preference.

Verifies the helpers that back the agent on/off toggle:
  - get_user_disabled_agents → list of agent_ids (default empty).
  - is_user_agent_disabled → boolean.
  - set_user_agent_disabled → idempotent, isolated per user, does not
    touch agent_scopes / tool_overrides.
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


class TestUserAgentDisable(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database()
        self.user_id = f"u-013-{uuid.uuid4()}"
        self.other_user = f"u-other-{uuid.uuid4()}"
        self.agent_id = f"agent-013-{uuid.uuid4()}"
        self.other_agent = f"agent-other-{uuid.uuid4()}"

    def tearDown(self) -> None:
        try:
            self.db.execute(
                "DELETE FROM user_preferences WHERE user_id IN (?, ?)",
                (self.user_id, self.other_user),
            )
        except Exception:
            pass

    def test_default_state_is_enabled(self) -> None:
        self.assertFalse(self.db.is_user_agent_disabled(self.user_id, self.agent_id))
        self.assertEqual(self.db.get_user_disabled_agents(self.user_id), [])

    def test_disable_then_enable_round_trip(self) -> None:
        self.assertTrue(self.db.set_user_agent_disabled(self.user_id, self.agent_id, True))
        self.assertTrue(self.db.is_user_agent_disabled(self.user_id, self.agent_id))
        self.assertEqual(
            self.db.get_user_disabled_agents(self.user_id),
            [self.agent_id],
        )
        self.assertTrue(self.db.set_user_agent_disabled(self.user_id, self.agent_id, False))
        self.assertFalse(self.db.is_user_agent_disabled(self.user_id, self.agent_id))
        self.assertEqual(self.db.get_user_disabled_agents(self.user_id), [])

    def test_idempotent_returns_false_when_state_unchanged(self) -> None:
        self.db.set_user_agent_disabled(self.user_id, self.agent_id, True)
        # Calling with the same state returns False (no-op).
        self.assertFalse(
            self.db.set_user_agent_disabled(self.user_id, self.agent_id, True)
        )

    def test_per_agent_isolation(self) -> None:
        self.db.set_user_agent_disabled(self.user_id, self.agent_id, True)
        # Toggling agent_a does not affect agent_b.
        self.assertFalse(self.db.is_user_agent_disabled(self.user_id, self.other_agent))
        self.db.set_user_agent_disabled(self.user_id, self.other_agent, True)
        # Both are now disabled but tracked independently.
        disabled = sorted(self.db.get_user_disabled_agents(self.user_id))
        self.assertEqual(disabled, sorted([self.agent_id, self.other_agent]))
        self.db.set_user_agent_disabled(self.user_id, self.agent_id, False)
        self.assertEqual(
            self.db.get_user_disabled_agents(self.user_id),
            [self.other_agent],
        )

    def test_per_user_isolation(self) -> None:
        # Disabling for user A must not affect user B.
        self.db.set_user_agent_disabled(self.user_id, self.agent_id, True)
        self.assertTrue(self.db.is_user_agent_disabled(self.user_id, self.agent_id))
        self.assertFalse(self.db.is_user_agent_disabled(self.other_user, self.agent_id))

    def test_does_not_clobber_other_preferences(self) -> None:
        self.db.set_user_preferences(self.user_id, {"theme": "dark"})
        self.db.set_user_agent_disabled(self.user_id, self.agent_id, True)
        # Theme survives.
        self.assertEqual(
            self.db.get_user_preferences(self.user_id).get("theme"),
            "dark",
        )
        # Re-enabling removes the agent_id but keeps theme.
        self.db.set_user_agent_disabled(self.user_id, self.agent_id, False)
        self.assertEqual(
            self.db.get_user_preferences(self.user_id).get("theme"),
            "dark",
        )


if __name__ == "__main__":
    unittest.main()
