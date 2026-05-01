/**
 * backgroundFetchCache — module-scoped session cache for background data
 * fetches issued from globally mounted UI regions.
 *
 * Feature 010-fix-page-flash. Implements FR-004 / FR-008 / FR-010 from
 * `specs/010-fix-page-flash/spec.md`: every in-scope background endpoint
 * is fetched at most once per browser session per cache key, with refresh
 * occurring only on explicit user action (manual refresh button, opening
 * a consuming view, etc.).
 *
 * Why this exists: prior to this fix, hooks mounted in the layout shell
 * (e.g., `useFlaggedToolsCount`, `useOnboardingState`) re-fired their
 * fetch on every silent OIDC token refresh because their `useEffect`
 * dep arrays included the access token. The state updates that followed
 * propagated through React Context and re-rendered the entire app
 * subtree, producing visible screen flashes. Routing those fetches
 * through this cache means a new token identity does NOT produce a new
 * request, and concurrent calls share a single in-flight promise.
 *
 * Lifecycle: entries live for the lifetime of the browser tab. There is
 * no time-based eviction. Eviction is by:
 *   - explicit `invalidate(key)` (e.g., when a panel that mutates the
 *     underlying data closes), or
 *   - tab close.
 *
 * Excluded by design (FR-011): backend-pushed Server-Driven UI streams.
 * Do NOT route the SDUI websocket / SSE through this cache; SDUI streams
 * must keep flowing in real time.
 */

const entries = new Map<string, Promise<unknown>>();

export interface GetOrFetchOptions {
    /**
     * If true, bypass any existing cached promise for this key, invoke
     * `fetcher`, and store the new in-flight promise. Use sparingly, and
     * only in response to an explicit user action that demands fresh
     * data (e.g., the user clicked a "Refresh" button).
     */
    refresh?: boolean;
}

/**
 * Returns the cached promise for `key` if one exists; otherwise calls
 * `fetcher`, stores the resulting promise under `key`, and returns it.
 *
 * Concurrent callers with the same `key` share the same promise. If the
 * fetcher rejects, the entry is evicted automatically so the next call
 * retries — failed responses are NOT cached.
 *
 * Example:
 * ```ts
 * const r = await backgroundFetchCache.getOrFetch(
 *     "admin-feedback-flagged?limit=100",
 *     () => listFlaggedTools(token, { limit: 100 }),
 * );
 * ```
 */
function getOrFetch<T>(
    key: string,
    fetcher: () => Promise<T>,
    opts?: GetOrFetchOptions,
): Promise<T> {
    if (!opts?.refresh) {
        const existing = entries.get(key);
        if (existing !== undefined) {
            return existing as Promise<T>;
        }
    }
    const p = fetcher();
    entries.set(key, p);
    // Evict on failure so a transient error doesn't poison the cache for
    // the rest of the session. Use `then`-with-rejection-handler so we
    // don't accidentally swallow the rejection — the original `p` is
    // what we return; the cleanup chain runs as a side branch.
    p.then(
        () => undefined,
        () => {
            if (entries.get(key) === p) entries.delete(key);
        },
    );
    return p;
}

/**
 * Remove the cached entry for `key` (if any). The next `getOrFetch(key, ...)`
 * call will invoke the fetcher again. Use this when an action mutates
 * the underlying data and a re-fetch is appropriate on next read.
 */
function invalidate(key: string): void {
    entries.delete(key);
}

/**
 * Test-only: clear all entries. Production code MUST NOT call this.
 */
function _resetForTests(): void {
    entries.clear();
}

export const backgroundFetchCache = {
    getOrFetch,
    invalidate,
    _resetForTests,
};
