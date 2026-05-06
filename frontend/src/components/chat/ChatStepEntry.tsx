/**
 * Inline step indicator rendered between user messages and the assistant
 * reply (feature 014-progress-notifications, US2).
 *
 * Per the user's simplification: each persisted step renders as a single
 * line — `Calling '<tool-name>'` — in chronological order. No status badges,
 * no expand/collapse, no args/result display. Tool inputs and outputs live
 * in the audit log; the chat surface only signals **what** was called.
 */
import type { ChatStep } from "../../types/chatSteps";

interface ChatStepEntryProps {
    step: ChatStep;
}

export function ChatStepEntry({ step }: ChatStepEntryProps) {
    return (
        <div
            data-testid="chat-step-entry"
            data-step-id={step.id}
            data-status={step.status}
            className="text-xs text-astral-muted"
        >
            <span data-testid="chat-step-line">
                Calling '{step.name}'
            </span>
        </div>
    );
}
