/**
 * Unit tests for SafeWebStorageStateStore (Feature 016 T008).
 *
 * Verifies the FR-006 soft-fail behavior: writes that throw must NOT
 * propagate, and the `astralbody:persistence-disabled` event must fire
 * exactly once per session per store instance.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
    SafeWebStorageStateStore,
    PERSISTENCE_DISABLED_EVENT,
} from "../safeStorageStore";

/** Tiny in-memory Storage shim that conforms to the DOM `Storage` shape. */
class InMemoryStorage implements Storage {
    private data = new Map<string, string>();
    public throwOnSet: Error | null = null;

    get length(): number {
        return this.data.size;
    }
    clear(): void {
        this.data.clear();
    }
    getItem(key: string): string | null {
        return this.data.has(key) ? this.data.get(key)! : null;
    }
    key(index: number): string | null {
        return Array.from(this.data.keys())[index] ?? null;
    }
    removeItem(key: string): void {
        this.data.delete(key);
    }
    setItem(key: string, value: string): void {
        if (this.throwOnSet) throw this.throwOnSet;
        this.data.set(key, value);
    }
}

describe("SafeWebStorageStateStore", () => {
    let store: InMemoryStorage;

    beforeEach(() => {
        store = new InMemoryStorage();
    });

    it("writes through to the underlying store on success", async () => {
        const safe = new SafeWebStorageStateStore({ store });
        await safe.set("user:alice", "{\"profile\":{\"sub\":\"alice\"}}");
        expect(store.getItem("oidc.user:alice")).toBe(
            "{\"profile\":{\"sub\":\"alice\"}}",
        );
    });

    it("swallows QuotaExceededError without throwing", async () => {
        store.throwOnSet = new DOMException("quota", "QuotaExceededError");
        const safe = new SafeWebStorageStateStore({ store });
        await expect(safe.set("user:bob", "x")).resolves.toBeUndefined();
    });

    it("fires astralbody:persistence-disabled exactly once per session", async () => {
        store.throwOnSet = new DOMException("quota", "QuotaExceededError");
        const safe = new SafeWebStorageStateStore({ store });

        const listener = vi.fn();
        window.addEventListener(PERSISTENCE_DISABLED_EVENT, listener);

        try {
            await safe.set("a", "1");
            await safe.set("b", "2");
            await safe.set("c", "3");
        } finally {
            window.removeEventListener(PERSISTENCE_DISABLED_EVENT, listener);
        }
        expect(listener).toHaveBeenCalledTimes(1);
    });

    it("get / remove / getAllKeys honor the prefix", async () => {
        const safe = new SafeWebStorageStateStore({ store });
        await safe.set("alpha", "1");
        await safe.set("beta", "2");
        // Inject something outside the OIDC prefix to ensure it's filtered.
        store.setItem("unrelated.key", "99");

        const all = await safe.getAllKeys();
        expect(new Set(all)).toEqual(new Set(["alpha", "beta"]));

        expect(await safe.get("alpha")).toBe("1");
        const removed = await safe.remove("alpha");
        expect(removed).toBe("1");
        expect(await safe.get("alpha")).toBeNull();
    });

    it("supports a custom prefix", async () => {
        const safe = new SafeWebStorageStateStore({ store, prefix: "astral." });
        await safe.set("k", "v");
        expect(store.getItem("astral.k")).toBe("v");
    });

    it("emits the underlying error name in the event detail", async () => {
        store.throwOnSet = new DOMException("oops", "SecurityError");
        const safe = new SafeWebStorageStateStore({ store });
        const received: CustomEvent[] = [];
        const listener = (e: Event) => {
            received.push(e as CustomEvent);
        };
        window.addEventListener(PERSISTENCE_DISABLED_EVENT, listener);
        try {
            await safe.set("k", "v");
        } finally {
            window.removeEventListener(PERSISTENCE_DISABLED_EVENT, listener);
        }
        expect(received).toHaveLength(1);
        expect(received[0].detail).toMatchObject({
            key: "oidc.k",
            reason: "SecurityError",
        });
    });
});
