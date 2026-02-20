import sqlite3
import logging
import os
import json
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger('Database')

class Database:
    def __init__(self, db_path: str = "data/chats.db"):
        self.db_path = db_path
        self._ensure_data_dir()
        self._init_db()

    def _ensure_data_dir(self):
        """Ensure the data directory exists."""
        dirname = os.path.dirname(self.db_path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Chats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')
        
        # Logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                component TEXT,
                message TEXT,
                timestamp INTEGER
            )
        ''')
        
        # Saved UI components table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_components (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                component_data TEXT NOT NULL,
                component_type TEXT NOT NULL,
                title TEXT,
                created_at INTEGER,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')
        
        # Add has_saved_components flag to chats table
        try:
            cursor.execute("ALTER TABLE chats ADD COLUMN has_saved_components BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

        # Draft agents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS draft_agents (
                session_id TEXT PRIMARY KEY,
                name TEXT,
                persona TEXT,
                model TEXT,
                api_keys TEXT,
                tools_desc TEXT,
                messages TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        conn.commit()
        conn.close()

    def execute(self, query: str, params: Tuple = ()) -> sqlite3.Cursor:
        """Execute a write operation (INSERT, UPDATE, DELETE)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error executing {query}: {e}")
            raise
        finally:
            conn.close()

    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            conn.close()

    def fetch_all(self, query: str, params: Tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            conn.close()

    def close(self):
        """Close connection (not strictly needed as we open/close per request for thread safety in simple sqlite usage)."""
        pass
