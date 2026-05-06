"""Feature 013 / US4 — tool-selection preference contract test.

Drives the data path that backs the /api/users/me/tool-selection
endpoints without standing up FastAPI. Pins the validation contract:
  - Empty arrays are rejected (FR-021 defensive).
  - Tools must belong to the agent.
  - Tools must pass is_tool_allowed (cannot widen — FR-020).
  - DELETE is idempotent (FR-025).
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


class TestToolSelectionPrefEndpoints(unittest.TestCase):
    """Mirror the validation chain in `set_user_tool_selection` /
    `clear_user_tool_selection` (api.py) without spinning up FastAPI."""

    def setUp(self) -> None:
        self.db = Database()
        self.user_id = f"u-013-{uuid.uuid4()}"
        self.agent_id = f"agent-013-{uuid.uuid4()}"
        self.tpm = ToolPermissionManager(db=self.db)
        self.tpm.register_tool_scopes(self.agent_id, {
            "search_web": "tools:search",
            "send_email": "tools:write",
        })
        # Enable search but NOT write — so send_email is permission-blocked.
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {
            "tools:search": True,
            "tools:write": False,
        })

    def tearDown(self) -> None:
        try:
            self.db.execute("DELETE FROM agent_scopes WHERE user_id = ?", (self.user_id,))
            self.db.execute("DELETE FROM tool_overrides WHERE user_id = ?", (self.user_id,))
            self.db.execute("DELETE FROM user_preferences WHERE user_id = ?", (self.user_id,))
        except Exception:
            pass

    def _validate_put(self, agent_tool_ids: set, selected: list) -> str:
        """Reproduce the API's validation rules. Returns 'ok' or a reason string."""
        if not selected:
            return "empty_selection_not_allowed"
        unknown = [t for t in selected if t not in agent_tool_ids]
        if unknown:
            return f"unknown_tools:{unknown}"
        blocked = [
            t for t in selected
            if not self.tpm.is_tool_allowed(self.user_id, self.agent_id, t)
        ]
        if blocked:
            return f"blocked_tools:{blocked}"
        return "ok"

    def test_put_rejects_empty_array(self) -> None:
        agent_tools = {"search_web", "send_email"}
        self.assertEqual(
            self._validate_put(agent_tools, []),
            "empty_selection_not_allowed",
        )

    def test_put_rejects_tools_not_on_agent(self) -> None:
        agent_tools = {"search_web", "send_email"}
        result = self._validate_put(agent_tools, ["search_web", "ghost_tool"])
        self.assertTrue(result.startswith("unknown_tools:"))

    def test_put_rejects_tools_blocked_by_permissions(self) -> None:
        agent_tools = {"search_web", "send_email"}
        result = self._validate_put(agent_tools, ["search_web", "send_email"])
        # send_email's scope (tools:write) is disabled.
        self.assertTrue(result.startswith("blocked_tools:"))

    def test_put_accepts_valid_subset(self) -> None:
        agent_tools = {"search_web", "send_email"}
        self.assertEqual(self._validate_put(agent_tools, ["search_web"]), "ok")

    def test_get_returns_none_when_unset_then_value_after_set(self) -> None:
        self.assertIsNone(self.db.get_user_tool_selection(self.user_id, self.agent_id))
        self.db.set_user_tool_selection(self.user_id, self.agent_id, ["search_web"])
        self.assertEqual(
            self.db.get_user_tool_selection(self.user_id, self.agent_id),
            ["search_web"],
        )

    def test_delete_clears_and_is_idempotent(self) -> None:
        self.db.set_user_tool_selection(self.user_id, self.agent_id, ["search_web"])
        self.assertTrue(self.db.clear_user_tool_selection(self.user_id, self.agent_id))
        self.assertIsNone(self.db.get_user_tool_selection(self.user_id, self.agent_id))
        # Second clear is a no-op (returns False, no exception).
        self.assertFalse(self.db.clear_user_tool_selection(self.user_id, self.agent_id))


if __name__ == "__main__":
    unittest.main()
