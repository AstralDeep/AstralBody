#!/usr/bin/env python3
"""
Database migration script to add user_id columns for session isolation.

This script:
1. Adds user_id column to all relevant tables (if not exists)
2. Sets user_id = 'legacy' for existing data
3. Creates indexes for performance
"""
import sqlite3
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.database import Database

def get_db_path() -> str:
    """Get the database path from Database class."""
    # Default path used by Database class
    return "data/chats.db"

def ensure_data_dir():
    """Ensure the data directory exists."""
    db_path = get_db_path()
    data_dir = os.path.dirname(db_path)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created data directory: {data_dir}")

def migrate():
    """Run the migration."""
    ensure_data_dir()
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. Creating new database...")
        # Initialize new database with schema
        db = Database(db_path)
        db.close()
        print("New database created with schema.")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=== AstralBody Session Isolation Migration ===")
    print(f"Database: {db_path}")
    
    # Tables to migrate with their CREATE TABLE statements for reference
    tables = [
        ("chats", "id TEXT PRIMARY KEY, title TEXT, created_at INTEGER, updated_at INTEGER"),
        ("messages", "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, timestamp INTEGER, FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE"),
        ("saved_components", "id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, component_data TEXT NOT NULL, component_type TEXT NOT NULL, title TEXT, created_at INTEGER, FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE"),
        ("draft_agents", "session_id TEXT PRIMARY KEY, name TEXT, persona TEXT, model TEXT, api_keys TEXT, tools_desc TEXT, messages TEXT, created_at INTEGER, updated_at INTEGER"),
        ("chat_files", "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL, original_name TEXT NOT NULL, backend_path TEXT NOT NULL, uploaded_at INTEGER, FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE"),
    ]
    
    # 1. Add user_id columns
    print("\n1. Adding user_id columns...")
    for table_name, _ in tables:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN user_id TEXT")
            print(f"  [+] Added user_id to {table_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "column user_id already exists" in str(e):
                print(f"  [~] user_id already exists in {table_name}")
            else:
                print(f"  [-] Failed to add user_id to {table_name}: {e}")
    
    # 2. Set legacy user_id for existing data
    print("\n2. Setting user_id='legacy' for existing data...")
    for table_name, _ in tables:
        try:
            cursor.execute(f"UPDATE {table_name} SET user_id = 'legacy' WHERE user_id IS NULL")
            updated = cursor.rowcount
            print(f"  [+] Set user_id='legacy' for {updated} rows in {table_name}")
        except sqlite3.OperationalError as e:
            print(f"  [-] Failed to update {table_name}: {e}")
    
    # 3. Create indexes for performance
    print("\n3. Creating indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_saved_components_user_id ON saved_components(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_draft_agents_user_id ON draft_agents(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_files_user_id ON chat_files(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_chats_user_updated ON chats(user_id, updated_at)",
    ]
    
    for index_sql in indexes:
        try:
            cursor.execute(index_sql)
            index_name = index_sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
            print(f"  [+] Created index {index_name}")
        except sqlite3.OperationalError as e:
            print(f"  [~] Index already exists or error: {e}")
    
    # 4. Verify migration
    print("\n4. Verifying migration...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables_in_db = [row[0] for row in cursor.fetchall()]
    
    for table_name, _ in tables:
        if table_name in tables_in_db:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in cursor.fetchall()]
            if "user_id" in columns:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE user_id IS NULL")
                null_count = cursor.fetchone()[0]
                if null_count == 0:
                    print(f"  [+] {table_name}: user_id column present, no NULL values")
                else:
                    print(f"  [!] {table_name}: user_id column present, but {null_count} NULL values remain")
            else:
                print(f"  [-] {table_name}: user_id column missing!")
        else:
            print(f"  [~] {table_name}: table does not exist (may be created later)")
    
    conn.commit()
    conn.close()
    
    print("\n=== Migration Complete ===")
    print("\nNext steps:")
    print("1. Update Database._init_db() to include user_id in CREATE TABLE statements")
    print("2. Update application code to require user_id for new records")
    print("3. Run this migration script in production after testing")

def main():
    """Main entry point."""
    try:
        migrate()
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()