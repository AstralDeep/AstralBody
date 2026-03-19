import unittest
import os
import json
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator.history import HistoryManager
from shared.database import Database

class TestHistoryManagerPostgres(unittest.TestCase):
    def setUp(self):
        self.data_dir = "test_data"
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        pass

    def test_init_creates_tables(self):
        hm = HistoryManager(data_dir=self.data_dir)
        # Verify tables exist by querying
        row = hm.db.fetch_one(
            "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'chats'"
        )
        self.assertEqual(row['count'], 1)

    def test_create_chat(self):
        hm = HistoryManager(data_dir=self.data_dir)
        chat_id = hm.create_chat()
        self.assertIsNotNone(chat_id)

        # Verify in DB
        row = hm.db.fetch_one("SELECT * FROM chats WHERE id = ?", (chat_id,))
        self.assertIsNotNone(row)
        self.assertEqual(row['title'], "New Chat")

        # Cleanup
        hm.db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    def test_add_message_and_get_chat(self):
        hm = HistoryManager(data_dir=self.data_dir)
        chat_id = hm.create_chat()

        hm.add_message(chat_id, "user", "Hello World")
        hm.add_message(chat_id, "assistant", {"response": "Hi there"})

        chat = hm.get_chat(chat_id)
        self.assertEqual(len(chat['messages']), 2)
        self.assertEqual(chat['messages'][0]['content'], "Hello World")
        self.assertEqual(chat['messages'][1]['content'], {"response": "Hi there"})

        # Verify title update
        self.assertEqual(chat['title'], "Hello World")

        # Cleanup
        hm.db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        hm.db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

if __name__ == '__main__':
    unittest.main()
