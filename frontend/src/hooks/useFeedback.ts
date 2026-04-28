/**
 * useFeedback — submit / retract / amend hook for component feedback.
 *
 * Tries the WebSocket path first (lower latency, integrates with the
 * server-side ack / quarantine envelope), falls back to REST when the
 * socket is unavailable per FR-005.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
    amendMyFeedback,
    retractMyFeedback,
    submitFeedback,
} from "../api/feedback";
import type {
    Category,
    FeedbackAmendRequest,
    FeedbackError,
    FeedbackErrorCode,
    FeedbackSubmitAck,
    FeedbackSubmitRequest,
    Sentiment,
} from "../types/feedback";

export interface UseFeedbackOptions {
    /** Bearer JWT — required for REST fallback. */
    token: string | null;
    /** Optional WebSocket; when present, submit prefers this path. */
    ws?: WebSocket | null;
}

export interface FeedbackToast {
    kind: "success" | "quarantined" | "error";
    message: string;
}

export interface UseFeedbackResult {
    submit: (req: FeedbackSubmitRequest) => Promise<FeedbackSubmitAck>;
    retract: (id: string) => Promise<void>;
    amend: (id: string, body: FeedbackAmendRequest) => Promise<void>;
    toast: FeedbackToast | null;
    clearToast: () => void;
}

const ACK_ACTIONS = new Set([
    "component_feedback_ack",
    "feedback_retract_ack",
    "feedback_amend_ack",
    "component_feedback_error",
]);

interface PendingResolver {
    kind: "submit" | "retract" | "amend";
    resolve: (value: any) => void;
    reject: (err: FeedbackError) => void;
}

export function useFeedback({ token, ws }: UseFeedbackOptions): UseFeedbackResult {
    const [toast, setToast] = useState<FeedbackToast | null>(null);
    const pendingRef = useRef<PendingResolver | null>(null);

    // Listen for server ack / error envelopes on the shared WS.
    useEffect(() => {
        if (!ws) return;
        const onMessage = (ev: MessageEvent) => {
            let msg: any;
            try {
                msg = JSON.parse(ev.data);
            } catch {
                return;
            }
            if (msg?.type !== "ui_event" || !ACK_ACTIONS.has(msg.action)) return;
            const pending = pendingRef.current;
            if (!pending) return;
            pendingRef.current = null;

            if (msg.action === "component_feedback_error") {
                const err: FeedbackError = {
                    code: (msg.payload?.code ?? "INVALID_INPUT") as FeedbackErrorCode,
                    message: msg.payload?.message ?? "feedback failed",
                };
                pending.reject(err);
                return;
            }
            if (msg.action === "component_feedback_ack" && pending.kind === "submit") {
                pending.resolve({
                    feedback_id: msg.payload.feedback_id,
                    status: msg.payload.status,
                    deduped: !!msg.payload.deduped,
                });
                return;
            }
            if (msg.action === "feedback_retract_ack" && pending.kind === "retract") {
                pending.resolve(msg.payload);
                return;
            }
            if (msg.action === "feedback_amend_ack" && pending.kind === "amend") {
                pending.resolve(msg.payload);
                return;
            }
        };
        ws.addEventListener("message", onMessage);
        return () => ws.removeEventListener("message", onMessage);
    }, [ws]);

    const submit = useCallback(async (req: FeedbackSubmitRequest): Promise<FeedbackSubmitAck> => {
        // Prefer WS path when open, fall back to REST otherwise (FR-005).
        if (ws && ws.readyState === WebSocket.OPEN) {
            const ack = await new Promise<FeedbackSubmitAck>((resolve, reject) => {
                pendingRef.current = { kind: "submit", resolve, reject };
                ws.send(JSON.stringify({
                    type: "ui_event",
                    action: "component_feedback",
                    payload: req,
                }));
            }).catch((err: FeedbackError) => {
                throw err;
            });
            announceToast(setToast, ack);
            window.dispatchEvent(new CustomEvent("feedback:ack", { detail: ack }));
            return ack;
        }
        if (!token) throw new Error("not authenticated");
        const ack = await submitFeedback(token, req);
        announceToast(setToast, ack);
        window.dispatchEvent(new CustomEvent("feedback:ack", { detail: ack }));
        return ack;
    }, [ws, token]);

    const retract = useCallback(async (id: string): Promise<void> => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            await new Promise<void>((resolve, reject) => {
                pendingRef.current = { kind: "retract", resolve: () => resolve(), reject };
                ws.send(JSON.stringify({
                    type: "ui_event",
                    action: "feedback_retract",
                    payload: { feedback_id: id },
                }));
            });
            setToast({ kind: "success", message: "Feedback retracted." });
            window.dispatchEvent(new CustomEvent("feedback:retract", { detail: { id } }));
            return;
        }
        if (!token) throw new Error("not authenticated");
        await retractMyFeedback(token, id);
        setToast({ kind: "success", message: "Feedback retracted." });
        window.dispatchEvent(new CustomEvent("feedback:retract", { detail: { id } }));
    }, [ws, token]);

    const amend = useCallback(async (id: string, body: FeedbackAmendRequest): Promise<void> => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            await new Promise<void>((resolve, reject) => {
                pendingRef.current = { kind: "amend", resolve: () => resolve(), reject };
                ws.send(JSON.stringify({
                    type: "ui_event",
                    action: "feedback_amend",
                    payload: { feedback_id: id, ...body },
                }));
            });
            setToast({ kind: "success", message: "Feedback updated." });
            window.dispatchEvent(new CustomEvent("feedback:amend", { detail: { id } }));
            return;
        }
        if (!token) throw new Error("not authenticated");
        await amendMyFeedback(token, id, body);
        setToast({ kind: "success", message: "Feedback updated." });
        window.dispatchEvent(new CustomEvent("feedback:amend", { detail: { id } }));
    }, [ws, token]);

    return {
        submit,
        retract,
        amend,
        toast,
        clearToast: useCallback(() => setToast(null), []),
    };
}

function announceToast(
    setToast: (t: FeedbackToast | null) => void,
    ack: FeedbackSubmitAck,
): void {
    if (ack.status === "quarantined") {
        setToast({
            kind: "quarantined",
            message: "Thanks — your comment is held for review.",
        });
    } else {
        setToast({ kind: "success", message: "Feedback recorded." });
    }
}

// Re-export types for convenience.
export type { Category, FeedbackError, Sentiment };
