/**
 * Audit log DTO types — feature 003-agent-audit-log.
 *
 * Mirrors the public-facing JSON Schema in
 * specs/003-agent-audit-log/contracts/audit-event-schema.json. Internal
 * AU-9 fields (prev_hash, entry_hash, key_id, schema_version) and the
 * forensic-only auth_principal / actor_user_id are intentionally absent
 * — those never cross the wire.
 */

export type AuditEventClass =
    | "auth"
    | "conversation"
    | "file"
    | "settings"
    | "agent_tool_call"
    | "agent_ui_render"
    | "agent_external_call"
    | "audit_view";

export type AuditOutcome =
    | "in_progress"
    | "success"
    | "failure"
    | "interrupted";

export interface AuditArtifactPointer {
    artifact_id: string;
    store: string;
    extension: string | null;
    size_bytes: number | null;
    available: boolean;
}

export interface AuditEvent {
    event_id: string;
    event_class: AuditEventClass;
    action_type: string;
    description: string;
    agent_id: string | null;
    conversation_id: string | null;
    correlation_id: string;
    outcome: AuditOutcome;
    outcome_detail: string | null;
    inputs_meta: Record<string, unknown>;
    outputs_meta: Record<string, unknown>;
    artifact_pointers: AuditArtifactPointer[];
    started_at: string;        // ISO-8601
    completed_at: string | null;
    recorded_at: string;       // ISO-8601
}

export interface AuditListResponse {
    items: AuditEvent[];
    next_cursor: string | null;
    filters_echo: Record<string, unknown>;
}

export interface AuditListFilters {
    limit?: number;
    cursor?: string;
    event_class?: AuditEventClass[];
    outcome?: AuditOutcome[];
    from?: string;             // ISO-8601
    to?: string;               // ISO-8601
    q?: string;
}

/**
 * Server→client live-append message envelope. Frontend dispatches it
 * via useWebSocket and re-broadcasts to the audit panel as a
 * CustomEvent("audit:append").
 */
export interface AuditAppendMessage {
    type: "audit_append";
    event: AuditEvent;
}
