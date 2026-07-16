-- Synthetic, sanitized representative state for a database already initialized
-- at AstralDeep schema revision 057.001. This fixture contains no schema DDL;
-- feature-060 tests must advance it only through the normal startup migration.

BEGIN;

DO $$
DECLARE
    current_revision TEXT;
BEGIN
    SELECT value INTO current_revision
    FROM schema_meta
    WHERE key = 'revision';

    IF current_revision IS DISTINCT FROM '057.001' THEN
        RAISE EXCEPTION
            'representative-057.sql requires schema revision 057.001, found %',
            COALESCE(current_revision, '<missing>');
    END IF;
END
$$;

INSERT INTO users (
    id, email, username, display_name, roles,
    last_login_at, created_at, updated_at
) VALUES
    (
        'fixture-owner-a', 'owner-a@example.invalid.test', 'fixture_owner_a',
        'Synthetic Owner A', '["user"]', 1735689600000, 1735689600000,
        1735689600000
    ),
    (
        'fixture-owner-b', 'owner-b@example.invalid.test', 'fixture_owner_b',
        'Synthetic Owner B', '["user"]', 1735689600000, 1735689600000,
        1735689600000
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO chats (
    id, user_id, title, created_at, updated_at,
    has_saved_components, agent_id
) VALUES
    (
        'fixture-chat-structured', 'fixture-owner-a',
        'Synthetic structured conversation', 1735689600000, 1735689660000,
        TRUE, 'fixture-server-agent'
    ),
    (
        'fixture-chat-empty-canvas', 'fixture-owner-b',
        'Synthetic transcript without canvas', 1735689720000, 1735689720000,
        FALSE, 'fixture-host-agent'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (
    id, chat_id, user_id, role, content, timestamp
) VALUES
    (
        60001, 'fixture-chat-structured', 'fixture-owner-a', 'user',
        '{"type":"text","text":"Synthetic migration question"}',
        1735689601000
    ),
    (
        60002, 'fixture-chat-structured', 'fixture-owner-a', 'assistant',
        '{"type":"ui_response","content":[{"type":"Text","text":"Synthetic structured answer"}]}',
        1735689602000
    ),
    (
        60003, 'fixture-chat-empty-canvas', 'fixture-owner-b', 'assistant',
        '[{"type":"Text","text":"Synthetic array-form transcript"}]',
        1735689721000
    )
ON CONFLICT (id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('messages', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM messages), 1),
    TRUE
);

INSERT INTO saved_components (
    id, chat_id, user_id, component_data, component_type, title,
    created_at, component_id, position, updated_at
) VALUES
    (
        'fixture-saved-component-card', 'fixture-chat-structured',
        'fixture-owner-a',
        '{"type":"Card","title":"Synthetic status","children":[{"type":"Text","text":"Fixture-only canvas content"}]}',
        'Card', 'Synthetic status', 1735689603000,
        'fixture-component-card', 0, 1735689603000
    ),
    (
        'fixture-saved-component-progress', 'fixture-chat-structured',
        'fixture-owner-a',
        '{"type":"Progress","value":1,"max":4,"label":"Synthetic progress"}',
        'Progress', 'Synthetic progress', 1735689604000,
        'fixture-component-progress', 1, 1735689604000
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO workspace_snapshot (
    id, chat_id, user_id, turn_message_id, cause, components,
    created_at, layouts
) VALUES (
    60001, 'fixture-chat-structured', 'fixture-owner-a', 60002,
    'assistant_turn',
    '[{"component_id":"fixture-component-card","component_data":{"type":"Card","title":"Synthetic status"}},{"component_id":"fixture-component-progress","component_data":{"type":"Progress","value":1,"max":4}}]',
    1735689605000,
    '[{"layout_key":"synthetic-primary","position":0,"layout":{"type":"Stack","children":["fixture-component-card","fixture-component-progress"]}}]'
)
ON CONFLICT (id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('workspace_snapshot', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM workspace_snapshot), 1),
    TRUE
);

INSERT INTO scheduled_job (
    id, user_id, agent_id, name, instruction, schedule_kind,
    schedule_expr, timezone, consented_scopes, delivery, status,
    target_chat_id, next_run_at, last_run_at, offline_grant_id,
    created_at, updated_at
) VALUES
    (
        '06000000-0000-4000-8000-000000000101', 'fixture-owner-a',
        'fixture-server-agent', 'Synthetic active schedule',
        'Generate a synthetic fixture status summary.', 'interval', '3600',
        'UTC', '["tools:read"]'::jsonb, 'in_app', 'active',
        'fixture-chat-structured', 1735693200000, 1735689600000, NULL,
        1735686000000, 1735689600000
    ),
    (
        '06000000-0000-4000-8000-000000000102', 'fixture-owner-b',
        'fixture-host-agent', 'Synthetic paused schedule',
        'Record a synthetic fixture heartbeat.', 'cron', '0 9 * * *',
        'UTC', '[]'::jsonb, 'in_app', 'paused',
        'fixture-chat-empty-canvas', NULL, 1735686000000, NULL,
        1735682400000, 1735686000000
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO job_run (
    id, job_id, user_id, started_at, ended_at, outcome,
    auth_ref, correlation_id, summary
) VALUES
    (
        '06000000-0000-4000-8000-000000000201',
        '06000000-0000-4000-8000-000000000101', 'fixture-owner-a',
        1735689500000, 1735689510000, 'success', 'fixture-grant-ref',
        '06000000-0000-4000-8000-000000000211',
        'Synthetic historical success'
    ),
    (
        '06000000-0000-4000-8000-000000000202',
        '06000000-0000-4000-8000-000000000101', 'fixture-owner-a',
        1735689600000, NULL, 'running', 'fixture-grant-ref',
        '06000000-0000-4000-8000-000000000212',
        'Synthetic in-progress run'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO background_task (
    task_id, user_id, chat_id, kind, status, title, summary,
    created_at, completed_at, notified
) VALUES
    (
        'fixture-background-running', 'fixture-owner-a',
        'fixture-chat-structured', 'async_chat', 'running',
        'Synthetic running task', NULL,
        '2025-01-01T00:00:00Z'::timestamptz, NULL, FALSE
    ),
    (
        'fixture-background-completed', 'fixture-owner-a',
        'fixture-chat-structured', 'async_chat', 'completed',
        'Synthetic completed task', 'Synthetic completion summary',
        '2024-12-31T23:50:00Z'::timestamptz,
        '2024-12-31T23:51:00Z'::timestamptz, TRUE
    ),
    (
        'fixture-background-failed', 'fixture-owner-b',
        'fixture-chat-empty-canvas', 'async_chat', 'failed',
        'Synthetic failed task', 'Synthetic safe failure summary',
        '2024-12-31T23:40:00Z'::timestamptz,
        '2024-12-31T23:41:00Z'::timestamptz, FALSE
    )
ON CONFLICT (task_id) DO NOTHING;

INSERT INTO draft_agents (
    id, user_id, agent_name, agent_slug, description, tools_spec,
    skill_tags, packages, status, generation_log, security_report,
    error_message, port, review_notes, reviewed_by, refinement_history,
    validation_report, required_credentials, created_at, updated_at,
    origin, source_chat_id, gap_fingerprint, revises_agent_id,
    self_test, phase, clarify_answers, plan_json, analyze_result,
    constitution_version, host_binding
) VALUES
    (
        '06000000-0000-4000-8000-000000000301', 'fixture-owner-a',
        'Synthetic Same Name', 'synthetic-same-name',
        'Synthetic server-local draft used only by migration tests.',
        '["status_read"]', '["fixture"]', '[]', 'validated',
        'Synthetic generation completed.', '{"decision":"pass"}', NULL, NULL,
        'Synthetic review complete.', 'fixture-reviewer', '[]',
        '{"passed":true}', '[]', 1735689600000, 1735689600000,
        'byo_client', 'fixture-chat-structured', 'fixture-gap-server', NULL,
        '{"passed":true}', 'analyze', '{}', '{"steps":[]}',
        '{"decision":"pass"}', '2.7.0', NULL
    ),
    (
        '06000000-0000-4000-8000-000000000302', 'fixture-owner-a',
        'Synthetic Same Name', 'synthetic-same-name',
        'Synthetic host-bound draft used only by migration tests.',
        '["status_read"]', '["fixture"]', '[]', 'validated',
        'Synthetic generation completed.', '{"decision":"pass"}', NULL, NULL,
        'Synthetic review complete.', 'fixture-reviewer', '[]',
        '{"passed":true}', '[]', 1735689601000, 1735689601000,
        'byo_client', 'fixture-chat-structured', 'fixture-gap-host', NULL,
        '{"passed":true}', 'analyze', '{}', '{"steps":[]}',
        '{"decision":"pass"}', '2.7.0',
        '{"client_id":"fixture-desktop-host"}'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO user_agent (
    agent_id, owner_user_id, owner_email, display_name, status,
    declared_tools, declared_scopes, declared_egress,
    constitution_version, validated_at, revalidation_required,
    draft_id, host_client_id, host_session_id, host_last_seen_at,
    is_public, deleted_at, created_at, updated_at
) VALUES
    (
        'fixture-server-agent', 'fixture-owner-a', 'owner-a@example.invalid.test',
        'Synthetic Server Agent', 'live', '["status_read"]',
        '["tools:read"]', '[]', '2.7.0', 1735689600000, FALSE,
        '06000000-0000-4000-8000-000000000301', NULL, NULL, NULL,
        FALSE, NULL, 1735689600000, 1735689600000
    ),
    (
        'fixture-host-agent', 'fixture-owner-a', 'owner-a@example.invalid.test',
        'Synthetic Host Agent', 'live', '["status_read"]',
        '["tools:read"]', '[]', '2.7.0', 1735689601000, FALSE,
        '06000000-0000-4000-8000-000000000302',
        'fixture-desktop-host', 'fixture-host-session', 1735689602000,
        FALSE, NULL, 1735689601000, 1735689602000
    ),
    (
        'fixture-deleted-agent', 'fixture-owner-b', 'owner-b@example.invalid.test',
        'Synthetic Deleted Agent', 'disabled', '[]', '[]', NULL,
        '2.7.0', 1735689500000, FALSE, NULL, NULL, NULL, NULL,
        FALSE, 1735689603000, 1735689400000, 1735689603000
    )
ON CONFLICT (agent_id) DO NOTHING;

INSERT INTO agent_ownership (
    agent_id, owner_email, is_public, created_at, updated_at
) VALUES
    (
        'fixture-server-agent', 'owner-a@example.invalid.test', FALSE,
        1735689600000, 1735689600000
    ),
    (
        'fixture-host-agent', 'owner-a@example.invalid.test', FALSE,
        1735689601000, 1735689601000
    ),
    (
        'fixture-deleted-agent', 'owner-b@example.invalid.test', FALSE,
        1735689400000, 1735689603000
    )
ON CONFLICT (agent_id) DO NOTHING;

INSERT INTO interaction_log (
    id, agent_id, tool_name, success, error_message, response_time_ms,
    chat_id, synthesized, created_at
) VALUES
    (
        60001, 'fixture-server-agent', 'status_read', TRUE, NULL, 12,
        'fixture-chat-structured', TRUE, 1735689600000
    ),
    (
        60002, 'fixture-server-agent', 'status_read', TRUE, NULL, 18,
        'fixture-chat-structured', FALSE, 1735689601000
    ),
    (
        60003, 'fixture-host-agent', 'status_read', FALSE,
        'synthetic_upstream_unavailable', 25,
        'fixture-chat-empty-canvas', FALSE, 1735689602000
    )
ON CONFLICT (id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('interaction_log', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM interaction_log), 1),
    TRUE
);

COMMIT;
