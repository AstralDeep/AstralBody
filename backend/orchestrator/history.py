import json
import os
import time
import uuid
from typing import List, Dict, Optional
import logging
import sys

# Ensure shared module is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.database import Database

logger = logging.getLogger('HistoryManager')

class HistoryManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, "chats.db")
        self.json_file = os.path.join(data_dir, "chats.json")
        self.db = Database(self.db_path)
        self._ensure_data_dir()
        self._migrate_from_json()

    def _ensure_data_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _migrate_from_json(self):
        """Migrate existing JSON history to SQLite."""
        if not os.path.exists(self.json_file):
            return

        # Check if DB is empty
        try:
            row = self.db.fetch_one("SELECT COUNT(*) as count FROM chats")
            if row['count'] > 0:
                # DB already has data, assume migration done or not needed
                return
        except Exception as e:
            logger.error(f"Error checking DB state: {e}")
            return

        logger.info("Migrating JSON history to SQLite...")
        try:
            with open(self.json_file, 'r') as f:
                chats = json.load(f)
            
            for chat_id, chat_data in chats.items():
                self.db.execute(
                    "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (chat_id, chat_data.get('title'), chat_data.get('created_at'), chat_data.get('updated_at'))
                )
                
                for msg in chat_data.get('messages', []):
                    # Serialize content if it's not a string
                    content = msg.get('content')
                    if not isinstance(content, str):
                        content = json.dumps(content)
                        
                    self.db.execute(
                        "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                        (chat_id, msg.get('role'), content, msg.get('timestamp'))
                    )
            
            # Rename JSON file to backup to prevent re-migration
            os.rename(self.json_file, self.json_file + ".bak")
            logger.info("Migration complete. JSON file renamed to .bak")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    def create_chat(self) -> str:
        """Create a new chat session."""
        chat_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        self.db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, "New Chat", timestamp, timestamp)
        )
        return chat_id

    def add_message(self, chat_id: str, role: str, content: any):
        """Add a message to a chat session."""
        timestamp = int(time.time() * 1000)
        
        # Serialize content if needed
        content_str = content
        if not isinstance(content, str):
            content_str = json.dumps(content)

        # Check if chat exists
        chat = self.db.fetch_one("SELECT id FROM chats WHERE id = ?", (chat_id,))
        if not chat:
            logger.warning(f"Attempted to add message to non-existent chat {chat_id}")
            return

        # Auto-update title logic
        if role == "user":
            # Check message count
            count_row = self.db.fetch_one("SELECT COUNT(*) as count FROM messages WHERE chat_id = ?", (chat_id,))
            if count_row['count'] == 0:
                # First message, update title
                display_content = str(content)
                title = display_content[:30] + "..." if len(display_content) > 30 else display_content
                self.db.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))

        self.db.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (chat_id, role, content_str, timestamp)
        )
        
        # Update chat timestamp
        self.db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (timestamp, chat_id))

    def update_chat_title(self, chat_id: str, title: str):
        """Update the title of a specific chat."""
        timestamp = int(time.time() * 1000)
        self.db.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?", (title, timestamp, chat_id))

    def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Get full details of a specific chat."""
        chat_row = self.db.fetch_one("SELECT * FROM chats WHERE id = ?", (chat_id,))
        if not chat_row:
            return None

        messages_rows = self.db.fetch_all("SELECT * FROM messages WHERE chat_id = ? ORDER BY timestamp ASC", (chat_id,))
        messages = []
        for row in messages_rows:
            content = row['content']
            # Try to deserialize JSON content
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass # Keep as string
            
            messages.append({
                "role": row['role'],
                "content": content,
                "timestamp": row['timestamp']
            })

        return {
            "id": chat_row['id'],
            "title": chat_row['title'],
            "created_at": chat_row['created_at'],
            "updated_at": chat_row['updated_at'],
            "messages": messages
        }

    def get_recent_chats(self, limit: int = 20) -> List[Dict]:
        """Get list of recent chats (metadata only)."""
        rows = self.db.fetch_all("SELECT * FROM chats ORDER BY updated_at DESC LIMIT ?", (limit,))
        
        results = []
        for row in rows:
            # Get last message for preview
            last_msg = self.db.fetch_one("SELECT content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1", (row['id'],))
            preview = ""
            if last_msg:
                content = last_msg['content']
                try:
                    content_obj = json.loads(content)
                    if isinstance(content_obj, str):
                        preview = content_obj
                    else:
                        preview = str(content_obj)
                except:
                    preview = str(content)
            
            results.append({
                "id": row['id'],
                "title": row['title'],
                "updated_at": row['updated_at'],
                "preview": preview
            })
            
        return results
    
    def delete_chat(self, chat_id: str):
        """Delete a chat and its messages."""
        self.db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
