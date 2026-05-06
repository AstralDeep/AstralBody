/**
 * Frontend types for the persistent step trail
 * (feature 014-progress-notifications, US2 / data-model.md).
 *
 * These mirror the backend ``chat_steps`` row shape exactly; the same shape
 * is delivered live via the ``chat_step`` WebSocket event and on rehydrate
 * via ``GET /api/chats/{id}/steps``. All textual fields arrive PHI-redacted
 * (FR-009b) — frontends MUST treat them as already-safe to render.
 */

export type ChatStepKind = "tool_call" | "agent_handoff" | "phase";

export type ChatStepStatus =
    | "in_progress"
    | "completed"
    | "errored"
    | "cancelled"
    | "interrupted";

/**
 * A single persistent step entry rendered between the user's message and
 * the eventual assistant reply.
 */
export interface ChatStep {
    id: string;
    chat_id: string;
    turn_message_id: number | null;
    kind: ChatStepKind;
    name: string;
    status: ChatStepStatus;
    /** PHI-redacted JSON-stringified args, ≤ 512 chars. NEVER raw PHI. */
    args_truncated: string | null;
    args_was_truncated: boolean;
    /** PHI-redacted result preview, ≤ 512 chars. NEVER raw PHI. */
    result_summary: string | null;
    result_was_truncated: boolean;
    /** Set only when ``status === "errored"``. PHI-redacted, ≤ 512 chars. */
    error_message: string | null;
    /** Epoch ms. */
    started_at: number;
    /** Epoch ms; ``null`` while ``status === "in_progress"``. */
    ended_at: number | null;
}

/**
 * Per-chat map of step id → step. Live-emitted events overwrite the entry
 * keyed by ``step.id``; the same map is populated by the rehydrate endpoint.
 */
export type ChatStepMap = Record<string, ChatStep>;

/** All chats' step maps, keyed by ``chat_id``. */
export type ChatStepsByChat = Record<string, ChatStepMap>;
