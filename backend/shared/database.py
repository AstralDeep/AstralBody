import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import os
import json
from typing import List, Dict, Optional, Tuple

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

        # Feature 013: bind a chat session to its active agent so the UI can
        # render the active-agent indicator (FR-006) and detect when the
        # bound agent becomes unavailable (FR-009). NULL is allowed for
        # backward compatibility with chats created before this column
        # existed; the frontend renders an "Unknown agent" state for those.
        if not self._column_exists(cursor, 'chats', 'agent_id'):
            cursor.execute("ALTER TABLE chats ADD COLUMN agent_id TEXT NULL")

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

        # Tool overrides — per-user, per-agent, per-tool, per-permission-kind
        # permission rows (Feature 013).
        #
        # Pre-013 semantics: one row per (user, agent, tool) capturing a
        # tool-wide disable override (legacy "tool_overrides"). Rows have
        # `permission_kind = NULL`.
        #
        # Post-013 semantics: one row per (user, agent, tool, permission_kind)
        # capturing the per-tool, per-kind enable/disable state (FR-010).
        # Legacy NULL rows continue to work as tool-wide overrides until
        # superseded by per-kind rows during user edits or the FR-015
        # backfill (executed by ToolPermissionManager.backfill_per_tool_rows).
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

        # Feature 013: extend tool_overrides with permission_kind. Legacy
        # rows have NULL kinds; new rows carry the specific scope kind.
        if not self._column_exists(cursor, 'tool_overrides', 'permission_kind'):
            cursor.execute("ALTER TABLE tool_overrides ADD COLUMN permission_kind TEXT NULL")
            # Drop the (user_id, agent_id, tool_name) unique constraint so
            # multiple per-kind rows can coexist for the same (user, agent,
            # tool). Replace with a unique index that includes permission_kind
            # via COALESCE so legacy NULL rows remain unique tool-wide.
            # PostgreSQL auto-generated constraint names follow the pattern
            # <table>_<col1>_<col2>_..._key. We use IF EXISTS to be safe in
            # case the constraint name varies.
            cursor.execute("""
                DO $$
                DECLARE
                    constraint_rec RECORD;
                BEGIN
                    FOR constraint_rec IN
                        SELECT conname FROM pg_constraint
                        WHERE conrelid = 'tool_overrides'::regclass
                          AND contype = 'u'
                          AND conname <> 'tool_overrides_user_agent_tool_kind_uniq'
                    LOOP
                        EXECUTE format('ALTER TABLE tool_overrides DROP CONSTRAINT %I', constraint_rec.conname);
                    END LOOP;
                END $$;
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS tool_overrides_user_agent_tool_kind_uniq
                ON tool_overrides (user_id, agent_id, tool_name, COALESCE(permission_kind, ''))
            """)

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

        # Feature 027 — agentic creation provenance on drafts. Additive,
        # idempotent (Constitution IX); all columns nullable or defaulted so
        # pre-027 code paths are unaffected. Rollback: redeploy prior image
        # (columns ignored) or ALTER TABLE draft_agents DROP COLUMN <col>.
        cursor.execute("ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'manual'")
        cursor.execute("ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS source_chat_id TEXT")
        cursor.execute("ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS gap_fingerprint TEXT")
        cursor.execute("ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS revises_agent_id TEXT")
        cursor.execute("ALTER TABLE draft_agents ADD COLUMN IF NOT EXISTS self_test TEXT")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_draft_gap "
            "ON draft_agents (user_id, source_chat_id, gap_fingerprint)"
        )

        # User attachments — chat-message file uploads, user-scoped (feature 002-file-uploads)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_attachments (
                attachment_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                category TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes BIGINT NOT NULL,
                sha256 TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                deleted_at BIGINT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_attachments_user ON user_attachments(user_id, created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_attachments_live ON user_attachments(user_id) WHERE deleted_at IS NULL')

        # Interaction log — captures tool call outcomes for knowledge synthesis
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interaction_log (
                id SERIAL PRIMARY KEY,
                agent_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                response_time_ms INTEGER,
                chat_id TEXT,
                synthesized BOOLEAN DEFAULT FALSE,
                created_at BIGINT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_log_synthesized ON interaction_log(synthesized)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_log_agent ON interaction_log(agent_id)')

        # Audit events — feature 003-agent-audit-log
        # HIPAA + NIST SP 800-53 AU compliant per-user audit log.
        # Append-only (no UPDATE/DELETE except the retention CLI under a
        # session GUC). See backend/audit/ for the recorder/repository.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id UUID PRIMARY KEY,
                actor_user_id TEXT NOT NULL,
                auth_principal TEXT NOT NULL,
                agent_id TEXT,
                event_class TEXT NOT NULL,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                conversation_id TEXT,
                correlation_id UUID NOT NULL,
                outcome TEXT NOT NULL,
                outcome_detail TEXT,
                inputs_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                outputs_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                artifact_pointers JSONB NOT NULL DEFAULT '[]'::jsonb,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                prev_hash BYTEA NOT NULL,
                entry_hash BYTEA NOT NULL,
                key_id TEXT NOT NULL,
                schema_version SMALLINT NOT NULL DEFAULT 1,
                CONSTRAINT audit_events_outcome_check CHECK (outcome IN ('in_progress','success','failure','interrupted'))
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_user_recorded ON audit_events(actor_user_id, recorded_at DESC, event_id DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_events(correlation_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_user_class_recorded ON audit_events(actor_user_id, event_class, recorded_at DESC)')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_failures ON audit_events(actor_user_id, recorded_at DESC) WHERE outcome IN ('failure','interrupted')")

        # Append-only enforcement: a trigger that raises on UPDATE/DELETE
        # unless the session GUC ``audit.allow_purge`` is set to 'true'.
        # The retention CLI sets that GUC; application code never does.
        cursor.execute('''
            CREATE OR REPLACE FUNCTION audit_events_protect() RETURNS trigger AS $func$
            BEGIN
                IF current_setting('audit.allow_purge', true) IS DISTINCT FROM 'true' THEN
                    RAISE EXCEPTION 'audit_events is append-only (TG_OP=%)', TG_OP
                        USING ERRCODE = '42501';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $func$ LANGUAGE plpgsql
        ''')
        cursor.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
        cursor.execute('''
            CREATE TRIGGER audit_events_no_update
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_protect()
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

        # ------------------------------------------------------------------
        # Feature 004 — component feedback & tool-improvement loop
        # ------------------------------------------------------------------
        # ComponentFeedback: append-only with logical supersession; lifecycle
        # enforced at the repository layer. Per-user isolation enforced at
        # the application layer (mirrors audit_events from feature 003).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS component_feedback (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                conversation_id TEXT,
                correlation_id TEXT,
                source_agent TEXT,
                source_tool TEXT,
                component_id TEXT,
                sentiment TEXT NOT NULL CHECK (sentiment IN ('positive','negative')),
                category TEXT NOT NULL DEFAULT 'unspecified'
                    CHECK (category IN
                        ('wrong-data','irrelevant','layout-broken','too-slow','other','unspecified')),
                comment_raw TEXT,
                comment_safety TEXT NOT NULL DEFAULT 'clean'
                    CHECK (comment_safety IN ('clean','quarantined')),
                comment_safety_reason TEXT,
                lifecycle TEXT NOT NULL DEFAULT 'active'
                    CHECK (lifecycle IN ('active','superseded','retracted')),
                superseded_by UUID REFERENCES component_feedback(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cf_user_created ON component_feedback(user_id, created_at DESC)')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cf_tool_created ON component_feedback(source_agent, source_tool, created_at DESC) WHERE lifecycle = 'active'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cf_quarantine ON component_feedback(comment_safety, created_at DESC) WHERE comment_safety = 'quarantined'")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cf_dedup_lookup ON component_feedback(user_id, correlation_id, component_id, created_at DESC)')

        # ToolQualitySignal: per-(agent, tool) snapshot per evaluation cycle.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_quality_signal (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agent_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                window_start TIMESTAMPTZ NOT NULL,
                window_end TIMESTAMPTZ NOT NULL,
                dispatch_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL,
                negative_feedback_count INTEGER NOT NULL,
                failure_rate REAL NOT NULL,
                negative_feedback_rate REAL NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('healthy','insufficient-data','underperforming')),
                computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (agent_id, tool_name, window_end)
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tqs_underperforming ON tool_quality_signal(computed_at DESC) WHERE status = 'underperforming'")

        # KnowledgeUpdateProposal: system-generated change to a synthesizer
        # knowledge artifact under backend/knowledge/. Always admin-gated.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_update_proposal (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agent_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                diff_payload TEXT NOT NULL,
                artifact_sha_at_gen TEXT NOT NULL,
                evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','accepted','applied','rejected','superseded')),
                reviewer_user_id TEXT,
                reviewed_at TIMESTAMPTZ,
                reviewer_rationale TEXT,
                applied_at TIMESTAMPTZ,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kup_pending ON knowledge_update_proposal(generated_at DESC) WHERE status = 'pending'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kup_tool ON knowledge_update_proposal(agent_id, tool_name, generated_at DESC)")

        # QuarantineEntry: pointer to a flagged ComponentFeedback. One per
        # feedback record (enforced by PRIMARY KEY on feedback_id).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quarantine_entry (
                feedback_id UUID PRIMARY KEY REFERENCES component_feedback(id) ON DELETE CASCADE,
                reason TEXT NOT NULL,
                detector TEXT NOT NULL CHECK (detector IN ('inline','loop_pre_pass')),
                detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                status TEXT NOT NULL DEFAULT 'held'
                    CHECK (status IN ('held','released','dismissed')),
                actor_user_id TEXT,
                actioned_at TIMESTAMPTZ
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_qe_held ON quarantine_entry(detected_at DESC) WHERE status = 'held'")

        # ------------------------------------------------------------------
        # Feature 005 — tool tips and getting started tutorial
        # ------------------------------------------------------------------
        # tutorial_step holds the canonical (current) copy of each step and
        # is editable by admins via /api/admin/tutorial/steps. Soft-delete
        # via archived_at so revisions and in-flight resumes stay valid.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tutorial_step (
                id BIGSERIAL PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                audience TEXT NOT NULL CHECK (audience IN ('user','admin')),
                display_order INTEGER NOT NULL,
                target_kind TEXT NOT NULL CHECK (target_kind IN ('static','sdui','none')),
                target_key TEXT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                archived_at TIMESTAMPTZ,
                CONSTRAINT tutorial_step_target_consistent CHECK (
                    (target_kind = 'none' AND target_key IS NULL)
                    OR (target_kind IN ('static','sdui') AND target_key IS NOT NULL AND length(target_key) > 0)
                ),
                CONSTRAINT tutorial_step_title_nonempty CHECK (length(btrim(title)) > 0 AND length(title) <= 120),
                CONSTRAINT tutorial_step_body_nonempty CHECK (length(btrim(body)) > 0 AND length(body) <= 1000)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tutorial_step_user_view ON tutorial_step(archived_at, audience, display_order)')

        # onboarding_state — one row per user; absence is the implicit
        # "not_started" default so first-run is distinguishable from a
        # deliberately persisted state.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS onboarding_state (
                user_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('not_started','in_progress','completed','skipped')),
                last_step_id BIGINT REFERENCES tutorial_step(id) ON DELETE SET NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ,
                skipped_at TIMESTAMPTZ,
                dismissed_at TIMESTAMPTZ,
                dismiss_count INTEGER NOT NULL DEFAULT 0
            )
        ''')

        # Migration: US-17 — add dimissed_at / dismiss_count columns for
        # "not now" cooldown. Safe to run idempotently.
        for col, col_def in [
            ("dismissed_at", "TIMESTAMPTZ"),
            ("dismiss_count", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                cursor.execute(
                    f"ALTER TABLE onboarding_state ADD COLUMN IF NOT EXISTS {col} {col_def}"
                )
            except Exception:
                conn.rollback()

        # tutorial_step_revision — append-only history of admin edits.
        # Full before/after snapshots live here; the audit log only carries
        # a structured changed-fields summary.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tutorial_step_revision (
                id BIGSERIAL PRIMARY KEY,
                step_id BIGINT NOT NULL REFERENCES tutorial_step(id) ON DELETE CASCADE,
                editor_user_id TEXT NOT NULL,
                edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                previous JSONB,
                current JSONB NOT NULL,
                change_kind TEXT NOT NULL CHECK (change_kind IN ('create','update','archive','restore'))
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tutorial_step_revision_step_time ON tutorial_step_revision(step_id, edited_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tutorial_step_revision_editor ON tutorial_step_revision(editor_user_id, edited_at DESC)')

        # ------------------------------------------------------------------
        # Feature 014 — in-chat progress notifications & persistent step trail
        # ------------------------------------------------------------------
        # One row per persistent step entry (tool_call / agent_handoff / phase)
        # captured by ChatStepRecorder. Persisted alongside the chat's
        # messages so step history rehydrates with the chat.
        # See specs/014-progress-notifications/data-model.md.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_steps (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'legacy',
                turn_message_id INTEGER,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'in_progress',
                args_truncated TEXT,
                args_was_truncated BOOLEAN NOT NULL DEFAULT FALSE,
                result_summary TEXT,
                result_was_truncated BOOLEAN NOT NULL DEFAULT FALSE,
                error_message TEXT,
                started_at BIGINT NOT NULL,
                ended_at BIGINT,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE,
                FOREIGN KEY (turn_message_id) REFERENCES messages (id) ON DELETE SET NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_steps_chat_id ON chat_steps(chat_id, started_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_steps_turn ON chat_steps(turn_message_id)')

        # Render-time cache: number of step rows per turn-anchoring message.
        # Maintained by ChatStepRecorder on lifecycle transitions so the chat
        # list endpoint can show counts without joining chat_steps.
        if not self._column_exists(cursor, 'messages', 'step_count'):
            cursor.execute("ALTER TABLE messages ADD COLUMN step_count INTEGER NOT NULL DEFAULT 0")

        # ------------------------------------------------------------------
        # Feature 025 — agentic soul integration
        # Per-user personalization (profile + personality/"soul"), durable
        # non-PHI memory, scheduled jobs ("cron"), background consolidation
        # ("dreaming"), and the encrypted offline-grant store that authorizes
        # unattended job runs. All rows are strictly user-scoped.
        # See specs/025-agentic-soul-integration/data-model.md.
        # ------------------------------------------------------------------

        # One row per user: profession, goals, personality, dreaming toggle.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_personalization (
                user_id TEXT PRIMARY KEY,
                profession TEXT,
                goals JSONB NOT NULL DEFAULT '[]'::jsonb,
                personality JSONB NOT NULL DEFAULT '{}'::jsonb,
                dreaming_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')

        # Durable, non-PHI personalization facts (structured-only categories).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_item (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('profession','goal','preference','workflow_tag','context')),
                value TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('explicit','promoted')),
                salience REAL NOT NULL DEFAULT 0,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_item_user_cat ON memory_item(user_id, category)')

        # Transient promotion candidates; consumed/aged by the dreaming sweep.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS short_term_signal (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('profession','goal','preference','workflow_tag','context')),
                value TEXT NOT NULL,
                recall_count INTEGER NOT NULL DEFAULT 0,
                last_seen_at BIGINT,
                created_at BIGINT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_short_term_signal_user_seen ON short_term_signal(user_id, last_seen_at)')

        # Encrypted offline-grant store (authority for unattended job runs).
        # refresh_token_enc is encrypted at rest and never returned by any API.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_offline_grant (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT,
                refresh_token_enc BYTEA NOT NULL,
                issued_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                revoked_at BIGINT,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_offline_grant_active ON user_offline_grant(user_id, agent_id) WHERE revoked_at IS NULL')

        # User-defined recurring/future tasks.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_job (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT,
                name TEXT NOT NULL,
                instruction TEXT NOT NULL,
                schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('one_shot','interval','cron')),
                schedule_expr TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                consented_scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
                delivery TEXT NOT NULL DEFAULT 'in_app' CHECK (delivery = 'in_app'),
                status TEXT NOT NULL CHECK (status IN ('active','paused','expired','completed','disabled')),
                target_chat_id TEXT,
                next_run_at BIGINT,
                last_run_at BIGINT,
                offline_grant_id UUID REFERENCES user_offline_grant(id) ON DELETE SET NULL,
                created_at BIGINT,
                updated_at BIGINT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_job_due ON scheduled_job(status, next_run_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_job_user ON scheduled_job(user_id, status)')

        # One execution record per job run.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_run (
                id UUID PRIMARY KEY,
                job_id UUID NOT NULL REFERENCES scheduled_job(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                started_at BIGINT NOT NULL,
                ended_at BIGINT,
                outcome TEXT NOT NULL CHECK (outcome IN ('running','success','failure','interrupted','skipped_auth')),
                auth_ref TEXT,
                correlation_id UUID NOT NULL,
                summary TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_job_run_job_time ON job_run(job_id, started_at DESC)')

        # A "dream": one consolidation sweep's human-readable review record.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consolidation_sweep (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                ran_at BIGINT NOT NULL,
                candidates_considered INTEGER NOT NULL DEFAULT 0,
                promoted_count INTEGER NOT NULL DEFAULT 0,
                summary TEXT NOT NULL,
                trigger TEXT NOT NULL CHECK (trigger IN ('scheduled','manual'))
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_consolidation_sweep_user_time ON consolidation_sweep(user_id, ran_at DESC)')

        # ── Feature 028 — workspace-auth-revival ────────────────────────────
        # Durable server-side OIDC sessions (replaces web_auth's in-memory
        # dict as source of truth; tokens Fernet-encrypted at rest).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS web_session (
                sid TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                access_token_enc TEXT NOT NULL,
                refresh_token_enc TEXT NOT NULL,
                interactive_anchor BIGINT NOT NULL,
                hard_expires_at BIGINT NOT NULL,
                last_refresh_at BIGINT NOT NULL,
                resumed BOOLEAN DEFAULT FALSE,
                created_at BIGINT NOT NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS ix_web_session_user ON web_session(user_id)')

        # Offline-tolerant sign-out: refresh tokens awaiting best-effort
        # revocation at Keycloak (server-side analog of 016's client queue).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_revocation_queue (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                refresh_token_enc TEXT NOT NULL,
                enqueued_at BIGINT NOT NULL,
                attempts INTEGER DEFAULT 0
            )
        ''')

        # Per-turn full-state workspace snapshots (read-only timeline).
        # components carries message-grade content; lifecycle == the chat's.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workspace_snapshot (
                id SERIAL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                turn_message_id INTEGER,
                cause TEXT NOT NULL,
                components TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS ix_workspace_snapshot_chat ON workspace_snapshot(chat_id, created_at)')
        # data-model.md declares turn_message_id as FK -> messages(id) ON
        # DELETE CASCADE. Added as a named constraint (idempotent; covers
        # deployments whose table predates the FK). NOT VALID skips
        # re-validating historic rows; new writes are enforced.
        cursor.execute('''
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = 'workspace_snapshot'
              AND constraint_name = 'fk_workspace_snapshot_turn_message'
        ''')
        if not cursor.fetchone():
            cursor.execute('''
                ALTER TABLE workspace_snapshot
                ADD CONSTRAINT fk_workspace_snapshot_turn_message
                FOREIGN KEY (turn_message_id) REFERENCES messages (id)
                ON DELETE CASCADE NOT VALID
            ''')

        # saved_components becomes the live workspace store: stable identity,
        # ordering, and in-place update timestamps (additive; legacy rows keep
        # NULLs and sort by created_at).
        for col, ddl in (("component_id", "TEXT"), ("position", "INTEGER"), ("updated_at", "BIGINT")):
            if not self._column_exists(cursor, 'saved_components', col):
                cursor.execute(f"ALTER TABLE saved_components ADD COLUMN {col} {ddl}")
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS ux_saved_components_chat_component
            ON saved_components (chat_id, component_id) WHERE component_id IS NOT NULL
        ''')

        # ── Feature 029: adaptive UI designer — canvas arrangements ─────────
        # A layout is a per-round designed tree whose leaves REFERENCE live
        # saved_components rows by component_id (overlay model: layouts never
        # own component content, so dropping this table degrades cleanly to
        # the flat position-ordered canvas). Rollback: DROP TABLE.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workspace_layout (
                id SERIAL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                layout_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                layout TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS ux_workspace_layout_chat_key
            ON workspace_layout (chat_id, layout_key)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ix_workspace_layout_chat_pos
            ON workspace_layout (chat_id, position)
        ''')
        # Snapshots additionally capture the live arrangements at turn
        # boundaries so the read-only timeline can materialize historical
        # designed states. NULL == pre-029 snapshot (rendered flat).
        # Rollback: ALTER TABLE workspace_snapshot DROP COLUMN layouts.
        if not self._column_exists(cursor, 'workspace_snapshot', 'layouts'):
            cursor.execute("ALTER TABLE workspace_snapshot ADD COLUMN layouts TEXT NULL")

        # ── Feature 029: agent catalog migrations (data-model.md) ───────────
        self._migrate_agent_catalog_029(cursor)

        # ── Feature 030: first-party agent visibility backfill ──────────────
        self._migrate_agent_visibility_030(cursor)

        conn.commit()
        conn.close()

    # Feature 029 identity sets (specs/029-agents-adaptive-ui-ci/baseline.md).
    # Both the declared hyphenated agent ids and the legacy underscore
    # directory-name rows exist in deployed databases — cover both.
    _ML_MERGED_AGENT_IDS = ('classify', 'classify-1', 'forecaster', 'forecaster-1',
                            'llm_factory', 'llm-factory-1')
    _ML_AGENT_ID = 'ml-services-1'
    # The five verb names classify and forecaster shared pre-merge; each is
    # exposed service-prefixed by the consolidated registry.
    _ML_PREFIXED_VERBS = ('submit_dataset', 'start_training_job', 'get_job_status',
                          'get_results', 'delete_dataset')
    _RETIRED_AGENT_IDS = ('email_tracker', 'email-tracker-1',
                          'grant_budgets', 'grant-budgets-1',
                          'grants', 'grants-1',
                          'linkedin', 'linkedin-1',
                          'nefarious', 'nefarious-1',
                          'nocodb', 'nocodb-1')

    def _migrate_agent_catalog_029(self, cursor):
        """Feature 029 one-time (idempotent) catalog migrations.

        1. classify/forecaster/llm_factory → ml-services-1 identity remap with
           settings carry-forward (FR-008): scopes merge with OR semantics
           (granted on any predecessor stays granted), per-tool overrides
           merge with AND semantics (disabled on any predecessor stays
           disabled — fail-safe), credentials/ownership carry over, and the
           five colliding verb names gain their service prefixes in stored
           per-tool rows.
        2. Permission/credential rows for the six retired agents are deleted
           (FR-003; lead-approved destructive — audit/chats/saved_components
           rows are intentionally preserved per data-model.md).

        Every statement is a no-op on re-run (UPDATE/DELETE match nothing,
        INSERT...SELECT reads an empty source), so this is safe at every boot.
        """
        ml_ids = self._ML_MERGED_AGENT_IDS
        ml_ph = ", ".join(["%s"] * len(ml_ids))
        retired = self._RETIRED_AGENT_IDS
        retired_ph = ", ".join(["%s"] * len(retired))
        verb_ph = ", ".join(["%s"] * len(self._ML_PREFIXED_VERBS))

        # (1a) Service-prefix the colliding verbs BEFORE the id remap (the
        # old agent id is what tells us which prefix a row needs).
        for table in ('tool_overrides', 'tool_permissions'):
            for prefix, old_ids in (('classify_', ('classify', 'classify-1')),
                                    ('forecaster_', ('forecaster', 'forecaster-1'))):
                cursor.execute(
                    f"UPDATE {table} SET tool_name = %s || tool_name "
                    f"WHERE agent_id IN (%s, %s) AND tool_name IN ({verb_ph})",
                    (prefix, *old_ids, *self._ML_PREFIXED_VERBS),
                )

        # (1b) Ownership: one surviving row (UNIQUE(agent_id)).
        cursor.execute(
            f"""INSERT INTO agent_ownership (agent_id, owner_email, is_public, created_at, updated_at)
                SELECT %s, owner_email, is_public, created_at, updated_at
                FROM agent_ownership WHERE agent_id IN ({ml_ph})
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                ON CONFLICT (agent_id) DO NOTHING""",
            (self._ML_AGENT_ID, *ml_ids),
        )

        # (1c) Scopes: OR-merge per (user, scope).
        cursor.execute(
            f"""INSERT INTO agent_scopes (user_id, agent_id, scope, enabled, updated_at)
                SELECT user_id, %s, scope, BOOL_OR(enabled), MAX(updated_at)
                FROM agent_scopes WHERE agent_id IN ({ml_ph})
                GROUP BY user_id, scope
                ON CONFLICT DO NOTHING""",
            (self._ML_AGENT_ID, *ml_ids),
        )

        # (1d) Per-tool overrides: AND-merge per (user, tool, kind) — a tool a
        # user disabled on any predecessor stays disabled on the merged agent.
        cursor.execute(
            f"""INSERT INTO tool_overrides (user_id, agent_id, tool_name, enabled, updated_at, permission_kind)
                SELECT user_id, %s, tool_name, BOOL_AND(enabled), MAX(updated_at), permission_kind
                FROM tool_overrides WHERE agent_id IN ({ml_ph})
                GROUP BY user_id, tool_name, permission_kind
                ON CONFLICT DO NOTHING""",
            (self._ML_AGENT_ID, *ml_ids),
        )
        cursor.execute(
            f"""INSERT INTO tool_permissions (user_id, agent_id, tool_name, allowed, updated_at)
                SELECT user_id, %s, tool_name, BOOL_AND(allowed), MAX(updated_at)
                FROM tool_permissions WHERE agent_id IN ({ml_ph})
                GROUP BY user_id, tool_name
                ON CONFLICT DO NOTHING""",
            (self._ML_AGENT_ID, *ml_ids),
        )

        # (1e) Credentials: key names are service-distinct (CLASSIFY_*,
        # FORECASTER_*, LLM_FACTORY_*), so rows carry over verbatim.
        cursor.execute(
            f"""INSERT INTO user_credentials (user_id, agent_id, credential_key, encrypted_value, created_at, updated_at)
                SELECT user_id, %s, credential_key, encrypted_value, created_at, updated_at
                FROM user_credentials WHERE agent_id IN ({ml_ph})
                ON CONFLICT DO NOTHING""",
            (self._ML_AGENT_ID, *ml_ids),
        )

        # (1f) Chat bindings follow the merged identity, then the old rows go.
        cursor.execute(f"UPDATE chats SET agent_id = %s WHERE agent_id IN ({ml_ph})",
                       (self._ML_AGENT_ID, *ml_ids))
        for table in ('agent_ownership', 'agent_scopes', 'tool_overrides',
                      'tool_permissions', 'user_credentials'):
            cursor.execute(f"DELETE FROM {table} WHERE agent_id IN ({ml_ph})", ml_ids)

        # (2) Retired agents: permission/credential rows are destroyed.
        for table in ('agent_ownership', 'agent_scopes', 'tool_overrides',
                      'tool_permissions', 'user_credentials'):
            cursor.execute(f"DELETE FROM {table} WHERE agent_id IN ({retired_ph})", retired)

    # Feature 030: the operator-bundled catalog (post-029 agent ids). These
    # are the agents every user should be able to SEE in the Agents surface
    # (visibility ≠ authorization — scopes stay fail-closed per user).
    # Drafts and user-created agents are never listed here.
    _FIRST_PARTY_PUBLIC_AGENT_IDS = (
        'connectors-1', 'dice-roller-1', 'etf-tracker-1-1', 'general-1',
        'journal-review-1', 'medical-1', 'ml-services-1', 'summarizer-1',
        'weather-1', 'web-research-1',
    )

    def _migrate_agent_visibility_030(self, cursor):
        """Feature 030 one-time (idempotent) visibility backfill.

        The 029 plug-and-play agents (web_research, summarizer) and bundled
        dice_roller registered through the ownerless auto-assign path, which
        hard-coded ``is_public=false`` — leaving them invisible in every tab
        of the Agents surface, so users could not discover or enable them
        (verified 030 walkthrough finding). Mark the fixed first-party
        catalog public; registration now defaults non-draft ownerless agents
        to public going forward.

        Idempotent: the UPDATE matches nothing once the flags are set.
        Rollback: ``UPDATE agent_ownership SET is_public = FALSE WHERE
        agent_id IN (<_FIRST_PARTY_PUBLIC_AGENT_IDS>)``.
        """
        ph = ", ".join(["%s"] * len(self._FIRST_PARTY_PUBLIC_AGENT_IDS))
        cursor.execute(
            f"UPDATE agent_ownership SET is_public = TRUE "
            f"WHERE agent_id IN ({ph}) AND is_public = FALSE",
            self._FIRST_PARTY_PUBLIC_AGENT_IDS,
        )

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

    # ── Chat ↔ Agent Binding (Feature 013) ───────────────────────────────

    def get_chat_agent(self, chat_id: str) -> Optional[str]:
        """Return the agent_id bound to the chat, or None if unbound (legacy chats)."""
        row = self.fetch_one("SELECT agent_id FROM chats WHERE id = ?", (chat_id,))
        if not row:
            return None
        return row.get("agent_id")

    def set_chat_agent(self, chat_id: str, agent_id: Optional[str]) -> bool:
        """Bind (or unbind) a chat to an agent. Returns True if a row was updated."""
        cursor = self.execute(
            "UPDATE chats SET agent_id = ? WHERE id = ?",
            (agent_id, chat_id),
        )
        return cursor.rowcount > 0

    # ── Per-User Tool Selection Preference (Feature 013 / FR-024) ────────

    def get_user_tool_selection(self, user_id: str, agent_id: str) -> Optional[List[str]]:
        """Return the user's saved tool selection for the given agent.

        Returns:
            A list of tool names if the user has narrowed the selection,
            or None when the user has not narrowed (orchestrator falls
            back to the agent's full permission-allowed set per FR-019).
        """
        prefs = self.get_user_preferences(user_id)
        sel_map = prefs.get("tool_selection") or {}
        if not isinstance(sel_map, dict):
            return None
        value = sel_map.get(agent_id)
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        return [str(v) for v in value]

    def set_user_tool_selection(
        self, user_id: str, agent_id: str, tool_names: List[str]
    ) -> None:
        """Save the user's tool selection for an agent (FR-024).

        Callers MUST pass a non-empty list — empty selection is blocked
        at the UI layer (FR-021) and rejected by the API (T035). This
        helper does not validate against permission scopes; that check
        belongs at the API boundary.
        """
        prefs = self.get_user_preferences(user_id)
        sel_map = prefs.get("tool_selection")
        if not isinstance(sel_map, dict):
            sel_map = {}
        sel_map[agent_id] = list(tool_names)
        prefs["tool_selection"] = sel_map
        self.set_user_preferences(user_id, prefs)

    def clear_user_tool_selection(self, user_id: str, agent_id: str) -> bool:
        """Clear the user's saved selection for an agent (FR-025 reset).

        Returns True if a saved selection was present and was removed,
        False if no selection existed (idempotent no-op).
        """
        prefs = self.get_user_preferences(user_id)
        sel_map = prefs.get("tool_selection")
        if not isinstance(sel_map, dict) or agent_id not in sel_map:
            return False
        del sel_map[agent_id]
        prefs["tool_selection"] = sel_map
        self.set_user_preferences(user_id, prefs)
        return True

    # ── Per-User Agent Disable (Feature 013 follow-up) ───────────────────
    # Lets a user temporarily disable an entire agent without changing its
    # scopes/permissions or affecting other users. Stored under
    # `user_preferences.disabled_agents` as a list of agent_ids. Absence
    # in the list means the agent is enabled (default).

    def get_user_disabled_agents(self, user_id: str) -> List[str]:
        """Return the list of agent_ids the user has disabled (may be empty)."""
        prefs = self.get_user_preferences(user_id)
        value = prefs.get("disabled_agents")
        if not isinstance(value, list):
            return []
        return [str(v) for v in value]

    def is_user_agent_disabled(self, user_id: str, agent_id: str) -> bool:
        """Return True iff the user has disabled this agent."""
        return agent_id in self.get_user_disabled_agents(user_id)

    def set_user_agent_disabled(
        self, user_id: str, agent_id: str, disabled: bool
    ) -> bool:
        """Toggle the user's per-agent disabled state.

        Returns True if the stored value changed, False if it was already
        in the requested state (idempotent).
        """
        prefs = self.get_user_preferences(user_id)
        current = prefs.get("disabled_agents")
        disabled_list: List[str] = (
            [str(v) for v in current] if isinstance(current, list) else []
        )
        present = agent_id in disabled_list
        if disabled and not present:
            disabled_list.append(agent_id)
        elif not disabled and present:
            disabled_list = [a for a in disabled_list if a != agent_id]
        else:
            return False  # already in the requested state
        prefs["disabled_agents"] = disabled_list
        self.set_user_preferences(user_id, prefs)
        return True

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
                           skill_tags: str = None, packages: str = None,
                           origin: str = "manual", source_chat_id: str = None,
                           gap_fingerprint: str = None, revises_agent_id: str = None) -> None:
        """Create a new draft agent record.

        Feature 027: ``origin`` records the entry point (``manual`` |
        ``auto_chat`` | ``revision``); ``source_chat_id`` + ``gap_fingerprint``
        scope capability-gap dedup; ``revises_agent_id`` links a revision
        draft to the live agent it stages changes for.
        """
        import time
        now = int(time.time() * 1000)
        self.execute(
            """INSERT INTO draft_agents (id, user_id, agent_name, agent_slug, description,
               tools_spec, skill_tags, packages, status, origin, source_chat_id,
               gap_fingerprint, revises_agent_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)""",
            (draft_id, user_id, agent_name, agent_slug, description,
             tools_spec, skill_tags, packages, origin, source_chat_id,
             gap_fingerprint, revises_agent_id, now, now)
        )

    def find_gap_draft(self, user_id: str, source_chat_id: str,
                       gap_fingerprint: str) -> Optional[Dict]:
        """Feature 027 (FR-007): the non-terminal draft already staged for a
        capability gap, or None. Terminal = live (resolved) or deleted
        (discarded); rejected drafts stay editable so they still count."""
        row = self.fetch_one(
            """SELECT * FROM draft_agents
               WHERE user_id = ? AND source_chat_id = ? AND gap_fingerprint = ?
                 AND status != 'live'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, source_chat_id, gap_fingerprint)
        )
        return dict(row) if row else None

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

    # ── Interaction Log (Knowledge Synthesis) ──────────────────────────────

    def log_interaction(self, agent_id: str, tool_name: str, success: bool,
                        error_message: str = None, response_time_ms: int = None,
                        chat_id: str = None) -> None:
        """Record a tool interaction for knowledge synthesis."""
        import time
        now = int(time.time() * 1000)
        self.execute(
            """INSERT INTO interaction_log (agent_id, tool_name, success, error_message,
               response_time_ms, chat_id, synthesized, created_at)
               VALUES (?, ?, ?, ?, ?, ?, FALSE, ?)""",
            (agent_id, tool_name, success, error_message, response_time_ms, chat_id, now)
        )

    def get_unsynthesized_interactions(self, limit: int = 500) -> List[Dict]:
        """Fetch interactions not yet processed by the knowledge synthesizer."""
        rows = self.fetch_all(
            "SELECT * FROM interaction_log WHERE synthesized = FALSE ORDER BY created_at ASC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in rows]

    def mark_interactions_synthesized(self, ids: List[int]) -> None:
        """Mark interaction rows as synthesized."""
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        self.execute(
            f"UPDATE interaction_log SET synthesized = TRUE WHERE id IN ({placeholders})",
            tuple(ids)
        )

    def get_interaction_stats(self, agent_id: str = None) -> List[Dict]:
        """Get aggregated interaction stats, optionally filtered by agent."""
        if agent_id:
            rows = self.fetch_all(
                """SELECT agent_id, tool_name, COUNT(*) as total_calls,
                   SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                   AVG(response_time_ms) as avg_response_ms
                   FROM interaction_log WHERE agent_id = ?
                   GROUP BY agent_id, tool_name""",
                (agent_id,)
            )
        else:
            rows = self.fetch_all(
                """SELECT agent_id, tool_name, COUNT(*) as total_calls,
                   SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                   AVG(response_time_ms) as avg_response_ms
                   FROM interaction_log
                   GROUP BY agent_id, tool_name"""
            )
        return [dict(r) for r in rows]

    def close(self):
        """No-op for compatibility — connections are opened/closed per request."""
        pass
