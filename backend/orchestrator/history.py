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
            
            # Check if chat has saved components
            has_saved = self.chat_has_saved_components(row['id'])
            
            results.append({
                "id": row['id'],
                "title": row['title'],
                "updated_at": row['updated_at'],
                "preview": preview,
                "has_saved_components": has_saved
            })
            
        return results
    
    def delete_chat(self, chat_id: str):
        """Delete a chat and its messages."""
        self.db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    # =========================================================================
    # Saved UI Components Methods
    # =========================================================================
    
    def save_component(self, chat_id: str, component_data: any, component_type: str, title: str = None) -> str:
        """Save a UI component to the database."""
        import json
        import uuid
        import time
        
        component_id = str(uuid.uuid4())
        created_at = int(time.time() * 1000)
        
        # Serialize component data
        component_json = json.dumps(component_data)
        
        # Use component type as title if not provided
        if not title:
            title = component_type.replace('_', ' ').title()
        
        self.db.execute(
            """INSERT INTO saved_components 
               (id, chat_id, component_data, component_type, title, created_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (component_id, chat_id, component_json, component_type, title, created_at)
        )
        
        # Update chat flag
        self.db.execute(
            "UPDATE chats SET has_saved_components = 1 WHERE id = ?",
            (chat_id,)
        )
        
        return component_id
    
    def get_saved_components(self, chat_id: str = None) -> List[Dict]:
        """Get saved components, optionally filtered by chat_id."""
        import json
        
        if chat_id:
            rows = self.db.fetch_all(
                "SELECT * FROM saved_components WHERE chat_id = ? ORDER BY created_at DESC",
                (chat_id,)
            )
        else:
            rows = self.db.fetch_all(
                "SELECT * FROM saved_components ORDER BY created_at DESC"
            )
        
        components = []
        for row in rows:
            try:
                component_data = json.loads(row['component_data'])
            except (json.JSONDecodeError, TypeError):
                component_data = row['component_data']
            
            components.append({
                "id": row['id'],
                "chat_id": row['chat_id'],
                "component_data": component_data,
                "component_type": row['component_type'],
                "title": row['title'],
                "created_at": row['created_at']
            })
        
        return components
    
    def delete_component(self, component_id: str) -> bool:
        """Delete a saved component."""
        # Get chat_id before deleting
        row = self.db.fetch_one(
            "SELECT chat_id FROM saved_components WHERE id = ?",
            (component_id,)
        )
        
        if not row:
            return False
        
        chat_id = row['chat_id']
        
        # Delete the component
        self.db.execute(
            "DELETE FROM saved_components WHERE id = ?",
            (component_id,)
        )
        
        # Check if chat still has components
        count_row = self.db.fetch_one(
            "SELECT COUNT(*) as count FROM saved_components WHERE chat_id = ?",
            (chat_id,)
        )
        
        if count_row['count'] == 0:
            # Update chat flag
            self.db.execute(
                "UPDATE chats SET has_saved_components = 0 WHERE id = ?",
                (chat_id,)
            )
        
        return True
    
    def get_component_by_id(self, component_id: str) -> Optional[Dict]:
        """Get a single saved component by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM saved_components WHERE id = ?",
            (component_id,)
        )
        if not row:
            return None
        
        try:
            component_data = json.loads(row['component_data'])
        except (json.JSONDecodeError, TypeError):
            component_data = row['component_data']
        
        return {
            "id": row['id'],
            "chat_id": row['chat_id'],
            "component_data": component_data,
            "component_type": row['component_type'],
            "title": row['title'],
            "created_at": row['created_at']
        }

    def replace_components(self, old_ids: list, new_components: list, chat_id: str) -> list:
        """Atomically delete old components and insert new ones. Returns list of new component dicts."""
        # Delete old components
        for old_id in old_ids:
            self.db.execute(
                "DELETE FROM saved_components WHERE id = ?",
                (old_id,)
            )
        
        # Insert new components
        created = []
        for comp in new_components:
            component_id = str(uuid.uuid4())
            created_at = int(time.time() * 1000)
            component_json = json.dumps(comp.get("component_data", {}))
            component_type = comp.get("component_type", "combined")
            title = comp.get("title", "Combined Component")
            
            self.db.execute(
                """INSERT INTO saved_components 
                   (id, chat_id, component_data, component_type, title, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (component_id, chat_id, component_json, component_type, title, created_at)
            )
            
            created.append({
                "id": component_id,
                "chat_id": chat_id,
                "component_data": comp.get("component_data", {}),
                "component_type": component_type,
                "title": title,
                "created_at": created_at
            })
        
        # Check if chat still has components
        count_row = self.db.fetch_one(
            "SELECT COUNT(*) as count FROM saved_components WHERE chat_id = ?",
            (chat_id,)
        )
        has_components = count_row and count_row['count'] > 0
        self.db.execute(
            "UPDATE chats SET has_saved_components = ? WHERE id = ?",
            (1 if has_components else 0, chat_id)
        )
        
        return created

    def chat_has_saved_components(self, chat_id: str) -> bool:
        """Check if a chat has saved components."""
        row = self.db.fetch_one(
            "SELECT has_saved_components FROM chats WHERE id = ?",
            (chat_id,)
        )
        
        if not row:
            return False
        
        return bool(row['has_saved_components'])
