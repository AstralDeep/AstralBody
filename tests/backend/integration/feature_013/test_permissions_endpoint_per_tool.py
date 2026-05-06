"""Feature 013 / US3 — per-tool permissions API integration test.

Drives the model+resolver path that backs `PUT /api/agents/{id}/permissions`
(per-tool shape) and `GET /api/agents/{id}/permissions` (per-tool response)
without standing up the full FastAPI app. The endpoint thin layer is
covered by the API smoke tests; this test pins the contract guarantees:

  - per-tool body shape persists (FR-010, FR-013).
  - legacy scope-shaped body still works AND mirrors per-tool rows.
  - 1:1 backfill is idempotent (FR-015).
  - GET response shape includes only applicable kinds per tool (FR-014).
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


class TestPermissionsEndpointPerTool(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database()
        self.user_id = f"u-013-{uuid.uuid4()}"
        self.agent_id = f"agent-013-{uuid.uuid4()}"
        self.tpm = ToolPermissionManager(db=self.db)
        self.tpm.register_tool_scopes(self.agent_id, {
            "search_web": "tools:search",
            "read_file": "tools:read",
            "send_email": "tools:write",
        })

    def tearDown(self) -> None:
        try:
            self.db.execute("DELETE FROM tool_overrides WHERE user_id = ?", (self.user_id,))
            self.db.execute("DELETE FROM agent_scopes WHERE user_id = ?", (self.user_id,))
        except Exception:
            pass

    def test_per_tool_body_persists_per_tool_rows(self) -> None:
        """Mirror the endpoint's per-tool path."""
        per_tool = {
            "search_web": {"tools:search": True},
            "send_email": {"tools:write": False},
        }
        for tool, kind_map in per_tool.items():
            for kind, enabled in kind_map.items():
                self.tpm.set_tool_permission(
                    self.user_id, self.agent_id, tool, kind, enabled
                )
        # Row presence + values
        eff = self.tpm.get_effective_tool_permissions(self.user_id, self.agent_id)
        self.assertTrue(eff["search_web"]["tools:search"])
        self.assertFalse(eff["send_email"]["tools:write"])

    def test_legacy_scope_body_writes_per_tool_rows_in_sync(self) -> None:
        """Mirror the endpoint's legacy fallback: scopes update + per-tool mirror."""
        # legacy scope payload
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {
            "tools:read": True, "tools:write": False, "tools:search": True,
        })
        # endpoint then mirrors per-tool rows from the new state
        for tool, required_scope in self.tpm.get_tool_scope_map(self.agent_id).items():
            scope_enabled = self.tpm.is_scope_enabled(
                self.user_id, self.agent_id, required_scope
            )
            self.tpm.set_tool_permission(
                self.user_id, self.agent_id, tool, required_scope, scope_enabled
            )
        eff = self.tpm.get_effective_tool_permissions(self.user_id, self.agent_id)
        self.assertTrue(eff["read_file"]["tools:read"])
        self.assertFalse(eff["send_email"]["tools:write"])
        self.assertTrue(eff["search_web"]["tools:search"])

    def test_get_returns_only_applicable_kinds_per_tool(self) -> None:
        """FR-014 — only the kind that applies to each tool appears in the response."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:read": True})
        eff = self.tpm.get_effective_tool_permissions(self.user_id, self.agent_id)
        # search_web only carries tools:search; not tools:read.
        self.assertEqual(set(eff["search_web"].keys()), {"tools:search"})
        self.assertEqual(set(eff["read_file"].keys()), {"tools:read"})
        self.assertEqual(set(eff["send_email"].keys()), {"tools:write"})

    def test_first_read_backfill_is_idempotent(self) -> None:
        """FR-015 — the lazy backfill GET triggers must be safe to call repeatedly."""
        self.tpm.set_agent_scopes(self.user_id, self.agent_id, {"tools:read": True})
        first = self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        second = self.tpm.backfill_per_tool_rows(self.user_id, self.agent_id)
        self.assertGreaterEqual(first, 1)
        self.assertEqual(second, 0)


if __name__ == "__main__":
    unittest.main()
