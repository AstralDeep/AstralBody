#!/usr/bin/env python3
"""
Database migration script to add user_id columns for session isolation.

This script:
1. Adds user_id column to all relevant tables (if not exists)
2. Sets user_id = 'legacy' for existing data
3. Creates indexes for performance

Note: For fresh PostgreSQL deployments, the schema already includes user_id columns.
This script is for migrating existing databases that predate session isolation.
"""
import os
import sys

import psycopg2

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.database import Database, _build_database_url


def get_database_url() -> str:
    """Get the database URL from environment."""
    return os.getenv("DATABASE_URL") or _build_database_url()


def migrate():
    """Run the migration."""
    database_url = get_database_url()

    # Ensure schema exists
    db = Database(database_url)
    db.close()

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    print("=== AstralBody Session Isolation Migration ===")
    print(f"Database: {database_url.split('@')[-1]}")

    # Tables to migrate
    tables = ["chats", "messages", "saved_components", "chat_files"]

    # 1. Add user_id columns
    print("\n1. Adding user_id columns...")
    for table_name in tables:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = 'user_id'",
            (table_name,)
        )
        if cursor.fetchone():
            print(f"  [~] user_id already exists in {table_name}")
        else:
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN user_id TEXT")
                print(f"  [+] Added user_id to {table_name}")
            except Exception as e:
                print(f"  [-] Failed to add user_id to {table_name}: {e}")

    # 2. Set legacy user_id for existing data
    print("\n2. Setting user_id='legacy' for existing data...")
    for table_name in tables:
        try:
            cursor.execute(f"UPDATE {table_name} SET user_id = 'legacy' WHERE user_id IS NULL")
            updated = cursor.rowcount
            print(f"  [+] Set user_id='legacy' for {updated} rows in {table_name}")
        except Exception as e:
            print(f"  [-] Failed to update {table_name}: {e}")

    # 3. Create indexes for performance
    print("\n3. Creating indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_saved_components_user_id ON saved_components(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_files_user_id ON chat_files(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_chats_user_updated ON chats(user_id, updated_at)",
    ]

    for index_sql in indexes:
        try:
            cursor.execute(index_sql)
            index_name = index_sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
            print(f"  [+] Created index {index_name}")
        except Exception as e:
            print(f"  [~] Index already exists or error: {e}")

    # 4. Verify migration
    print("\n4. Verifying migration...")
    cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    tables_in_db = [row[0] for row in cursor.fetchall()]

    for table_name in tables:
        if table_name in tables_in_db:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = 'user_id'",
                (table_name,)
            )
            if cursor.fetchone():
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
