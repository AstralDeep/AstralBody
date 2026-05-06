/**
 * REST client for the persistent step trail
 * (feature 014-progress-notifications, T023).
 *
 * Used to rehydrate step entries on initial chat load and on WebSocket
 * reconnect, per ``contracts/chat_steps_rest.md``. The same shape arrives
 * live via the ``chat_step`` WebSocket event — consumers merge both feeds
 * into one ``ChatStepMap`` keyed by ``step.id``.
 */
import { API_URL } from "../config";
import type { ChatStep } from "../types/chatSteps";

function headers(token: string): HeadersInit {
    return {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
}

interface ChatStepsResponse {
    chat_id: string;
    steps: ChatStep[];
}

/**
 * Fetch the chronological sequence of persisted step entries for a chat.
 *
 * @param token Bearer JWT for the authenticated user.
 * @param chatId Owning chat identifier.
 * @returns Steps sorted by ``started_at`` ascending. Empty array for chats
 *          with no recorded steps.
 * @throws Error with the HTTP status code on any non-2xx response (callers
 *         can branch on the message text — 401/403/404/500 surface here).
 */
export async function fetchChatSteps(token: string, chatId: string): Promise<ChatStep[]> {
    const resp = await fetch(`${API_URL}/api/chats/${encodeURIComponent(chatId)}/steps`, {
        method: "GET",
        headers: headers(token),
    });
    if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText);
        throw new Error(`${resp.status} ${text}`);
    }
    const body = (await resp.json()) as ChatStepsResponse;
    return body.steps;
}
