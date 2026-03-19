import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import os
import json
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger('Database')

def _build_database_url() -> str:
    """Build a PostgreSQL connection URL from individual DB_* env vars."""
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "astralbody")
    user = os.getenv("DB_USER", "astral")
    password = os.getenv("DB_PASSWORD", "astral_dev")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


class Database:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv("DATABASE_URL") or _build_database_url()
        self._init_db()

    def _get_connection(self):
        """Get a database connection with dict-like row factory."""
        conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        return conn

    def _translate_query(self, query: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s placeholders.

        Also escapes literal % (e.g. in LIKE patterns) to %% so psycopg2
        doesn't interpret them as parameter placeholders.
        """
        # First escape any existing % that aren't parameter placeholders
        query = query.replace('%', '%%')
        # Then convert ? placeholders to %s
        return query.replace('?', '%s')

    def _column_exists(self, cursor, table_name: str, column_name: str) -> bool:
        """Check if a column exists on a table via information_schema."""
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table_name, column_name)
        )
        return cursor.fetchone() is not None

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Chats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')

        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp BIGINT,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')

        # Logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                level TEXT,
                component TEXT,
                message TEXT,
                timestamp BIGINT
            )
        ''')

        # Saved UI components table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_components (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_id TEXT,
                component_data TEXT NOT NULL,
                component_type TEXT NOT NULL,
                title TEXT,
                created_at BIGINT,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')

        # Chat files mapping table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_files (
                id SERIAL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_id TEXT,
                original_name TEXT NOT NULL,
                backend_path TEXT NOT NULL,
                uploaded_at BIGINT,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')

        # Add has_saved_components flag to chats table
        if not self._column_exists(cursor, 'chats', 'has_saved_components'):
            cursor.execute("ALTER TABLE chats ADD COLUMN has_saved_components BOOLEAN DEFAULT FALSE")

        # Auto-migrate user_id column for all tables
        for table in ['chats', 'messages', 'saved_components', 'chat_files']:
            if not self._column_exists(cursor, table, 'user_id'):
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT 'legacy'")

        # Tool permissions table (per-user, per-agent, per-tool)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_permissions (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                allowed BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at BIGINT,
                UNIQUE(user_id, agent_id, tool_name)
            )
        ''')

        # Per-user credentials for agents requiring external API keys
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_credentials (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                credential_key TEXT NOT NULL,
                encrypted_value TEXT NOT NULL,
                created_at BIGINT,
                updated_at BIGINT,
                UNIQUE(user_id, agent_id, credential_key)
            )
        ''')

        # Agent ownership and visibility
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_ownership (
                id SERIAL PRIMARY KEY,
                agent_id TEXT NOT NULL UNIQUE,
                owner_email TEXT NOT NULL,
                is_public BOOLEAN NOT NULL DEFAULT FALSE,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')

        # Agent scopes — per-user, per-agent scope-based authorization
        # Replaces per-tool permissions with 4 scopes: tools:read, tools:write, tools:search, tools:system
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_scopes (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at BIGINT,
                UNIQUE(user_id, agent_id, scope)
            )
        ''')

        # Tool overrides — per-user, per-agent, per-tool disable overrides
        # When a scope is enabled but a specific tool should be disabled
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_overrides (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at BIGINT,
                UNIQUE(user_id, agent_id, tool_name)
            )
        ''')

        # Users table — persists user profiles from Keycloak/OIDC
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                username TEXT,
                display_name TEXT,
                roles TEXT,
                last_login_at BIGINT,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')

        # User preferences table — stores per-user settings (e.g. theme)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                preferences TEXT NOT NULL DEFAULT '{}',
                updated_at BIGINT
            )
        ''')

        # Draft agents table — user-created agents in draft/testing/live states
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS draft_agents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                agent_slug TEXT NOT NULL,
                description TEXT NOT NULL,
                tools_spec TEXT,
                skill_tags TEXT,
                packages TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                generation_log TEXT,
                security_report TEXT,
                error_message TEXT,
                port INTEGER,
                review_notes TEXT,
                reviewed_by TEXT,
                refinement_history TEXT,
                validation_report TEXT,
                required_credentials TEXT,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')

        # Indexes on user_id for query performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_saved_components_user_id ON saved_components(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_files_user_id ON chat_files(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_scopes_user_id ON agent_scopes(user_id, agent_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tool_overrides_user_agent ON tool_overrides(user_id, agent_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_draft_agents_user_id ON draft_agents(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_draft_agents_status ON draft_agents(status)')

        conn.commit()
        conn.close()

    def execute(self, query: str, params: Tuple = ()):
        """Execute a write operation (INSERT, UPDATE, DELETE)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(self._translate_query(query), params)
            conn.commit()
            return cursor
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error executing {query}: {e}")
            raise
        finally:
            conn.close()

    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Dict]:
        """Fetch a single row."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(self._translate_query(query), params)
            return cursor.fetchone()
        finally:
            conn.close()

    def fetch_all(self, query: str, params: Tuple = ()) -> List[Dict]:
        """Fetch all rows."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(self._translate_query(query), params)
            return cursor.fetchall()
        finally:
            conn.close()

    # ── Agent Ownership ──────────────────────────────────────────────────

    def get_agent_ownership(self, agent_id: str) -> Optional[Dict]:
        """Get ownership info for an agent."""
        row = self.fetch_one(
            "SELECT agent_id, owner_email, is_public, created_at, updated_at FROM agent_ownership WHERE agent_id = ?",
            (agent_id,)
        )
        if row:
            return dict(row)
        return None

    def set_agent_ownership(self, agent_id: str, owner_email: str, is_public: bool = False) -> None:
        """Set or update ownership for an agent."""
        import time
        now = int(time.time() * 1000)
        existing = self.get_agent_ownership(agent_id)
        if existing:
            self.execute(
                "UPDATE agent_ownership SET owner_email = ?, is_public = ?, updated_at = ? WHERE agent_id = ?",
                (owner_email, is_public, now, agent_id)
            )
        else:
            self.execute(
                "INSERT INTO agent_ownership (agent_id, owner_email, is_public, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (agent_id, owner_email, is_public, now, now)
            )

    def set_agent_visibility(self, agent_id: str, is_public: bool) -> bool:
        """Toggle public/private visibility. Returns True if updated."""
        import time
        now = int(time.time() * 1000)
        cursor = self.execute(
            "UPDATE agent_ownership SET is_public = ?, updated_at = ? WHERE agent_id = ?",
            (is_public, now, agent_id)
        )
        return cursor.rowcount > 0

    def get_all_agent_ownership(self) -> List[Dict]:
        """Get ownership info for all agents."""
        rows = self.fetch_all("SELECT agent_id, owner_email, is_public FROM agent_ownership")
        return [dict(r) for r in rows]

    # ── Users ─────────────────────────────────────────────────────────────

    def upsert_user(self, user_id: str, email: str = None, username: str = None,
                    display_name: str = None, roles: List[str] = None) -> None:
        """Create or update a user profile from JWT claims."""
        import time
        now = int(time.time() * 1000)
        roles_json = json.dumps(roles) if roles else None
        existing = self.get_user(user_id)
        if existing:
            self.execute(
                """UPDATE users SET email = COALESCE(?, email), username = COALESCE(?, username),
                   display_name = COALESCE(?, display_name), roles = COALESCE(?, roles),
                   last_login_at = ?, updated_at = ? WHERE id = ?""",
                (email, username, display_name, roles_json, now, now, user_id)
            )
        else:
            self.execute(
                """INSERT INTO users (id, email, username, display_name, roles, last_login_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, email, username, display_name, roles_json, now, now, now)
            )

    def get_user(self, user_id: str) -> Optional[Dict]:
        """Get a user profile by ID."""
        row = self.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if row:
            result = dict(row)
            if result.get("roles"):
                try:
                    result["roles"] = json.loads(result["roles"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return result
        return None

    def get_all_users(self) -> List[Dict]:
        """Get all user profiles."""
        rows = self.fetch_all("SELECT * FROM users ORDER BY last_login_at DESC")
        results = []
        for row in rows:
            r = dict(row)
            if r.get("roles"):
                try:
                    r["roles"] = json.loads(r["roles"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(r)
        return results

    # ── User Preferences ─────────────────────────────────────────────────

    def get_user_preferences(self, user_id: str) -> Dict:
        """Get user preferences (returns empty dict if none stored)."""
        row = self.fetch_one(
            "SELECT preferences FROM user_preferences WHERE user_id = ?",
            (user_id,)
        )
        if row:
            try:
                return json.loads(row["preferences"])
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def set_user_preferences(self, user_id: str, preferences: Dict) -> None:
        """Set or update user preferences (merges with existing)."""
        import time
        now = int(time.time() * 1000)
        existing = self.get_user_preferences(user_id)
        merged = {**existing, **preferences}
        prefs_json = json.dumps(merged)
        self.execute(
            """INSERT INTO user_preferences (user_id, preferences, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET preferences = ?, updated_at = ?""",
            (user_id, prefs_json, now, prefs_json, now)
        )

    # ── Draft Agents ────────────────────────────────────────────────────

    def create_draft_agent(self, draft_id: str, user_id: str, agent_name: str,
                           agent_slug: str, description: str, tools_spec: str = None,
                           skill_tags: str = None, packages: str = None) -> None:
        """Create a new draft agent record."""
        import time
        now = int(time.time() * 1000)
        self.execute(
            """INSERT INTO draft_agents (id, user_id, agent_name, agent_slug, description,
               tools_spec, skill_tags, packages, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (draft_id, user_id, agent_name, agent_slug, description,
             tools_spec, skill_tags, packages, now, now)
        )

    def get_draft_agent(self, draft_id: str) -> Optional[Dict]:
        """Get a draft agent by ID."""
        row = self.fetch_one("SELECT * FROM draft_agents WHERE id = ?", (draft_id,))
        return dict(row) if row else None

    def get_user_draft_agents(self, user_id: str) -> List[Dict]:
        """Get all draft agents for a user (excludes live/rejected agents)."""
        rows = self.fetch_all(
            "SELECT * FROM draft_agents WHERE user_id = ? AND status NOT IN ('live', 'rejected') ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(r) for r in rows]

    def get_draft_agent_by_slug(self, slug: str) -> Optional[Dict]:
        """Get a draft agent by its slug."""
        row = self.fetch_one(
            "SELECT * FROM draft_agents WHERE agent_slug = ?", (slug,)
        )
        return dict(row) if row else None

    def get_pending_review_drafts(self) -> List[Dict]:
        """Get all draft agents awaiting admin review."""
        rows = self.fetch_all(
            "SELECT * FROM draft_agents WHERE status = 'pending_review' ORDER BY updated_at ASC"
        )
        return [dict(r) for r in rows]

    def update_draft_agent(self, draft_id: str, **kwargs) -> bool:
        """Update draft agent fields. Pass any column as keyword argument."""
        import time
        kwargs['updated_at'] = int(time.time() * 1000)
        set_clauses = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [draft_id]
        cursor = self.execute(
            f"UPDATE draft_agents SET {set_clauses} WHERE id = ?",
            tuple(values)
        )
        return cursor.rowcount > 0

    def delete_draft_agent(self, draft_id: str) -> bool:
        """Delete a draft agent record."""
        cursor = self.execute("DELETE FROM draft_agents WHERE id = ?", (draft_id,))
        return cursor.rowcount > 0

    def close(self):
        """No-op for compatibility — connections are opened/closed per request."""
        pass
