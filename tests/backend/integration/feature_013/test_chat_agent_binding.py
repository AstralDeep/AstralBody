"""Feature 013 / US2 — chat ↔ agent binding integration tests.

Verifies the end-to-end persistence path:
  - HistoryManager.create_chat persists agent_id when supplied.
  - get_chat / get_recent_chats surface agent_id.
  - get_chat_agent / set_chat_agent round-trip.
  - Deleting the agent from agent_ownership does NOT mutate
    chats.agent_id (the frontend detects unavailability via the
    agents list rather than via chat-row mutation, per FR-009).
"""
from __future__ import annotations

import os
import sys
import unittest
import uuid

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from orchestrator.history import HistoryManager  # noqa: E402
from shared.database import Database  # noqa: E402


class TestChatAgentBinding(unittest.TestCase):
    def setUp(self) -> None:
        self.hm = HistoryManager(data_dir="test_data")
        self.user_id = f"u-013-{uuid.uuid4()}"
        self.agent_id = f"agent-013-{uuid.uuid4()}"
        # seed an ownership row so the agent looks "real" to anyone who
        # cross-references agent_ownership; Story 2 doesn't require it
        # but the unavailability scenario does.
        Database().set_agent_ownership(self.agent_id, owner_email=f"{self.user_id}@example.com")

    def tearDown(self) -> None:
        try:
            self.hm.db.execute(
                "DELETE FROM messages WHERE user_id = ?", (self.user_id,)
            )
            self.hm.db.execute(
                "DELETE FROM chats WHERE user_id = ?", (self.user_id,)
            )
            self.hm.db.execute(
                "DELETE FROM agent_ownership WHERE agent_id = ?", (self.agent_id,)
            )
        except Exception:
            pass

    def test_create_chat_persists_agent_id(self) -> None:
        chat_id = self.hm.create_chat(user_id=self.user_id, agent_id=self.agent_id)
        self.assertEqual(self.hm.db.get_chat_agent(chat_id), self.agent_id)

    def test_create_chat_without_agent_id_leaves_column_null(self) -> None:
        chat_id = self.hm.create_chat(user_id=self.user_id)
        self.assertIsNone(self.hm.db.get_chat_agent(chat_id))

    def test_get_chat_surfaces_agent_id_in_dict(self) -> None:
        chat_id = self.hm.create_chat(user_id=self.user_id, agent_id=self.agent_id)
        chat = self.hm.get_chat(chat_id, user_id=self.user_id)
        self.assertIsNotNone(chat)
        assert chat is not None
        self.assertEqual(chat["agent_id"], self.agent_id)

    def test_get_recent_chats_surfaces_agent_id(self) -> None:
        chat_id = self.hm.create_chat(user_id=self.user_id, agent_id=self.agent_id)
        # Add a message so the chat shows up in recent.
        self.hm.add_message(chat_id, "user", "hi", user_id=self.user_id)
        recent = self.hm.get_recent_chats(limit=10, user_id=self.user_id)
        match = next((c for c in recent if c["id"] == chat_id), None)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match["agent_id"], self.agent_id)

    def test_set_chat_agent_round_trip(self) -> None:
        chat_id = self.hm.create_chat(user_id=self.user_id)
        self.assertIsNone(self.hm.db.get_chat_agent(chat_id))
        self.hm.db.set_chat_agent(chat_id, self.agent_id)
        self.assertEqual(self.hm.db.get_chat_agent(chat_id), self.agent_id)
        # Switching to another agent updates the binding (FR-008).
        other = f"agent-other-{uuid.uuid4()}"
        self.hm.db.set_chat_agent(chat_id, other)
        self.assertEqual(self.hm.db.get_chat_agent(chat_id), other)
        # Setting to None unbinds.
        self.hm.db.set_chat_agent(chat_id, None)
        self.assertIsNone(self.hm.db.get_chat_agent(chat_id))

    def test_deleting_agent_ownership_does_not_mutate_chat_agent_id(self) -> None:
        """Per FR-009 the frontend detects unavailability separately; chats keep their bound agent_id."""
        chat_id = self.hm.create_chat(user_id=self.user_id, agent_id=self.agent_id)
        # Simulate the agent being deleted/deprecated.
        self.hm.db.execute(
            "DELETE FROM agent_ownership WHERE agent_id = ?", (self.agent_id,)
        )
        # Chat row's agent_id stays as-is; the system MUST NOT silently re-route.
        self.assertEqual(self.hm.db.get_chat_agent(chat_id), self.agent_id)


if __name__ == "__main__":
    unittest.main()
