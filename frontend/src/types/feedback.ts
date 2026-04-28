// Feature 004 — TypeScript types for the component feedback & tool
// auto-improvement loop. Wire shapes match the backend DTOs in
// backend/feedback/schemas.py and the contracts in
// specs/004-component-feedback-loop/contracts/.

export type Sentiment = 'positive' | 'negative';

export type Category =
  | 'wrong-data'
  | 'irrelevant'
  | 'layout-broken'
  | 'too-slow'
  | 'other'
  | 'unspecified';

export const CATEGORIES: Category[] = [
  'wrong-data',
  'irrelevant',
  'layout-broken',
  'too-slow',
  'other',
  'unspecified',
];

export type CommentSafety = 'clean' | 'quarantined';

export type Lifecycle = 'active' | 'superseded' | 'retracted';

export type QualityStatus = 'healthy' | 'insufficient-data' | 'underperforming';

export type ProposalStatus =
  | 'pending'
  | 'accepted'
  | 'applied'
  | 'rejected'
  | 'superseded';

export type QuarantineDetector = 'inline' | 'loop_pre_pass';

export type QuarantineStatus = 'held' | 'released' | 'dismissed';

export type FeedbackErrorCode =
  | 'INVALID_INPUT'
  | 'NOT_FOUND'
  | 'EDIT_WINDOW_EXPIRED'
  | 'STALE_PROPOSAL'
  | 'INVALID_PATH'
  | 'UNAUTHENTICATED';

// ---- Submit / list shapes ----

export interface FeedbackSubmitRequest {
  correlation_id?: string | null;
  component_id?: string | null;
  source_agent?: string | null;
  source_tool?: string | null;
  sentiment: Sentiment;
  category?: Category;
  comment?: string | null;
}

export interface FeedbackSubmitAck {
  feedback_id: string;
  status: 'recorded' | 'quarantined';
  deduped: boolean;
}

export interface FeedbackError {
  code: FeedbackErrorCode;
  message: string;
}

export interface FeedbackAmendRequest {
  sentiment?: Sentiment;
  category?: Category;
  comment?: string | null;
}

export interface ComponentFeedback {
  id: string;
  conversation_id: string | null;
  correlation_id: string | null;
  source_agent: string | null;
  source_tool: string | null;
  component_id: string | null;
  sentiment: Sentiment;
  category: Category;
  comment: string | null;
  comment_safety: CommentSafety;
  lifecycle: Lifecycle;
  created_at: string;
  updated_at: string;
}

export interface ListFeedbackResponse {
  items: ComponentFeedback[];
  next_cursor: string | null;
}

// ---- Admin shapes ----

export interface FlaggedTool {
  agent_id: string;
  tool_name: string;
  window_start: string;
  window_end: string;
  dispatch_count: number;
  failure_count: number;
  negative_feedback_count: number;
  failure_rate: number;
  negative_feedback_rate: number;
  category_breakdown: Record<Category, number>;
  flagged_at: string;
  pending_proposal_id: string | null;
}

export interface FlaggedToolsResponse {
  items: FlaggedTool[];
  next_cursor: string | null;
}

export interface FlaggedToolEvidence {
  agent_id: string;
  tool_name: string;
  window_start: string;
  window_end: string;
  audit_event_ids: string[];
  component_feedback_ids: string[];
  category_breakdown: Record<Category, number>;
}

export interface ProposalSummary {
  id: string;
  agent_id: string;
  tool_name: string;
  artifact_path: string;
  status: ProposalStatus;
  generated_at: string;
  reviewer_user_id: string | null;
  reviewed_at: string | null;
  evidence_summary: { audit_events: number; component_feedback: number };
}

export interface ProposalsResponse {
  items: ProposalSummary[];
  next_cursor: string | null;
}

export interface ProposalDetail {
  id: string;
  agent_id: string;
  tool_name: string;
  artifact_path: string;
  diff_payload: string;
  artifact_sha_at_gen: string;
  current_artifact_sha: string;
  is_current: boolean;
  evidence: {
    audit_event_ids: string[];
    component_feedback_ids: string[];
    window_start: string;
    window_end: string;
  };
  status: ProposalStatus;
  reviewer_user_id: string | null;
  reviewed_at: string | null;
  reviewer_rationale: string | null;
  applied_at: string | null;
  generated_at: string;
}

export interface AcceptProposalRequest {
  edited_diff?: string | null;
}

export interface RejectProposalRequest {
  rationale: string;
}

export interface QuarantineEntry {
  feedback_id: string;
  user_id: string;
  source_agent: string | null;
  source_tool: string | null;
  comment_raw: string | null;
  reason: string;
  detector: QuarantineDetector;
  detected_at: string;
  status: QuarantineStatus;
}

export interface QuarantineListResponse {
  items: QuarantineEntry[];
  next_cursor: string | null;
}

// ---- Component metadata extension on UIRender items ----

/** Optional metadata key the orchestrator stamps on each rendered
 *  component dict when it originated from a tool dispatch. Frontend
 *  consumers (specifically FeedbackControl) read this to scope a user's
 *  feedback submission to the originating dispatch.
 */
export const SOURCE_CORRELATION_ID_KEY = '_source_correlation_id' as const;
