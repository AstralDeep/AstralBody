import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, render, waitFor } from "@testing-library/react";

import { OnboardingProvider, useOnboarding } from "../OnboardingContext";
import type { OnboardingState, TutorialStep } from "../types";

const NOT_STARTED: OnboardingState = {
    status: "not_started",
    last_step_id: null,
    last_step_slug: null,
    started_at: null,
    completed_at: null,
    skipped_at: null,
};

const STEPS: TutorialStep[] = [
    {
        id: 1, slug: "welcome", audience: "user", display_order: 10,
        target_kind: "none", target_key: null, title: "Welcome", body: "Hi",
    },
    {
        id: 2, slug: "chat", audience: "user", display_order: 20,
        target_kind: "static", target_key: "chat.input", title: "Chat", body: "Type",
    },
    {
        id: 3, slug: "finish", audience: "user", display_order: 30,
        target_kind: "none", target_key: null, title: "Done", body: "End",
    },
];

interface FetchCall {
    url: string;
    init?: RequestInit;
}

type OnboardingApi = ReturnType<typeof useOnboarding>;

function setupFetchMock(initialState: OnboardingState) {
    let state: OnboardingState = { ...initialState };
    const calls: FetchCall[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        if (url.endsWith("/api/onboarding/state") && (!init || !init.method || init.method === "GET")) {
            return new Response(JSON.stringify(state), { status: 200 });
        }
        if (url.endsWith("/api/onboarding/state") && init?.method === "PUT") {
            const body = JSON.parse(init.body as string) as { status: OnboardingState["status"]; last_step_id: number | null };
            const next: OnboardingState = {
                ...state,
                status: body.status,
                last_step_id: body.last_step_id,
                last_step_slug: STEPS.find((s) => s.id === body.last_step_id)?.slug ?? null,
                started_at: state.started_at ?? "2026-04-28T00:00:00Z",
                completed_at: body.status === "completed" ? "2026-04-28T00:01:00Z" : state.completed_at,
                skipped_at: body.status === "skipped" ? "2026-04-28T00:01:00Z" : state.skipped_at,
            };
            state = next;
            return new Response(JSON.stringify(next), { status: 200 });
        }
        if (url.endsWith("/api/onboarding/replay") && init?.method === "POST") {
            return new Response(null, { status: 204 });
        }
        if (url.endsWith("/api/tutorial/steps")) {
            return new Response(JSON.stringify({ steps: STEPS }), { status: 200 });
        }
        return new Response("not found", { status: 404 });
    });
    (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    return { fetchMock, calls, getState: () => state };
}

interface ProbeProps {
    onReady: (api: OnboardingApi) => void;
}

function Probe({ onReady }: ProbeProps) {
    const api = useOnboarding();
    onReady(api);
    return null;
}

function makeApiHolder() {
    const holder: { current: OnboardingApi | null } = { current: null };
    const setApi = (api: OnboardingApi) => { holder.current = api; };
    const get = (): OnboardingApi => {
        if (!holder.current) {
            throw new Error("OnboardingContext probe not yet ready");
        }
        return holder.current;
    };
    return { setApi, get };
}

describe("OnboardingContext", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("auto-launches when status is not_started", async () => {
        setupFetchMock(NOT_STARTED);
        const holder = makeApiHolder();
        render(
            <OnboardingProvider accessToken="t">
                <Probe onReady={holder.setApi} />
            </OnboardingProvider>,
        );
        await waitFor(() => {
            expect(holder.get().visible).toBe(true);
        });
        expect(holder.get().currentStep?.slug).toBe("welcome");
    });

    it("does not auto-launch for completed users", async () => {
        setupFetchMock({ ...NOT_STARTED, status: "completed", completed_at: "2026-04-28T00:00:00Z" });
        const holder = makeApiHolder();
        render(
            <OnboardingProvider accessToken="t">
                <Probe onReady={holder.setApi} />
            </OnboardingProvider>,
        );
        await waitFor(() => {
            expect(holder.get().state.status).toBe("completed");
        });
        expect(holder.get().visible).toBe(false);
    });

    it("advances on next() and persists in_progress", async () => {
        const { calls } = setupFetchMock(NOT_STARTED);
        const holder = makeApiHolder();
        render(
            <OnboardingProvider accessToken="t">
                <Probe onReady={holder.setApi} />
            </OnboardingProvider>,
        );
        await waitFor(() => expect(holder.get().visible).toBe(true));
        await act(async () => { await holder.get().next(); });
        expect(holder.get().currentStep?.slug).toBe("chat");
        const puts = calls.filter((c) => c.init?.method === "PUT");
        expect(puts.length).toBeGreaterThanOrEqual(1);
    });

    it("flips to completed on next() from final step", async () => {
        const { getState } = setupFetchMock(NOT_STARTED);
        const holder = makeApiHolder();
        render(
            <OnboardingProvider accessToken="t">
                <Probe onReady={holder.setApi} />
            </OnboardingProvider>,
        );
        await waitFor(() => expect(holder.get().visible).toBe(true));
        await act(async () => { await holder.get().next(); }); // -> chat
        await act(async () => { await holder.get().next(); }); // -> finish
        await act(async () => { await holder.get().next(); }); // -> completed + close
        await waitFor(() => {
            expect(getState().status).toBe("completed");
            expect(holder.get().visible).toBe(false);
        });
    });

    it("skip() persists skipped status", async () => {
        const { getState } = setupFetchMock(NOT_STARTED);
        const holder = makeApiHolder();
        render(
            <OnboardingProvider accessToken="t">
                <Probe onReady={holder.setApi} />
            </OnboardingProvider>,
        );
        await waitFor(() => expect(holder.get().visible).toBe(true));
        await act(async () => { await holder.get().skip(); });
        await waitFor(() => {
            expect(getState().status).toBe("skipped");
        });
    });

    it("replay() launches overlay without mutating persisted state", async () => {
        const completedState: OnboardingState = {
            ...NOT_STARTED,
            status: "completed",
            completed_at: "2026-04-28T00:00:00Z",
        };
        const { getState, calls } = setupFetchMock(completedState);
        const holder = makeApiHolder();
        render(
            <OnboardingProvider accessToken="t">
                <Probe onReady={holder.setApi} />
            </OnboardingProvider>,
        );
        await waitFor(() => expect(holder.get().state.status).toBe("completed"));
        await act(async () => { await holder.get().replay(); });
        await waitFor(() => expect(holder.get().visible).toBe(true));
        expect(getState().status).toBe("completed");
        const replayCalls = calls.filter((c) => c.url.endsWith("/replay"));
        expect(replayCalls.length).toBe(1);
    });
});
