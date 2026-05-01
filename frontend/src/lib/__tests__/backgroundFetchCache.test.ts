/**
 * Tests for backgroundFetchCache (feature 010-fix-page-flash).
 *
 * Pins the dedup contract that hooks mounted in globally rendered
 * regions rely on: a given key is fetched at most once per session,
 * concurrent callers share a single in-flight promise, failed
 * responses are not cached, and explicit refresh bypasses the cache.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backgroundFetchCache } from "../backgroundFetchCache";

beforeEach(() => {
    backgroundFetchCache._resetForTests();
});

afterEach(() => {
    backgroundFetchCache._resetForTests();
    vi.restoreAllMocks();
});

describe("backgroundFetchCache.getOrFetch", () => {
    it("invokes the fetcher exactly once for a single key across concurrent callers", async () => {
        const fetcher = vi.fn().mockResolvedValue({ count: 7 });
        const a = backgroundFetchCache.getOrFetch("k", fetcher);
        const b = backgroundFetchCache.getOrFetch("k", fetcher);
        const c = backgroundFetchCache.getOrFetch("k", fetcher);
        const [ra, rb, rc] = await Promise.all([a, b, c]);
        expect(fetcher).toHaveBeenCalledTimes(1);
        expect(ra).toEqual({ count: 7 });
        expect(rb).toEqual({ count: 7 });
        expect(rc).toEqual({ count: 7 });
    });

    it("returns the cached value on subsequent calls without re-invoking the fetcher", async () => {
        const fetcher = vi.fn().mockResolvedValue("hello");
        const first = await backgroundFetchCache.getOrFetch("k", fetcher);
        const second = await backgroundFetchCache.getOrFetch("k", fetcher);
        const third = await backgroundFetchCache.getOrFetch("k", fetcher);
        expect(fetcher).toHaveBeenCalledTimes(1);
        expect(first).toBe("hello");
        expect(second).toBe("hello");
        expect(third).toBe("hello");
    });

    it("isolates cache entries by key", async () => {
        const fetcherA = vi.fn().mockResolvedValue("A");
        const fetcherB = vi.fn().mockResolvedValue("B");
        const ra = await backgroundFetchCache.getOrFetch("a", fetcherA);
        const rb = await backgroundFetchCache.getOrFetch("b", fetcherB);
        expect(ra).toBe("A");
        expect(rb).toBe("B");
        expect(fetcherA).toHaveBeenCalledTimes(1);
        expect(fetcherB).toHaveBeenCalledTimes(1);
    });

    it("evicts the entry when the fetcher rejects so the next call retries", async () => {
        const fetcher = vi
            .fn()
            .mockRejectedValueOnce(new Error("network down"))
            .mockResolvedValueOnce("recovered");
        await expect(backgroundFetchCache.getOrFetch("k", fetcher)).rejects.toThrow(
            "network down",
        );
        // Yield a microtask so the rejection-eviction chain runs before the next call.
        await Promise.resolve();
        const second = await backgroundFetchCache.getOrFetch("k", fetcher);
        expect(second).toBe("recovered");
        expect(fetcher).toHaveBeenCalledTimes(2);
    });

    it("does NOT cache transient errors — repeated failures still retry each time", async () => {
        const fetcher = vi.fn().mockRejectedValue(new Error("offline"));
        await expect(backgroundFetchCache.getOrFetch("k", fetcher)).rejects.toThrow();
        await Promise.resolve();
        await expect(backgroundFetchCache.getOrFetch("k", fetcher)).rejects.toThrow();
        await Promise.resolve();
        await expect(backgroundFetchCache.getOrFetch("k", fetcher)).rejects.toThrow();
        expect(fetcher).toHaveBeenCalledTimes(3);
    });

    it("refresh: true bypasses the cache and stores the new result", async () => {
        const fetcher = vi
            .fn()
            .mockResolvedValueOnce({ v: 1 })
            .mockResolvedValueOnce({ v: 2 });
        const first = await backgroundFetchCache.getOrFetch("k", fetcher);
        const cachedSecond = await backgroundFetchCache.getOrFetch("k", fetcher);
        const refreshedThird = await backgroundFetchCache.getOrFetch("k", fetcher, {
            refresh: true,
        });
        const cachedFourth = await backgroundFetchCache.getOrFetch("k", fetcher);
        expect(first).toEqual({ v: 1 });
        expect(cachedSecond).toEqual({ v: 1 });
        expect(refreshedThird).toEqual({ v: 2 });
        expect(cachedFourth).toEqual({ v: 2 });
        expect(fetcher).toHaveBeenCalledTimes(2);
    });
});

describe("backgroundFetchCache.invalidate", () => {
    it("removes the entry so the next call refetches", async () => {
        const fetcher = vi
            .fn()
            .mockResolvedValueOnce("first")
            .mockResolvedValueOnce("second");
        await backgroundFetchCache.getOrFetch("k", fetcher);
        backgroundFetchCache.invalidate("k");
        const second = await backgroundFetchCache.getOrFetch("k", fetcher);
        expect(second).toBe("second");
        expect(fetcher).toHaveBeenCalledTimes(2);
    });

    it("is a no-op for keys that were never fetched", () => {
        expect(() => backgroundFetchCache.invalidate("never-cached")).not.toThrow();
    });

    it("only affects the named key", async () => {
        const fetcherA = vi.fn().mockResolvedValue("A");
        const fetcherB = vi.fn().mockResolvedValue("B");
        await backgroundFetchCache.getOrFetch("a", fetcherA);
        await backgroundFetchCache.getOrFetch("b", fetcherB);
        backgroundFetchCache.invalidate("a");
        await backgroundFetchCache.getOrFetch("a", fetcherA);
        await backgroundFetchCache.getOrFetch("b", fetcherB);
        expect(fetcherA).toHaveBeenCalledTimes(2); // refetched after invalidate
        expect(fetcherB).toHaveBeenCalledTimes(1); // still cached
    });
});
