import unittest
import os
import shutil
import json
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator.history import HistoryManager
from shared.database import Database

class TestHistoryManagerSQLite(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_data"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_init_creates_db(self):
        hm = HistoryManager(data_dir=self.test_dir)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "chats.db")))
        
    def test_create_chat(self):
        hm = HistoryManager(data_dir=self.test_dir)
        chat_id = hm.create_chat()
        self.assertIsNotNone(chat_id)
        
        # Verify in DB
        db = Database(os.path.join(self.test_dir, "chats.db"))
        row = db.fetch_one("SELECT * FROM chats WHERE id = ?", (chat_id,))
        self.assertIsNotNone(row)
        self.assertEqual(row['title'], "New Chat")

    def test_add_message_and_get_chat(self):
        hm = HistoryManager(data_dir=self.test_dir)
        chat_id = hm.create_chat()
        
        hm.add_message(chat_id, "user", "Hello World")
        hm.add_message(chat_id, "assistant", {"response": "Hi there"})
        
        chat = hm.get_chat(chat_id)
        self.assertEqual(len(chat['messages']), 2)
        self.assertEqual(chat['messages'][0]['content'], "Hello World")
        self.assertEqual(chat['messages'][1]['content'], {"response": "Hi there"})
        
        # Verify title update
        self.assertEqual(chat['title'], "Hello World")

    def test_migration(self):
        # Create a legacy JSON file
        json_data = {
            "chat1": {
                "id": "chat1",
                "title": "Legacy Chat",
                "created_at": 1000,
                "updated_at": 2000,
                "messages": [
                    {"role": "user", "content": "Legacy Msg", "timestamp": 1500}
                ]
            }
        }
        with open(os.path.join(self.test_dir, "chats.json"), 'w') as f:
            json.dump(json_data, f)
            
        # Initialize HistoryManager, should trigger migration
        hm = HistoryManager(data_dir=self.test_dir)
        
        # Check DB
        chat = hm.get_chat("chat1")
        self.assertIsNotNone(chat)
        self.assertEqual(chat['title'], "Legacy Chat")
        self.assertEqual(len(chat['messages']), 1)
        self.assertEqual(chat['messages'][0]['content'], "Legacy Msg")
        
        # Check backup file
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "chats.json.bak")))

if __name__ == '__main__':
    unittest.main()
