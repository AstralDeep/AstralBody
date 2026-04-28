/**
 * Shared types for the onboarding subsystem (feature 005).
 *
 * Mirror the public DTOs in `backend/onboarding/schemas.py` and the
 * contracts under `specs/005-tooltips-tutorial/contracts/`.
 */

export type OnboardingStatus =
    | "not_started"
    | "in_progress"
    | "completed"
    | "skipped";

export interface OnboardingState {
    status: OnboardingStatus;
    last_step_id: number | null;
    last_step_slug: string | null;
    started_at: string | null;
    completed_at: string | null;
    skipped_at: string | null;
}

export type StepAudience = "user" | "admin";
export type TargetKind = "static" | "sdui" | "none";

/**
 * Tutorial step shape returned by `GET /api/tutorial/steps` (user view).
 * The admin view also surfaces `archived_at` and `updated_at`; the user
 * view strips those.
 */
export interface TutorialStep {
    id: number;
    slug: string;
    audience: StepAudience;
    display_order: number;
    target_kind: TargetKind;
    target_key: string | null;
    title: string;
    body: string;
}

/**
 * Tutorial step shape returned by the admin endpoints — adds the
 * fields the user view hides. Used by `TutorialAdminPanel` only.
 */
export interface AdminTutorialStep extends TutorialStep {
    archived_at: string | null;
    updated_at: string | null;
}

export interface TutorialStepRevision {
    id: number;
    step_id: number;
    editor_user_id: string;
    edited_at: string;
    change_kind: "create" | "update" | "archive" | "restore";
    previous: Record<string, unknown> | null;
    current: Record<string, unknown>;
}
