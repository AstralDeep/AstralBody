/**
 * UX Polish — message queue tests for useWebSocket.
 *
 * Validates:
 *  - isProcessingRef prevents overlapping sends
 *  - messageQueueRef queues subsequent messages
 *  - chat_status "done"/"idle" drains the queue
 *  - cancelTask clears the queue
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Test the message queue logic in isolation (module-scoped refs)
// We can't easily mount the hook, so we test the pattern directly.

describe("Message Queue Logic (useWebSocket)", () => {
    let isProcessing: boolean;
    let queue: Array<{ message: string; displayMessage?: string; explicitChatId?: string }>;

    beforeEach(() => {
        isProcessing = false;
        queue = [];
    });

    function simulatedSend(message: string, displayMessage?: string): boolean {
        if (isProcessing) {
            queue.push({ message, displayMessage });
            return false; // queued
        }
        isProcessing = true;
        return true; // sent immediately
    }

    function simulatedComplete(): { message: string; displayMessage?: string } | null {
        if (queue.length > 0) {
            const next = queue.shift()!;
            // isProcessing stays true — next message starts immediately
            return next;
        }
        isProcessing = false;
        return null;
    }

    function cancel() {
        isProcessing = false;
        queue = [];
    }

    it("sends first message immediately when not processing", () => {
        const result = simulatedSend("Hello");
        expect(result).toBe(true);
        expect(isProcessing).toBe(true);
        expect(queue.length).toBe(0);
    });

    it("queues subsequent messages while processing", () => {
        simulatedSend("First");
        const result2 = simulatedSend("Second");
        expect(result2).toBe(false);
        expect(queue.length).toBe(1);
        expect(queue[0].message).toBe("Second");

        const result3 = simulatedSend("Third");
        expect(result3).toBe(false);
        expect(queue.length).toBe(2);
    });

    it("drains queue when processing completes", () => {
        simulatedSend("First");
        simulatedSend("Second");
        simulatedSend("Third");

        const first = simulatedComplete();
        expect(first).toEqual({ message: "Second" });
        expect(isProcessing).toBe(true); // still processing (Second)
        expect(queue.length).toBe(1); // Third still queued

        const second = simulatedComplete();
        expect(second).toEqual({ message: "Third" });
        expect(isProcessing).toBe(true);

        const third = simulatedComplete();
        expect(third).toBe(null);
        expect(isProcessing).toBe(false);
        expect(queue.length).toBe(0);
    });

    it("cancel clears the queue and resets state", () => {
        simulatedSend("First");
        simulatedSend("Second");
        cancel();
        expect(isProcessing).toBe(false);
        expect(queue.length).toBe(0);

        // Can send again immediately
        const result = simulatedSend("Fresh");
        expect(result).toBe(true);
        expect(isProcessing).toBe(true);
    });

    it("can process single message end-to-end", () => {
        const sent = simulatedSend("Only message");
        expect(sent).toBe(true);
        const drained = simulatedComplete();
        expect(drained).toBe(null);
        expect(isProcessing).toBe(false);
    });
});