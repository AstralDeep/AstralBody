import json
import os
import time
import uuid
from typing import List, Dict, Optional
import logging

logger = logging.getLogger('HistoryManager')

class HistoryManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.history_file = os.path.join(data_dir, "chats.json")
        self.chats: Dict[str, Dict] = {}
        self._ensure_data_dir()
        self.load_history()

    def _ensure_data_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_history(self):
        """Load chat history from JSON file."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.chats = json.load(f)
                logger.info(f"Loaded {len(self.chats)} chats from history.")
            except Exception as e:
                logger.error(f"Failed to load history: {e}")
                self.chats = {}
        else:
            self.chats = {}

    def save_history(self):
        """Save chat history to JSON file."""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.chats, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def create_chat(self) -> str:
        """Create a new chat session."""
        chat_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        self.chats[chat_id] = {
            "id": chat_id,
            "title": "New Chat",
            "created_at": timestamp,
            "updated_at": timestamp,
            "messages": []
        }
        self.save_history()
        return chat_id

    def add_message(self, chat_id: str, role: str, content: any):
        """Add a message to a chat session."""
        if chat_id not in self.chats:
            logger.warning(f"Attempted to add message to non-existent chat {chat_id}")
            return

        timestamp = int(time.time() * 1000)
        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp
        }
        
        # Auto-update title based on first user message (fallback)
        if role == "user" and len(self.chats[chat_id]["messages"]) == 0:
            # Use first 30 chars of message as title
            title = str(content)[:30] + "..." if len(str(content)) > 30 else str(content)
            self.chats[chat_id]["title"] = title

        self.chats[chat_id]["messages"].append(message)
        self.chats[chat_id]["updated_at"] = timestamp
        self.save_history()

    def update_chat_title(self, chat_id: str, title: str):
        """Update the title of a specific chat."""
        if chat_id in self.chats:
            self.chats[chat_id]["title"] = title
            self.chats[chat_id]["updated_at"] = int(time.time() * 1000)
            self.save_history()

    def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Get full details of a specific chat."""
        return self.chats.get(chat_id)

    def get_recent_chats(self, limit: int = 20) -> List[Dict]:
        """Get list of recent chats (metadata only)."""
        # Sort by updated_at desc
        sorted_chats = sorted(
            self.chats.values(),
            key=lambda x: x.get("updated_at", 0),
            reverse=True
        )
        
        # Return summary info
        return [
            {
                "id": c["id"],
                "title": c.get("title", "Untitled Chat"),
                "updated_at": c.get("updated_at", 0),
                "preview": c["messages"][-1]["content"] if c["messages"] else ""
            }
            for c in sorted_chats[:limit]
        ]
    
    def delete_chat(self, chat_id: str):
        if chat_id in self.chats:
            del self.chats[chat_id]
            self.save_history()
