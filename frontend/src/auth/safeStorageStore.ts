/**
 * SafeWebStorageStateStore — a `StateStore` implementation for
 * `oidc-client-ts` that wraps a browser `Storage` (typically
 * `window.localStorage`) and degrades gracefully when the underlying
 * store rejects a write.
 *
 * Why it exists:
 *   - Feature 016 FR-006 requires that, when the protected store
 *     rejects the credential write at login time (quota exceeded,
 *     security error in private browsing, sandbox failure on Flutter
 *     WebView under certain configurations), the login MUST NOT be
 *     blocked. The user proceeds into the dashboard for the current
 *     session and a dismissible warning informs them that persistence
 *     is disabled.
 *   - The stock `WebStorageStateStore` from `oidc-client-ts` lets the
 *     write error propagate, which would abort the OIDC sign-in
 *     callback. This wrapper swallows write errors, emits a console
 *     warning, and fires a `astralbody:persistence-disabled` window
 *     event so the UI layer (App.tsx) can raise a sonner toast.
 *
 * Implementation note:
 *   - We deliberately do NOT silently fall back to a less-protected
 *     store (cookies, sessionStorage, in-memory). Spec FR-006 forbids
 *     that. The session works in memory only (held by oidc-client-ts's
 *     UserManager) until the user reloads.
 */

import type { StateStore } from "oidc-client-ts";

/**
 * Custom-event detail dispatched on `window` when a persisted write
 * fails. UI subscribers receive this once-per-session signal and
 * surface a non-blocking warning to the user.
 */
export interface PersistenceDisabledDetail {
    /** The localStorage key that the write was attempting to set. */
    key: string;
    /** Brief, user-safe reason string (no PII, no token material). */
    reason: string;
}

/** Name of the event dispatched on `window` when a write fails. */
export const PERSISTENCE_DISABLED_EVENT = "astralbody:persistence-disabled";

/**
 * Construct options. `store` is typically `window.localStorage`. In
 * tests, pass an in-memory shim that implements the `Storage` shape.
 */
export interface SafeWebStorageStateStoreOptions {
    /** The underlying `Storage` to wrap. */
    store: Storage;
    /**
     * Optional key prefix. `oidc-client-ts`'s default
     * `WebStorageStateStore` uses `"oidc."`; we preserve that default
     * so on-disk keys are identical (no migration on the rename).
     */
    prefix?: string;
}

/**
 * Drop-in `StateStore` replacement with soft-failing writes (FR-006).
 *
 * Only `set()` swallows errors — `get`, `remove`, and `getAllKeys`
 * propagate any underlying error so the OIDC library can surface
 * actual read failures (which would indicate something far more
 * serious than a quota miss).
 */
export class SafeWebStorageStateStore implements StateStore {
    private readonly store: Storage;
    private readonly prefix: string;
    /** True after the first dispatch of {@link PERSISTENCE_DISABLED_EVENT}; used to suppress duplicate toasts. */
    private warningEmitted = false;

    /**
     * @param opts - See {@link SafeWebStorageStateStoreOptions}.
     */
    constructor(opts: SafeWebStorageStateStoreOptions) {
        this.store = opts.store;
        this.prefix = opts.prefix ?? "oidc.";
    }

    /**
     * Write a value. Errors from the underlying store (quota,
     * security, sandbox) are swallowed and reported via the
     * `astralbody:persistence-disabled` window event. Resolves
     * successfully in either case so the OIDC callback does not abort.
     */
    async set(key: string, value: string): Promise<void> {
        const fullKey = this.prefix + key;
        try {
            this.store.setItem(fullKey, value);
        } catch (err) {
            const reason = err instanceof DOMException ? err.name : "unknown";
            // eslint-disable-next-line no-console
            console.warn(
                `[persistent-login] localStorage.setItem rejected for key=${fullKey}; ` +
                `persistence disabled for this session. Reason: ${reason}`,
            );
            if (!this.warningEmitted && typeof window !== "undefined") {
                this.warningEmitted = true;
                try {
                    window.dispatchEvent(
                        new CustomEvent<PersistenceDisabledDetail>(
                            PERSISTENCE_DISABLED_EVENT,
                            { detail: { key: fullKey, reason } },
                        ),
                    );
                } catch {
                    // Defensive: even event dispatch can throw in
                    // exotic sandbox conditions. Ignore.
                }
            }
        }
    }

    /**
     * Read a value. Errors propagate to the caller.
     */
    async get(key: string): Promise<string | null> {
        return this.store.getItem(this.prefix + key);
    }

    /**
     * Remove a key and return the value it held (or null if absent).
     * Errors propagate to the caller.
     */
    async remove(key: string): Promise<string | null> {
        const fullKey = this.prefix + key;
        const item = this.store.getItem(fullKey);
        this.store.removeItem(fullKey);
        return item;
    }

    /**
     * Return all keys (prefix-stripped) the store currently holds for
     * this OIDC instance.
     */
    async getAllKeys(): Promise<string[]> {
        const keys: string[] = [];
        for (let i = 0; i < this.store.length; i++) {
            const k = this.store.key(i);
            if (k && k.startsWith(this.prefix)) {
                keys.push(k.substring(this.prefix.length));
            }
        }
        return keys;
    }
}
