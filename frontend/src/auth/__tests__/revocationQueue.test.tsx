/**
 * Unit tests for revocationQueue.ts (Feature 016 T012).
 *
 * Covers:
 *   - Enqueue and FIFO eviction at 16-entry cap
 *   - Drain calls the Keycloak revoke endpoint per entry
 *   - 4xx response = definitive: entry dropped (goal achieved)
 *   - 5xx / network error = transient: attempts incremented, entry kept
 *   - 5 failed attempts: entry dropped with console warning
 *   - sessionStorage backing: queue cleared on tab close (semantics)
 *   - astralbody:revocation-queued-offline event fires when offline
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
    revocationQueue,
    MAX_QUEUE_LENGTH,
    MAX_ATTEMPTS_PER_ENTRY,
    QUEUE_KEY,
    REVOCATION_QUEUED_OFFLINE_EVENT,
    attemptRevoke,
    type RevocationEntry,
} from "../revocationQueue";

const baseEntry = (i: number): RevocationEntry => ({
    refresh_token: `rt-${i}`,
    authority: "https://kc.example",
    client_id: "astral-frontend",
    queued_at: new Date(2026, 0, 1, 0, 0, i).toISOString(),
    attempts: 0,
});

beforeEach(() => {
    window.sessionStorage.clear();
    revocationQueue._resetForTests();
    vi.restoreAllMocks();
    // Default navigator.onLine = true in jsdom.
    Object.defineProperty(navigator, "onLine", {
        value: true,
        writable: true,
        configurable: true,
    });
});

// ---------------------------------------------------------------------------
// Enqueue / FIFO cap
// ---------------------------------------------------------------------------

describe("revocationQueue.enqueue", () => {
    it("appends entries and size() reflects them", () => {
        revocationQueue.enqueue(baseEntry(1));
        revocationQueue.enqueue(baseEntry(2));
        expect(revocationQueue.size()).toBe(2);
    });

    it("evicts oldest when MAX_QUEUE_LENGTH is exceeded (FIFO)", () => {
        for (let i = 0; i < MAX_QUEUE_LENGTH + 3; i++) {
            revocationQueue.enqueue(baseEntry(i));
        }
        expect(revocationQueue.size()).toBe(MAX_QUEUE_LENGTH);
        // The oldest three (indices 0, 1, 2) must have been dropped.
        const stored = JSON.parse(
            window.sessionStorage.getItem(QUEUE_KEY)!,
        ) as RevocationEntry[];
        expect(stored[0].refresh_token).toBe("rt-3");
        expect(stored[stored.length - 1].refresh_token).toBe(
            `rt-${MAX_QUEUE_LENGTH + 2}`,
        );
    });

    it("fires astralbody:revocation-queued-offline when navigator.onLine === false", () => {
        Object.defineProperty(navigator, "onLine", {
            value: false,
            writable: true,
            configurable: true,
        });
        const listener = vi.fn();
        window.addEventListener(REVOCATION_QUEUED_OFFLINE_EVENT, listener);
        try {
            revocationQueue.enqueue(baseEntry(1));
        } finally {
            window.removeEventListener(REVOCATION_QUEUED_OFFLINE_EVENT, listener);
        }
        expect(listener).toHaveBeenCalledTimes(1);
    });

    it("does NOT fire the offline event when navigator.onLine === true", () => {
        const listener = vi.fn();
        window.addEventListener(REVOCATION_QUEUED_OFFLINE_EVENT, listener);
        try {
            revocationQueue.enqueue(baseEntry(1));
        } finally {
            window.removeEventListener(REVOCATION_QUEUED_OFFLINE_EVENT, listener);
        }
        expect(listener).not.toHaveBeenCalled();
    });
});

// ---------------------------------------------------------------------------
// Drain
// ---------------------------------------------------------------------------

describe("revocationQueue.drain", () => {
    it("calls /protocol/openid-connect/revoke for each entry", async () => {
        const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
        (window as unknown as { fetch: typeof fetch }).fetch = fetchMock;

        revocationQueue.enqueue(baseEntry(1));
        revocationQueue.enqueue(baseEntry(2));
        await revocationQueue.drain();
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(fetchMock.mock.calls[0][0]).toBe(
            "https://kc.example/protocol/openid-connect/revoke",
        );
        // Queue should be empty after success
        expect(revocationQueue.size()).toBe(0);
    });

    it("drops entries on 4xx (definitive — goal achieved)", async () => {
        (window as unknown as { fetch: typeof fetch }).fetch = vi
            .fn()
            .mockResolvedValue(new Response(null, { status: 400 }));
        revocationQueue.enqueue(baseEntry(1));
        await revocationQueue.drain();
        expect(revocationQueue.size()).toBe(0);
    });

    it("keeps and increments attempts on 5xx (transient)", async () => {
        (window as unknown as { fetch: typeof fetch }).fetch = vi
            .fn()
            .mockResolvedValue(new Response(null, { status: 503 }));
        revocationQueue.enqueue(baseEntry(1));
        await revocationQueue.drain();
        expect(revocationQueue.size()).toBe(1);
        const stored = JSON.parse(window.sessionStorage.getItem(QUEUE_KEY)!) as RevocationEntry[];
        expect(stored[0].attempts).toBe(1);
    });

    it("keeps and increments attempts on network error", async () => {
        (window as unknown as { fetch: typeof fetch }).fetch = vi
            .fn()
            .mockRejectedValue(new Error("ECONNREFUSED"));
        revocationQueue.enqueue(baseEntry(1));
        await revocationQueue.drain();
        expect(revocationQueue.size()).toBe(1);
        const stored = JSON.parse(window.sessionStorage.getItem(QUEUE_KEY)!) as RevocationEntry[];
        expect(stored[0].attempts).toBe(1);
    });

    it("drops entries after MAX_ATTEMPTS_PER_ENTRY failures", async () => {
        const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
        try {
            (window as unknown as { fetch: typeof fetch }).fetch = vi
                .fn()
                .mockResolvedValue(new Response(null, { status: 503 }));
            // Plant an entry already at attempts = MAX-1 so the next failed
            // attempt pushes it over the cap.
            const entry: RevocationEntry = {
                ...baseEntry(1),
                attempts: MAX_ATTEMPTS_PER_ENTRY - 1,
            };
            window.sessionStorage.setItem(QUEUE_KEY, JSON.stringify([entry]));
            await revocationQueue.drain();
            expect(revocationQueue.size()).toBe(0);
            expect(warn).toHaveBeenCalled();
        } finally {
            warn.mockRestore();
        }
    });
});

// ---------------------------------------------------------------------------
// attemptRevoke direct test (already covered via drain, but pin the
// HTTP shape so a refactor doesn't accidentally hit the wrong endpoint).
// ---------------------------------------------------------------------------

describe("attemptRevoke", () => {
    it("POSTs form-encoded body with token + token_type_hint + client_id", async () => {
        const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
        (window as unknown as { fetch: typeof fetch }).fetch = fetchMock;
        await attemptRevoke(baseEntry(1));
        const [, init] = fetchMock.mock.calls[0];
        expect(init.method).toBe("POST");
        expect(init.headers["content-type"]).toBe("application/x-www-form-urlencoded");
        const body = String(init.body);
        expect(body).toContain("token=rt-1");
        expect(body).toContain("token_type_hint=refresh_token");
        expect(body).toContain("client_id=astral-frontend");
    });
});
