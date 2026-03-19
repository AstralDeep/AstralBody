#!/usr/bin/env python3
"""
One-time migration script: copy data from SQLite files into PostgreSQL.

Usage (from backend/ directory):
    python -m scripts.migrate_sqlite_to_postgres

Reads from:
    data/astral.db       -> main app tables
    data/test_audit.db   -> audit trail tables

Writes to: PostgreSQL via DATABASE_URL or DB_* env vars.

Safe to run multiple times — uses INSERT ... ON CONFLICT DO NOTHING
so existing rows in PostgreSQL are not duplicated or overwritten.
"""
import os
import sys
import sqlite3

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

import psycopg2
from shared.database import Database, _build_database_url
from qual_audit.database import AuditDatabase


def get_pg_url() -> str:
    return os.getenv("DATABASE_URL") or _build_database_url()


def ensure_schemas(pg_url: str):
    """Create all PostgreSQL tables before migrating data."""
    print("Ensuring PostgreSQL schemas exist...")
    db = Database(pg_url)
    db.close()
    # AuditDatabase creates tables in __init__; no close() method needed
    AuditDatabase(pg_url)
    print("  Schemas ready.")


def get_sqlite_tables(sqlite_conn):
    """Get list of tables in a SQLite database."""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cursor.fetchall()]


def get_columns(sqlite_conn, table):
    """Get column names for a SQLite table."""
    cursor = sqlite_conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def migrate_table(sqlite_conn, pg_conn, table, pg_columns):
    """Migrate a single table from SQLite to PostgreSQL."""
    sqlite_cursor = sqlite_conn.cursor()

    # Get SQLite columns
    sqlite_cols = get_columns(sqlite_conn, table)

    # Only migrate columns that exist in both SQLite and PostgreSQL
    common_cols = [c for c in sqlite_cols if c in pg_columns]
    if not common_cols:
        print(f"  [~] {table}: no common columns, skipping")
        return 0

    # Read all rows from SQLite
    col_list = ", ".join(common_cols)
    sqlite_cursor.execute(f"SELECT {col_list} FROM {table}")
    rows = sqlite_cursor.fetchall()

    if not rows:
        print(f"  [~] {table}: empty, nothing to migrate")
        return 0

    # Detect boolean columns so we can cast SQLite 0/1 → Python bool
    bool_cols = get_pg_boolean_columns(pg_conn, table)
    bool_indices = [i for i, c in enumerate(common_cols) if c in bool_cols]

    def cast_row(row):
        if not bool_indices:
            return row
        row = list(row)
        for i in bool_indices:
            if row[i] is not None:
                row[i] = bool(row[i])
        return tuple(row)

    # Build INSERT ... ON CONFLICT DO NOTHING
    placeholders = ", ".join(["%s"] * len(common_cols))
    insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    pg_cursor = pg_conn.cursor()
    inserted = 0
    errors = 0
    for row in rows:
        try:
            pg_cursor.execute(insert_sql, cast_row(row))
            if pg_cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            pg_conn.rollback()
            errors += 1
            if errors <= 3:
                print(f"  [!] {table}: error inserting row: {e}")
            elif errors == 4:
                print(f"  [!] {table}: (suppressing further errors...)")
            continue

    pg_conn.commit()
    skipped = len(rows) - inserted - errors
    parts = [f"{inserted}/{len(rows)} rows migrated"]
    if skipped > 0:
        parts.append(f"{skipped} already existed")
    if errors > 0:
        parts.append(f"{errors} errors")
    print(f"  [+] {table}: {', '.join(parts)}")
    return inserted


def get_pg_columns(pg_conn, table):
    """Get column names for a PostgreSQL table."""
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
        (table,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_pg_boolean_columns(pg_conn, table):
    """Get set of column names that are boolean in PostgreSQL."""
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND data_type = 'boolean'",
        (table,)
    )
    return {row[0] for row in cursor.fetchall()}


def migrate_main_db(sqlite_path, pg_url):
    """Migrate the main astral.db database."""
    print(f"\n=== Migrating Main Database: {sqlite_path} ===")

    if not os.path.exists(sqlite_path):
        print(f"  [~] SQLite file not found, skipping: {sqlite_path}")
        return

    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = psycopg2.connect(pg_url)

    # Tables to migrate in dependency order (parents before children)
    tables_ordered = [
        "users",
        "user_preferences",
        "chats",
        "messages",
        "logs",
        "saved_components",
        "chat_files",
        "tool_permissions",
        "user_credentials",
        "agent_ownership",
        "agent_scopes",
        "tool_overrides",
        "draft_agents",
    ]

    sqlite_tables = get_sqlite_tables(sqlite_conn)
    total = 0

    for table in tables_ordered:
        if table not in sqlite_tables:
            print(f"  [~] {table}: not in SQLite, skipping")
            continue

        pg_columns = get_pg_columns(pg_conn, table)
        if not pg_columns:
            print(f"  [~] {table}: not in PostgreSQL, skipping")
            continue

        total += migrate_table(sqlite_conn, pg_conn, table, pg_columns)

    sqlite_conn.close()
    pg_conn.close()
    print(f"\nMain database migration complete: {total} total rows migrated")


def migrate_audit_db(sqlite_path, pg_url):
    """Migrate the test_audit.db database."""
    print(f"\n=== Migrating Audit Database: {sqlite_path} ===")

    if not os.path.exists(sqlite_path):
        print(f"  [~] SQLite file not found, skipping: {sqlite_path}")
        return

    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = psycopg2.connect(pg_url)

    # Tables in dependency order
    tables_ordered = [
        "test_runs",
        "test_case_results",
        "test_evidence",
        "audit_entries",
        "latex_artifacts",
    ]

    sqlite_tables = get_sqlite_tables(sqlite_conn)
    total = 0

    for table in tables_ordered:
        if table not in sqlite_tables:
            print(f"  [~] {table}: not in SQLite, skipping")
            continue

        pg_columns = get_pg_columns(pg_conn, table)
        if not pg_columns:
            print(f"  [~] {table}: not in PostgreSQL, skipping")
            continue

        total += migrate_table(sqlite_conn, pg_conn, table, pg_columns)

    sqlite_conn.close()
    pg_conn.close()
    print(f"\nAudit database migration complete: {total} total rows migrated")


def reset_sequences(pg_url):
    """Reset all SERIAL sequences to max(id)+1 so new inserts don't collide with migrated data."""
    print("\n=== Resetting SERIAL sequences ===")
    pg_conn = psycopg2.connect(pg_url)
    cursor = pg_conn.cursor()

    # Find all columns with sequences (SERIAL/BIGSERIAL)
    cursor.execute("""
        SELECT table_name, column_name, pg_get_serial_sequence(table_name, column_name) AS seq
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_default LIKE 'nextval%%'
    """)
    rows = cursor.fetchall()

    for table_name, column_name, seq_name in rows:
        if not seq_name:
            continue
        cursor.execute(f"SELECT COALESCE(MAX({column_name}), 0) FROM {table_name}")
        max_id = cursor.fetchone()[0]
        new_val = max_id + 1
        cursor.execute(f"SELECT setval('{seq_name}', {new_val}, false)")
        print(f"  [+] {table_name}.{column_name}: sequence reset to {new_val}")

    pg_conn.commit()
    pg_conn.close()


def main():
    pg_url = get_pg_url()
    print("SQLite → PostgreSQL Data Migration")
    print(f"Target: {pg_url.split('@')[-1] if '@' in pg_url else pg_url}")

    # Create tables in PostgreSQL before migrating data
    ensure_schemas(pg_url)

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    data_dir = os.path.join(backend_dir, "data")

    migrate_main_db(os.path.join(data_dir, "astral.db"), pg_url)
    migrate_audit_db(os.path.join(data_dir, "test_audit.db"), pg_url)

    # Reset SERIAL sequences so new inserts don't collide with migrated IDs
    reset_sequences(pg_url)

    print("\n=== Migration Complete ===")
    print("You can verify with: docker compose exec postgres psql -U astral -d astralbody -c '\\dt'")


if __name__ == "__main__":
    main()
