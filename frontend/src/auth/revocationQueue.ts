/**
 * revocationQueue — offline-tolerant best-effort retry for OIDC
 * refresh-token revocations (FR-009b, FR-008).
 *
 * Design rationale (research.md §R-5):
 *
 *   - The queue is backed by **sessionStorage**, not localStorage,
 *     deliberately. If the user clears their browser data we want the
 *     queue to be gone — replaying a sign-out for a credential whose
 *     local trace is already erased is wasted work. sessionStorage is
 *     also origin-scoped, so cross-deployment isolation is free.
 *
 *   - The queue is **drained on the `online` event** (browser comes
 *     back from offline) **and on module init** (next launch after a
 *     failed drain). Each entry is attempted; successful entries (or
 *     definitive 4xx — token already invalid → goal achieved) are
 *     removed; transient failures (network/5xx) increment `attempts`
 *     and stay in the queue; entries with `attempts >= 5` are dropped.
 *
 *   - The queue is hard-capped at **16 entries** (FIFO eviction). The
 *     realistic case is "user signs out once while offline" — queue
 *     size 1. The cap exists to bound adversarial worst cases.
 *
 *   - The queue dispatches a `astralbody:revocation-queued-offline`
 *     window event when an enqueue happens while `navigator.onLine`
 *     is false, so the UI can show the "signed out locally, server
 *     confirmation pending" toast (FR-009b).
 */

/** sessionStorage key for the queue. */
export const QUEUE_KEY = "astralbody.revocationQueue.v1";
/** Custom-event fired when an entry is enqueued while offline. */
export const REVOCATION_QUEUED_OFFLINE_EVENT = "astralbody:revocation-queued-offline";
/** Maximum entries held in the queue (FIFO eviction beyond this). */
export const MAX_QUEUE_LENGTH = 16;
/** Maximum retry attempts per entry before it is dropped. */
export const MAX_ATTEMPTS_PER_ENTRY = 5;

/** Shape of a queued revocation entry. */
export interface RevocationEntry {
    refresh_token: string;
    authority: string;
    client_id: string;
    queued_at: string;
    attempts: number;
}

/** Read the queue from sessionStorage, returning [] on any error. */
function readQueue(): RevocationEntry[] {
    if (typeof window === "undefined" || !window.sessionStorage) return [];
    const raw = window.sessionStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    try {
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed.filter(
            (e): e is RevocationEntry =>
                e &&
                typeof e === "object" &&
                typeof e.refresh_token === "string" &&
                typeof e.authority === "string" &&
                typeof e.client_id === "string" &&
                typeof e.queued_at === "string" &&
                typeof e.attempts === "number",
        );
    } catch {
        return [];
    }
}

/** Persist the queue back to sessionStorage. */
function writeQueue(q: RevocationEntry[]): void {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    try {
        window.sessionStorage.setItem(QUEUE_KEY, JSON.stringify(q));
    } catch {
        // Quota exceeded etc. — drop silently. A failed revocation
        // queue is a small audit gap, not a functional regression.
    }
}

/**
 * Issue a single revocation request against the Keycloak `revoke`
 * endpoint. Public so tests can stub it.
 *
 * @returns one of:
 *   - "success" — server confirmed revocation (2xx)
 *   - "definitive" — server rejected as already-invalid (4xx) — drop
 *   - "transient" — network/5xx — retry later
 */
export async function attemptRevoke(entry: RevocationEntry): Promise<"success" | "definitive" | "transient"> {
    if (typeof fetch === "undefined") return "transient";
    const url = `${entry.authority}/protocol/openid-connect/revoke`;
    let resp: Response;
    try {
        resp = await fetch(url, {
            method: "POST",
            headers: { "content-type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
                token: entry.refresh_token,
                token_type_hint: "refresh_token",
                client_id: entry.client_id,
            }).toString(),
            // keepalive lets a revocation initiated by signOut survive
            // the subsequent redirect navigation.
            keepalive: true,
        });
    } catch {
        return "transient";
    }
    if (resp.ok) return "success";
    // 400/401 from /revoke means the token is already invalid — the
    // goal of the revocation has been achieved, drop the entry.
    if (resp.status >= 400 && resp.status < 500) return "definitive";
    return "transient";
}

/** Public surface of the revocation queue module. */
export interface RevocationQueueApi {
    /**
     * Enqueue a revocation attempt. Inserts at the tail; if doing so
     * would exceed {@link MAX_QUEUE_LENGTH}, drops the oldest entry.
     * If `navigator.onLine` is false at enqueue time, fires the
     * `astralbody:revocation-queued-offline` window event so the UI
     * can show the "signed out locally, server confirmation pending"
     * toast.
     */
    enqueue(entry: RevocationEntry): void;
    /**
     * Drain the queue. For each entry, calls `attemptRevoke()`;
     * success/definitive removes the entry; transient increments
     * `attempts`; entries that hit {@link MAX_ATTEMPTS_PER_ENTRY} are
     * dropped with a console warning.
     */
    drain(): Promise<void>;
    /** Inspect current queue length (for tests + observability). */
    size(): number;
    /** Clear the queue entirely. Tests use this; production should not. */
    _resetForTests(): void;
}

const isOffline = (): boolean => {
    if (typeof navigator === "undefined") return false;
    // navigator.onLine is unreliable in some Flutter WebView versions —
    // treat undefined as "online" so we don't queue forever in tests.
    return typeof navigator.onLine === "boolean" ? !navigator.onLine : false;
};

let draining = false;

/** Singleton revocation queue (browser-global). */
export const revocationQueue: RevocationQueueApi = {
    enqueue(entry: RevocationEntry): void {
        const q = readQueue();
        q.push(entry);
        while (q.length > MAX_QUEUE_LENGTH) q.shift();
        writeQueue(q);
        if (typeof window !== "undefined" && isOffline()) {
            try {
                window.dispatchEvent(new CustomEvent(REVOCATION_QUEUED_OFFLINE_EVENT));
            } catch {
                /* defensive */
            }
        }
    },

    async drain(): Promise<void> {
        if (draining) return;
        draining = true;
        try {
            const q = readQueue();
            if (q.length === 0) return;
            const remaining: RevocationEntry[] = [];
            for (const entry of q) {
                const result = await attemptRevoke(entry);
                if (result === "success" || result === "definitive") {
                    // Drop the entry.
                    continue;
                }
                const updated: RevocationEntry = {
                    ...entry,
                    attempts: entry.attempts + 1,
                };
                if (updated.attempts >= MAX_ATTEMPTS_PER_ENTRY) {
                    // eslint-disable-next-line no-console
                    console.warn(
                        `[revocationQueue] dropping entry after ${updated.attempts} attempts ` +
                        `(authority=${updated.authority}, queued_at=${updated.queued_at})`,
                    );
                    continue;
                }
                remaining.push(updated);
            }
            writeQueue(remaining);
        } finally {
            draining = false;
        }
    },

    size(): number {
        return readQueue().length;
    },

    _resetForTests(): void {
        if (typeof window === "undefined" || !window.sessionStorage) return;
        try {
            window.sessionStorage.removeItem(QUEUE_KEY);
        } catch {
            /* ignore */
        }
    },
};

/**
 * Module-init hook: attach an `online` listener that drains the
 * queue, and kick off one drain immediately. Idempotent — safe to
 * import the module multiple times.
 *
 * Disabled in non-browser environments (tests, SSR).
 */
let initialized = false;
export function initRevocationQueue(): void {
    if (initialized || typeof window === "undefined") return;
    initialized = true;
    window.addEventListener("online", () => {
        void revocationQueue.drain();
    });
    // Kick off an initial drain; do not await — the caller (main.tsx)
    // does not want to block app start.
    void revocationQueue.drain();
}
